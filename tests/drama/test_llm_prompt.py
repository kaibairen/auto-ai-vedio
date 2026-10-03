"""FIX-DN1 P0-2 / P0-3: preattached prompt wiring + bounded skill reference excerpts."""

from __future__ import annotations

import json
from pathlib import Path

from aiv_drama.config import SKILL_PATHS, Settings, skill_reference_relpaths
from aiv_drama.models import (
    AttachRequest,
    DramaBriefWrite,
    EpisodeCreate,
    GeneratedDraft,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
    ProjectCreate,
)
from tests.drama.helpers import persist_and_confirm_intent
from aiv_drama.provider.llm import LlmProvider


def _settings(tmp_path: Path, *, repo_root: Path | None = None) -> Settings:
    return Settings(
        data_dir=(tmp_path / "data").resolve(),
        repo_root=(repo_root or tmp_path).resolve(),
        default_provider="llm",
        openai_api_key="test-key",
        openai_base_url="https://llm.test/v1",
        openai_model="deepseek-chat",
    )


def _write_skill_tree(root: Path, *, with_references: bool = True, missing_one: bool = False) -> None:
    female = root / ".skill" / "writing" / "女频短剧编剧"
    refs = female / "references"
    refs.mkdir(parents=True, exist_ok=True)
    (female / "SKILL.md").write_text("# 女频短剧编剧\n型判定后读 references 表\n", encoding="utf-8")
    files = {
        "ticai-yurenshe.md": "# 题材与人设\n女频型判定表\n",
        "jiegou-kuangjia.md": "# 结构框架\n女频四幕骨架 绝境铺垫\n",
        "shuangdian-sheji.md": "# 爽点设计\n情感兑现与打脸节奏\n",
        "luoji-jiaoyan-qingdan.md": "# 审稿清单\n逻辑自洽检查\n",
    }
    for name, text in files.items():
        if missing_one and name == "luoji-jiaoyan-qingdan.md":
            continue
        (refs / name).write_text(text, encoding="utf-8")


def _fake_ok(monkeypatch, *, body_md: str = "# 大纲\n- 桥段序列：\n  1. 程序员登场\n"):
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "body_md": body_md,
                                    "characters": [
                                        {"name": "程序员", "one_line": "预挂男主"},
                                        {"name": "豆包", "one_line": "奶蛙"},
                                    ],
                                    "scenes": [{"name": "公司", "one_line": "开场"}],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("aiv_drama.provider.llm.httpx.post", fake_post)
    return captured


def test_llm_prompt_includes_preattached_and_rules(tmp_path, monkeypatch):
    _write_skill_tree(tmp_path)
    captured = _fake_ok(monkeypatch)
    provider = LlmProvider(_settings(tmp_path))
    draft = provider.generate(
        episode_id="EP01",
        lane="female",
        shot_cap=12,
        brief={
            "title_intent": "程序员与豆包",
            "pin": None,
            "setting_notes": "都市",
            "preattached_characters": [
                {
                    "id": "CHAR-01",
                    "name": "程序员",
                    "one_line": "程序员·男",
                    "library_ref": {"id": "CHAR-01", "version": 1},
                },
                {
                    "id": "CHAR-02",
                    "name": "豆包",
                    "one_line": "奶蛙豆包",
                    "library_ref": {"id": "CHAR-02", "version": 1},
                },
            ],
        },
    )
    user = json.loads(captured["json"]["messages"][1]["content"])
    cards = user["brief"]["preattached_characters"]
    assert cards[0]["id"] == "CHAR-01"
    assert cards[0]["name"] == "程序员"
    assert cards[0]["one_line"] == "程序员·男"
    assert cards[0]["library_ref"] == {"id": "CHAR-01", "version": 1}
    assert cards[1]["name"] == "豆包"
    assert any("大纲主角必须使用预挂角色的姓名" in r for r in user["rules"])
    assert any("禁止另造同名角色" in r for r in user["rules"])
    assert any("follow this episode's cast" in r for r in user["rules"])
    rules_text = "".join(user["rules"])
    assert "程序员/豆包" not in rules_text
    assert "豆包" not in rules_text
    assert "宫格" in rules_text
    assert draft.characters[0]["name"] == "程序员"


def test_llm_injects_reference_excerpts_and_lists_real_paths(tmp_path, monkeypatch):
    _write_skill_tree(tmp_path)
    captured = _fake_ok(monkeypatch)
    provider = LlmProvider(_settings(tmp_path))
    draft = provider.generate(
        episode_id="EP01",
        lane="female",
        shot_cap=12,
        brief={"title_intent": "一句", "preattached_characters": []},
    )
    user = json.loads(captured["json"]["messages"][1]["content"])
    excerpt = user["skill_references_excerpt"]
    assert "女频四幕骨架" in excerpt
    assert "jiegou-kuangjia.md" in excerpt
    assert SKILL_PATHS["female"] in draft.source_skills
    ref_paths = [p for p in draft.source_skills if "/references/" in p]
    assert ref_paths
    expected = set(skill_reference_relpaths("female"))
    assert set(ref_paths) <= expected
    assert all((tmp_path / p).is_file() for p in draft.source_skills)
    assert len(user["skill_excerpt"]) <= 2000
    assert len(excerpt) <= 2400 + 400  # headings + 4×800 budget


