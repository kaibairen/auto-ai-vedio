from __future__ import annotations

from pathlib import Path

from aiv_drama.models import DramaBriefWrite, OutlineWrite
from tests.drama.helpers import generate_ready, seed_project_episode


def test_projection_files_and_no_secrets(svc, data_dir):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    ep_dir = Path(data_dir) / "projects" / pid / "episodes" / "EP01"
    assert (ep_dir / "EP01-brief.yaml").is_file()
    assert (ep_dir / "EP01-大纲.md").is_file()
    assert (ep_dir / "EP01-cast.yaml").is_file()
    assert (ep_dir / ".aiv" / "episode.json").is_file()
    meta = (ep_dir / ".aiv" / "episode.json").read_text(encoding="utf-8")
    assert '"pipeline_profile": "drama"' in meta
    assert "D-N2" in meta
    assert "force_pass" not in meta
    md = (ep_dir / "EP01-大纲.md").read_text(encoding="utf-8")
    assert "node: D-N1" in md
    assert "宫格" not in md
    text = "".join(p.read_text(encoding="utf-8") for p in ep_dir.rglob("*") if p.is_file())
    assert "OPENAI_API_KEY" not in text
    assert "AIV_OPENAI_API_KEY" not in text
    lib = Path(data_dir) / "projects" / pid / "libraries" / "characters" / "CHAR-01" / "v3" / "character.yaml"
    assert lib.is_file()
    assert "episodes" not in str(lib.relative_to(Path(data_dir) / "projects" / pid / "libraries"))


def test_unlock_marks_stale_on_disk(svc, data_dir):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    svc.put_outline(
        pid,
        "EP01",
        OutlineWrite(body_md=rec["outline"]["body_md"] + "\n", unlock_edit=True),
    )
    meta = (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / ".aiv" / "episode.json").read_text(
        encoding="utf-8"
    )
    assert "D-N2" in meta
    assert '"d_n2": true' in meta


def test_brief_confirm_stale_when_locked(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    from aiv_drama.errors import AppError

    try:
        svc.put_brief(pid, "EP01", DramaBriefWrite(title_intent="改题材", lane_preference="female"))
        raise AssertionError("expected downstream_locked")
    except AppError as exc:
        assert exc.code == "downstream_locked"
    env = svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(title_intent="改题材确认", lane_preference="female", confirm_stale_outline=True),
    )
    assert env["brief"]["title_intent"] == "改题材确认"
    assert "D-N2" in svc._rec(pid, "EP01")["episode"]["stale_downstream"]
