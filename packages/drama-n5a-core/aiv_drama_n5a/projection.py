from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from aiv_drama.store import atomic_write_text

_VER_RE = re.compile(r"_v(\d+)\.png$", re.I)


def grids_dirname() -> str:
    return "grids"


def grid_filename(ep: str, layout: int, version: int) -> str:
    return f"{ep}_grid_{layout}_v{version}.png"


def checklist_filename(ep: str) -> str:
    return f"{ep}_g4-checklist.yaml"


def evidence_filename(ep: str) -> str:
    return f"{ep}_g4-evidence.json"


def grid_relpath(ep: str, layout: int, version: int) -> str:
    return f"episodes/{ep}/{grids_dirname()}/{grid_filename(ep, layout, version)}"


def checklist_relpath(ep: str) -> str:
    return f"episodes/{ep}/{grids_dirname()}/{checklist_filename(ep)}"


def evidence_relpath(ep: str) -> str:
    return f"episodes/{ep}/{grids_dirname()}/{evidence_filename(ep)}"


def grids_dir(episode_dir: Path) -> Path:
    return episode_dir / grids_dirname()


def next_grid_version(episode_dir: Path, ep: str, layout: int) -> int:
    folder = grids_dir(episode_dir)
    if not folder.is_dir():
        return 1
    highest = 0
    prefix = f"{ep}_grid_{layout}_v"
    for path in folder.glob(f"{prefix}*.png"):
        match = _VER_RE.search(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def write_grid_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def write_checklist_yaml(path: Path, payload: dict[str, Any]) -> None:
    body = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, body)


def read_checklist_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def write_evidence_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_evidence_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None
