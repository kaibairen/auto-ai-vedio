from __future__ import annotations

from pathlib import Path

from aiv_drama_n2.models import StoryboardGenerateRequest
from aiv_drama_n2.projection import CSV_COLUMNS

from tests.drama.helpers import lock_g1b, seed_project_episode


def test_storyboard_projection_csv_md_episode_json(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    ep_dir = Path(data_dir) / "projects" / pid / "episodes" / "EP01"
    csv_path = ep_dir / "EP01-分镜.csv"
    md_path = ep_dir / "EP01-分镜.md"
    assert csv_path.is_file()
    assert md_path.is_file()
    csv_text = csv_path.read_text(encoding="utf-8")
    header = csv_text.splitlines()[0]
    for col in CSV_COLUMNS:
        assert col in header
    assert "prompt" not in header.split(",")
    assert "MS" in csv_text or "CU" in csv_text
    assert "中景" not in csv_text
    md = md_path.read_text(encoding="utf-8")
    assert "node: D-N2" in md
    assert "borrowed_dongman" in md
    assert "宫格" not in md
    meta = (ep_dir / ".aiv" / "episode.json").read_text(encoding="utf-8")
    assert '"g2"' in meta
    assert "D-N3" in meta
    assert "force_pass" not in meta
    assert "storyboard_meta" in meta
    text = "".join(p.read_text(encoding="utf-8") for p in ep_dir.rglob("*") if p.is_file())
    assert "OPENAI_API_KEY" not in text
    assert "AIV_OPENAI_API_KEY" not in text


def test_unlock_edit_marks_dn3_stale_on_disk(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    from aiv_drama_n2.models import StoryboardWrite
    from tests.drama.helpers import sample_row

    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(scene_id=scene, action="解锁")]
    svc.put_storyboard(
        pid,
        "EP01",
        StoryboardWrite.model_validate({"rows": rows, "unlock_edit": True}),
        raw={"rows": rows, "unlock_edit": True},
    )
    meta = (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / ".aiv" / "episode.json").read_text(
        encoding="utf-8"
    )
    assert '"d_n3": true' in meta
