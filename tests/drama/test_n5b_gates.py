"""AIV-036 N5b gate refusals + persist writers. Zero live Job POST."""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n5b.client import ArkSeedanceClient, parse_task_id, parse_task_status, parse_video_url, tasks_url
from aiv_drama_n5b.constants import SEEDANCE_SKU_PRIMARY
from aiv_drama_n5b.models import N5bSubmitRequest
from aiv_drama_n5b.persist import (
    clip_meta_path,
    clip_mp4_path,
    list_clip_inventory,
    md5_bytes,
    write_clip_bytes,
    write_clip_meta,
)
from tests.drama.helpers import (
    sample_n5b_line,
    seed_project_episode,
    stamp_g4_locked,
    write_n5b_jsonl,
)


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_submit_g4_required(svc):
    pid = seed_project_episode(svc)
    write_n5b_jsonl(svc, pid, [sample_n5b_line()])
    exc = _err(lambda: svc.submit_n5b(pid, "EP01", N5bSubmitRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "g4_required"
    assert exc.details.get("posted") is False


def test_submit_live_job_forbidden_when_g4_locked(svc, monkeypatch):
    monkeypatch.delenv("AIV_N5B_ALLOW_LIVE_JOB", raising=False)
    pid = seed_project_episode(svc)
    write_n5b_jsonl(svc, pid, [sample_n5b_line(aspect="2.35:1")])
    stamp_g4_locked(svc, pid)
    calls = {"post": 0}

    def boom(*_a, **_k):
        calls["post"] += 1
        raise AssertionError("httpx.post must not run")

    monkeypatch.setattr("httpx.post", boom)
    exc = _err(lambda: svc.submit_n5b(pid, "EP01", N5bSubmitRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "live_job_forbidden"
    assert exc.details.get("posted") is False
    assert exc.details.get("dry_run") is True
    assert exc.details.get("mapped")
    assert exc.details["mapped"][0]["body"]["ratio"] == "21:9"
    assert calls["post"] == 0


def test_submit_impl_hold_even_when_flag_set(svc, monkeypatch):
    monkeypatch.setenv("AIV_N5B_ALLOW_LIVE_JOB", "1")
    # Recreate settings after env change
    from aiv_drama.config import Settings
    from aiv_drama.service import DramaService

    svc2 = DramaService(Settings.from_env())
    pid = seed_project_episode(svc2)
    write_n5b_jsonl(svc2, pid, [sample_n5b_line()])
    stamp_g4_locked(svc2, pid)
    posts = []

    def track(*_a, **_k):
        posts.append(True)
        raise AssertionError("must not POST")

    monkeypatch.setattr("httpx.post", track)
    exc = _err(lambda: svc2.submit_n5b(pid, "EP01", N5bSubmitRequest(actor="a"), raw={"actor": "a"}))
    assert exc.code == "n5b_impl_hold"
    assert exc.details.get("posted") is False
    assert posts == []


def test_mode_b_missing_face_does_not_block_submit_code(svc, monkeypatch):
    """CTO: Mode B look review must not block N5b skeleton."""
    monkeypatch.delenv("AIV_N5B_ALLOW_LIVE_JOB", raising=False)
    pid = seed_project_episode(svc)
    write_n5b_jsonl(svc, pid, [sample_n5b_line(ref=None)])
    stamp_g4_locked(svc, pid)
    rec = svc._rec(pid, "EP01")
    cards = ((rec.get("n3") or {}).get("cards") or {})
    for card in list(cards.get("characters") or []):
        card["refs"] = []
    svc._commit(rec)
    exc = _err(lambda: svc.submit_n5b(pid, "EP01", N5bSubmitRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.code == "live_job_forbidden"
    assert exc.code != "usable_for_n4_false"


def test_force_pass_forbidden_on_submit_and_g5(svc):
    pid = seed_project_episode(svc)
    stamp_g4_locked(svc, pid)
    exc = _err(
        lambda: svc.submit_n5b(
            pid, "EP01", N5bSubmitRequest(actor="yangzhou"), raw={"actor": "yangzhou", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"
    exc2 = _err(lambda: svc.confirm_gate_g5(pid, "EP01", {"decision": "pass", "actor": "yangzhou", "skip_gate": True}))
    assert exc2.status_code == 400
    assert exc2.code == "force_pass_forbidden"


def test_g5_rework_without_clips_and_pass_requires_real_pair(svc, data_dir):
    pid = seed_project_episode(svc)
    stamp_g4_locked(svc, pid)
    rework = svc.confirm_gate_g5(pid, "EP01", {"verdict": "rework", "actor": "yangzhou"})
    assert rework["gate"]["last_decision"] == "rework"
    assert rework["gate"]["locked"] is False
    exc = _err(lambda: svc.confirm_gate_g5(pid, "EP01", {"decision": "pass", "actor": "yangzhou"}))
    assert exc.code == "clips_required"
    ep_dir = Path(data_dir) / "projects" / pid / "episodes" / "EP01"
    payload = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
    written = write_clip_bytes(ep_dir, "S01", payload)
    write_clip_meta(
        ep_dir,
        "S01",
        {"SKU": SEEDANCE_SKU_PRIMARY, "job_id": "cgt-mock-1", "md5": written["md5"], "duration": 5, "ratio": "21:9"},
    )
    assert clip_mp4_path(ep_dir, "S01").is_file()
    assert clip_meta_path(ep_dir, "S01").is_file()
    inv = list_clip_inventory(ep_dir)
    assert inv[0]["complete"] is True
    passed = svc.confirm_gate_g5(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert passed["gate"]["locked"] is True
    assert passed["gate"]["last_decision"] == "pass"


def test_persist_refuses_empty_and_colorbar_markers(tmp_path):
    exc = _err(lambda: write_clip_bytes(tmp_path, "S01", b""))
    assert exc.status_code == 422
    fake = _err(lambda: write_clip_bytes(tmp_path, "S01", b"COLORBAR-smpte-placeholder"))
    assert fake.code == "fake_pixels_forbidden"
    assert not (tmp_path / "clips" / "S01.mp4").exists()
    exc_meta = _err(lambda: write_clip_meta(tmp_path, "S01", {"SKU": "x"}))
    assert exc_meta.status_code == 422


def test_client_mock_http_ok_no_network():
    posts = []
    gets = []

    def post(url, headers=None, json=None, timeout=None):
        posts.append({"url": url, "json": json, "auth": (headers or {}).get("Authorization")})
        return _Resp(200, {"id": "cgt-mock-ok"})

    def get(url, headers=None, timeout=None):
        gets.append(url)
        return _Resp(
            200,
            {"id": "cgt-mock-ok", "status": "succeeded", "content": {"video_url": "https://example.test/v.mp4"}},
        )

    client = ArkSeedanceClient(api_key="ark-test-key", allow_live=True, post=post, get=get)
    created = client.create_task({"model": SEEDANCE_SKU_PRIMARY, "content": [{"type": "text", "text": "x"}], "duration": 5})
    assert created["id"] == "cgt-mock-ok"
    assert created["posted"] is True
    assert posts[0]["url"] == tasks_url()
    assert "/contents/generations/tasks" in posts[0]["url"]
    assert posts[0]["auth"] == "Bearer ark-test-key"
    polled = client.get_task("cgt-mock-ok")
    assert polled["status"] == "succeeded"
    assert polled["video_url"] == "https://example.test/v.mp4"
    assert parse_task_id({"task_id": "alt"}) == "alt"
    assert parse_task_status({"status": "queued"}) == "queued"
    assert parse_video_url({"content": {"video_url": "https://x/v.mp4"}}) == "https://x/v.mp4"


def test_client_refuses_without_allow_live():
    client = ArkSeedanceClient(api_key="x", allow_live=False)
    exc = _err(lambda: client.create_task({"model": SEEDANCE_SKU_PRIMARY}))
    assert exc.code == "live_job_forbidden"
    assert exc.details.get("posted") is False


def test_md5_roundtrip(tmp_path):
    data = b"\x00\x00\x00\x18ftypmp42unit"
    out = write_clip_bytes(tmp_path, "S03", data)
    assert out["md5"] == md5_bytes(data)
