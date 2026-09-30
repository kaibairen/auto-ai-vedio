"""D-N2 live LLM StoryboardProvider — mocked HTTP, no real keys."""

from __future__ import annotations

import json
from pathlib import Path

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama_n2.models import StoryboardGenerateRequest
from aiv_drama_n2.provider import generate_rows, get_storyboard_provider
from aiv_drama_n2.provider.fixture import FixtureStoryboardProvider
from aiv_drama_n2.provider.llm import LlmStoryboardProvider, STORYBOARD_GUIDE_PATH
from aiv_drama_n2.validate import SEEDANCE_SKILL_PATH, STORYBOARD_SKILL_PATH, collect_issues

from tests.drama.helpers import lock_g1b, seed_project_episode


def _settings(tmp_path: Path, *, key: str | None = "test-key", default: str = "fixture") -> Settings:
    return Settings(
        data_dir=(tmp_path / "data").resolve(),
        repo_root=tmp_path.resolve(),
        default_provider=default,
        openai_api_key=key,
        openai_base_url="https://llm.test/v1",
        openai_model="deepseek-chat",
    )


def _write_dongman_skill(root: Path) -> None:
    skill = root / ".skill" / "writing" / "动态漫-转分镜"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("# 动态漫转分镜\n镜头：远景/全景/中景/近景/特写\n一镜一运镜\n", encoding="utf-8")
    (skill / "动态漫剧本转分镜生成指南.md").write_text("# 指南\n桥段映射到镜号\n", encoding="utf-8")
    banned = root / ".skill" / "generation" / "Seedance2.0-分镜"
    banned.mkdir(parents=True, exist_ok=True)
    (banned / "SKILL.md").write_text("# Seedance 出片 — must not be injected\n", encoding="utf-8")


def _sample_outline_cast() -> tuple[dict, dict]:
    outline = {
        "lane": "female",
        "shot_cap": 12,
        "version": 1,
        "body_md": "# 大纲\n- 桥段序列：\n  1. 开篇钩子\n  2. 立规\n  3. 中段加压\n  4. 主爽\n  5. 集尾悬念\n",
    }
    cast = {
        "characters": [
            {"id": "CHAR-01", "name": "林晚", "one_line": "重生女主"},
            {"id": "CHAR-02", "name": "谢衡", "one_line": "边关主将"},
        ],
        "scenes": [
            {"id": "SCENE-01", "name": "边关营帐", "one_line": "开场"},
            {"id": "SCENE-02", "name": "校场", "one_line": "主爽"},
        ],
    }
    return outline, cast


def _fake_ok(monkeypatch, *, rows: list[dict] | None = None):
    captured: dict = {}
    if rows is None:
        rows = [
            {
                "shot_id": "S01",
                "bridge_id": "B1",
                "seq": 1,
                "duration_s": 5,
                "shot_size": "中景",
                "camera": "推",
                "action": "推门入室环顾",
                "char_ids": ["林晚"],
                "scene_id": "边关营帐",
                "dialogue": None,
                "transition": "cut",
                "dynamic_level": "基础",
                "tool_duration_bucket": None,
                "grid_strict": False,
                "notes": "angle:eye",
            },
            {
                "shot_id": "S02",
                "bridge_id": "B2",
                "seq": 2,
                "duration_s": 5,
                "shot_size": "CU",
                "camera": "STATIC",
                "action": "空镜群杂",
                "char_ids": ["NONE"],
                "scene_id": "SCENE-01",
                "dialogue": None,
                "transition": "cut",
                "notes": "群杂背影",
            },
        ]

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": json.dumps({"rows": rows}, ensure_ascii=False)}}]}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("aiv_drama_n2.provider.llm.httpx.post", fake_post)
    return captured


def test_provider_branch_fixture_vs_llm(tmp_path):
    settings = _settings(tmp_path)
    assert isinstance(get_storyboard_provider("fixture", settings), FixtureStoryboardProvider)
    assert isinstance(get_storyboard_provider("skill", settings), FixtureStoryboardProvider)
    assert isinstance(get_storyboard_provider("llm", settings), LlmStoryboardProvider)
    assert isinstance(get_storyboard_provider("openai", settings), LlmStoryboardProvider)
    defaulted = _settings(tmp_path, default="fixture")
    assert isinstance(get_storyboard_provider(None, defaulted), FixtureStoryboardProvider)
    llm_default = _settings(tmp_path, default="llm")
    assert isinstance(get_storyboard_provider(None, llm_default), LlmStoryboardProvider)


