"""Opt-in SCENE plate generate. Does not route through CHAR look commands."""

from __future__ import annotations

import inspect
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app, n3_generate_scene
from aiv_drama.errors import AppError
from aiv_drama_n3.cards import SCENE_REF_ROLE, has_usable_ref
from aiv_drama_n3.gold_sheet import md5_text
from aiv_drama_n3.models import N3GenerateSceneRequest, N3MaterializeRequest
from aiv_drama_n3.seedream import SEEDREAM_SKU_CHAIN, SEEDREAM_SKU_PRIMARY
from aiv_drama_n3.scene_look import (
    SCENE_PLATE_EN,
    SCENE_PLATE_KIND,
    SCENE_PLATE_OUTPUT,
    SCENE_PLATE_RECIPE,
    SCENE_PLATE_ROLE,
    SCENE_PLATE_STYLE,
    SCENE_PROMPT_ORDER,
    TEMPLATE_BAN_TOKENS,
    assemble_scene_plate_prompt,
    assemble_scene_plate_sections,
    generate_scene_plate,
    record_scene_plate_ref,
)
from tests.drama.helpers import lock_g2, seed_project_episode

runner = CliRunner()


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _scene_card(**extra) -> dict:
    card = {
        "id": "SCENE-01",
        "kind": "scene",
        "name": "室内门厅",
        "one_line": "迎客空间",
        "refs": [],
    }
    card.update(extra)
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


def test_has_usable_ref_scene_accepts_plate_not_character_roles_only():
    """Scene usable ref = path+md5 and not missing_file; project convention is plate."""
    assert SCENE_REF_ROLE == "plate" == SCENE_PLATE_ROLE
    scene = {
        "kind": "scene",
        "refs": [{"path": "/tmp/scene.jpg", "md5": "abc123", "role": "plate", "missing_file": False}],
    }
    assert has_usable_ref(scene) is True
    char = {
        "kind": "character",
        "refs": [{"path": "/tmp/scene.jpg", "md5": "abc123", "role": "plate", "missing_file": False}],
    }
    assert has_usable_ref(char) is False
    char_face = {
        "kind": "character",
        "refs": [{"path": "/tmp/face.jpg", "md5": "abc123", "role": "face", "missing_file": False}],
    }
    assert has_usable_ref(char_face) is True


def test_assemble_uses_name_and_one_line_only():
    card = _scene_card(appearance="红柱石阶与铜灯", light_anchor="深夜冷白顶光", immutable="不可移铜鼎")
    prompt = assemble_scene_plate_prompt(card)
    assert "室内门厅" in prompt
    assert "迎客空间" in prompt
    assert SCENE_PLATE_STYLE in prompt
    assert SCENE_PLATE_RECIPE in prompt
    assert SCENE_PLATE_EN in prompt
    assert SCENE_PLATE_OUTPUT in prompt
    assert "红柱石阶与铜灯" not in prompt
    assert "深夜冷白顶光" not in prompt
    assert "不可移铜鼎" not in prompt
    assert "ONLY identity anchor" not in prompt
    names = [n for n, _ in assemble_scene_plate_sections(card)]
    assert names == list(SCENE_PROMPT_ORDER)


def test_templates_do_not_hardcode_episode_tokens():
    blobs = (SCENE_PLATE_STYLE, SCENE_PLATE_RECIPE, SCENE_PLATE_EN, SCENE_PLATE_OUTPUT)
    for blob in blobs:
        for token in TEMPLATE_BAN_TOKENS:
            assert token not in blob


def test_assemble_rejects_char_and_incomplete_scene():
    exc = _err(lambda: assemble_scene_plate_prompt({"id": "CHAR-01", "kind": "character", "name": "甲", "one_line": "乙"}))
    assert exc.code == "char_look_forbidden"
    exc2 = _err(lambda: assemble_scene_plate_prompt({"id": "SCENE-01", "kind": "scene", "name": "门厅"}))
    assert exc2.code == "card_incomplete"


