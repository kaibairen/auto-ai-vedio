from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _walk_for_repo(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(8):
        if (cur / ".prompt" / "koubo-口水话.md").is_file():
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
    for start in (Path.cwd(), here.parents[2], here.parents[1]):
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
        data = os.environ.get("AIV_DATA_DIR", "data")
        provider = os.environ.get("AIV_LLM_PROVIDER", "fixture").strip().lower()
        if provider not in {"fixture", "openai"}:
            provider = "fixture"
        return cls(
            data_dir=Path(data).resolve(),
            repo_root=find_repo_root(),
            default_provider=provider,
            openai_api_key=os.environ.get("AIV_OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY"),
            openai_base_url=(
                os.environ.get("AIV_OPENAI_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_model=os.environ.get("AIV_OPENAI_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4o-mini",
        )

    @property
    def prompt_koubo_a(self) -> Path:
        return self.repo_root / ".prompt" / "koubo-口水话.md"

    @property
    def prompt_koubo_b(self) -> Path:
        return self.repo_root / ".prompt" / "koubo-长文章.md"

    def prompt_path(self, path: str) -> Path:
        return self.prompt_koubo_a if path == "A" else self.prompt_koubo_b
