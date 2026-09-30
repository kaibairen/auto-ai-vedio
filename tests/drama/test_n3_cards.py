"""021a · cards from cast only. docs≠PASS. ForcePass=never."""

from __future__ import annotations

from aiv_drama.errors import AppError
from aiv_drama_n3.crop import CROP_COLUMNS
from aiv_drama_n3.models import N3AttachRequest, N3MaterializeRequest

from tests.drama.helpers import lock_g2, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_cards_only_from_cast_char_scene(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    env = svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    cast_chars = {c["id"] for c in rec["cast"]["characters"]}
    cast_scenes = {s["id"] for s in rec["cast"]["scenes"]}
    card_chars = {c["id"] for c in env["cards"]["characters"]}
    card_scenes = {s["id"] for s in env["cards"]["scenes"]}
    assert card_chars
    assert card_chars <= cast_chars
    assert card_scenes <= cast_scenes
    assert all(cid.startswith("CHAR-") for cid in card_chars)
    assert all(sid.startswith("SCENE-") for sid in card_scenes)
    assert "NONE" not in card_chars
    disk = svc.store.episode_dir(pid, "EP01") / "cards"
    assert (disk / "index.yaml").is_file()


def test_no_invent_and_no_b_class_char(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    rec["cast"]["characters"].append(
        {"id": "CHAR-88", "name": "【系统音】", "one_line": "系统播报", "library_ref": None}
    )
    rec["cast"]["characters"].append(
        {"id": "FAKE-01", "name": "路人甲", "one_line": "群杂", "library_ref": None}
    )
    env = svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou", unlock_edit=True))
    ids = {c["id"] for c in env["cards"]["characters"]}
    assert "CHAR-88" not in ids
    assert "FAKE-01" not in ids
    skipped = [w for w in (env.get("warnings") or []) if w.get("code") == "b_class_skipped"]
    assert skipped
    exc = _err(
        lambda: svc.attach_n3_card(
            pid,
            "EP01",
            N3AttachRequest(id="CHAR-99", version=1, kind="character", actor="yangzhou"),
            raw={"id": "CHAR-99", "version": 1},
        )
    )
    assert exc.status_code == 422
    assert exc.code == "card_id_not_in_cast"


def test_storyboard_crop_is_readonly_projection(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    crop = svc.get_n3_crop(pid, "EP01")["storyboard_crop"]
    assert crop["readonly"] is True
    assert crop["source_node"] == "D-N2"
    assert list(crop["columns"]) == list(CROP_COLUMNS)
    if crop["rows"]:
        row = crop["rows"][0]
        assert "bridge_id" not in row
        assert "tool_duration_bucket" not in row
        assert "grid_strict" not in row
        assert "duration" in row
        assert row["duration"] == row["duration_s"]
    rec = svc._rec(pid, "EP01")
    sb = rec["storyboard"]
    before = [(r["shot_id"], r.get("duration_s"), r.get("shot_size"), r.get("camera")) for r in sb["rows"]]
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    after = [
        (r["shot_id"], r.get("duration_s"), r.get("shot_size"), r.get("camera"))
        for r in svc._rec(pid, "EP01")["storyboard"]["rows"]
    ]
    assert before == after
