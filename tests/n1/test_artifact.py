from __future__ import annotations

from pathlib import Path

from aiv_n1.artifact import dump_frontmatter, read_n1_markdown, write_n1_markdown


def test_frontmatter_roundtrip(tmp_path: Path):
    path = tmp_path / "N1-口播定稿.md"
    meta = {
        "node": "N1",
        "path": "A",
        "framework": "惊喜揭秘型",
        "chars": 12,
        "source_ref": ".aiv/n1-raw.txt",
        "confirmed_by": "bot:demo",
        "locked": True,
        "version": 1,
        "defects": [],
        "provider": "fixture",
    }
    write_n1_markdown(path, meta, "［标题］\n钩子\n\n文案内容：\n正文一段。\n")
    text = path.read_text(encoding="utf-8")
    assert "\n...\n" not in text
    loaded, body = read_n1_markdown(path)
    assert loaded["locked"] is True
    assert loaded["confirmed_by"] == "bot:demo"
    assert "文案内容" in body
    assert dump_frontmatter(meta).startswith("---\n")