def test_dry_run_writes_prompt_not_sheet_and_skips_api(tmp_path, monkeypatch):
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Ark must not run on dry-run")

    monkeypatch.setattr("aiv_drama_n3.scene_look.generate_seedream_sheet", boom)
    card = _scene_card()
    look = generate_scene_plate(
        card=card,
        out_dir=tmp_path / "out",
        api_key="sk-should-not-be-used",
        dry_run=True,
    )
    assert called["n"] == 0
    assert look["dry_run"] is True
    assert look["kind"] == SCENE_PLATE_KIND
    assert look["role"] == "plate"
    assert look["sheet_path"] is None
    assert look["sku_chain"] == list(SEEDREAM_SKU_CHAIN)
    assert look["sku_chain"][0] == SEEDREAM_SKU_PRIMARY
    prompt_path = Path(look["prompt_path"])
    assert prompt_path.is_file()
    written = prompt_path.read_text(encoding="utf-8")
    assert written == assemble_scene_plate_prompt(card)
    assert look["prompt_md5"] == md5_text(written)
    assert not (tmp_path / "out" / "SCENE-01-scene-plate.jpg").exists()
    recorded = json.loads(Path(look["recorded_path"]).read_text(encoding="utf-8"))
    assert recorded["sku_chain"][0] == SEEDREAM_SKU_PRIMARY
    assert "image" not in recorded["body_keys"]
    assert "image" not in recorded
    assert card.get("refs") == []
    assert "sk-" not in json.dumps(look)


def test_scene_card_records_plate_ref_without_touching_character_cards():
    scene = _scene_card()
    character = {
        "id": "CHAR-01",
        "kind": "character",
        "name": "预挂甲",
        "one_line": "职司一句",
        "refs": [{"path": "/tmp/face.jpg", "md5": "facehash", "role": "face", "missing_file": False}],
    }
    char_before = deepcopy(character)
    record_scene_plate_ref(scene, path="/tmp/looks/SCENE-01-scene-plate.jpg", md5="platedigest")
    assert scene["refs"] == [
        {
            "path": "/tmp/looks/SCENE-01-scene-plate.jpg",
            "md5": "platedigest",
            "role": "plate",
            "missing_file": False,
        }
    ]
    assert has_usable_ref(scene) is True
    assert scene["missing_ref"] is False
    assert character == char_before
    assert has_usable_ref(character) is True
    exc = _err(lambda: record_scene_plate_ref(character, path="/tmp/x.jpg", md5="abc"))
    assert exc.code == "char_look_forbidden"
    assert character == char_before


def test_episode_live_records_plate_on_scene_only(svc, tmp_path, monkeypatch):
    jpeg = b"\xff\xd8\xff" + b"plate" * 20
    posts = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        posts.append(json["model"])
        assert json["model"] == SEEDREAM_SKU_PRIMARY
        assert "image" not in json
        assert "sequential_image_generation" not in json
        return _Resp(200, payload={"data": [{"url": "https://cdn.example/s.jpg"}]})

    def fake_get(url, timeout=None):
        return _Resp(200, content=jpeg)

    def boom(*_a, **_k):
        raise AssertionError("must not route through CHAR look generate")

    monkeypatch.setattr("aiv_drama_n3.look_generate.generate_gold_a_sheet", boom)
    monkeypatch.setattr("aiv_drama_n3.split_look.generate_split_look", boom, raising=False)
    svc.settings = replace(svc.settings, ark_api_key="sk-test-not-for-network")

    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    scene_id = rec["n3"]["cards"]["scenes"][0]["id"]
    chars_before = deepcopy(rec["n3"]["cards"]["characters"])
    env = svc.generate_n3_scene(
        pid,
        "EP01",
        N3GenerateSceneRequest(id=scene_id, dry_run=False, actor="eng-scene"),
        raw={"id": scene_id, "dry_run": False, "actor": "eng-scene"},
        post=fake_post,
        get=fake_get,
    )
    assert env["ok"] is True
    assert env["usable_for_n4"] is False
    assert env["auto_flipped_usable"] is False
    look = env["look"]
    assert look["role"] == "plate"
    sheet = Path(look["sheet_path"])
    assert "looks" in sheet.parts
    assert scene_id in sheet.parts
    assert sheet.read_bytes() == jpeg
    rec2 = svc._rec(pid, "EP01")
    scene = next(s for s in rec2["n3"]["cards"]["scenes"] if s["id"] == scene_id)
    assert scene["refs"]
    assert scene["refs"][0]["role"] == "plate"
    assert scene["refs"][0]["md5"] == look["sheet_md5"]
    assert has_usable_ref(scene) is True
    assert rec2["n3"]["cards"]["characters"] == chars_before
    assert posts == [SEEDREAM_SKU_PRIMARY]
    assert "sk-test-not-for-network" not in json.dumps(env)