def test_llm_missing_key_fails_clearly(tmp_path):
    settings = _settings(tmp_path, key=None)
    provider = get_storyboard_provider("llm", settings)
    assert isinstance(provider, LlmStoryboardProvider)
    outline, cast = _sample_outline_cast()
    try:
        provider.generate(episode_id="EP01", outline=outline, cast=cast, shot_cap=12, tool_profile=None)
        raise AssertionError("expected AppError")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "provider"
        assert exc.details.get("node") == "D-N2"
        assert "AIV_OPENAI_API_KEY" in exc.message


def test_llm_http_prompt_and_fold(tmp_path, monkeypatch):
    _write_dongman_skill(tmp_path)
    captured = _fake_ok(monkeypatch)
    outline, cast = _sample_outline_cast()
    rows = LlmStoryboardProvider(_settings(tmp_path)).generate(
        episode_id="EP01",
        outline=outline,
        cast=cast,
        shot_cap=12,
        tool_profile=None,
    )
    assert captured["url"] == "https://llm.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    user = json.loads(captured["json"]["messages"][1]["content"])
    assert user["node"] == "D-N2"
    assert user["storyboard_skill"] == "borrowed_dongman"
    assert "林晚" in json.dumps(user["cast"], ensure_ascii=False)
    assert "开篇钩子" in (user["outline"]["body_md"] or "")
    assert STORYBOARD_SKILL_PATH in user["skill_paths"]
    assert STORYBOARD_GUIDE_PATH in user["skill_paths"]
    assert SEEDANCE_SKILL_PATH not in user["skill_excerpt"]
    assert "Seedance 出片" not in user["skill_excerpt"]
    assert any("CHAR-*" in r for r in user["rules"])
    assert rows[0]["char_ids"] == ["CHAR-01"]
    assert rows[0]["scene_id"] == "SCENE-01"
    assert rows[0]["shot_size"] == "MS"
    assert rows[0]["camera"] == "PUSH"
    assert rows[1]["char_ids"] == ["NONE"]
    assert all(r["bridge_id"] for r in rows)


def test_llm_prompt_forbidden_from_model(tmp_path, monkeypatch):
    _write_dongman_skill(tmp_path)
    _fake_ok(
        monkeypatch,
        rows=[
            {
                "bridge_id": "B1",
                "seq": 1,
                "duration_s": 5,
                "shot_size": "MS",
                "camera": "STATIC",
                "action": "Seedance 0-5s:[Image1] 完整时间轴",
                "char_ids": ["CHAR-01"],
                "scene_id": "SCENE-01",
            }
        ],
    )
    outline, cast = _sample_outline_cast()
    try:
        LlmStoryboardProvider(_settings(tmp_path)).generate(
            episode_id="EP01", outline=outline, cast=cast, shot_cap=12, tool_profile=None
        )
        raise AssertionError("expected prompt_forbidden")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "prompt_forbidden"


def test_llm_clears_invalid_bucket_when_tool_profile_unset(tmp_path, monkeypatch):
    _write_dongman_skill(tmp_path)
    _fake_ok(
        monkeypatch,
        rows=[
            {
                "bridge_id": "B1",
                "seq": 1,
                "duration_s": 4,
                "shot_size": "MS",
                "camera": "STATIC",
                "action": "推门入室",
                "char_ids": ["CHAR-01"],
                "scene_id": "SCENE-01",
                "tool_duration_bucket": "3s",
            },
            {
                "bridge_id": "B2",
                "seq": 2,
                "duration_s": 4,
                "shot_size": "CU",
                "camera": "STATIC",
                "action": "空镜群杂",
                "char_ids": ["NONE"],
                "scene_id": "SCENE-01",
                "tool_duration_bucket": "4s",
                "notes": "群杂背影",
            },
        ],
    )
    outline, cast = _sample_outline_cast()
    rows = LlmStoryboardProvider(_settings(tmp_path)).generate(
        episode_id="EP01", outline=outline, cast=cast, shot_cap=12, tool_profile=None
    )
    assert [r["tool_duration_bucket"] for r in rows] == [None, None]
    issues = collect_issues(
        rows, shot_cap=12, tool_profile=None, cast=cast, outline_body=outline["body_md"]
    )
    assert not any(i.get("code") == "duration_bucket_mismatch" for i in issues)


