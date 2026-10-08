"""Gaps 9–18: look cap / single SKU / Seedance stop / outputs / L reviews / spend.

ForcePass=never. L layers are not G gates. Empty Idempotency-Key is not a free retry.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama.biz import LOOK_ATTEMPT_CAP, SPEND_CAP
from aiv_drama.models import EpisodeCreate
from aiv_drama_n3.gold_sheet import LOOK_KIND, LOOK_ROLE
from aiv_drama_n3.models import N3GenerateLookRequest, N3MaterializeRequest, N3ThickenRequest
from aiv_drama_n3.seedream import SEEDREAM_SKU_PRIMARY
from tests.drama.helpers import lock_g2, lock_g3_usable, seed_project_episode
from tests.drama.test_n3_look_generate import _face, _sheet_card
from tests.drama.test_n4_api import _setup_g3_usable


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _prep_look_card(svc, pid) -> None:
    rec = svc._rec(pid, "EP01")
    gold = _sheet_card()
    rec["n3"]["cards"]["characters"][0]["appearance"] = gold["wardrobe"]
    rec["n3"]["cards"]["characters"][0]["immutable"] = gold["immutable"]
    rec["n3"]["cards"]["characters"][0]["height"] = gold["height"]
    svc._commit(rec)


def _fake_look_ok(**kwargs):
    dest = Path(kwargs["out_dir"])
    dest.mkdir(parents=True, exist_ok=True)
    prompt = dest / "CHAR-01-doubao-sheet-prompt.txt"
    prompt.write_text("p", encoding="utf-8")
    return {
        "ok": True,
        "node": "D-N3",
        "kind": LOOK_KIND,
        "role": LOOK_ROLE,
        "card_id": "CHAR-01",
        "aspect": "3:2",
        "size": "2048x1365",
        "sku_chain": [SEEDREAM_SKU_PRIMARY],
        "prompt_path": str(prompt),
        "prompt_md5": "a" * 32,
        "prompt_chars": 1,
        "prompt_adapter": None,
        "face_ref_path": str(kwargs["face_ref"]),
        "face_ref_md5": kwargs.get("expected_md5") or ("b" * 32),
        "sheet_path": str(dest / "CHAR-01-turnaround-sheet-3x2.jpg"),
        "sheet_md5": "c" * 32,
        "model": SEEDREAM_SKU_PRIMARY,
        "dry_run": False,
        "usable_for_n4": False,
        "attempts": [{"model": SEEDREAM_SKU_PRIMARY, "http": 200, "status": "ok", "image": True}],
    }


def _fake_look_fail(**_kwargs):
    raise AppError(502, "provider", "seedream failed", node="D-N3")


def _look_ready(svc, pid, tmp_path):
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    _prep_look_card(svc, pid)
    return _face(tmp_path)


def _register(client, pid, tmp_path, *, kind: str, payload: bytes, name: str = "art.bin"):
    path = tmp_path / name
    path.write_bytes(payload)
    md5 = hashlib.md5(payload).hexdigest()
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": kind, "path": str(path), "md5": md5, "bytes": len(payload), "actor": "eng"},
    )
    assert res.status_code == 200, res.text
    return md5, path


# ----- 9 look cap + single SKU + empty key -----------------------------------------


def test_look_cap_counts_failures_and_hash_change_does_not_reset(svc, tmp_path, monkeypatch):
    pid = seed_project_episode(svc)
    face = _look_ready(svc, pid, tmp_path)
    monkeypatch.setattr("aiv_drama_n3.ops.generate_gold_a_sheet", _fake_look_fail)
    first = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(face)},
        )
    )
    assert first.code == "provider"
    assert first.details["attempts_used"] == 1
    other = tmp_path / "other.jpg"
    other.write_bytes(b"\xff\xd8other-face")
    consent_ignored = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(other), user_consent=True, actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(other), "user_consent": True},
        )
    )
    assert consent_ignored.code == "redraw_needs_user"
    svc.record_redraw_consent(pid, "EP01", raw={"user": True, "actor": "viewer"})
    second = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(other), actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(other)},
        )
    )
    assert second.code == "provider"
    assert second.details["attempts_used"] == LOOK_ATTEMPT_CAP
    capped = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(face)},
        )
    )
    assert capped.code == "attempt_cap"
    assert capped.status_code == 409
    assert capped.details["attempts_used"] == 2


def test_look_empty_idempotency_key_is_not_a_free_retry(svc, tmp_path, monkeypatch):
    pid = seed_project_episode(svc)
    face = _look_ready(svc, pid, tmp_path)
    monkeypatch.setattr("aiv_drama_n3.ops.generate_gold_a_sheet", _fake_look_ok)
    first = svc.generate_n3_look(
        pid,
        "EP01",
        N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
        raw={"id": "CHAR-01", "face_ref": str(face)},
        idempotency_key="",
    )
    assert first["attempts_used"] == 1
    second = svc.generate_n3_look(
        pid,
        "EP01",
        N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
        raw={"id": "CHAR-01", "face_ref": str(face)},
        idempotency_key="   ",
    )
    assert second["attempts_used"] == 2
    third = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(face)},
            idempotency_key="",
        )
    )
    assert third.code == "attempt_cap"


def test_look_nonempty_idempotency_key_replays(svc, tmp_path, monkeypatch):
    pid = seed_project_episode(svc)
    face = _look_ready(svc, pid, tmp_path)
    hits = {"n": 0}

    def once(**kwargs):
        hits["n"] += 1
        return _fake_look_ok(**kwargs)

    monkeypatch.setattr("aiv_drama_n3.ops.generate_gold_a_sheet", once)
    a = svc.generate_n3_look(
        pid,
        "EP01",
        N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
        raw={"id": "CHAR-01", "face_ref": str(face)},
        idempotency_key="look-1",
    )
    b = svc.generate_n3_look(
        pid,
        "EP01",
        N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
        raw={"id": "CHAR-01", "face_ref": str(face)},
        idempotency_key="look-1",
    )
    assert a["attempts_used"] == b["attempts_used"] == 1
    assert hits["n"] == 1


def test_http_redraw_needs_user_and_retry_forbidden(client, tmp_path, monkeypatch):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize", json={"actor": "x"})
    _prep_look_card(svc, pid)
    face = _face(tmp_path)
    monkeypatch.setattr("aiv_drama_n3.ops.generate_gold_a_sheet", _fake_look_fail)
    url = f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look"
    first = client.post(url, json={"id": "CHAR-01", "face_ref": str(face), "actor": "eng"})
    assert first.status_code == 502
    assert first.json()["error"]["details"]["attempts_used"] == 1
    blocked = client.post(url, json={"id": "CHAR-01", "face_ref": str(face), "actor": "eng"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "redraw_needs_user"
    spoof = client.post(
        url, json={"id": "CHAR-01", "face_ref": str(face), "actor": "eng", "user_consent": True}
    )
    assert spoof.status_code == 409
    assert spoof.json()["error"]["code"] == "redraw_needs_user"
    retry = client.post(url, json={"id": "CHAR-01", "face_ref": str(face), "retry": True})
    assert retry.status_code == 400
    assert retry.json()["error"]["code"] == "validation"
    force = client.post(url, json={"id": "CHAR-01", "face_ref": str(face), "force_pass": True})
    assert force.status_code == 400
    assert force.json()["error"]["code"] == "force_pass_forbidden"
    recorded = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/redraw-consent",
        json={"user": True, "actor": "viewer"},
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["recorded"] is True
    second = client.post(url, json={"id": "CHAR-01", "face_ref": str(face), "actor": "eng"})
    assert second.status_code == 502
    assert second.json()["error"]["details"]["attempts_used"] == 2


# ----- 10 Seedance one-shot + episode_stopped --------------------------------------


def test_segment_video_episode_stopped_and_already_attempted(client, monkeypatch):
    pid = _setup_g3_usable(client)
    asm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"tool_profile": "seedance_2", "actor": "yangzhou"},
    )
    assert asm.status_code == 200, asm.text
    lines = asm.json()["lines"]
    assert lines
    a = lines[0]
    b = lines[1] if len(lines) > 1 else {"shot_id": "S99", "prompt": a.get("prompt") or ""}
    sha_a = hashlib.sha256((a.get("prompt") or "").encode("utf-8")).hexdigest()
    sha_b = hashlib.sha256((b.get("prompt") or "").encode("utf-8")).hexdigest()

    def fail_provider(**_k):
        raise AppError(502, "provider", "seedance failed", node="D-N4")

    monkeypatch.setattr("aiv_drama.biz.generate_seedance_segment", fail_provider)
    first = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{a['shot_id']}/video",
        json={"prompt_sha256": sha_a, "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert first.status_code == 502
    stopped = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{b['shot_id']}/video",
        json={"prompt_sha256": sha_b, "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert stopped.status_code == 409
    assert stopped.json()["error"]["code"] == "episode_stopped"
    again = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{a['shot_id']}/video",
        json={"prompt_sha256": sha_a, "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_attempted"


def test_segment_video_success_attempt_is_one(client, monkeypatch, tmp_path):
    pid = _setup_g3_usable(client)
    asm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"tool_profile": "seedance_2", "actor": "yangzhou"},
    )
    line = asm.json()["lines"][0]
    sha = hashlib.sha256((line.get("prompt") or "").encode("utf-8")).hexdigest()

    def ok(**_k):
        return {"bytes": b"fake-mp4", "output_md5": hashlib.md5(b"fake-mp4").hexdigest(), "provider_request_id": "req-1"}

    monkeypatch.setattr("aiv_drama.biz.generate_seedance_segment", ok)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{line['shot_id']}/video",
        json={"prompt_sha256": sha, "tool_profile": "seedance_2", "actor": "gen"},
        headers={"Idempotency-Key": "seg-1"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "succeeded"
    assert body["attempt"] == 1
    replay = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{line['shot_id']}/video",
        json={"prompt_sha256": sha, "tool_profile": "seedance_2", "actor": "gen"},
        headers={"Idempotency-Key": "seg-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["attempt"] == 1
    second = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{line['shot_id']}/video",
        json={"prompt_sha256": sha, "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_attempted"


# ----- 11–16 outputs / rough-cut / seams / subtitles / bed / tts -------------------


def test_output_md5_register_and_duplicate(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    payload = b"sheet-bytes"
    md5, _path = _register(client, pid, tmp_path, kind="image", payload=payload)
    again = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(_path), "md5": md5, "bytes": len(payload), "actor": "eng"},
    )
    assert again.status_code == 200
    assert again.json()["md5"] == md5
    assert again.json()["output_id"] == f"image:{md5}"
    bad = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(_path), "md5": "0" * 32, "bytes": len(payload)},
    )
    assert bad.status_code == 409
    assert bad.json()["error"]["code"] == "md5_mismatch"
    extra = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(_path), "md5": md5, "bytes": len(payload), "mystery": 1},
    )
    assert extra.status_code == 422


def test_rough_cut_seams_subtitles_bed_voice(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    video_md5, _ = _register(client, pid, tmp_path, kind="segment_video", payload=b"vid", name="seg.mp4")
    stem_md5, _ = _register(client, pid, tmp_path, kind="audio_stem", payload=b"cc0-stem", name="stem.bin")
    take_md5, _ = _register(client, pid, tmp_path, kind="tts_line", payload=b"tts-take", name="take.bin")
    audio_md5 = hashlib.md5(b"mix").hexdigest()
    cut = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={
            "version": "rc1",
            "video_stream_md5": video_md5,
            "audio_md5": audio_md5,
            "actor": "eng",
        },
    )
    assert cut.status_code == 200, cut.text
    assert cut.json()["version"] == "rc1"
    assert cut.json()["video_stream_md5"] == video_md5
    overwrite = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={
            "version": "rc1",
            "video_stream_md5": video_md5,
            "audio_md5": hashlib.md5(b"other").hexdigest(),
            "actor": "eng",
        },
    )
    assert overwrite.status_code == 409
    assert overwrite.json()["error"]["code"] == "version_exists"
    ruleset = "1" * 32
    seams = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/rc1/seams",
        json={"ruleset_md5": ruleset, "actor": "eng"},
    )
    assert seams.status_code == 200, seams.text
    assert "seams" in seams.json()
    assert isinstance(seams.json()["pass"], bool)
    by_metric = {row["metric"]: row["value"] for row in seams.json()["seams"]}
    folded_join = (int(ruleset[:8], 16) % 50) / 1000.0
    folded_loud = (int(ruleset[:8], 16) % 20) / 10.0
    assert by_metric["join_delta_s"] != folded_join
    assert by_metric["loudness_jump_db"] != folded_loud
    assert not (by_metric["join_delta_s"] == 0.0 and by_metric["loudness_jump_db"] == 0.0)
    other_md5, _ = _register(
        client, pid, tmp_path, kind="segment_video", payload=bytes(range(256)) * 8, name="seg2.mp4"
    )
    cut2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={
            "version": "rc2",
            "video_stream_md5": other_md5,
            "audio_md5": audio_md5,
            "actor": "eng",
        },
    )
    assert cut2.status_code == 200, cut2.text
    seams2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/rc2/seams",
        json={"ruleset_md5": ruleset, "actor": "eng"},
    )
    assert seams2.status_code == 200, seams2.text
    by_metric2 = {row["metric"]: row["value"] for row in seams2.json()["seams"]}
    assert by_metric2 != by_metric
    mismatch = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/rc1/seams",
        json={"ruleset_md5": "2" * 32, "actor": "eng"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "ruleset_mismatch"
    late = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/subtitles/v1",
        json={
            "body_sha256": "a" * 64,
            "in_points": [{"line_no": 1, "in_s": 2.0, "out_s": 1.0}],
            "actor": "sub",
        },
    )
    assert late.status_code == 400
    assert late.json()["error"]["code"] == "validation"
    sub = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/subtitles/v1",
        json={
            "body_sha256": "a" * 64,
            "in_points": [{"line_no": 1, "in_s": 0.2, "out_s": 1.4}],
            "actor": "sub",
        },
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["line_count"] == 1
    clash = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/subtitles/v1",
        json={"body_sha256": "b" * 64, "in_points": [{"line_no": 1, "in_s": 0.2, "out_s": 1.4}]},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "version_exists"
    missing_src = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/bed",
        json={
            "version": "bed1",
            "spec_md5": "3" * 32,
            "sources": [{"source_id": "s1", "md5": "9" * 32, "license": "CC0"}],
            "actor": "eng",
        },
    )
    assert missing_src.status_code == 422
    assert missing_src.json()["error"]["code"] == "source_unregistered"
    bed = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/bed",
        json={
            "version": "bed1",
            "spec_md5": "3" * 32,
            "sources": [{"source_id": "s1", "md5": stem_md5, "license": "CC0"}],
            "actor": "eng",
        },
    )
    assert bed.status_code == 200, bed.text
    assert bed.json()["sample_rate"] == 48000
    assert bed.json()["channels"] == 2
    unreg = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/voice",
        json={"version": "vox1", "line_no": 1, "take_md5": "8" * 32, "in_s": 0.4, "actor": "eng"},
    )
    assert unreg.status_code == 409
    assert unreg.json()["error"]["code"] == "take_unregistered"
    voice = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/voice",
        json={"version": "vox1", "line_no": 1, "take_md5": take_md5, "in_s": 0.4, "actor": "eng"},
    )
    assert voice.status_code == 200, voice.text
    assert voice.json()["placed_md5"]
    assert "synthesized" not in voice.json() or voice.json().get("synthesized") is False


def test_seams_refuse_when_rough_cut_file_missing(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    video_md5, _ = _register(client, pid, tmp_path, kind="segment_video", payload=b"vid", name="seg.mp4")
    audio_md5 = hashlib.md5(b"mix").hexdigest()
    cut = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={"version": "rc-miss", "video_stream_md5": video_md5, "audio_md5": audio_md5, "actor": "eng"},
    )
    assert cut.status_code == 200, cut.text
    path = Path(svc._rec(pid, "EP01")["rough_cuts"]["rc-miss"]["path"])
    assert path.is_file()
    path.unlink()
    missing = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/rc-miss/seams",
        json={"ruleset_md5": "3" * 32, "actor": "eng"},
    )
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "subject_mismatch"


# ----- 17 L reviews + four open-item states ----------------------------------------


def test_reviews_four_states_and_not_mapped_to_g_gates(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    lock_g3_usable(svc, pid, svc.settings.data_dir)
    g3_before = client.get(f"/api/v0/projects/{pid}/episodes/EP01/gates/g3").json()
    assert g3_before["gate"]["locked"] is True
    subject, _ = _register(client, pid, tmp_path, kind="rough_cut", payload=b"cut", name="cut.bin")
    force = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L1", "subject_md5": subject, "verdict": "fail", "actor": "rev", "force_pass": True},
    )
    assert force.status_code == 400
    assert force.json()["error"]["code"] == "force_pass_forbidden"
    l1 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L1", "subject_md5": subject, "verdict": "fail", "actor": "rev"},
    )
    assert l1.status_code == 200, l1.text
    review_id = l1.json()["review_id"]
    states = ("blocks_l2", "waiting_on_user", "non_blocking")
    for idx, state in enumerate(states, start=1):
        item = client.post(
            f"/api/v0/projects/{pid}/episodes/EP01/open-items",
            json={
                "review_id": review_id,
                "item_no": idx,
                "state": state,
                "owner": "rev",
                "text": f"item-{state}",
            },
        )
        assert item.status_code == 200, item.text
        assert item.json()["state"] == state
    create_closed = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items",
        json={
            "review_id": review_id,
            "item_no": 4,
            "state": "closed",
            "owner": "rev",
            "text": "item-closed",
        },
    )
    assert create_closed.status_code == 409
    assert create_closed.json()["error"]["code"] == "close_conditions"
    blocking_bool = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items",
        json={
            "review_id": review_id,
            "item_no": 9,
            "state": "non_blocking",
            "owner": "rev",
            "text": "nope",
            "blocking": True,
        },
    )
    assert blocking_bool.status_code == 400
    l2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L2", "subject_md5": subject, "verdict": "pass", "actor": "rev2"},
    )
    assert l2.status_code == 409
    assert l2.json()["error"]["code"] == "blocks_l2_open"
    worker_close = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/2/close",
        json={"actor": "worker", "conclusion": "fixed_by_worker", "file_md5": subject},
    )
    assert worker_close.status_code == 409
    assert worker_close.json()["error"]["code"] == "waiting_on_user"
    spoof_prefix = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/2/close",
        json={"actor": "worker", "conclusion": "user:wardrobe_accepted", "file_md5": subject},
    )
    assert spoof_prefix.status_code == 409
    assert spoof_prefix.json()["error"]["code"] == "waiting_on_user"
    worker_file = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/2/conclusion",
        json={"conclusion": "wardrobe_accepted", "actor": "worker", "user": False},
    )
    assert worker_file.status_code == 409
    assert worker_file.json()["error"]["code"] == "waiting_on_user"
    recorded = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/2/conclusion",
        json={"conclusion": "wardrobe_accepted", "actor": "viewer", "user": True},
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["state"] == "waiting_on_user"
    worker_proxy = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/2/close",
        json={"actor": "worker", "conclusion": "wardrobe_accepted", "file_md5": subject},
    )
    assert worker_proxy.status_code == 409
    assert worker_proxy.json()["error"]["code"] == "waiting_on_user"
    user_close = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/2/close",
        json={"actor": "viewer", "conclusion": "wardrobe_accepted", "file_md5": subject},
    )
    assert user_close.status_code == 200, user_close.text
    assert user_close.json()["state"] == "closed"
    casual_l2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/1/close",
        json={"actor": "rev", "conclusion": "fixed", "file_md5": subject},
    )
    assert casual_l2.status_code == 409
    assert casual_l2.json()["error"]["code"] == "close_conditions"
    casual_nb = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/3/close",
        json={"actor": "rev", "conclusion": "note", "file_md5": subject},
    )
    assert casual_nb.status_code == 409
    assert casual_nb.json()["error"]["code"] == "close_conditions"
    owner_l2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/1/conclusion",
        json={"conclusion": "fixed", "actor": "rev"},
    )
    assert owner_l2.status_code == 200, owner_l2.text
    worker_l2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/1/close",
        json={"actor": "worker", "conclusion": "fixed", "file_md5": subject},
    )
    assert worker_l2.status_code == 409
    assert worker_l2.json()["error"]["code"] == "close_conditions"
    close_l2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/1/close",
        json={"actor": "rev", "conclusion": "fixed", "file_md5": subject},
    )
    assert close_l2.status_code == 200, close_l2.text
    assert close_l2.json()["state"] == "closed"
    owner_nb = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/3/conclusion",
        json={"conclusion": "note", "actor": "rev"},
    )
    assert owner_nb.status_code == 200, owner_nb.text
    worker_nb = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/3/close",
        json={"actor": "worker", "conclusion": "note", "file_md5": subject},
    )
    assert worker_nb.status_code == 409
    assert worker_nb.json()["error"]["code"] == "close_conditions"
    close_nb = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/3/close",
        json={"actor": "rev", "conclusion": "note", "file_md5": subject},
    )
    assert close_nb.status_code == 200, close_nb.text
    assert close_nb.json()["state"] == "closed"
    g3_after = client.get(f"/api/v0/projects/{pid}/episodes/EP01/gates/g3").json()
    assert g3_after["gate"]["locked"] is True
    assert g3_after["gate"]["last_decision"] == g3_before["gate"]["last_decision"]
    g1b = client.get(f"/api/v0/projects/{pid}/episodes/EP01/gates/g1b").json()
    assert g1b["gate"]["locked"] is True


# ----- 18 spend ceiling + redraw_needs_user already covered ------------------------


def test_spend_over_cap_and_blocked_look(svc, tmp_path, monkeypatch):
    pid = seed_project_episode(svc)
    face = _look_ready(svc, pid, tmp_path)
    monkeypatch.setattr("aiv_drama_n3.ops.generate_gold_a_sheet", _fake_look_ok)
    first = svc.add_cost_entry(
        pid,
        raw={"provider": "ark", "operation": "seedream", "amount": 40, "currency": "CNY", "ref_id": "c1", "actor": "gen"},
    )
    assert first["spent"] == 40
    assert first["cap"] == SPEND_CAP
    replay = svc.add_cost_entry(
        pid,
        raw={"provider": "ark", "operation": "seedream", "amount": 40, "ref_id": "c1", "actor": "gen"},
    )
    assert replay["spent"] == 40
    over = _err(
        lambda: svc.add_cost_entry(
            pid,
            raw={"provider": "ark", "operation": "seedream", "amount": 30, "ref_id": "c2", "actor": "gen"},
        )
    )
    assert over.code == "over_cap"
    svc.add_cost_entry(
        pid,
        raw={"provider": "ark", "operation": "seedream", "amount": 20, "ref_id": "c3", "actor": "gen"},
    )
    blocked = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(face)},
        )
    )
    assert blocked.code == "over_cap"
    got = svc.get_project_cost(pid)
    assert got["blocked"] is True
    assert got["cap"] == SPEND_CAP


def test_thicken_refuses_when_spend_blocked_without_model(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    svc.add_cost_entry(
        pid,
        raw={
            "provider": "ark",
            "operation": "llm",
            "amount": 60,
            "currency": "CNY",
            "ref_id": "full",
            "actor": "gen",
        },
    )
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("thicken_cards must not run when spend is blocked")

    monkeypatch.setattr("aiv_drama_n3.ops.thicken_cards", boom)
    blocked = _err(
        lambda: svc.thicken_n3_cards(
            pid,
            "EP01",
            N3ThickenRequest(provider="llm", actor="eng"),
            raw={"provider": "llm", "actor": "eng"},
        )
    )
    assert blocked.code == "over_cap"
    assert called["n"] == 0


def test_spend_cap_is_one_project_bucket_not_per_episode(svc, tmp_path, monkeypatch):
    pid = seed_project_episode(svc)
    face = _look_ready(svc, pid, tmp_path)
    svc.create_episode(pid, EpisodeCreate(episode_id="EP02", pipeline_profile="drama", title="第二集"))
    first = svc.add_cost_entry(
        pid,
        raw={
            "provider": "ark",
            "operation": "seedream",
            "amount": 40,
            "currency": "CNY",
            "ref_id": "e1",
            "actor": "gen",
            "episode_id": "EP01",
        },
    )
    assert first["spent"] == 40
    assert first["remaining"] == 20
    second = svc.add_cost_entry(
        pid,
        raw={
            "provider": "ark",
            "operation": "seedance",
            "amount": 20,
            "currency": "CNY",
            "ref_id": "e2",
            "actor": "gen",
            "episode_id": "EP02",
        },
    )
    assert second["spent"] == 60
    assert second["blocked"] is True
    over = _err(
        lambda: svc.add_cost_entry(
            pid,
            raw={
                "provider": "ark",
                "operation": "tts",
                "amount": 1,
                "ref_id": "e3",
                "actor": "gen",
                "episode_id": "EP02",
            },
        )
    )
    assert over.code == "over_cap"
    monkeypatch.setattr("aiv_drama_n3.ops.generate_gold_a_sheet", _fake_look_ok)
    blocked = _err(
        lambda: svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face), actor="eng"),
            raw={"id": "CHAR-01", "face_ref": str(face)},
        )
    )
    assert blocked.code == "over_cap"
    got = svc.get_project_cost(pid)
    assert got["spent"] == 60
    assert got["cap"] == SPEND_CAP
    assert got["blocked"] is True
    rec01 = svc._rec(pid, "EP01")
    rec02 = svc._rec(pid, "EP02")
    assert rec01.get("cost") in (None, {})
    assert rec02.get("cost") in (None, {})


def test_http_force_pass_and_openapi_biz(client):
    spec = client.get("/openapi/drama-biz.v0.yaml")
    assert spec.status_code == 200
    text = spec.text
    assert "episode_stopped" in text
    assert "waiting_on_user" in text
    assert "redraw_needs_user" in text
    assert "close_conditions" in text
    assert "/redraw-consent" in text
    assert "once per project" in text
    assert "/segments/{segment_id}/video" in text
    assert "force_pass_forbidden" in text
    catalog = client.get("/api/v0/drama/error-catalog").json()
    assert "attempt_cap" in catalog["messages"]
    assert "redraw_needs_user" in catalog["messages"]
