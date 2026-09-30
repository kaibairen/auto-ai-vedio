"""Persistable D-N2 skill path + excerpt/trace (BRIEF-AIV-020 P0-C)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from aiv_drama.config import SKILL_ENTRY_EXCERPT_LIMIT, SKILL_REFERENCE_EXCERPT_LIMIT, Settings
from aiv_drama_n2.validate import SEEDANCE_SKILL_PATH, STORYBOARD_SKILL_PATH

STORYBOARD_GUIDE_PATH = ".skill/writing/动态漫-转分镜/动态漫剧本转分镜生成指南.md"


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_excerpt(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def excerpt_borrowed_dongman(settings: Settings) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Return (joined excerpt, relative paths, per-file excerpt meta)."""
    chunks: list[str] = []
    used: list[str] = []
    excerpts: list[dict[str, Any]] = []
    pairs = (
        (STORYBOARD_SKILL_PATH, SKILL_ENTRY_EXCERPT_LIMIT),
        (STORYBOARD_GUIDE_PATH, SKILL_REFERENCE_EXCERPT_LIMIT),
    )
    for rel, limit in pairs:
        text = _read_excerpt(settings.repo_root / rel, limit)
        if not text.strip():
            continue
        chunks.append(f"### {rel}\n{text}")
        used.append(rel)
        excerpts.append(
            {
                "path": rel,
                "chars": len(text),
                "hash": _sha256_hex(text)[:16],
                "sha256": _sha256_hex(text),
            }
        )
    return "\n\n".join(chunks), used, excerpts


def load_storyboard_skill_evidence(
    settings: Settings,
    *,
    skill: str = "borrowed_dongman",
) -> dict[str, Any]:
    if skill != "borrowed_dongman":
        return {
            "skill": skill,
            "paths": [],
            "excerpt": "",
            "excerpts": [],
            "trace": {
                "skill": skill,
                "paths": [],
                "excerpts": [],
                "excerpt_chars": 0,
                "injected": False,
            },
        }
    excerpt, paths, excerpts = excerpt_borrowed_dongman(settings)
    if any(SEEDANCE_SKILL_PATH in (p or "") for p in paths):
        paths = [p for p in paths if SEEDANCE_SKILL_PATH not in p]
        excerpts = [e for e in excerpts if SEEDANCE_SKILL_PATH not in str(e.get("path") or "")]
        excerpt = "\n\n".join(
            chunk for chunk in excerpt.split("\n\n") if SEEDANCE_SKILL_PATH not in chunk
        )
    trace = {
        "skill": skill,
        "paths": list(paths),
        "excerpts": excerpts,
        "excerpt_chars": len(excerpt),
        "injected": bool(paths),
    }
    return {
        "skill": skill,
        "paths": paths,
        "excerpt": excerpt,
        "excerpts": excerpts,
        "trace": trace,
    }


def n2_request_evidence(
    *,
    provider: str | None,
    skill: str,
    tool_profile: str | None,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "storyboard_skill": skill,
        "tool_profile": tool_profile,
        "skill_paths": list(evidence.get("paths") or []),
        "skill_excerpt": evidence.get("excerpt") or "",
        "skill_trace": dict(evidence.get("trace") or {}),
    }