def test_llm_skips_missing_reference_without_500(tmp_path, monkeypatch):
    _write_skill_tree(tmp_path, missing_one=True)
    _fake_ok(monkeypatch)
    provider = LlmProvider(_settings(tmp_path))
    draft = provider.generate(
        episode_id="EP01",
        lane="female",
        shot_cap=12,
        brief={"title_intent": "一句"},
    )
    listed = [p for p in draft.source_skills if p.endswith("luoji-jiaoyan-qingdan.md")]
    assert listed == []
    assert SKILL_PATHS["female"] in draft.source_skills
    assert any("jiegou-kuangjia.md" in p for p in draft.source_skills)


def test_generate_outline_passes_preattached_into_provider(svc, monkeypatch):
    pid = svc.create_project(ProjectCreate(name="prompt-wire"))["project"]["id"]
    svc.put_library_character(
        pid, "CHAR-01", LibraryCharacterWrite(name="程序员", one_line="程序员·男", version=1)
    )
    svc.put_library_character(
        pid, "CHAR-02", LibraryCharacterWrite(name="豆包", one_line="奶蛙豆包", version=1)
    )
    svc.create_episode(pid, EpisodeCreate(episode_id="EP01", pipeline_profile="drama"))
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(title_intent="程序员与豆包", lane_preference="female", hero_one_line="程序员·男"),
    )
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=1))
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-02", version=1))
    persist_and_confirm_intent(svc, pid, follow_precast=True)

    seen: dict = {}

    class _Stub:
        def generate(self, **kwargs):
            seen.update(kwargs)
            return GeneratedDraft(
                body_md="# 大纲\n- 桥段序列：\n  1. 程序员与豆包\n",
                lane="female",
                shot_cap=12,
                characters=[
                    {"name": "林码", "one_line": "重生女主"},
                    {"name": "豆包", "one_line": "第二豆包"},
                    {"name": "二皇子", "one_line": "温柔王子"},
                ],
                scenes=[{"name": "公司", "one_line": "开场"}],
                source_skills=[
                    SKILL_PATHS["female"],
                    ".skill/writing/女频短剧编剧/references/jiegou-kuangjia.md",
                ],
            )

    monkeypatch.setattr("aiv_drama.service.get_provider", lambda *a, **k: _Stub())
    env = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane="female", provider="fixture"),
        raw={"lane": "female", "provider": "fixture"},
    )
    cards = seen["brief"]["preattached_characters"]
    assert [c["id"] for c in cards] == ["CHAR-01", "CHAR-02"]
    assert cards[0]["name"] == "程序员"
    assert cards[0]["library_ref"] == {"id": "CHAR-01", "version": 1}
    names = [c["name"] for c in env["cast"]["characters"]]
    assert "林码" not in names
    assert names.count("豆包") == 1
    assert names.count("程序员") == 1
    assert "二皇子" in names
    assert env["ok"] is True


def test_generate_outline_sends_library_name_after_rename(svc, monkeypatch):
    pid = svc.create_project(ProjectCreate(name="prompt-rename"))["project"]["id"]
    svc.put_library_character(
        pid, "CHAR-01", LibraryCharacterWrite(name="程序员", one_line="程序员·男", version=1)
    )
    svc.put_library_character(
        pid, "CHAR-02", LibraryCharacterWrite(name="豆包", one_line="奶蛙脸陪聊破局者", version=1)
    )
    svc.create_episode(pid, EpisodeCreate(episode_id="EP01", pipeline_profile="drama"))
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(title_intent="程序员与豆包", lane_preference="female", hero_one_line="程序员·男"),
    )
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=1))
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-02", version=1))
    svc.put_library_character(
        pid,
        "CHAR-02",
        LibraryCharacterWrite(
            name="奶蛙公主",
            one_line="踢飞两大模型王子，带着程序员私奔",
            version=2,
        ),
    )
    persist_and_confirm_intent(svc, pid, follow_precast=True)

    seen: dict = {}

    class _Stub:
        def generate(self, **kwargs):
            seen.update(kwargs)
            return GeneratedDraft(
                body_md="# 大纲\n- 桥段序列：\n  1. 奶蛙公主登场\n",
                lane="female",
                shot_cap=12,
                characters=[
                    {"name": "程序员", "one_line": "预挂男主"},
                    {"name": "豆包", "one_line": "奶蛙脸陪聊破局者"},
                    {"name": "二皇子", "one_line": "温柔王子"},
                ],
                scenes=[{"name": "公司", "one_line": "开场"}],
                source_skills=[SKILL_PATHS["female"]],
            )

    monkeypatch.setattr("aiv_drama.service.get_provider", lambda *a, **k: _Stub())
    lane = svc._rec(pid, "EP01")["brief"]["lane_preference"]
    env = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane=lane, provider="fixture"),
        raw={"lane": lane, "provider": "fixture"},
    )
    cards = seen["brief"]["preattached_characters"]
    frog_card = next(c for c in cards if c["id"] == "CHAR-02")
    assert frog_card["name"] == "奶蛙公主"
    assert frog_card["one_line"] == "踢飞两大模型王子，带着程序员私奔"
    names = [c["name"] for c in env["cast"]["characters"]]
    assert "豆包" not in names
    frog = next(c for c in env["cast"]["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert frog["one_line"] == "踢飞两大模型王子，带着程序员私奔"
    assert env["ok"] is True
