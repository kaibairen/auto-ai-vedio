from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from aiv_drama.store import atomic_write_text
from aiv_schema.models import NODE_DN1


def _dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _strip_frontmatter(body_md: str) -> str:
    text = body_md or ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


def write_brief(episode_dir: Path, ep: str, brief: dict[str, Any]) -> Path:
    path = episode_dir / f"{ep}-brief.yaml"
    atomic_write_text(path, _dump_yaml(brief))
    return path


def write_outline(
    episode_dir: Path,
    ep: str,
    outline: dict[str, Any],
    source_skills: list[str] | None = None,
) -> Path:
    path = episode_dir / f"{ep}-大纲.md"
    fm = {
        "node": NODE_DN1,
        "lane": outline.get("lane"),
        "locked": outline.get("locked"),
        "version": outline.get("version"),
        "confirmed_by": outline.get("confirmed_by"),
        "shot_cap": outline.get("shot_cap"),
        "source_skills": source_skills or outline.get("source_skills") or [],
    }
    body = _strip_frontmatter(outline.get("body_md") or "")
    text = "---\n" + _dump_yaml(fm) + "---\n" + body
    if not text.endswith("\n"):
        text += "\n"
    atomic_write_text(path, text)
    return path


def write_cast(episode_dir: Path, ep: str, cast: dict[str, Any]) -> Path:
    path = episode_dir / f"{ep}-cast.yaml"
    payload = {
        "episode": cast.get("episode") or ep,
        "lane": cast.get("lane"),
        "characters": cast.get("characters") or [],
        "scenes": cast.get("scenes") or [],
        "version": cast.get("version"),
        "locked": cast.get("locked"),
        "confirmed_by": cast.get("confirmed_by"),
    }
    atomic_write_text(path, _dump_yaml(payload))
    return path


def write_episode_json(episode_dir: Path, meta: dict[str, Any]) -> Path:
    path = episode_dir / ".aiv" / "episode.json"
    import json

    atomic_write_text(path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return path


def write_library_character(lib_dir: Path, record: dict[str, Any]) -> Path:
    path = lib_dir / "character.yaml"
    atomic_write_text(path, _dump_yaml(record))
    return path


def assert_no_secrets(episode_dir: Path) -> None:
    """Guard: episode projection must not contain API keys."""
    banned = ("OPENAI_API_KEY", "AIV_OPENAI_API_KEY", "sk-")
    if not episode_dir.is_dir():
        return
    for path in episode_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in banned:
            if token in text and token == "sk-" and "sk-" in text:
                # only fail on long key-like tokens
                import re

                if re.search(r"sk-[A-Za-z0-9]{20,}", text):
                    raise RuntimeError(f"secret leaked into {path}")
            elif token != "sk-" and token in text:
                raise RuntimeError(f"secret leaked into {path}")