def test_generate_storyboard_llm_uses_live_provider(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    seen: dict = {}

    class _Stub:
        name = "llm"

        def generate(self, **kwargs):
            seen.update(kwargs)
            return [
                {
                    "shot_id": "S01",
                    "bridge_id": "B1",
                    "seq": 1,
                    "duration_s": 5,
                    "shot_size": "MS",
                    "camera": "PUSH",
                    "action": "真模型一镜",
                    "char_ids": ["CHAR-01"],
                    "scene_id": "SCENE-01",
                    "dialogue": None,
                    "transition": "cut",
                    "dynamic_level": "基础",
                    "tool_duration_bucket": None,
                    "grid_strict": False,
                    "notes": "angle:eye",
                }
            ]

    monkeypatch.setattr(
        "aiv_drama_n2.ops.generate_rows",
        lambda settings, **kw: (_Stub().generate(**{k: kw[k] for k in ("episode_id", "outline", "cast", "shot_cap", "tool_profile")})),
    )
    env = svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="llm"),
        raw={"provider": "llm"},
    )
    assert env["storyboard"]["rows"][0]["action"] == "真模型一镜"
    assert seen["outline"]["body_md"]
    assert seen["cast"]["characters"]


def test_generate_storyboard_llm_no_key_422(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    monkeypatch.delenv("AIV_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    object.__setattr__(svc.settings, "openai_api_key", None)
    monkeypatch.setattr(
        "aiv_drama_n2.provider.llm.httpx.post",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("missing key must not HTTP")),
    )
    try:
        svc.generate_storyboard(
            pid,
            "EP01",
            StoryboardGenerateRequest(provider="llm"),
            raw={"provider": "llm"},
        )
        raise AssertionError("expected provider error")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "provider"
        assert "AIV_OPENAI_API_KEY" in exc.message


def test_generate_rows_llm_hits_http_not_fixture(tmp_path, monkeypatch):
    _write_dongman_skill(tmp_path)
    captured = _fake_ok(monkeypatch)
    outline, cast = _sample_outline_cast()
    rows = generate_rows(
        _settings(tmp_path),
        provider="llm",
        outline=outline,
        cast=cast,
        shot_cap=12,
        tool_profile=None,
        episode_id="EP01",
    )
    assert captured["url"] == "https://llm.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert rows[0]["char_ids"] == ["CHAR-01"]
    assert rows[0]["shot_size"] == "MS"
    fixture_rows = generate_rows(
        _settings(tmp_path, key=None),
        provider="fixture",
        outline=outline,
        cast=cast,
        shot_cap=12,
        tool_profile=None,
        episode_id="EP01",
    )
    assert fixture_rows[0]["action"] != rows[0]["action"]


def test_llm_truncates_to_shot_cap(tmp_path, monkeypatch):
    _write_dongman_skill(tmp_path)
    raw = [
        {
            "bridge_id": "B1",
            "seq": i,
            "duration_s": 5,
            "shot_size": "ms",
            "camera": "static",
            "action": f"镜{i}",
            "char_ids": ["CHAR-01"],
            "scene_id": "SCENE-01",
        }
        for i in range(1, 16)
    ]
    _fake_ok(monkeypatch, rows=raw)
    outline, cast = _sample_outline_cast()
    rows = LlmStoryboardProvider(_settings(tmp_path)).generate(
        episode_id="EP01", outline=outline, cast=cast, shot_cap=8, tool_profile=None
    )
    assert len(rows) == 8
    assert rows[-1]["shot_id"] == "S08"
    assert rows[0]["shot_size"] == "MS"
    assert rows[0]["camera"] == "STATIC"


def test_llm_http_error_502(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("upstream down")

    monkeypatch.setattr("aiv_drama_n2.provider.llm.httpx.post", boom)
    outline, cast = _sample_outline_cast()
    try:
        LlmStoryboardProvider(_settings(tmp_path)).generate(
            episode_id="EP01", outline=outline, cast=cast, shot_cap=12, tool_profile=None
        )
        raise AssertionError("expected 502")
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "provider"
        assert exc.details.get("node") == "D-N2"


def test_unknown_provider_422(tmp_path):
    try:
        get_storyboard_provider("gpt", _settings(tmp_path))
        raise AssertionError("expected validation")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "validation"


def test_fixture_generate_does_not_call_http(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    monkeypatch.setattr(
        "aiv_drama_n2.provider.llm.httpx.post",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("fixture must not HTTP")),
    )
    env = svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="fixture"),
        raw={"provider": "fixture"},
    )
    assert env["storyboard"]["rows"]
    assert env["storyboard"]["rows"][0]["bridge_id"]
