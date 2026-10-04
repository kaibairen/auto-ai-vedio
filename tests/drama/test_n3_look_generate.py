"""BRIEF-AIV-032 — gold-A 3:2 look-generate. ForcePass=never. usable never auto-flip."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app
from aiv_drama.errors import AppError
from aiv_drama_n3.gold_sheet import (
    EN_IDENTITY_ANCHOR,
    OUTPUT_SHEET_LINE,
    PROMPT_ORDER,
    RECIPE_TURNAROUND_TEMPLATE,
    STYLE_BANANA_PHOTOREAL_FINAL,
    assemble_gold_a_sheet_prompt,
    assemble_sections,
    format_negatives,
    load_look_card,
    md5_text,
    verify_face_ref_md5,
)
from aiv_drama_n3.look_generate import (
    L3_FULLBODY_BACK_ADAPTER,
    _maybe_append_prompt_adapter,
    generate_gold_a_sheet,
)
from aiv_drama_n3.models import N3GenerateLookRequest, N3MaterializeRequest
from aiv_drama_n3.seedream import (
    ARK_IMAGES_URL,
    FORBIDDEN_ARK_KEYS,
    SEEDREAM_SKU_CHAIN,
    SEEDREAM_SKU_PRIMARY,
    SHEET_SIZE,
    build_ark_body,
    generate_seedream_sheet,
)
from tests.drama.helpers import lock_g2, seed_project_episode

ROOT = Path(__file__).resolve().parents[2]
GOLD_PROMPT = ROOT / "fixtures" / "drama" / "gold-a" / "CHAR-01-doubao-sheet-r1-prompt.txt"
GOLD_CARD = ROOT / "fixtures" / "drama" / "gold-a" / "CHAR-01-card.yaml"
GOLD_PROMPT_MD5 = "c816ba7f394a6279a5d661b28b6eb194"
LIVE_R2_PROMPT_MD5 = "54bd7270c8a3c2c7fc0c795b1d786c58"
runner = CliRunner()


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _face(tmp_path: Path, payload: bytes = b"\xff\xd8fake-face-bytes") -> Path:
    path = tmp_path / "CHAR-01-user-ref.jpg"
    path.write_bytes(payload)
    return path


def _gold_card() -> dict:
    return load_look_card(GOLD_CARD)


def _sheet_card() -> dict:
    """RECIPE wardrobe/immutable/height without gold face-md5 bind (unit face is fake)."""
    card = dict(_gold_card())
    card.pop("refs", None)
    return card


class _Resp:
    def __init__(self, status_code=200, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_constants_immutable_and_prompt_order():
    assert STYLE_BANANA_PHOTOREAL_FINAL.startswith("统一画风：高端写实棚拍定妆")
    assert "禁豆包拟人IP插画与矢量吉祥物立绘感。" in STYLE_BANANA_PHOTOREAL_FINAL
    assert RECIPE_TURNAROUND_TEMPLATE.startswith("3:2 横版角色设定卡/转面板")
    assert "两张大图上下排列" in RECIPE_TURNAROUND_TEMPLATE
    assert "六张小图必须是同一张脸同一发际线。" in RECIPE_TURNAROUND_TEMPLATE
    assert "表情特写：开心只抬眼皮，嘴保持这张角色卡写的嘴型，不许另改嘴" in RECIPE_TURNAROUND_TEMPLATE
    assert "表情特写：生气只把眼皮压低，眉和嘴保持角色卡，不许皱眉，不许改嘴型" in RECIPE_TURNAROUND_TEMPLATE
    assert "头部背面按这张角色卡的遮挡画。角色卡没写遮挡时，露出后脑头型" in RECIPE_TURNAROUND_TEMPLATE
    assert "开心/愉悦（happy，笑但克制不夸张）" not in RECIPE_TURNAROUND_TEMPLATE
    assert "生气/愤怒（angry，眉眼紧张但不夸张变形）" not in RECIPE_TURNAROUND_TEMPLATE
    assert "back of head，用于发型与头型一致性" not in RECIPE_TURNAROUND_TEMPLATE
    assert OUTPUT_SHEET_LINE == "输出单张3:2横版合板"
    assert "ONLY identity anchor" in EN_IDENTITY_ANCHOR
    assert PROMPT_ORDER == (
        "style_final",
        "recipe_turnaround",
        "wardrobe",
        "immutable",
        "height",
        "negatives",
        "en_identity_anchor",
        "output_sheet_line",
    )
    gold = GOLD_PROMPT.read_text(encoding="utf-8")
    assert STYLE_BANANA_PHOTOREAL_FINAL in gold
    assert RECIPE_TURNAROUND_TEMPLATE in gold
    # Pin SoT hashes so silent STYLE/RECIPE edits fail (升 ADDENDUM/RECIPE 另拍)
    assert md5_text(STYLE_BANANA_PHOTOREAL_FINAL) == "5dea838ce0d0baae09a15febcf475ef1"
    assert md5_text(RECIPE_TURNAROUND_TEMPLATE) == "41b9a44302a5c1e949ffd741b3425d52"
    assert md5_text(format_negatives()) == "2bf2300e5dfc0e261e46316c7b7e73ec"
    assert md5_text(EN_IDENTITY_ANCHOR) == "950e43999e7556a7b51199e42b663009"
    assert md5_text(OUTPUT_SHEET_LINE) == "6a435c3686c78abc0a8bc03faa152b98"


def test_assemble_matches_eng031_gold_prompt():
    prompt = assemble_gold_a_sheet_prompt(_gold_card())
    expected = GOLD_PROMPT.read_text(encoding="utf-8")
    assert prompt == expected
    assert prompt.index(STYLE_BANANA_PHOTOREAL_FINAL) == 0
    assert prompt.index(RECIPE_TURNAROUND_TEMPLATE) > 0
    assert prompt.index("角色穿着：") < prompt.index("不可变：")
    assert prompt.index("不可变：") < prompt.index("人物身高1.75米")
    assert prompt.index("人物身高1.75米") < prompt.index("禁令：")
    assert prompt.index("禁令：") < prompt.index(EN_IDENTITY_ANCHOR)
    assert prompt.index(EN_IDENTITY_ANCHOR) < prompt.index(OUTPUT_SHEET_LINE)
    names = [n for n, _ in assemble_sections(_gold_card())]
    assert names == list(PROMPT_ORDER)
    assert md5_text(prompt) == GOLD_PROMPT_MD5


def test_adapter_off_matches_gold_prompt_md5(monkeypatch):
    """AIV_LOOK_PROMPT_ADAPTER=off|0|empty-explicit → baseline gold assemble md5."""
    base = assemble_gold_a_sheet_prompt(_gold_card())
    assert md5_text(base) == GOLD_PROMPT_MD5
    for raw in ("off", "0", "false", "no", ""):
        monkeypatch.setenv("AIV_LOOK_PROMPT_ADAPTER", raw)
        prompt = _maybe_append_prompt_adapter(base)
        assert prompt == base
        assert md5_text(prompt) == GOLD_PROMPT_MD5
        assert "【L3硬约束】" not in prompt


def test_adapter_on_default_appends_l3_and_differs_from_gold(monkeypatch):
    """Gold sheet path default ON: L3 真背 sentence; md5 ≠ baseline. STYLE/RECIPE unchanged."""
    monkeypatch.delenv("AIV_LOOK_PROMPT_ADAPTER", raising=False)
    base = assemble_gold_a_sheet_prompt(_gold_card())
    assert md5_text(base) == GOLD_PROMPT_MD5
    prompt = _maybe_append_prompt_adapter(base)
    assert "【L3硬约束】" in prompt
    assert "90°真背" in prompt
    assert "完整后脑至鞋跟的全身背影" in prompt
    assert "Left strip MUST include full-body back view standing" in prompt
    assert prompt.endswith(L3_FULLBODY_BACK_ADAPTER + "\n") or prompt.endswith(L3_FULLBODY_BACK_ADAPTER)
    assert L3_FULLBODY_BACK_ADAPTER in prompt
    assert md5_text(prompt) != GOLD_PROMPT_MD5
    assert md5_text(prompt) == LIVE_R2_PROMPT_MD5
    assert md5_text(STYLE_BANANA_PHOTOREAL_FINAL) == "5dea838ce0d0baae09a15febcf475ef1"
    assert md5_text(RECIPE_TURNAROUND_TEMPLATE) == "41b9a44302a5c1e949ffd741b3425d52"
    monkeypatch.setenv("AIV_LOOK_PROMPT_ADAPTER", "l3")
    assert md5_text(_maybe_append_prompt_adapter(base)) == LIVE_R2_PROMPT_MD5


def test_generate_look_adapter_off_writes_gold_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("AIV_LOOK_PROMPT_ADAPTER", "off")
    face = _face(tmp_path)
    look = generate_gold_a_sheet(
        card=_sheet_card(),
        face_ref=face,
        out_dir=tmp_path / "looks",
        api_key=None,
        dry_run=True,
    )
    written = Path(look["prompt_path"]).read_text(encoding="utf-8")
    assert look.get("prompt_adapter") is None
    assert md5_text(written) == GOLD_PROMPT_MD5
    assert written == GOLD_PROMPT.read_text(encoding="utf-8")


def test_assemble_does_not_invent_wardrobe():
    exc = _err(lambda: assemble_gold_a_sheet_prompt({"id": "CHAR-02", "kind": "character"}))
    assert exc.code == "look_card_incomplete"
    assert "自写" in exc.message


def test_shared_turnaround_template_keeps_card_identity_interpolation():
    card = {
        "id": "CHAR-GEN",
        "wardrobe": "plain wool coat, dark trousers, lace-up boots",
        "immutable": "round wire glasses; short dark hair",
        "height": "1.70米",
    }
    prompt = assemble_gold_a_sheet_prompt(card)
    assert "表情特写：开心只抬眼皮，嘴保持这张角色卡写的嘴型，不许另改嘴" in prompt
    assert "表情特写：生气只把眼皮压低，眉和嘴保持角色卡，不许皱眉，不许改嘴型" in prompt
    assert "头部背面按这张角色卡的遮挡画。角色卡没写遮挡时，露出后脑头型" in prompt
    assert "角色穿着：plain wool coat, dark trousers, lace-up boots" in prompt
    assert "不可变：round wire glasses; short dark hair" in prompt
    assert "人物身高1.70米" in prompt
    assert "开心/愉悦（happy，笑但克制不夸张）" not in prompt
    assert "生气/愤怒（angry，眉眼紧张但不夸张变形）" not in prompt
    assert "back of head，用于发型与头型一致性" not in prompt
    assert "禁豆包拟人IP插画与矢量吉祥物立绘感。" in prompt


def test_face_md5_gate_before_generate(tmp_path, monkeypatch):
    face = _face(tmp_path)
    digest = hashlib.md5(face.read_bytes()).hexdigest()
    bind = verify_face_ref_md5(face, expected_md5=digest)
    assert bind["md5"] == digest
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Ark must not run on bind fail")

    monkeypatch.setattr("aiv_drama_n3.look_generate.generate_seedream_sheet", boom)
    exc = _err(
        lambda: generate_gold_a_sheet(
            card=_sheet_card(),
            face_ref=face,
            expected_md5="0" * 32,
            out_dir=tmp_path / "out",
            api_key="sk-should-not-be-used",
            dry_run=False,
        )
    )
    assert exc.code == "material_bind"
    assert called["n"] == 0
    assert not (tmp_path / "out" / "CHAR-01-turnaround-sheet-3x2.jpg").exists()


def test_ark_body_minimal_no_sequential():
    body = build_ark_body(
        model=SEEDREAM_SKU_PRIMARY,
        prompt="p",
        image_data_url="data:image/jpeg;base64,QQ==",
    )
    assert body["size"] == SHEET_SIZE == "2048x1365"
    assert body["watermark"] is False
    assert body["response_format"] == "url"
    assert set(body) == {"model", "prompt", "size", "watermark", "response_format", "image"}
    assert "sequential_image_generation" not in body
    assert FORBIDDEN_ARK_KEYS.isdisjoint(body)
    assert SEEDREAM_SKU_CHAIN == (
        "doubao-seedream-5-0-flash-260915",
        "doubao-seedream-5-0-pro-260628",
        "doubao-seedream-4-5-251128",
        "wan2.7-image",
    )
    assert ARK_IMAGES_URL == "https://ark.cn-beijing.volces.com/api/v3/images/generations"


def test_sku_fallback_then_success():
    posts = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        posts.append(json["model"])
        assert "sequential_image_generation" not in json
        assert "Authorization" in headers
        assert "sk-live" not in str(json)
        if json["model"] != "doubao-seedream-5-0-pro-260628":
            return _Resp(400, text="model not found")
        return _Resp(200, payload={"data": [{"url": "https://cdn.example/sheet.jpg"}]})

    def fake_get(url, timeout=None):
        assert url == "https://cdn.example/sheet.jpg"
        return _Resp(200, content=b"jpeg-bytes")

    out = generate_seedream_sheet(
        api_key="sk-live",
        prompt="p",
        image_data_url="data:image/jpeg;base64,QQ==",
        post=fake_post,
        get=fake_get,
    )
    assert out["model"] == "doubao-seedream-5-0-pro-260628"
    assert out["bytes"] == b"jpeg-bytes"
    assert posts[0] == SEEDREAM_SKU_PRIMARY
    assert "doubao-seedream-5-0-pro-260628" in posts


def test_dry_run_writes_prompt_not_sheet(tmp_path, monkeypatch):
    monkeypatch.delenv("AIV_LOOK_PROMPT_ADAPTER", raising=False)
    face = _face(tmp_path)
    look = generate_gold_a_sheet(
        card=_sheet_card(),
        face_ref=face,
        out_dir=tmp_path / "looks",
        api_key=None,
        dry_run=True,
    )
    assert look["dry_run"] is True
    assert look["usable_for_n4"] is False
    assert look["sheet_path"] is None
    assert look["sequential_image_generation"] is False
    prompt_path = Path(look["prompt_path"])
    assert prompt_path.is_file()
    written = prompt_path.read_text(encoding="utf-8")
    assert "【L3硬约束】" in written
    assert "90°真背" in written
    assert md5_text(written) != GOLD_PROMPT_MD5
    assert look.get("prompt_adapter") == "l3"
    recorded = json.loads(Path(look["recorded_path"]).read_text(encoding="utf-8"))
    assert recorded["endpoint"] == ARK_IMAGES_URL
    assert recorded["size"] == "2048x1365"
    assert recorded["sequential_image_generation"] is False
    blob = json.dumps(look)
    assert "sk-" not in blob
    assert "Bearer " not in blob


def test_episode_generate_look_dry_run_does_not_flip_usable(svc, tmp_path):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    char = rec["n3"]["cards"]["characters"][0]
    gold = _sheet_card()
    char["appearance"] = gold["wardrobe"]
    char["immutable"] = gold["immutable"]
    char["height"] = gold["height"]
    svc._commit(rec)
    face = _face(tmp_path)
    env = svc.generate_n3_look(
        pid,
        "EP01",
        N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), dry_run=True, actor="eng-032"),
        raw={"id": "CHAR-01", "face_ref": str(face), "dry_run": True, "actor": "eng-032"},
    )
    assert env["ok"] is True
    assert env["usable_for_n4"] is False
    assert env["look"]["usable_for_n4"] is False
    assert env["look_usable_for_n4"] is False
    assert env["auto_flipped_usable"] is False
    assert env["look"]["dry_run"] is True
    assert Path(env["look"]["prompt_path"]).is_file()
    refs = env["cards"]["characters"][0].get("refs") or []
    assert not any((r.get("role") in {"face", "full"}) for r in refs)
    assert env["cards"]["characters"][0]["looks"][0]["role"] == "turnaround_sheet"


def test_http_generate_look_force_and_sequential(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize", json={"actor": "x"})
    rec = svc._rec(pid, "EP01")
    gold = _sheet_card()
    rec["n3"]["cards"]["characters"][0]["appearance"] = gold["wardrobe"]
    rec["n3"]["cards"]["characters"][0]["immutable"] = gold["immutable"]
    rec["n3"]["cards"]["characters"][0]["height"] = gold["height"]
    svc._commit(rec)
    face = _face(tmp_path)
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
        json={"id": "CHAR-01", "face_ref": str(face), "dry_run": True, "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"
    seq = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
        json={"id": "CHAR-01", "face_ref": str(face), "dry_run": True, "sequential_image_generation": "auto"},
    )
    assert seq.status_code == 400
    scene = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
        json={"id": "SCENE-01", "face_ref": str(face), "dry_run": True},
    )
    assert scene.status_code == 422
    assert scene.json()["error"]["code"] == "scene_look_forbidden"
    ok = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
        json={"id": "CHAR-01", "face_ref": str(face), "dry_run": True, "actor": "eng-032"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["usable_for_n4"] is False
    assert body["look"]["usable_for_n4"] is False
    assert "sk-" not in ok.text
    spec = client.get("/openapi/drama-n3.v0.yaml")
    assert "cards/generate-look" in spec.text
    assert "2048x1365" in spec.text


def test_cli_standalone_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("AIV_LOOK_PROMPT_ADAPTER", raising=False)
    face = _face(tmp_path)
    digest = hashlib.md5(face.read_bytes()).hexdigest()
    card_path = tmp_path / "CHAR-01-card.yaml"
    card_path.write_text(GOLD_CARD.read_text(encoding="utf-8").replace("refs:\n", "refs_unused:\n"), encoding="utf-8")
    out = tmp_path / "sheet-out"
    res = runner.invoke(
        app,
        [
            "drama",
            "n3",
            "generate-look",
            "--card",
            str(card_path),
            "--face-ref",
            str(face),
            "--expected-md5",
            digest,
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["usable_for_n4"] is False
    assert payload["dry_run"] is True
    written = Path(payload["prompt_path"]).read_text(encoding="utf-8")
    assert "【L3硬约束】" in written
    assert "90°真背" in written
    assert md5_text(written) != GOLD_PROMPT_MD5
    assert payload.get("prompt_adapter") == "l3"
    assert "sk-" not in res.output


def test_live_generate_writes_sheet_keeps_usable_false(tmp_path):
    face = _face(tmp_path)
    jpeg = b"\xff\xd8\xff" + b"sheet" * 20

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        assert url == ARK_IMAGES_URL
        assert json["size"] == "2048x1365"
        assert "sequential_image_generation" not in json
        assert json["model"] == SEEDREAM_SKU_PRIMARY
        return _Resp(200, payload={"data": [{"url": "https://cdn.example/s.jpg"}]})

    def fake_get(url, timeout=None):
        return _Resp(200, content=jpeg)

    look = generate_gold_a_sheet(
        card=_sheet_card(),
        face_ref=face,
        out_dir=tmp_path / "out",
        api_key="not-a-real-key",
        dry_run=False,
        post=fake_post,
        get=fake_get,
    )
    assert look["usable_for_n4"] is False
    assert look["model"] == SEEDREAM_SKU_PRIMARY
    sheet = Path(look["sheet_path"])
    assert sheet.read_bytes() == jpeg
    assert look["sheet_md5"] == hashlib.md5(jpeg).hexdigest()
    assert "not-a-real-key" not in json.dumps(look)


def test_live_without_key_is_honest(tmp_path):
    face = _face(tmp_path)
    exc = _err(
        lambda: generate_gold_a_sheet(
            card=_sheet_card(),
            face_ref=face,
            out_dir=tmp_path / "out",
            api_key=None,
            dry_run=False,
        )
    )
    assert exc.code == "provider"
    assert Path(tmp_path / "out" / "CHAR-01-doubao-sheet-prompt.txt").is_file()
    assert not (tmp_path / "out" / "CHAR-01-turnaround-sheet-3x2.jpg").exists()
