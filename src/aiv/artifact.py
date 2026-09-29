from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from aiv.validation import count_chars

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)
TITLE_RE = re.compile(r"［标题］\s*(.+)")
BODY_RE = re.compile(r"文案内容：\s*(.*)", re.S)

FRONTMATTER_KEYS = (
    "node",
    "path",
    "framework",
    "chars",
    "source_ref",
    "confirmed_by",
    "locked",
    "version",
)


def compose_markdown(title: str, body: str) -> str:
    title = title.strip()
    body = body.strip()
    lines = []
    if title:
        lines.append("［标题］")
        lines.append(title)
        lines.append("")
    lines.append("文案内容：")
    lines.append(body)
    return "\n".join(lines).rstrip() + "\n"


def parse_title_body(markdown: str) -> tuple[str, str]:
    title_m = TITLE_RE.search(markdown)
    body_m = BODY_RE.search(markdown)
    title = title_m.group(1).strip() if title_m else ""
    if body_m:
        body = body_m.group(1).strip()
    else:
        body = markdown.strip()
    return title, body


def dump_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        value = meta.get(key, "")
        if key == "locked":
            lines.append(f"{key}: {str(bool(value)).lower()}")
        elif key in {"chars", "version"}:
            lines.append(f"{key}: {int(value or 0)}")
        elif key == "node":
            lines.append("node: N1")
        else:
            text = "" if value is None else str(value)
            lines.append(f"{key}: {yaml.safe_dump(text, allow_unicode=True).strip()}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_n1_markdown(path: Path, meta: dict[str, Any], body_md: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    title, body = parse_title_body(body_md)
    if "chars" not in meta or meta.get("chars") in (None, ""):
        meta["chars"] = count_chars(body)
    text = dump_frontmatter(meta) + body_md.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def read_n1_markdown(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, m.group(2)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()
