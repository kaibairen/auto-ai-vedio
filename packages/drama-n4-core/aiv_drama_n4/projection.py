from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiv_drama.store import atomic_write_text


def prompts_jsonl_name(ep: str) -> str:
    return f"{ep}-prompts.jsonl"


def prompts_jsonl_versioned_name(ep: str, version: int) -> str:
    return f"{ep}-prompts.v{version}.jsonl"


def prompts_jsonl_relpath(ep: str) -> str:
    return f"episodes/{ep}/{prompts_jsonl_name(ep)}"


def prompts_jsonl_versioned_relpath(ep: str, version: int) -> str:
    return f"episodes/{ep}/{prompts_jsonl_versioned_name(ep, version)}"


def write_prompts_jsonl(
    episode_dir: Path,
    ep: str,
    lines: list[dict[str, Any]],
    *,
    version: int,
) -> Path:
    """Overwrite current jsonl and keep a sidecar vN for traceability."""
    body = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in lines)
    path = episode_dir / prompts_jsonl_name(ep)
    atomic_write_text(path, body)
    sidecar = episode_dir / prompts_jsonl_versioned_name(ep, version)
    atomic_write_text(sidecar, body)
    return path


def read_prompts_jsonl(episode_dir: Path, ep: str) -> list[dict[str, Any]]:
    path = episode_dir / prompts_jsonl_name(ep)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        rows.append(json.loads(raw))
    return rows
