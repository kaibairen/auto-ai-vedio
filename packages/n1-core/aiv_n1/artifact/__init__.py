from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from aiv_n1.validate import draft_chars

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)
TITLE_RE = re.compile(r"［标题］\s*(.+)")
BODY_RE = re.compile(r"文案内容：\s*(.*)", re.S)

REQUIRED_KEYS = (
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
    lines = ["［标题］", title, "", "文案内容：", body]
    return "\n".join(lines).rstrip() + "\n"


def parse_title_body(markdown: str) -> tuple[str, str]:
    title_m = TITLE_RE.search(markdown)
    body_m = BODY_RE.search(markdown)
    title = title_m.group(1).strip() if title_m else ""
    body = body_m.group(1).strip() if body_m else markdown.strip()
    return title, body


def has_required_format(markdown: str) -> bool:
    return bool(TITLE_RE.search(markdown) and BODY_RE.search(markdown))


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(json.dumps(str(x), ensure_ascii=False) for x in value) + "]"
    text = str(value)
    if text == "":
        return '""'
    special = set(":#{[]}&*!|>'\"%@`,\n\t")
    if (
        text != text.strip()
        or text[:1] in special
        or any(ch in special for ch in text)
        or text.lower() in {"true", "false", "null", "yes", "no", "on", "off"}
    ):
        return json.dumps(text, ensure_ascii=False)
    return text


def dump_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key in REQUIRED_KEYS:
        value = meta.get(key, "")
        if key == "node":
            lines.append("node: N1")
        elif key == "locked":
            lines.append(f"locked: {_yaml_scalar(bool(value))}")
        elif key in {"chars", "version"}:
            lines.append(f"{key}: {int(value or 0)}")
        else:
            lines.append(f"{key}: {_yaml_scalar('' if value is None else value)}")
    if "defects" in meta:
        lines.append(f"defects: {_yaml_scalar(meta.get('defects') or [])}")
    if meta.get("provider"):
        lines.append(f"provider: {_yaml_scalar(meta['provider'])}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_n1_markdown(path: Path, meta: dict[str, Any], body_md: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    title, body = parse_title_body(body_md)
    meta = dict(meta)
    meta["chars"] = draft_chars(title, body)
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
