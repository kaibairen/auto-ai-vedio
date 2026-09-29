from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiv_n1.config import Settings
from aiv_n1.validate import validate_ep

N1_FILENAME = "N1-口播定稿.md"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    """episodes/EP##/ at data_dir (ENG §5). project_id is metadata only (provisional:P-PROJ)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.data_dir = settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def episode_dir(self, ep: str) -> Path:
        return self.data_dir / "episodes" / validate_ep(ep)

    def artifact_path(self, ep: str) -> Path:
        return self.episode_dir(ep) / N1_FILENAME

    def aiv_dir(self, ep: str) -> Path:
        return self.episode_dir(ep) / ".aiv"

    def session_path(self, ep: str) -> Path:
        return self.aiv_dir(ep) / "n1-session.json"

    def episode_meta_path(self, ep: str) -> Path:
        return self.aiv_dir(ep) / "episode.json"

    def raw_path(self, ep: str) -> Path:
        return self.aiv_dir(ep) / "n1-raw.txt"

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
