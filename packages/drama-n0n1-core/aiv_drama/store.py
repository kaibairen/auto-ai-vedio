from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from aiv_drama.config import Settings


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class JsonStore:
    """API-source persistence. Disk yaml/md under episodes/** is projection only."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.data_dir / "store.json"
        self.state: dict[str, Any] = self._empty()
        self.load()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "projects": {},
            "episodes": {},
            "library": {},
            "idempotency": {},
            "counters": {"project": 0},
        }

    def load(self) -> None:
        if self.path.is_file():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
            for key, default in self._empty().items():
                self.state.setdefault(key, deepcopy(default))
        else:
            self.state = self._empty()

    def save(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.path, json.dumps(self.state, ensure_ascii=False, indent=2) + "\n")

    def project_root(self, project_id: str) -> Path:
        return self.settings.data_dir / "projects" / project_id

    def episode_dir(self, project_id: str, ep: str) -> Path:
        return self.project_root(project_id) / "episodes" / ep

    def library_dir(self, project_id: str, character_id: str, version: int) -> Path:
        return self.project_root(project_id) / "libraries" / "characters" / character_id / f"v{version}"
