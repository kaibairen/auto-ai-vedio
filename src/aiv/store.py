from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiv.config import Settings
from aiv.validation import validate_ep, validate_project_id

N1_FILENAME = "N1-口播定稿.md"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.data_dir = settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str) -> Path:
        return self.data_dir / "projects" / validate_project_id(project_id)

    def episode_dir(self, project_id: str, ep: str) -> Path:
        return self.project_root(project_id) / "episodes" / validate_ep(ep)

    def artifact_path(self, project_id: str, ep: str) -> Path:
        return self.episode_dir(project_id, ep) / N1_FILENAME

    def aiv_dir(self, project_id: str, ep: str) -> Path:
        return self.episode_dir(project_id, ep) / ".aiv"

    def session_path(self, project_id: str, ep: str) -> Path:
        return self.aiv_dir(project_id, ep) / "n1-session.json"

    def episode_meta_path(self, project_id: str, ep: str) -> Path:
        return self.aiv_dir(project_id, ep) / "episode.json"

    def raw_path(self, project_id: str, ep: str) -> Path:
        return self.aiv_dir(project_id, ep) / "raw.txt"

    def rel_artifact(self, ep: str) -> str:
        return f"episodes/{validate_ep(ep)}/{N1_FILENAME}"

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
