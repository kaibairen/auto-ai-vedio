"""Gaps 9–18 against the signed open-API design. ForcePass=never. L ≠ G."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.gold_sheet import load_look_card
from aiv_drama_n3.models import N3GenerateLookRequest, N3MaterializeRequest
from aiv_drama_n3.seedream import SEEDREAM_SKU_PRIMARY
from aiv_drama_post.seams import ruleset_md5
from tests.drama.helpers import lock_g2, seed_project_episode
from tests.drama.test_n3_look_generate import GOLD_CARD, _Resp, _face, _sheet_card
from tests.drama.test_n4_api import _setup_g3_usable


def _digest(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _prep_look_card(svc, pid: str) -> None:
    rec = svc._rec(pid, "EP01")
    gold = _sheet_card()
    rec["n3"]["cards"]["characters"][0]["appearance"] = gold["wardrobe"]
    rec["n3"]["cards"]["characters"][0]["immutable"] = gold["immutable"]
    rec["n3"]["cards"]["characters"][0]["height"] = gold["height"]
    svc._commit(rec)


def _look_ready(svc, pid: str) -> None:
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    _prep_look_card(svc, pid)


def _fail_post(_url, headers=None, json=None, timeout=None):  # noqa: A002
    assert json["model"] == SEEDREAM_SKU_PRIMARY
    return _Resp(400, text="model not found")


def test_look_two_failures_then_attempt_cap_and_one_sku(svc, tmp_path):
    svc.settings = replace(svc.settings, ark_api_key="test-key-not-secret")
    pid = seed_project_episode(svc)
    _look_ready(svc, pid)
    face_a = _face(tmp_path, b"\xff\xd8face-a")
    face_b = tmp_path / "CHAR-01-user-ref-b.jpg"
    face_b.write_bytes(b"\xff\xd8face-b")
    posts: list[str] = []

    def counting_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        posts.append(json["model"])
        return _fail_post(url, headers, json, timeout)

    first = None
    try:
        svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face_a), actor="gen"),
            raw={"id": "CHAR-01", "face_ref": str(face_a), "actor": "gen"},
            post=counting_post,
            get=lambda *a, **k: _Resp(200, content=b"x"),
        )
    except AppError as exc:
        first = exc
    assert first is not None
    assert first.code == "provider"
    assert first.details["attempts_used"] == 1
    assert posts == [SEEDREAM_SKU_PRIMARY]

    second_blocked = None
    try:
        svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face_b), actor="gen"),
            raw={"id": "CHAR-01", "face_ref": str(face_b), "actor": "gen"},
            post=counting_post,
            get=lambda *a, **k: _Resp(200, content=b"x"),
        )
    except AppError as exc:
        second_blocked = exc
    assert second_blocked is not None
    assert second_blocked.code == "redraw_needs_user"
    assert posts == [SEEDREAM_SKU_PRIMARY]

    second = None
    try:
        svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face_b), actor="gen", user_consent=True),
            raw={"id": "CHAR-01", "face_ref": str(face_b), "actor": "gen", "user_consent": True},
            post=counting_post,
            get=lambda *a, **k: _Resp(200, content=b"x"),
        )
    except AppError as exc:
        second = exc
    assert second is not None
    assert second.code == "provider"
    assert second.details["attempts_used"] == 2
    assert posts == [SEEDREAM_SKU_PRIMARY, SEEDREAM_SKU_PRIMARY]

    cap = None
    try:
        svc.generate_n3_look(
            pid,
            "EP01",
            N3GenerateLookRequest(id="CHAR-01", face_ref=str(face_b), actor="gen", user_consent=True),
            raw={"id": "CHAR-01", "face_ref": str(face_b), "actor": "gen", "user_consent": True},
            post=counting_post,
            get=lambda *a, **k: _Resp(200, content=b"x"),
        )
    except AppError as exc:
        cap = exc
    assert cap is not None
    assert cap.code == "attempt_cap"
    assert cap.status_code == 409
    assert cap.details["attempts_used"] == 2
    assert posts == [SEEDREAM_SKU_PRIMARY, SEEDREAM_SKU_PRIMARY]


def test_http_look_attempt_cap_and_force_pass(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    _look_ready(svc, pid)
    face = _face(tmp_path)

    def boom(*_a, **_k):
        raise AppError(502, "provider", "ark fail", attempts=[{"model": SEEDREAM_SKU_PRIMARY}])

    import aiv_drama_n3.ops as n3_ops

    orig = n3_ops.generate_gold_a_sheet
    n3_ops.generate_gold_a_sheet = boom
    try:
        one = client.post(
            f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
            json={"id": "CHAR-01", "face_ref": str(face), "actor": "gen"},
        )
        assert one.status_code == 502
        assert one.json()["error"]["details"]["attempts_used"] == 1
        two = client.post(
            f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
            json={"id": "CHAR-01", "face_ref": str(face), "actor": "gen", "user_consent": True},
        )
        assert two.status_code == 502
        assert two.json()["error"]["details"]["attempts_used"] == 2
        three = client.post(
            f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
            json={"id": "CHAR-01", "face_ref": str(face), "actor": "gen", "user_consent": True},
        )
        assert three.status_code == 409
        assert three.json()["error"]["code"] == "attempt_cap"
        assert three.json()["error"]["details"]["attempts_used"] == 2
    finally:
        n3_ops.generate_gold_a_sheet = orig

    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
        json={"id": "CHAR-01", "face_ref": str(face), "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"


def _assemble(client) -> tuple[str, list[dict]]:
    pid = _setup_g3_usable(client)
    asm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"tool_profile": "seedance_2", "actor": "yangzhou"},
    )
    assert asm.status_code == 200, asm.text
    lines = asm.json()["lines"]
    assert len(lines) >= 2
    return pid, lines


def test_segment_video_once_and_episode_stopped(client):
    pid, lines = _assemble(client)
    svc = client.app.state.service
    a, b = lines[0], lines[1]
    first = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{a['shot_id']}/video",
        json={"prompt_sha256": a["fingerprint"], "ref_md5s": [], "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["attempt"] == 1
    assert first.json()["status"] == "succeeded"
    again = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{a['shot_id']}/video",
        json={"prompt_sha256": a["fingerprint"], "ref_md5s": [], "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_attempted"

    def fail_hook(**_k):
        return {
            "status": "failed",
            "output_md5": None,
            "output_path": None,
            "provider_request_id": "fail-1",
        }

    svc.seedance_hook = fail_hook
    # new project so the first success does not hide episode_stopped
    pid2, lines2 = _assemble(client)
    svc2 = client.app.state.service
    svc2.seedance_hook = fail_hook
    x, y = lines2[0], lines2[1]
    failed = client.post(
        f"/api/v0/projects/{pid2}/episodes/EP01/segments/{x['shot_id']}/video",
        json={"prompt_sha256": x["fingerprint"], "ref_md5s": [], "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    stopped = client.post(
        f"/api/v0/projects/{pid2}/episodes/EP01/segments/{y['shot_id']}/video",
        json={
            "prompt_sha256": y["fingerprint"],
            "ref_md5s": [],
            "tool_profile": "seedance_2",
            "actor": "gen",
            "user_consent": True,
        },
    )
    assert stopped.status_code == 409
    assert stopped.json()["error"]["code"] == "episode_stopped"


def test_segment_video_prompt_mismatch_upstream_and_force(client):
    pid, lines = _assemble(client)
    shot = lines[0]["shot_id"]
    bad = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{shot}/video",
        json={"prompt_sha256": "0" * 64, "ref_md5s": [], "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert bad.status_code == 409
    assert bad.json()["error"]["code"] == "prompt_mismatch"
    force = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/{shot}/video",
        json={
            "prompt_sha256": lines[0]["fingerprint"],
            "ref_md5s": [],
            "tool_profile": "seedance_2",
            "force": True,
        },
    )
    assert force.status_code == 400
    assert force.json()["error"]["code"] == "force_pass_forbidden"
    early = client.post(
        "/api/v0/projects/proj_99/episodes/EP01/segments/S01/video",
        json={"prompt_sha256": "abc", "ref_md5s": [], "tool_profile": "seedance_2"},
    )
    assert early.status_code == 404


def test_segment_video_upstream_unlocked(client):
    from tests.drama.helpers import seed_project_episode as seed

    svc = client.app.state.service
    pid = seed(svc)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/segments/S01/video",
        json={"prompt_sha256": "abc", "ref_md5s": [], "tool_profile": "seedance_2", "actor": "gen"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "upstream_unlocked"


def test_outputs_md5_and_duplicate(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    data = b"output-bytes-1"
    path = _write(tmp_path / "out.bin", data)
    digest = _digest(data)
    ok = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(path), "md5": digest, "bytes": len(data), "actor": "eng"},
    )
    assert ok.status_code == 200, ok.text
    first_id = ok.json()["output_id"]
    dup = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(path), "md5": digest, "bytes": len(data), "actor": "eng"},
    )
    assert dup.status_code == 200
    assert dup.json()["output_id"] == first_id
    mismatch = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(path), "md5": "0" * 32, "bytes": len(data), "actor": "eng"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "md5_mismatch"


def test_rough_cut_stream_lock_and_version(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    video = _write(tmp_path / "v.bin", b"video-stream")
    video_md5 = _digest(b"video-stream")
    other = _write(tmp_path / "v2.bin", b"video-stream-2")
    other_md5 = _digest(b"video-stream-2")
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "segment_video", "path": str(video), "md5": video_md5, "bytes": 12, "actor": "eng"},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "segment_video", "path": str(other), "md5": other_md5, "bytes": 14, "actor": "eng"},
    )
    cut = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={"version": "rc1", "video_stream_md5": video_md5, "audio_md5": "a" * 32, "actor": "eng"},
    )
    assert cut.status_code == 200, cut.text
    same = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={"version": "rc1", "video_stream_md5": video_md5, "audio_md5": "a" * 32, "actor": "eng"},
    )
    assert same.status_code == 200
    exists = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={"version": "rc1", "video_stream_md5": video_md5, "audio_md5": "b" * 32, "actor": "eng"},
    )
    assert exists.status_code == 409
    assert exists.json()["error"]["code"] == "version_exists"
    mismatch = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={"version": "rc2", "video_stream_md5": other_md5, "audio_md5": "a" * 32, "actor": "eng"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "video_stream_mismatch"


def test_seams_ruleset_and_missing_version(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    video = _write(tmp_path / "v.bin", b"video-stream")
    video_md5 = _digest(b"video-stream")
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "segment_video", "path": str(video), "md5": video_md5, "bytes": 12, "actor": "eng"},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts",
        json={"version": "rc1", "video_stream_md5": video_md5, "audio_md5": "a" * 32, "actor": "eng"},
    )
    missing = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/nope/seams",
        json={"ruleset_md5": ruleset_md5(), "actor": "eng"},
    )
    assert missing.status_code == 404
    bad = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/rc1/seams",
        json={"ruleset_md5": "0" * 32, "actor": "eng"},
    )
    assert bad.status_code == 409
    assert bad.json()["error"]["code"] == "ruleset_mismatch"
    ok = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/rough-cuts/rc1/seams",
        json={"ruleset_md5": ruleset_md5(), "actor": "eng"},
    )
    assert ok.status_code == 200, ok.text
    assert "seams" in ok.json()
    assert isinstance(ok.json()["pass"], bool)


def test_subtitles_validation_and_version(client):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    bad = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/subtitles/s1",
        json={"body_sha256": "aa", "in_points": [{"line_no": 1, "in_s": 2.0, "out_s": 1.0}], "actor": "sub"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "validation"
    ok = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/subtitles/s1",
        json={"body_sha256": "bb", "in_points": [{"line_no": 1, "in_s": 0.0, "out_s": 1.2}], "actor": "sub"},
    )
    assert ok.status_code == 200
    assert ok.json()["line_count"] == 1
    clash = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/subtitles/s1",
        json={"body_sha256": "cc", "in_points": [{"line_no": 1, "in_s": 0.0, "out_s": 1.2}], "actor": "sub"},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "version_exists"


def test_audio_bed_and_voice(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    src = _write(tmp_path / "cc0.bin", b"cc0-audio")
    src_md5 = _digest(b"cc0-audio")
    take = _write(tmp_path / "take.bin", b"tts-take")
    take_md5 = _digest(b"tts-take")
    missing = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/bed",
        json={
            "version": "bed1",
            "spec_md5": "s" * 32,
            "sources": [{"source_id": "s1", "md5": src_md5, "license": "CC0"}],
            "actor": "eng",
        },
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "source_unregistered"
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "audio_stem", "path": str(src), "md5": src_md5, "bytes": 9, "actor": "eng"},
    )
    bed = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/bed",
        json={
            "version": "bed1",
            "spec_md5": "s" * 32,
            "sources": [{"source_id": "s1", "md5": src_md5, "license": "CC0"}],
            "actor": "eng",
        },
    )
    assert bed.status_code == 200, bed.text
    assert bed.json()["sample_rate"] == 48000
    voice_miss = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/voice",
        json={"version": "v1", "line_no": 1, "take_md5": take_md5, "in_s": 0.4, "actor": "eng"},
    )
    assert voice_miss.status_code == 409
    assert voice_miss.json()["error"]["code"] == "take_unregistered"
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "tts_line", "path": str(take), "md5": take_md5, "bytes": 8, "actor": "eng"},
    )
    voice = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/audio/voice",
        json={"version": "v1", "line_no": 1, "take_md5": take_md5, "in_s": 0.4, "actor": "eng"},
    )
    assert voice.status_code == 200, voice.text
    assert voice.json()["placed_md5"]


def test_reviews_four_states_and_not_g_gates(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    blob = _write(tmp_path / "cut.bin", b"reviewed")
    digest = _digest(b"reviewed")
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "rough_cut", "path": str(blob), "md5": digest, "bytes": 8, "actor": "eng"},
    )
    g3_before = svc._rec(pid, "EP01")["gate_g3"]
    miss = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L1", "subject_md5": "0" * 32, "verdict": "pass", "actor": "rev"},
    )
    assert miss.status_code == 409
    assert miss.json()["error"]["code"] == "subject_mismatch"
    r1 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L1", "subject_md5": digest, "verdict": "conditional", "actor": "rev"},
    )
    assert r1.status_code == 200, r1.text
    review_id = r1.json()["review_id"]
    item = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items",
        json={
            "review_id": review_id,
            "item_no": 1,
            "state": "waiting_on_user",
            "owner": "user",
            "text": "服装接受",
        },
    )
    assert item.status_code == 200
    worker = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/1/close",
        json={"actor": "worker", "conclusion": "closed by engineering", "file_md5": digest},
    )
    assert worker.status_code == 409
    assert worker.json()["error"]["code"] == "waiting_on_user"
    user = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items/1/close",
        json={"actor": "worker", "conclusion": "user:服装接受", "file_md5": digest},
    )
    assert user.status_code == 200
    assert user.json()["state"] == "closed"
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/open-items",
        json={"review_id": review_id, "item_no": 2, "state": "blocks_l2", "owner": "rev", "text": "seam"},
    )
    l2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L2", "subject_md5": digest, "verdict": "pass", "actor": "rev"},
    )
    assert l2.status_code == 409
    assert l2.json()["error"]["code"] == "blocks_l2_open"
    force = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/reviews",
        json={"level": "L3", "subject_md5": digest, "verdict": "pass", "actor": "rev", "force_pass": True},
    )
    assert force.status_code == 400
    assert force.json()["error"]["code"] == "force_pass_forbidden"
    g3_after = svc._rec(pid, "EP01")["gate_g3"]
    assert g3_after == g3_before


def test_cost_over_cap_and_redraw_consent_blocks_generate(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    snap = client.get(f"/api/v0/projects/{pid}/cost")
    assert snap.status_code == 200
    assert snap.json()["cap"] == 60
    assert snap.json()["blocked"] is False
    over = client.post(
        f"/api/v0/projects/{pid}/cost/entries",
        json={"provider": "ark", "operation": "seedream", "amount": 70, "currency": "CNY", "ref_id": "r-over", "actor": "gen"},
    )
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "over_cap"
    after = client.get(f"/api/v0/projects/{pid}/cost").json()
    assert after["spent"] == 0
    _look_ready(svc, pid)
    first = client.post(
        f"/api/v0/projects/{pid}/cost/entries",
        json={"provider": "ark", "operation": "seedream", "amount": 60, "currency": "CNY", "ref_id": "r1", "actor": "gen"},
    )
    assert first.status_code == 200
    assert first.json()["blocked"] is True
    replay = client.post(
        f"/api/v0/projects/{pid}/cost/entries",
        json={"provider": "ark", "operation": "seedream", "amount": 60, "currency": "CNY", "ref_id": "r1", "actor": "gen"},
    )
    assert replay.status_code == 200
    assert replay.json()["spent"] == 60
    face = _face(tmp_path)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("provider must not run when blocked")

    import aiv_drama_n3.ops as n3_ops

    orig = n3_ops.generate_gold_a_sheet
    n3_ops.generate_gold_a_sheet = boom
    try:
        blocked = client.post(
            f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/generate-look",
            json={"id": "CHAR-01", "face_ref": str(face), "actor": "gen"},
        )
    finally:
        n3_ops.generate_gold_a_sheet = orig
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "over_cap"
    assert called["n"] == 0
    store = json.loads((svc.settings.data_dir / "store.json").read_text(encoding="utf-8"))
    dumped = json.dumps(store)
    assert "ARK_API_KEY" not in dumped
    assert "sk-" not in dumped


def test_force_on_cost_and_outputs(client, tmp_path):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    path = _write(tmp_path / "x.bin", b"xx")
    res = client.post(
        f"/api/v0/projects/{pid}/cost/entries",
        json={
            "provider": "ark",
            "operation": "llm",
            "amount": 1,
            "currency": "CNY",
            "ref_id": "x",
            "force_pass": True,
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"
    res2 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/outputs",
        json={"kind": "image", "path": str(path), "md5": _digest(b"xx"), "bytes": 2, "force": True},
    )
    assert res2.status_code == 400
    assert res2.json()["error"]["code"] == "force_pass_forbidden"


def test_gold_card_fixture_still_loads():
    assert load_look_card(GOLD_CARD)["id"] == "CHAR-01"
