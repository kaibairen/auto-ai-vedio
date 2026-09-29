from __future__ import annotations

from aiv.artifact import sha256_file


def test_fixture_demo_writes_locked_markdown(service, project, ep, repo_root):
    a = repo_root / ".prompt" / "koubo-口水话.md"
    b = repo_root / ".prompt" / "koubo-长文章.md"
    ha, hb = sha256_file(a), sha256_file(b)
    view = service.demo(project, ep, "A", actor="bot:demo")
    assert view["locked"] is True
    assert view["artifact"]["frontmatter"]["node"] == "N1"
    assert view["artifact"]["frontmatter"]["path"] == "A"
    assert "writer" in {e["id"] for e in view["next_edges"]}
    assert sha256_file(a) == ha
    assert sha256_file(b) == hb


def test_no_writer_artifact_created(service, project, ep):
    service.demo(project, ep, "A")
    ep_dir = service.store.episode_dir(project, ep)
    names = {p.name for p in ep_dir.iterdir() if p.is_file()}
    assert "N1-口播定稿.md" in names
    assert "EP01-大纲.md" not in names
    assert "EP01-cast.yaml" not in names
