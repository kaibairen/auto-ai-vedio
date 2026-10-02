"""021a · G3 thin gate. F1 usable_for_n4. ForcePass=never."""

from __future__ import annotations

from aiv_drama.errors import AppError
from aiv_drama.models import OutlineGenerateRequest
from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n3.validate import WEAK_BINDING_MESSAGE

from tests.drama.helpers import lock_g2, persist_and_confirm_intent, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_g2_unlocked_blocks_n3_writes(svc):
    pid = seed_project_episode(svc)
    persist_and_confirm_intent(svc, pid)
    svc.generate_outline(
        pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female", "provider": "fixture"}
    )
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou")))
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"
    assert exc.details.get("gate") == "g2"


def test_g3_confirm_reject_and_no_auto_n4(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    passed = svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou", "note": "本集用这些卡"})
    assert passed["gate"]["locked"] is True
    assert passed["gate"]["state"] == "passed"
    assert passed["next_edges"] == ["D-N4"]
    assert passed["auto_open_dn4"] is False
    assert svc._rec(pid, "EP01")["d_n4_jobs"] == []
    consumer = svc.get_dn4_consumer(pid, "EP01")
    assert consumer["started"] is False
    rejected = svc.confirm_gate_g3(pid, "EP01", {"decision": "reject", "actor": "yangzhou", "note": "换挂"})
    assert rejected["gate"]["locked"] is False
    assert rejected["gate"]["last_decision"] == "reject"
    assert rejected["next_edges"] == ["D-N3"]


def test_force_pass_skip_gate_hard_fail(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    for key in ("force_pass", "force", "skip_gate"):
        exc = _err(lambda k=key: svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou", k: True}))
        assert exc.status_code == 400
        assert exc.code == "force_pass_forbidden"
        assert exc.details.get("gate") == "g3"
        assert svc._rec(pid, "EP01")["gate_g3"]["locked"] is False


def test_missing_ref_warns_but_g3_confirm_allowed(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    mat = svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    assert any(c.get("missing_ref") for c in mat["cards"]["characters"] + mat["cards"]["scenes"])
    passed = svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert passed["gate"]["locked"] is True
    warns = [w for w in (passed.get("warnings") or []) if w.get("code") == "missing_ref"]
    assert warns
    assert any(WEAK_BINDING_MESSAGE in (w.get("message") or "") for w in warns)
    assert passed["usable_for_n4"] is False
    assert passed["cards"]["usable_for_n4"] is False


def test_usable_for_n4_true_only_with_refs_and_g3(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    for card in rec["n3"]["cards"]["characters"] + rec["n3"]["cards"]["scenes"]:
        path = data_dir / "refs" / f"{card['id']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ref-bytes")
        card["refs"] = [{"path": str(path), "md5": "abc", "role": "face", "missing_file": False}]
        card["missing_ref"] = False
        card["weak_binding"] = False
    svc._commit(rec)
    assert svc.get_gate_g3(pid, "EP01")["usable_for_n4"] is False  # G3 not locked
    passed = svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert passed["gate"]["locked"] is True
    # AIV-031: has_usable_ref / G3 pass must NOT imply usable_for_n4.
    assert passed["usable_for_n4"] is False
