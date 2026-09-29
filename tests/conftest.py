from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiv.api.app import create_app
from aiv.config import Settings, find_repo_root
from aiv.service import N1Service


@pytest.fixture
def repo_root() -> Path:
    return find_repo_root()


@pytest.fixture
def settings(tmp_path: Path, repo_root: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        repo_root=repo_root,
        default_provider="fixture",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini",
    )


@pytest.fixture
def service(settings: Settings) -> N1Service:
    return N1Service(settings)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def project() -> str:
    return "demo"


@pytest.fixture
def ep() -> str:
    return "EP01"
