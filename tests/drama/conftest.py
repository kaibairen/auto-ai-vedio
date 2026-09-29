from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from aiv_api.app import create_app
from aiv_drama.config import Settings
from aiv_drama.service import DramaService


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setenv("AIV_DATA_DIR", str(root))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    monkeypatch.setenv("AIV_REPO_ROOT", os.getcwd())
    return root


@pytest.fixture
def settings(data_dir) -> Settings:
    return Settings.from_env()


@pytest.fixture
def svc(settings) -> DramaService:
    return DramaService(settings)


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