def test_episode_dry_run_does_not_record_ref(svc, tmp_path, monkeypatch):
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Ark must not run on dry-run")

    monkeypatch.setattr("aiv_drama_n3.scene_look.generate_seedream_sheet", boom)
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    scene_id = rec["n3"]["cards"]["scenes"][0]["id"]
    chars_before = deepcopy(rec["n3"]["cards"]["characters"])
    env = svc.generate_n3_scene(
        pid,
        "EP01",
        N3GenerateSceneRequest(id=scene_id, dry_run=True, actor="eng-scene"),
        raw={"id": scene_id, "dry_run": True, "actor": "eng-scene"},
    )
    assert called["n"] == 0
    assert env["look"]["dry_run"] is True
    assert Path(env["look"]["prompt_path"]).is_file()
    rec2 = svc._rec(pid, "EP01")
    scene = next(s for s in rec2["n3"]["cards"]["scenes"] if s["id"] == scene_id)
    assert not any((r.get("role") == "plate") for r in (scene.get("refs") or []))
    assert has_usable_ref(scene) is False
    assert rec2["n3"]["cards"]["characters"] == chars_before


def test_generate_scene_has_no_model_or_face_ref():
    params = inspect.signature(generate_scene_plate).parameters
    assert "models" not in params
    assert "model" not in params
    assert "skip_flash" not in params
    assert "face_ref" not in params
    names = set(inspect.signature(n3_generate_scene).parameters)
    assert "model" not in names
    assert "skip_flash" not in names
    assert "face_ref" not in names
    assert "dry_run" in names


def test_http_generate_scene_rejects_char(client):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize", json={"actor": "x"})
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-scene",
        json={"id": "CHAR-01", "dry_run": True, "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"
    char = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-scene",
        json={"id": "CHAR-01", "dry_run": True},
    )
    assert char.status_code == 422
    assert char.json()["error"]["code"] == "char_look_forbidden"
    rec = svc._rec(pid, "EP01")
    scene_id = rec["n3"]["cards"]["scenes"][0]["id"]
    ok = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-scene",
        json={"id": scene_id, "dry_run": True, "actor": "eng-scene"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["look"]["dry_run"] is True
    assert body["look"]["role"] == "plate"
    assert Path(body["look"]["prompt_path"]).is_file()
    rec2 = svc._rec(pid, "EP01")
    scene = next(s for s in rec2["n3"]["cards"]["scenes"] if s["id"] == scene_id)
    assert not any((r.get("role") == "plate") for r in (scene.get("refs") or []))


def test_cli_standalone_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Ark must not run on dry-run")

    monkeypatch.setattr("aiv_cli.cli.generate_gold_a_sheet", boom)
    monkeypatch.setattr("aiv_drama_n3.scene_look.generate_seedream_sheet", boom)
    card_path = tmp_path / "SCENE-01-card.yaml"
    card_path.write_text(
        "id: SCENE-01\nkind: scene\nname: 室内门厅\none_line: 迎客空间\n",
        encoding="utf-8",
    )
    out = tmp_path / "scene-out"
    listing = runner.invoke(app, ["drama", "n3", "--help"])
    assert listing.exit_code == 0, listing.output
    assert "generate-scene" in listing.output
    help_res = runner.invoke(app, ["drama", "n3", "generate-scene", "--help"])
    assert help_res.exit_code == 0, help_res.output
    assert "--dry-run" in help_res.output
    assert "--face-ref" not in help_res.output
    assert "--model" not in help_res.output
    res = runner.invoke(
        app,
        [
            "drama",
            "n3",
            "generate-scene",
            "--card",
            str(card_path),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["dry_run"] is True
    assert payload["kind"] == SCENE_PLATE_KIND
    written = Path(payload["prompt_path"]).read_text(encoding="utf-8")
    assert "室内门厅" in written
    assert "迎客空间" in written
    assert payload["sku_chain"][0] == SEEDREAM_SKU_PRIMARY
    assert called["n"] == 0
    assert "sk-" not in res.output
