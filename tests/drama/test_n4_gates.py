"""026 · usable=false no write; missing file honest BLOCK; stale; overwrite version."""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n4.models import N4AssembleRequest
from aiv_drama_n4.projection import prompts_jsonl_name

from tests.drama.helpers import attach_real_refs, lock_g2, lock_g3_usable, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_usable_false_does_not_write_jsonl(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert svc.get_gate_g3(pid, "EP01")["usable_for_n4"] is False
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 422
    assert exc.code == "usable_for_n4_false"
    assert exc.details.get("written") is False
    assert exc.details.get("missing_refs")
    ep_dir = Path(data_dir) / "projects" / pid / "episodes" / "EP01"
    assert not (ep_dir / prompts_jsonl_name("EP01")).exists()
    consumer = svc.get_dn4_consumer(pid, "EP01")
    assert consumer["started"] is False


def test_missing_file_honest_block(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    for card in rec["n3"]["cards"]["characters"] + rec["n3"]["cards"]["scenes"]:
        ghost = data_dir / "refs" / f"{card['id']}-ghost.png"
        card["refs"] = [{"path": str(ghost), "md5": "abc", "role": "face", "missing_file": False}]
        card["missing_ref"] = False
        card["weak_binding"] = False
    svc._commit(rec)
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    # N3 usable may be true (stored missing_file=false) but file is absent — assemble must BLOCK.
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 422
    assert exc.code == "usable_for_n4_false"
    reasons = {m.get("reason") for m in (exc.details.get("missing_refs") or [])}
    assert "missing_file" in reasons
    assert not (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")).exists()


def test_assemble_writes_jsonl_and_consumer_started(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g3_usable(svc, pid, data_dir)
    env = svc.assemble_n4(
        pid,
        "EP01",
        N4AssembleRequest(actor="yangzhou", tool_profile="seedance_2_0"),
        raw={"actor": "yangzhou", "tool_profile": "seedance_2_0"},
    )
    assert env["written"] is True
    assert env["started"] is True
    assert env["n4"]["tool_profile"] == "seedance_2"
    assert env["n4"]["tool_profile_input"] == "seedance_2_0"
    assert env["assemble_version"] == 1
    path = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / "EP01-prompts.jsonl"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.strip()
    assert "seedance_2" in text
    assert "CHAR-01" not in "".join(line.get("prompt", "") for line in env["lines"])
    consumer = svc.get_dn4_consumer(pid, "EP01")
    assert consumer["started"] is True
    assert consumer["jsonl"]
    assert consumer["artifact"] == "episodes/EP01/EP01-prompts.jsonl"


def test_overwrite_bumps_assemble_version(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g3_usable(svc, pid, data_dir)
    first = svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="a"), raw={"actor": "a"})
    second = svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="b"), raw={"actor": "b"})
    assert first["assemble_version"] == 1
    assert second["assemble_version"] == 2
    assert second["n4"]["previous_assemble_version"] == 1
    assert second["n4"]["history"]


def test_upstream_stale_blocks_write_until_reassemble(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g3_usable(svc, pid, data_dir)
    svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    rec["n3"]["cards"]["stale"] = True
    rec["n4"]["stale"] = True
    svc._commit(rec)
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "stale_upstream"
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou", unlock_edit=True))
    attach_real_refs(svc, pid, data_dir)
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    again = svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    assert again["written"] is True
    assert again["n4"]["stale"] is False
    assert again["assemble_version"] >= 2


def test_force_pass_forbidden_on_assemble(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g3_usable(svc, pid, data_dir)
    exc = _err(
        lambda: svc.assemble_n4(
            pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"
