from __future__ import annotations

from pathlib import Path

from aiv.artifact import dump_frontmatter, read_n1_markdown, write_n1_markdown


def test_frontmatter_roundtrip_no_document_end_markers(tmp_path: Path):
    path = tmp_path / "N1-口播定稿.md"
    meta = {
        "node": "N1",
        "path": "A",
        "framework": "惊喜揭秘型",
        "chars": 12,
        "source_ref": ".aiv/raw.txt",
        "confirmed_by": "bot:demo",
        "locked": True,
        "version": 1,
    }
    write_n1_markdown(path, meta, "［标题］\n钩子\n\n文案内容：\n正文一段。\n")
    text = path.read_text(encoding="utf-8")
    assert "\n...\n" not in text
    assert "confirmed_by:" in text
    loaded, body = read_n1_markdown(path)
    assert loaded["node"] == "N1"
    assert loaded["path"] == "A"
    assert loaded["framework"] == "惊喜揭秘型"
    assert loaded["locked"] is True
    assert loaded["confirmed_by"] == "bot:demo"
    assert loaded["version"] == 1
    assert "文案内容" in body
    dumped = dump_frontmatter(meta)
    assert dumped.startswith("---\n")
    assert dumped.strip().endswith("---")
