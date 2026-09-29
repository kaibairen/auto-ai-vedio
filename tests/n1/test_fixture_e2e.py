from __future__ import annotations

from aiv_n1.artifact import sha256_file


def test_t_p01_fixture_locks_without_key(service, project, ep, repo_root):
    a = repo_root / ".prompt" / "koubo-口水话.md"
    b = repo_root / ".prompt" / "koubo-长文章.md"
    ha, hb = sha256_file(a), sha256_file(b)
    env = service.demo(project, ep, "A", actor="bot:demo")
    assert env["ok"] is True
    assert env["session"]["status"] == "locked"
    assert env["artifact"]["frontmatter"]["node"] == "N1"
    assert env["artifact"]["frontmatter"]["confirmed_by"] == "bot:demo"
    assert sha256_file(a) == ha
    assert sha256_file(b) == hb


def test_t_p02_no_secrets_in_episodes(service, project, ep):
    service.demo(project, ep, "A")
    root = service.store.episode_dir(ep)
    for p in root.rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert "api_key" not in text.lower()
            assert "sk-" not in text
