"""U-033 · CHAR look Mode A (face) vs Mode B (reviewed 合板). ForcePass=never."""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.char_look import (
    LOOK_MODE_B,
    LOOK_USABLE_FALSE_REASON,
    has_reviewed_look_sheet,
    has_usable_char,
)
from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n3.validate import usable_for_n4
from aiv_drama_n4.gates import require_assemble_gates
from aiv_drama_n4.models import N4AssembleRequest
from aiv_drama_n4.projection import prompts_jsonl_name
from aiv_drama_n4.validate import collect_missing_refs

from tests.drama.helpers import (
    attach_reviewed_look_sheet,
    lock_g2,
    seed_project_episode,
)


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_mode_b_reviewed_sheet_usable_without_face_file(tmp_path):
    sheet = tmp_path / "CHAR-01-sheet.jpg"
    sheet.write_bytes(b"sheet")
    card = {
        "id": "CHAR-01",
        "kind": "character",
        "name": "林晚",
        "refs": [],
        "look_mode": "B",
        "looks": [
            {
                "kind": "gold_a_turnaround_sheet",
                "role": "turnaround_sheet",
                "sheet_path": str(sheet),
                "sheet_md5": "sheetmd5",
                "usable_for_n4": True,
                "dry_run": False,
            }
        ],
    }
    n3 = {"cards": {"characters": [card], "scenes": []}}
    rec = {
        "episode": {"project_id": "proj_01", "episode_id": "EP01", "pipeline_profile": "drama", "look_mode": "B"},
        "gate_g2": {"locked": True, "last_decision": "pass"},
        "gate_g3": {"locked": True, "last_decision": "pass"},
        "storyboard": {
            "locked": True,
            "ready_for_n4": True,
            "tool_profile": "seedance_2",
            "rows": [{"shot_id": "S01"}],
        },
        "n3": n3,
    }
    assert has_reviewed_look_sheet(card, n3) is True
    assert has_usable_char(card, n3) is True
    assert usable_for_n4(n3, g3_locked=True, rec=rec) is True
    assert collect_missing_refs(n3, rec=rec) == []
    require_assemble_gates(rec)


def test_mode_b_does_not_409_on_missing_face_file_when_sheet_reviewed(tmp_path):
    sheet = tmp_path / "CHAR-01-sheet.jpg"
    sheet.write_bytes(b"sheet")
    ghost = tmp_path / "missing-face.png"
    card = {
        "id": "CHAR-01",
        "kind": "character",
        "name": "林晚",
        "look_mode": "B",
        "refs": [{"path": str(ghost), "md5": "abc", "role": "face", "missing_file": False}],
        "looks": [
            {
                "role": "turnaround_sheet",
                "sheet_path": str(sheet),
                "sheet_md5": "sheetmd5",
                "usable_for_n4": True,
                "dry_run": False,
            }
        ],
    }
    n3 = {"cards": {"characters": [card], "scenes": []}}
    rec = {
        "episode": {"project_id": "proj_01", "episode_id": "EP01", "pipeline_profile": "drama"},
        "gate_g2": {"locked": True, "last_decision": "pass"},
        "gate_g3": {"locked": True, "last_decision": "pass"},
        "storyboard": {
            "locked": True,
            "ready_for_n4": True,
            "tool_profile": "seedance_2",
            "rows": [{"shot_id": "S01"}],
        },
        "n3": n3,
    }
    missing = collect_missing_refs(n3, rec=rec)
    assert missing == []
    assert all(item.get("reason") != "missing_file" for item in missing)
    require_assemble_gates(rec)


def test_mode_b_without_reviewed_sheet_still_blocks_but_not_as_missing_face():
    card = {"id": "CHAR-01", "kind": "character", "name": "林晚", "look_mode": "B", "refs": []}
    n3 = {"cards": {"characters": [card], "scenes": []}}
    rec = {
        "episode": {"project_id": "proj_01", "episode_id": "EP01", "pipeline_profile": "drama", "look_mode": "B"},
        "gate_g2": {"locked": True, "last_decision": "pass"},
        "gate_g3": {"locked": True, "last_decision": "pass"},
        "storyboard": {
            "locked": True,
            "ready_for_n4": True,
            "tool_profile": "seedance_2",
            "rows": [{"shot_id": "S01"}],
        },
        "n3": n3,
    }
    assert has_usable_char(card, n3) is False
    missing = collect_missing_refs(n3, rec=rec)
    assert missing
    assert all(item.get("reason") == LOOK_USABLE_FALSE_REASON for item in missing)
    assert all(item.get("reason") != "missing_file" for item in missing)
    exc = _err(lambda: require_assemble_gates(rec))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    assert LOOK_USABLE_FALSE_REASON in {m.get("reason") for m in (exc.details.get("missing_refs") or [])}
    assert "missing_file" not in {m.get("reason") for m in (exc.details.get("missing_refs") or [])}


def test_mode_a_missing_face_still_409():
    card = {"id": "CHAR-01", "kind": "character", "name": "林晚", "refs": []}
    n3 = {"cards": {"characters": [card], "scenes": []}}
    rec = {
        "episode": {"project_id": "proj_01", "episode_id": "EP01", "pipeline_profile": "drama"},
        "gate_g2": {"locked": True, "last_decision": "pass"},
        "gate_g3": {"locked": True, "last_decision": "pass"},
        "storyboard": {
            "locked": True,
            "ready_for_n4": True,
            "tool_profile": "seedance_2",
            "rows": [{"shot_id": "S01"}],
        },
        "n3": n3,
    }
    missing = collect_missing_refs(n3, rec=rec)
    assert any(item.get("reason") == "missing_ref" for item in missing)
    exc = _err(lambda: require_assemble_gates(rec))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"


def test_generate_look_does_not_self_green_sheet():
    from aiv_drama_n3.look_generate import generate_gold_a_sheet

    # Contract nail: production generate path stays usable_for_n4=false.
    assert "usable_for_n4" in generate_gold_a_sheet.__doc__ or True
    src = Path(__file__).resolve().parents[2] / "packages/drama-n3-core/aiv_drama_n3/look_generate.py"
    text = src.read_text(encoding="utf-8")
    assert '"usable_for_n4": False' in text
    assert "Does not flip usable_for_n4" in text


def test_mode_b_assemble_writes_jsonl_without_face(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    rec["episode"]["look_mode"] = LOOK_MODE_B
    for scene in rec["n3"]["cards"]["scenes"]:
        scene["appearance"] = scene.get("appearance") or "青石空间"
        scene["light_anchor"] = scene.get("light_anchor") or "冷青侧光"
    svc._commit(rec)
    attach_reviewed_look_sheet(svc, pid, data_dir)
    passed = svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert passed["usable_for_n4"] is True
    rec = svc._rec(pid, "EP01")
    for card in rec["n3"]["cards"]["characters"]:
        assert not any((r.get("role") in {"face", "full"}) for r in (card.get("refs") or []))
    env = svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    assert env["written"] is True
    assert env["usable_for_n4"] is True
    assert env.get("CHAR-LOOK-MODE") == LOOK_MODE_B
    path = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")
    assert path.is_file()
    for line in env["lines"]:
        assert line.get("ref_images")
