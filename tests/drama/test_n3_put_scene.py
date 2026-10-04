"""Opt-in single SCENE work card. Does not rematerialize CHAR or drop looks."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app
from aiv_drama.errors import AppError
from aiv_drama_n3.cards import materialize_cards, upsert_one_scene_card
from aiv_drama_n3.gold_sheet import LOOK_KIND, LOOK_ROLE
from aiv_drama_n3.models import N3MaterializeRequest, N3PutSceneRequest

from tests.drama.helpers import lock_g2, seed_project_episode

runner = CliRunner()


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _char_yaml_snapshot(cards_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(cards_dir.glob("CHAR-*.yaml"))}


def _plant_looks(svc, pid: str, data_dir: Path, *, ep: str = "EP01") -> tuple[dict, dict, Path]:
    rec = svc._rec(pid, ep)
    cards = rec["n3"]["cards"]
    look_root = Path(data_dir) / "projects" / pid / "episodes" / ep / "looks"
    n3_looks: dict[str, dict] = {}
    for card in cards.get("characters") or []:
        ident = card["id"]
        dest = look_root / ident
        dest.mkdir(parents=True, exist_ok=True)
        sheet = dest / "sheet.png"
        sheet.write_bytes(f"look-{ident}".encode("utf-8"))
        slim = {
            "kind": LOOK_KIND,
            "role": LOOK_ROLE,
            "sheet_path": str(sheet),
            "sheet_md5": "lookmd5",
            "usable_for_n4": False,
        }
        card["looks"] = [slim]
        card["appearance"] = "preset wardrobe"
        card["immutable"] = "preset face lock"
        n3_looks[ident] = {"sheet_path": str(sheet), "sheet_md5": "lookmd5"}
    rec["n3"]["looks"] = n3_looks
    svc._commit(rec)
    return deepcopy(cards.get("characters") or []), deepcopy(n3_looks), look_root


def test_upsert_one_scene_card_does_not_emit_characters():
    cast = {
        "characters": [{"id": "CHAR-01", "name": "预挂甲", "one_line": "男主"}],
        "scenes": [],
    }
    storyboard = {"rows": [{"shot_id": "S01", "char_ids": ["CHAR-01"], "scene_id": "SCENE-08"}]}
    previous = {
        "characters": [{"id": "CHAR-01", "name": "预挂甲", "looks": [{"kind": LOOK_KIND}]}],
        "scenes": [],
    }
    card, row, skipped = upsert_one_scene_card(
        "SCENE-08",
        cast,
        storyboard,
        previous,
        name="茶水间空间",
        one_line="办公茶水",
    )
    assert not skipped
    assert card is not None
    assert card["id"] == "SCENE-08"
    assert card["kind"] == "scene"
    assert card["name"] == "茶水间空间"
    assert row["id"] == "SCENE-08"
    chars, scenes, _ = materialize_cards(cast, storyboard, previous)
    assert scenes == []
    assert chars[0]["id"] == "CHAR-01"


def test_put_scene_keeps_character_files_and_looks(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    chars_before, looks_before, look_root = _plant_looks(svc, pid, data_dir)
    cards_dir = svc.store.episode_dir(pid, "EP01") / "cards"
    yaml_before = _char_yaml_snapshot(cards_dir)
    assert yaml_before
    look_bytes_before = {p.name: p.read_bytes() for p in look_root.rglob("*") if p.is_file()}
    rec = svc._rec(pid, "EP01")
    rec["cast"]["scenes"] = []
    rec["n3"]["cards"]["scenes"] = []
    rec["storyboard"]["rows"][0]["scene_id"] = "SCENE-08"
    svc._commit(rec)

    env = svc.put_n3_scene(
        pid,
        "EP01",
        N3PutSceneRequest(id="SCENE-08", name="茶水间空间", one_line="办公茶水", actor="yangzhou"),
        raw={"id": "SCENE-08", "name": "茶水间空间", "one_line": "办公茶水", "actor": "yangzhou"},
    )
    assert env["ok"] is True
    assert env["rewrote_characters"] is False
    assert env["put_scene"]["id"] == "SCENE-08"
    assert env["put_scene"]["created"] is True
    scene_ids = [s["id"] for s in env["cards"]["scenes"]]
    assert "SCENE-08" in scene_ids
    rec_after = svc._rec(pid, "EP01")
    assert rec_after["n3"]["cards"]["characters"] == chars_before
    assert rec_after["n3"]["looks"] == looks_before
    assert _char_yaml_snapshot(cards_dir) == yaml_before
    look_bytes_after = {p.name: p.read_bytes() for p in look_root.rglob("*") if p.is_file()}
    assert look_bytes_after == look_bytes_before
    cast_scene = next(s for s in rec_after["cast"]["scenes"] if s["id"] == "SCENE-08")
    assert cast_scene["name"] == "茶水间空间"
    char_names = [c.get("name") for c in rec_after["cast"]["characters"]]
    assert char_names == [c.get("name") for c in chars_before]


def test_put_scene_updates_one_scene_without_touching_others(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    chars_before, looks_before, _look_root = _plant_looks(svc, pid, data_dir)
    rec = svc._rec(pid, "EP01")
    existing_scenes = deepcopy(rec["n3"]["cards"]["scenes"] or [])
    assert existing_scenes
    target = existing_scenes[0]["id"]
    env = svc.put_n3_scene(
        pid,
        "EP01",
        N3PutSceneRequest(id=target, name="营帐门厅", one_line="入场空间", actor="yangzhou"),
        raw={"id": target, "name": "营帐门厅", "one_line": "入场空间"},
    )
    assert env["put_scene"]["created"] is False
    rec_after = svc._rec(pid, "EP01")
    assert rec_after["n3"]["cards"]["characters"] == chars_before
    assert rec_after["n3"]["looks"] == looks_before
    updated = next(s for s in rec_after["n3"]["cards"]["scenes"] if s["id"] == target)
    assert updated["name"] == "营帐门厅"
    assert updated["one_line"] == "入场空间"
    other_before = {s["id"]: s for s in existing_scenes if s["id"] != target}
    other_after = {s["id"]: s for s in rec_after["n3"]["cards"]["scenes"] if s["id"] != target}
    assert other_after == other_before


def test_put_scene_rejects_char_id_and_b_class(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    bad_char = _err(
        lambda: svc.put_n3_scene(
            pid,
            "EP01",
            N3PutSceneRequest(id="CHAR-01", name="茶水间空间", one_line="空间"),
            raw={"id": "CHAR-01", "name": "茶水间空间", "one_line": "空间"},
        )
    )
    assert bad_char.status_code == 422
    assert "SCENE-" in bad_char.message
    missing = _err(
        lambda: svc.put_n3_scene(
            pid,
            "EP01",
            N3PutSceneRequest(id="SCENE-09", actor="yangzhou"),
            raw={"id": "SCENE-09"},
        )
    )
    assert missing.status_code == 422
    assert missing.code == "card_incomplete"
    chrome = _err(
        lambda: svc.put_n3_scene(
            pid,
            "EP01",
            N3PutSceneRequest(id="SCENE-09", name="系统音", one_line="播报"),
            raw={"id": "SCENE-09", "name": "系统音", "one_line": "播报"},
        )
    )
    assert chrome.status_code == 422
    assert chrome.code == "validation"


def test_put_scene_requires_g2(svc):
    pid = seed_project_episode(svc)
    exc = _err(
        lambda: svc.put_n3_scene(
            pid,
            "EP01",
            N3PutSceneRequest(id="SCENE-08", name="茶水间空间", one_line="办公茶水"),
            raw={"id": "SCENE-08", "name": "茶水间空间", "one_line": "办公茶水"},
        )
    )
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"


def test_http_put_scene_and_image_gen_forbidden(client):
    from tests.drama.test_n3_api import _setup_g2

    pid = _setup_g2(client)
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/put-scene",
        json={"id": "SCENE-08", "name": "茶水间空间", "one_line": "办公茶水", "image_gen": True},
    )
    assert banned.status_code == 400
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/put-scene",
        json={"id": "SCENE-08", "name": "茶水间空间", "one_line": "办公茶水", "actor": "yangzhou"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["put_scene"]["id"] == "SCENE-08"
    assert body["rewrote_characters"] is False
    spec = client.get("/openapi/drama-n3.v0.yaml")
    assert spec.status_code == 200
    assert "cards/put-scene" in spec.text


def test_cli_put_scene_after_materialize(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
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
    put = runner.invoke(
        app,
        [
            "drama",
            "n3",
            "put-scene",
            "--project",
            "proj_01",
            "--ep",
            "EP01",
            "--id",
            "SCENE-08",
            "--name",
            "茶水间空间",
            "--one-line",
            "办公茶水",
            "--actor",
            "yangzhou",
        ],
    )
    assert put.exit_code == 0, put.output
    assert "SCENE-08" in put.output
    assert '"rewrote_characters": false' in put.output
