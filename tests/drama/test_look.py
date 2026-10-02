"""AIV-031 look materialize. ForcePass=never. docs≠PASS. ≠绿 N4."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_look.paths import is_hotlink_url, looks_relpath, reject_hotlink_path
from aiv_drama_look.prompt import DEFAULT_STYLE_REF, assemble_look_prompt, require_look_must
from aiv_drama_look.provider.ark import ArkSeedreamClient
from aiv_drama_look.provider.base import FrozenParams, ImageResult, default_frozen_params
from aiv_drama_look.provider.dashscope import DashScopeWanClient
from aiv_drama_look.provider.errors import classify_http_error
from aiv_drama_look.provider.select import build_image_provider
from aiv_drama_look.refs import append_ref, make_ref, md5_bytes, only_provenance_roles
from aiv_drama_look.seed import derive_seed, seed_for_card
from aiv_drama_look.sku import DEFAULT_SKU, SKU_L1, next_sku, reject_upgrade_reason, resolve_sku
from aiv_drama_n3.cards import has_usable_ref
from aiv_drama_n3.library import resolve_ref_file
from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n4.models import N4AssembleRequest
from aiv_drama_n4.projection import prompts_jsonl_name
from aiv_drama_look.models import LookGenerateRequest

from tests.drama.helpers import lock_g2, seed_project_episode

MINIMAL_PNG = b"\x89PNG\r\n\x1a\n" + b"aiv-031-look-fixture"


class FakeLookProvider:
    name = "fake"
    supports_sequential = True
    max_refs = 9

    def __init__(self, blob: bytes = MINIMAL_PNG) -> None:
        self.blob = blob
        self.calls: list[dict] = []

    def generate(self, prompt, refs, frozen_params, seed=None, *, sku=None):
        self.calls.append(
            {"prompt": prompt, "refs": refs, "frozen": frozen_params, "seed": seed, "sku": sku}
        )
        return ImageResult(images=[self.blob], sku=sku or DEFAULT_SKU, provider=self.name, seed=seed, seed_replay="ok")


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _fill_must(svc, pid, ep="EP01"):
    rec = svc._rec(pid, ep)
    for card in rec["n3"]["cards"]["characters"]:
        card["appearance"] = "方脸短碎发，深蓝工装外套，左耳银钉"
        card["immutable"] = ["方脸短碎发", "深蓝工装外套", "左耳银钉"]
    for card in rec["n3"]["cards"]["scenes"]:
        card["appearance"] = "室内门厅，冷白顶灯，深色显示墙"
        card["light_anchor"] = "深夜，顶冷白灯为主，屏幕蓝光辅，低环境光"
    svc._commit(rec)


def _first_ids(svc, pid, ep="EP01") -> tuple[str, str]:
    cards = svc._rec(pid, ep)["n3"]["cards"]
    return cards["characters"][0]["id"], cards["scenes"][0]["id"]


def _materialize(svc, pid, *, tool_profile="seedance_2"):
    lock_g2(svc, pid, tool_profile=tool_profile)
    return svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))


# ----- path / md5 / role -------------------------------------------------------


def test_looks_relpath_matches_design():
    path = looks_relpath("EP01", "character", "CHAR-01", "face", "front")
    assert path == "episodes/EP01/n3/looks/char/CHAR-01/face_front.png"
    scene = looks_relpath("EP01", "scene", "SCENE-01", "plate", "empty")
    assert scene == "episodes/EP01/n3/looks/scene/SCENE-01/plate_empty.png"


def test_hotlink_url_rejected_as_ref_path():
    assert is_hotlink_url("https://cdn.example/face.png")
    assert is_hotlink_url("http://x/y")
    assert not is_hotlink_url("episodes/EP01/n3/looks/char/CHAR-01/face_front.png")
    exc = _err(lambda: reject_hotlink_path("https://cdn.example/face.png"))
    assert exc.status_code == 400
    assert exc.code == "hotlink_url_forbidden"
    exc2 = _err(lambda: make_ref(path="https://evil/x.png", md5="abc", role="face"))
    assert exc2.code == "hotlink_url_forbidden"


def test_md5_and_role_gate():
    digest = md5_bytes(MINIMAL_PNG)
    assert len(digest) == 32
    char = {"id": "CHAR-01", "kind": "character", "refs": []}
    hung = append_ref(char, {"path": "episodes/EP01/n3/looks/char/CHAR-01/face_front.png", "md5": digest, "role": "face"})
    assert has_usable_ref(hung) is True
    assert hung.get("usable_for_n4") is not True
    style = append_ref(
        {"id": "CHAR-01", "kind": "character", "refs": []},
        {"path": "episodes/EP01/n3/looks/char/CHAR-01/web_refs/src_x_01.png", "md5": digest, "role": "style_ref"},
    )
    assert has_usable_ref(style) is False
    assert only_provenance_roles(style) is True
    empty_md5 = _err(lambda: make_ref(path="episodes/EP01/n3/looks/char/CHAR-01/face_front.png", md5="", role="face"))
    assert empty_md5.status_code == 422


def test_prompt_maps_card_fields_not_episode_prose():
    card = {
        "id": "CHAR-01",
        "kind": "character",
        "appearance": "方脸短碎发，深蓝工装外套",
        "immutable": ["方脸短碎发", "深蓝工装外套"],
    }
    out = assemble_look_prompt(card, view="front")
    assert DEFAULT_STYLE_REF in out["prompt"]
    assert "方脸短碎发" in out["prompt"]
    assert "深蓝工装外套" in out["prompt"]
    assert "近景，胸以上" in out["prompt"]
    assert "边关翻盘" not in out["prompt"]
    assert "被流放的庶女" not in out["prompt"]
    hollow = _err(lambda: require_look_must({"id": "CHAR-01", "kind": "character", "appearance": "好看", "immutable": []}))
    assert hollow.code == "look_incomplete"


def test_seed_char_reuse_scene_namespace():
    assert derive_seed("X-01", "character") != derive_seed("X-01", "scene")
    first = seed_for_card("CHAR-01", "character")
    again = seed_for_card("CHAR-01", "character", existing_meta={"seed": first})
    assert again == first
    side = seed_for_card("CHAR-01", "character", existing_meta={"seed": 4242})
    assert side == 4242


def test_sku_upgrade_hooks_reject_prettier():
    assert next_sku(DEFAULT_SKU) == SKU_L1
    assert reject_upgrade_reason("api_fail") == "api_fail"
    exc = _err(lambda: reject_upgrade_reason("更好看"))
    assert exc.status_code == 422
    sku, meta = resolve_sku(None, settings_sku=DEFAULT_SKU, current_sku=DEFAULT_SKU, upgrade_reason="identity_drift")
    assert sku == SKU_L1
    assert meta["reason"] == "identity_drift"
    assert meta["sku_from"] == DEFAULT_SKU


def test_classify_and_key_isolation(settings):
    assert classify_http_error(401, "") == "auth"
    assert classify_http_error(429, "") == "quota"
    assert classify_http_error(500, "") == "5xx"
    isolated = replace(settings, openai_api_key="sk-deepseek-not-for-look", ark_api_key=None, dashscope_api_key=None)
    exc = _err(lambda: build_image_provider(isolated, "auto"))
    assert exc.status_code == 422
    assert "AIV_OPENAI" in exc.message
    exc2 = _err(lambda: build_image_provider(isolated, "openai"))
    assert "isolated" in exc2.message.lower() or "AIV_OPENAI" in exc2.message


def test_ark_client_sends_flash_sku_watermark_off(settings, monkeypatch):
    captured: dict = {}
    b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"data": [{"b64_json": b64, "seed": 7}]}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("aiv_drama_look.provider.ark.httpx.post", fake_post)
    cfg = replace(settings, ark_api_key="ark-test-key", openai_api_key="sk-should-not-appear")
    client = ArkSeedreamClient(cfg)
    result = client.generate("prompt", [], default_frozen_params(), 11, sku=DEFAULT_SKU)
    assert result.images[0] == MINIMAL_PNG
    assert captured["url"].endswith("/images/generations")
    assert captured["headers"]["Authorization"] == "Bearer ark-test-key"
    assert "sk-should-not-appear" not in str(captured)
    assert captured["json"]["watermark"] is False
    assert captured["json"]["model"] == DEFAULT_SKU
    assert captured["json"]["sequential_image_generation"] == "disabled"
    assert captured["json"]["seed"] == 11


def test_dashscope_client_beijing_wan(settings, monkeypatch):
    captured: dict = {}
    b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            img = "data:image/png;base64," + b64
            return {"output": {"choices": [{"message": {"content": [{"image": img}]}}]}}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("aiv_drama_look.provider.dashscope.httpx.post", fake_post)
    cfg = replace(settings, dashscope_api_key="ds-test-key", openai_api_key="sk-nope")
    client = DashScopeWanClient(cfg)
    result = client.generate("prompt", [], FrozenParams(), 3, sku="wan2.7-image")
    assert result.images[0] == MINIMAL_PNG
    assert "multimodal-generation" in captured["url"]
    assert "dashscope.aliyuncs.com" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer ds-test-key"
    assert captured["json"]["parameters"]["watermark"] is False
    assert captured["json"]["parameters"]["enable_sequential"] is False
    assert "sk-nope" not in str(captured)


# ----- generate + N4 409 -------------------------------------------------------


def test_generate_look_hangs_ref_does_not_flip_usable(svc, data_dir):
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    _fill_must(svc, pid)
    cid, _sid = _first_ids(svc, pid)
    fake = FakeLookProvider()
    env = svc.generate_look(
        pid,
        "EP01",
        LookGenerateRequest(id=cid, actor="eng-031"),
        raw={"id": cid, "actor": "eng-031"},
        image_provider=fake,
    )
    assert env["usable_for_n4"] is False
    assert env["cards"]["usable_for_n4"] is False
    assert env["look"]["usable_for_n4_flipped"] is False
    assert env["look"]["role"] == "face"
    assert env["look"]["path"] == f"episodes/EP01/n3/looks/char/{cid}/face_front.png"
    assert env["look"]["md5"] == md5_bytes(MINIMAL_PNG)
    rec = svc._rec(pid, "EP01")
    char = next(c for c in rec["n3"]["cards"]["characters"] if c["id"] == cid)
    assert char["refs"][0]["role"] == "face"
    assert char["refs"][0]["md5"] == md5_bytes(MINIMAL_PNG)
    assert not is_hotlink_url(char["refs"][0]["path"])
    abs_path = Path(data_dir) / "projects" / pid / env["look"]["path"]
    assert abs_path.is_file()
    assert abs_path.read_bytes() == MINIMAL_PNG
    assert resolve_ref_file(svc.settings, env["look"]["path"]) == abs_path
    meta = abs_path.parent / "meta.json"
    assert meta.is_file()
    assert "ARK_API_KEY" not in meta.read_text(encoding="utf-8")
    assert fake.calls[0]["frozen"].watermark is False


def test_n4_409_when_refs_empty(svc, data_dir):
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    assert not (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")).exists()


def test_n4_409_after_char_look_without_scene_face(svc, data_dir):
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    _fill_must(svc, pid)
    cid, _sid = _first_ids(svc, pid)
    svc.generate_look(
        pid,
        "EP01",
        LookGenerateRequest(id=cid, actor="eng-031"),
        raw={"id": cid},
        image_provider=FakeLookProvider(),
    )
    assert svc.get_n3(pid, "EP01")["usable_for_n4"] is False
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    missing_ids = {m.get("id") for m in (exc.details.get("missing_refs") or [])}
    assert any(str(i).startswith("SCENE-") for i in missing_ids) or missing_ids
    assert not (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")).exists()


def test_n4_409_style_ref_only_is_not_face(svc, data_dir):
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    rec = svc._rec(pid, "EP01")
    web = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / "n3" / "looks" / "char" / "CHAR-01" / "web_refs" / "src_x_01.png"
    web.parent.mkdir(parents=True, exist_ok=True)
    web.write_bytes(MINIMAL_PNG)
    rec["n3"]["cards"]["characters"] = [
        append_ref(
            card,
            {
                "path": "episodes/EP01/n3/looks/char/CHAR-01/web_refs/src_x_01.png",
                "md5": md5_bytes(MINIMAL_PNG),
                "role": "style_ref",
            },
        )
        for card in rec["n3"]["cards"]["characters"]
    ]
    svc._commit(rec)
    assert has_usable_ref(rec["n3"]["cards"]["characters"][0]) is False
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"


def test_generate_scene_plate_empty(svc, data_dir):
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    _fill_must(svc, pid)
    sid = svc._rec(pid, "EP01")["n3"]["cards"]["scenes"][0]["id"]
    env = svc.generate_look(
        pid,
        "EP01",
        LookGenerateRequest(id=sid, actor="eng-031"),
        raw={"id": sid},
        image_provider=FakeLookProvider(),
    )
    assert env["look"]["role"] == "plate"
    assert env["look"]["path"] == f"episodes/EP01/n3/looks/scene/{sid}/plate_empty.png"
    assert env["usable_for_n4"] is False
    assert (Path(data_dir) / "projects" / pid / env["look"]["path"]).is_file()


def test_http_look_generate_and_force_pass(client, monkeypatch):
    monkeypatch.setattr(
        "aiv_drama_look.ops.build_image_provider",
        lambda settings, name, sku=None: FakeLookProvider(),
    )
    from tests.drama.test_n3_api import _setup_g2

    pid = _setup_g2(client)
    mat = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize", json={"actor": "yangzhou"})
    assert mat.status_code == 200, mat.text
    svc = client.app.state.service
    _fill_must(svc, pid)
    cid, _sid = _first_ids(svc, pid)
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/looks/generate",
        json={"id": cid, "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"
    flip = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/looks/generate",
        json={"id": cid, "usable_for_n4": True},
    )
    assert flip.status_code == 400
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/looks/generate",
        json={"id": cid, "actor": "eng-031"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["usable_for_n4"] is False
    assert body["look"]["role"] == "face"
    spec = client.get("/openapi/drama-look.v0.yaml")
    assert spec.status_code == 200
    assert "doubao-seedream-5-0-flash-260915" in spec.text
    assert "usable_for_n4" in spec.text


def test_thicken_still_rejects_image_gen(client):
    from tests.drama.test_n3_api import _setup_g2

    pid = _setup_g2(client)
    client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize", json={"actor": "yangzhou"})
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/thicken",
        json={"actor": "yangzhou", "provider": "llm", "generate_look": True},
    )
    assert res.status_code == 400
    assert "文字" in res.json()["error"]["message"] or res.json()["error"]["code"] == "validation"
