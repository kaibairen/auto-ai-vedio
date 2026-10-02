"""BRIEF-AIV-029 — N3 text thicken. ForcePass=never. docs≠PASS."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app
from aiv_drama.errors import AppError
from aiv_drama_n3.models import N3MaterializeRequest, N3ThickenRequest
from aiv_drama_n3.templates import KEEP_CHAR_TEMPLATES, SEEDANCE_PARAM_REF, thicken_skill_paths
from aiv_drama_n3.thicken import apply_patch_to_card, soft_merge_cam
from aiv_drama_n3.validate import WEAK_BINDING_MESSAGE

from tests.drama.helpers import lock_g2, seed_project_episode

runner = CliRunner()


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _enable_llm(svc):
    svc.settings = replace(
        svc.settings,
        openai_api_key="sk-test",
        openai_model="deepseek-chat",
        openai_base_url="https://api.deepseek.com/v1",
    )
    return svc


def _fake_thicken(monkeypatch, *, mutate=None, raw_content=None):
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            if raw_content is not None:
                return {"choices": [{"message": {"content": raw_content}}]}
            user = json.loads(captured["json"]["messages"][1]["content"])
            cards = []
            for thin in user.get("cards") or []:
                ident = thin["id"]
                kind = thin["kind"]
                if kind == "character":
                    patch = {
                        "id": ident,
                        "kind": kind,
                        "appearance": f"{thin.get('name')} 方脸短碎发，深蓝工装外套，左耳银钉",
                        "immutable": ["方脸短碎发", "深蓝工装外套", "左耳银钉"],
                        "light_look": "柔和正面主光，弱补光，中性偏冷棚光",
                        "look_shot_pref": "CU",
                        "framing": "胸以上居中，白底无纹理",
                    }
                else:
                    patch = {
                        "id": ident,
                        "kind": kind,
                        "name": thin.get("name"),
                        "appearance": f"{thin.get('name')} 室内门厅，冷白顶灯，深色显示墙，乱线键盘区",
                        "light_anchor": "深夜，顶冷白灯为主，屏幕蓝光辅，低环境光",
                        "space_anchors": ["深色显示器墙", "乱线键盘区", "冷白顶灯"],
                    }
                if mutate:
                    mutate(patch, thin)
                cards.append(patch)
            return {"choices": [{"message": {"content": json.dumps({"cards": cards}, ensure_ascii=False)}}]}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("aiv_drama_n3.thicken.httpx.post", fake_post)
    return captured


def _materialize(svc, pid):
    lock_g2(svc, pid)
    return svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))


def test_soft_merge_cam_does_not_require_extras():
    appearance, light = soft_merge_cam("character", "方脸黑框眼镜", None, {})
    assert appearance == "方脸黑框眼镜"
    assert light is None
    appearance, light = soft_merge_cam(
        "scene",
        "门厅纵深",
        "深夜，顶冷白灯为主，低环境光",
        {"space_anchors": ["吧台", "落地窗"], "framing_scene": "门廊纵深居中"},
    )
    assert "空间锚：吧台、落地窗" in (appearance or "")
    assert "门廊纵深居中" in (appearance or "")
    assert light == "深夜，顶冷白灯为主，低环境光"


def test_apply_patch_strips_refs_and_usable():
    card = {
        "id": "CHAR-01",
        "kind": "character",
        "name": "林晚",
        "one_line": "重生女主",
        "refs": [],
        "missing_ref": True,
        "weak_binding": True,
        "appearance": None,
        "immutable": None,
        "light_anchor": None,
    }
    updated = apply_patch_to_card(
        card,
        {
            "id": "CHAR-01",
            "appearance": "方脸短碎发，深蓝外套",
            "immutable": ["方脸短碎发", "深蓝外套"],
            "refs": [{"path": "/tmp/fake.png", "md5": "abc", "role": "face"}],
            "look_path": "/tmp/fake.png",
            "md5": "abc",
            "usable_for_n4": True,
            "missing_ref": False,
        },
    )
    assert updated["appearance"]
    assert updated["refs"] == []
    assert updated["missing_ref"] is True
    assert updated.get("usable_for_n4") is not True


def test_thicken_happy_path_fills_must_and_keeps_thin_refs(svc, monkeypatch, data_dir):
    _enable_llm(svc)
    captured = _fake_thicken(monkeypatch)
    pid = seed_project_episode(svc)
    mat = _materialize(svc, pid)
    assert all(not c.get("appearance") for c in mat["cards"]["characters"])
    env = svc.thicken_n3_cards(
        pid,
        "EP01",
        N3ThickenRequest(actor="eng-dogfood-029", provider="llm"),
        raw={"actor": "eng-dogfood-029", "provider": "llm"},
    )
    assert env["ok"] is True
    assert env["fixture_hits"] == 0
    assert env["provider"] == "llm"
    assert env["model"] == "deepseek-chat"
    assert env["usable_for_n4"] is False
    assert env["cards"]["usable_for_n4"] is False
    assert env["gate"]["locked"] is False
    assert env["scene_template"]["status"] == "provisional_inline"
    assert env["scene_template"]["path"] is None
    assert not any("场景卡" in (p or "") for p in env["prompt_paths"])
    assert SEEDANCE_PARAM_REF not in env["prompt_paths"]
    for rel in KEEP_CHAR_TEMPLATES:
        if (svc.settings.repo_root / rel).is_file():
            assert rel in env["prompt_paths"]
            assert rel in env["thicken_prompt_paths"]
    assert env["thicken_skill_paths"] == []
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert "images" not in captured["url"]
    user = json.loads(captured["json"]["messages"][1]["content"])
    assert user["scene_template"]["path"] is None
    assert "provisional_inline" in user["scene_template"]["status"]
    assert ".skill/generation/Seedance2.0-分镜/SKILL.md" not in (user.get("skill_paths") or [])
    for card in env["cards"]["characters"]:
        assert card["appearance"]
        assert card["immutable"]
        assert card["missing_ref"] is True
        assert card["refs"] == []
        assert "近景，胸以上" in card["appearance"]
    for card in env["cards"]["scenes"]:
        assert card["appearance"]
        assert card["light_anchor"]
        assert card["template_status"] == "provisional_inline"
        assert card["template_path"] is None
        assert card["missing_ref"] is True
        assert "空间锚：" in card["appearance"]
    ep_json = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / ".aiv" / "episode.json"
    meta = json.loads(ep_json.read_text(encoding="utf-8"))
    n3m = meta.get("n3_meta") or {}
    assert n3m["scene_template"] == "provisional_inline"
    assert n3m["fixture_hits"] == 0
    assert all(str(p).startswith(".prompt/consistency/") for p in n3m.get("thicken_prompt_paths") or [])
    assert all(not str(p).startswith(".prompt/") for p in n3m.get("thicken_skill_paths") or [])


def test_thicken_bio_skill_stays_off_n1_n2_skill_paths(svc, monkeypatch):
    _enable_llm(svc)
    captured = _fake_thicken(monkeypatch)
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    n2_before = list(svc.get_storyboard(pid, "EP01").get("skill_paths") or [])
    outline_before = list(svc.get_outline(pid, "EP01").get("skill_paths") or [])
    env = svc.thicken_n3_cards(
        pid,
        "EP01",
        N3ThickenRequest(actor="yangzhou", provider="llm", include_bio_skill=True),
        raw={"actor": "yangzhou", "provider": "llm", "include_bio_skill": True},
    )
    expected = thicken_skill_paths(svc.settings.repo_root, include_bio_skill=True)
    assert env["thicken_skill_paths"] == expected
    assert expected
    assert all(str(p).startswith(".skill/writing/动态漫-人物小传/") for p in expected)
    assert all(not str(p).startswith(".prompt/") for p in env["thicken_skill_paths"])
    user = json.loads(captured["json"]["messages"][1]["content"])
    assert user["skill_paths"] == expected
    n2_after = list(svc.get_storyboard(pid, "EP01").get("skill_paths") or [])
    outline_after = list(svc.get_outline(pid, "EP01").get("skill_paths") or [])
    assert n2_after == n2_before
    assert outline_after == outline_before
    assert all(not str(p).startswith(".prompt/") for p in n2_after)
    rec = svc._rec(pid, "EP01")
    assert "skill_paths" not in ((rec.get("n3") or {}).get("cards") or {})


def test_thicken_force_pass_and_fixture_and_image_keys_banned(svc, monkeypatch):
    _enable_llm(svc)
    _fake_thicken(monkeypatch)
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    for key in ("force_pass", "force", "skip_gate"):
        exc = _err(
            lambda k=key: svc.thicken_n3_cards(
                pid,
                "EP01",
                N3ThickenRequest(actor="yangzhou", provider="llm"),
                raw={"actor": "yangzhou", "provider": "llm", k: True},
            )
        )
        assert exc.status_code == 400
        assert exc.code == "force_pass_forbidden"
    exc = _err(
        lambda: svc.thicken_n3_cards(
            pid,
            "EP01",
            N3ThickenRequest(actor="yangzhou", provider="fixture"),
            raw={"actor": "yangzhou", "provider": "fixture"},
        )
    )
    assert exc.status_code == 422
    assert exc.code == "provider"
    exc = _err(
        lambda: svc.thicken_n3_cards(
            pid,
            "EP01",
            N3ThickenRequest(actor="yangzhou", provider="llm"),
            raw={"actor": "yangzhou", "provider": "llm", "image_gen": True},
        )
    )
    assert exc.status_code == 400
    rec = svc._rec(pid, "EP01")
    char = rec["n3"]["cards"]["characters"][0]
    assert not char.get("appearance")


def test_thicken_requires_materialize_and_unlocked_g3(svc, monkeypatch):
    _enable_llm(svc)
    _fake_thicken(monkeypatch)
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    exc = _err(
        lambda: svc.thicken_n3_cards(
            pid, "EP01", N3ThickenRequest(actor="yangzhou"), raw={"actor": "yangzhou", "provider": "llm"}
        )
    )
    assert exc.status_code == 422
    assert exc.code == "cards_empty"
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(
        lambda: svc.thicken_n3_cards(
            pid, "EP01", N3ThickenRequest(actor="yangzhou"), raw={"actor": "yangzhou", "provider": "llm"}
        )
    )
    assert exc.status_code == 409
    assert exc.code == "locked"
    env = svc.thicken_n3_cards(
        pid,
        "EP01",
        N3ThickenRequest(actor="yangzhou", unlock_edit=True),
        raw={"actor": "yangzhou", "provider": "llm", "unlock_edit": True},
    )
    assert env["gate"]["locked"] is False
    assert env["cards"]["characters"][0]["appearance"]


def test_thicken_incomplete_does_not_commit(svc, monkeypatch):
    _enable_llm(svc)

    def hollow(patch, thin):
        if thin["kind"] == "character":
            patch["appearance"] = "好看"
            patch["immutable"] = []

    _fake_thicken(monkeypatch, mutate=hollow)
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    exc = _err(
        lambda: svc.thicken_n3_cards(
            pid, "EP01", N3ThickenRequest(actor="yangzhou"), raw={"actor": "yangzhou", "provider": "llm"}
        )
    )
    assert exc.status_code == 422
    assert exc.code == "thicken_incomplete"
    rec = svc._rec(pid, "EP01")
    assert not rec["n3"]["cards"]["characters"][0].get("appearance")
    assert rec.get("n3", {}).get("thicken") is None


def test_thicken_llm_refs_do_not_become_success(svc, monkeypatch):
    _enable_llm(svc)

    def with_refs(patch, _thin):
        patch["refs"] = [{"path": "looks/CHAR.png", "md5": "deadbeef", "role": "face"}]
        patch["usable_for_n4"] = True

    _fake_thicken(monkeypatch, mutate=with_refs)
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    env = svc.thicken_n3_cards(
        pid, "EP01", N3ThickenRequest(actor="yangzhou"), raw={"actor": "yangzhou", "provider": "llm"}
    )
    for card in env["cards"]["characters"] + env["cards"]["scenes"]:
        assert card["refs"] == []
        assert card["missing_ref"] is True
    assert env["usable_for_n4"] is False


def test_duplicate_scene_name_warns_does_not_block_g3_or_merge_ids(svc, monkeypatch):
    _enable_llm(svc)
    _fake_thicken(monkeypatch)
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    rec = svc._rec(pid, "EP01")
    scenes = rec["n3"]["cards"]["scenes"]
    assert len(scenes) >= 2
    scenes[1]["name"] = scenes[0]["name"]
    id_a, id_b = scenes[0]["id"], scenes[1]["id"]
    svc._commit(rec)
    env = svc.thicken_n3_cards(
        pid, "EP01", N3ThickenRequest(actor="yangzhou"), raw={"actor": "yangzhou", "provider": "llm"}
    )
    warns = [w for w in (env.get("warnings") or []) if w.get("code") == "duplicate_scene_name"]
    assert warns
    assert set(warns[0].get("ids") or warns[0].get("details", {}).get("ids") or []) == {id_a, id_b}
    after_ids = {s["id"] for s in env["cards"]["scenes"]}
    assert id_a in after_ids and id_b in after_ids
    assert id_a != id_b
    passed = svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert passed["gate"]["locked"] is True
    assert passed["usable_for_n4"] is False
    still = [w for w in (passed.get("warnings") or []) if w.get("code") == "duplicate_scene_name"]
    assert still
    assert any(w.get("code") == "missing_ref" for w in (passed.get("warnings") or []))
    assert any(WEAK_BINDING_MESSAGE in (w.get("message") or "") for w in (passed.get("warnings") or []))


def test_thicken_missing_cam_extras_still_ok(svc, monkeypatch):
    _enable_llm(svc)

    def no_cam(patch, thin):
        for key in (
            "look_shot_pref",
            "framing",
            "light_look",
            "space_anchors",
            "framing_scene",
            "scene_shot_pref",
        ):
            patch.pop(key, None)
        if thin["kind"] == "character":
            patch["appearance"] = "方脸短碎发，深蓝外套，左耳银钉"
            patch["immutable"] = ["方脸短碎发", "深蓝外套"]
        else:
            patch["appearance"] = "室内门厅，冷白顶灯，深色显示墙"
            patch["light_anchor"] = "深夜，顶冷白灯为主，低环境光"

    _fake_thicken(monkeypatch, mutate=no_cam)
    pid = seed_project_episode(svc)
    _materialize(svc, pid)
    env = svc.thicken_n3_cards(
        pid, "EP01", N3ThickenRequest(actor="yangzhou"), raw={"actor": "yangzhou", "provider": "llm"}
    )
    assert env["cards"]["characters"][0]["appearance"]
    assert env["cards"]["scenes"][0]["light_anchor"]


def test_http_thicken_happy_and_force_pass(client, monkeypatch):
    svc = _enable_llm(client.app.state.service)
    _fake_thicken(monkeypatch)
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    mat = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    assert mat.status_code == 200, mat.text
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/thicken",
        json={"actor": "yangzhou", "provider": "llm", "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"
    image = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/thicken",
        json={"actor": "yangzhou", "provider": "llm", "image_gen": True},
    )
    assert image.status_code == 400
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/thicken",
        json={"actor": "eng-dogfood-029", "provider": "llm"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["fixture_hits"] == 0
    assert body["cards"]["characters"][0]["appearance"]
    assert body["usable_for_n4"] is False


def test_cli_thicken_after_materialize(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    monkeypatch.setenv("AIV_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AIV_OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("AIV_OPENAI_MODEL", "deepseek-chat")
    _fake_thicken(monkeypatch)
    demo = runner.invoke(app, ["--fixture", "drama", "demo", "--ep", "EP01", "--lane", "female"])
    assert demo.exit_code == 0, demo.output
    gen = runner.invoke(
        app,
        ["drama", "storyboard", "generate", "--project", "proj_01", "--ep", "EP01", "--provider", "fixture"],
    )
    assert gen.exit_code == 0, gen.output
    con = runner.invoke(
        app,
        ["drama", "g2", "confirm", "--project", "proj_01", "--ep", "EP01", "--decision", "pass", "--actor", "yangzhou"],
    )
    assert con.exit_code == 0, con.output
    mat = runner.invoke(app, ["drama", "n3", "materialize", "--project", "proj_01", "--ep", "EP01", "--actor", "yangzhou"])
    assert mat.exit_code == 0, mat.output
    thick = runner.invoke(
        app,
        [
            "drama",
            "n3",
            "thicken",
            "--project",
            "proj_01",
            "--ep",
            "EP01",
            "--provider",
            "llm",
            "--actor",
            "eng-dogfood-029",
        ],
    )
    assert thick.exit_code == 0, thick.output
    payload = json.loads(thick.output)
    assert payload["fixture_hits"] == 0
    assert payload["cards"]["characters"][0]["appearance"]
    assert payload["usable_for_n4"] is False
    fx = runner.invoke(
        app,
        ["drama", "n3", "thicken", "--project", "proj_01", "--ep", "EP01", "--provider", "fixture", "--actor", "x"],
    )
    assert fx.exit_code == 2, fx.output
    assert "provider" in fx.output
