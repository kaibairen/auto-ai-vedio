from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROJECT_ID = "default"

SKILL_PATHS = {
    "female": ".skill/writing/女频短剧编剧/SKILL.md",
    "male": ".skill/writing/男频短剧编剧/SKILL.md",
}

SHOT_CAP_HARD = 12


def _walk_for_repo(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(12):
        if (cur / ".skill" / "writing" / "女频短剧编剧" / "SKILL.md").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def find_repo_root() -> Path:
    env = os.environ.get("AIV_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for start in (Path.cwd(), *here.parents[:6]):
        found = _walk_for_repo(start)
        if found:
            return found
    return Path.cwd().resolve()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    repo_root: Path
    default_provider: str
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str

    @classmethod
    def from_env(cls) -> Settings:
        data = os.environ.get("AIV_DATA_DIR", "./data")
        provider = os.environ.get("AIV_LLM_PROVIDER", "fixture").strip().lower()
        if provider in {"openai", "openai_compat"}:
            provider = "llm"
        if provider not in {"fixture", "llm"}:
            provider = "fixture"
        return cls(
            data_dir=Path(data).resolve(),
            repo_root=find_repo_root(),
            default_provider=provider,
            openai_api_key=os.environ.get("AIV_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            openai_base_url=(
                os.environ.get("AIV_OPENAI_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_model=os.environ.get("AIV_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
        )

    def skill_relpath(self, lane: str) -> str:
        return SKILL_PATHS[lane]

    def skill_abspath(self, lane: str) -> Path:
        return self.repo_root / SKILL_PATHS[lane]
