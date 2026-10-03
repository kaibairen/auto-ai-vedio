"""F3 · N3 observability uses template_paths / prompt_paths only.

Never write .prompt into D-N1 / D-N2 skill_paths. 018b is not reopened.
SCENE card templates: materialize stays deferred; thicken uses provisional_inline.
Do not invent KEEP SCENE paths.
Seedance param refs are not N3 card templates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

KEEP_CHAR_TEMPLATES = (
    ".prompt/consistency/人物卡模板/复杂角色信息一致性角色卡--提示词模板.md",
    ".prompt/consistency/人物卡模板/角色一致性提示词-附使用方法.md",
)

KEEP_STORYBOARD_REF = (
    ".prompt/consistency/故事板-臭猫参考/臭猫故事板提示词参考.txt",
)

# KEEP-registered but not an N3 card template (N4/N5 param surface).
SEEDANCE_PARAM_REF = (
    ".prompt/consistency/故事板-臭猫参考/臭猫系列seedance2.0视频提示词与参数.md"
)

N3_KEEP_DEFAULT = KEEP_CHAR_TEMPLATES + KEEP_STORYBOARD_REF

# Optional CHAR bio skill — thicken_skill_paths only. Never N1/N2 skill_paths.
BIO_SKILL_PATHS = (
    ".skill/writing/动态漫-人物小传/SKILL.md",
    ".skill/writing/动态漫-人物小传/动态漫人物小传写作指南.md",
)

SCENE_TEMPLATE_PROVISIONAL = {
    "status": "provisional_inline",
    "path": None,
    "note": (
        "CTO Q1: SCENE thicken uses an in-code provisional template. "
        "Do not invent a KEEP SCENE prompt path. Formal KEEP is another BRIEF."
    ),
}

# In-code SCENE thicken template (not a repo KEEP path).
SCENE_PROVISIONAL_INLINE = """\
你在加厚本集 SCENE 工作卡的文字槽（不出图、不写 refs/md5）。
MUST：
- appearance = 空间本体（室内外/陈设/尺度/可复用空镜头要素，3–5 个可见点）。写「哪里长什么样」，禁止只写剧情动作或纯气氛词。
- light_anchor = 一句：〔时段〕+〔主光来源/方向〕+〔色温/氛围一词〕+ 可选实用光。例：深夜，顶冷白灯为主，屏幕蓝光辅，低环境光。
SHOULD：
- 同显示名的不同 SCENE-ID 必须用内外/层次后缀消歧（例：营帐门厅·迎客 / 营帐门厅·围困）。禁止静默合并 ID。禁止事件名当场名（如「庆祝时刻」）。
- space_function 可写入干净 one_line；immutable 可写场内不可变陈设。
CAM 软并：space_anchors / framing_scene 并入 appearance；不要因为缺 CAM 扩展槽而拒绝加厚。
"""


def existing_repo_paths(repo_root: Path, relpaths: tuple[str, ...] | list[str]) -> list[str]:
    out: list[str] = []
    root = Path(repo_root)
    for rel in relpaths:
        if not rel or rel.startswith("/"):
            continue
        if (root / rel).is_file():
            out.append(rel)
    return out


def n3_template_paths(repo_root: Path) -> list[str]:
    """KEEP candidates that exist on disk. No invented SCENE template paths."""
    return existing_repo_paths(repo_root, N3_KEEP_DEFAULT)


def n3_prompt_paths(repo_root: Path) -> list[str]:
    """Same KEEP set as template_paths (F3 dual field)."""
    return n3_template_paths(repo_root)


def thicken_prompt_paths(repo_root: Path) -> list[str]:
    """KEEP paths actually used for thicken. No invented SCENE file."""
    return existing_repo_paths(repo_root, N3_KEEP_DEFAULT)


def thicken_skill_paths(repo_root: Path, *, include_bio_skill: bool = False) -> list[str]:
    """Optional bio skill only. Never includes .prompt (F3 / R2)."""
    if not include_bio_skill:
        return []
    paths = existing_repo_paths(repo_root, BIO_SKILL_PATHS)
    assert_no_prompt_in_skill_paths(paths)
    return paths


def thicken_observability(repo_root: Path, *, include_bio_skill: bool = False) -> dict[str, Any]:
    obs = n3_observability(repo_root)
    prompts = thicken_prompt_paths(repo_root)
    skills = thicken_skill_paths(repo_root, include_bio_skill=include_bio_skill)
    obs["prompt_paths"] = list(prompts)
    obs["template_paths"] = list(obs["template_paths"])
    obs["thicken_prompt_paths"] = list(prompts)
    obs["thicken_skill_paths"] = list(skills)
    obs["scene_template"] = dict(SCENE_TEMPLATE_PROVISIONAL)
    return obs


def n3_observability(repo_root: Path) -> dict[str, Any]:
    templates = n3_template_paths(repo_root)
    return {
        "template_paths": list(templates),
        "prompt_paths": list(templates),
        "scene_template": {
            "status": "deferred",
            "path": None,
            "note": "独立 SCENE 卡模板仍缺（LEARN D1 / F2）；本拍用 one_line stub，不发明 KEEP 路径",
        },
        "seedance_param_ref": {
            "path": SEEDANCE_PARAM_REF if (Path(repo_root) / SEEDANCE_PARAM_REF).is_file() else None,
            "role": "n4n5_param_ref",
            "in_n3_card_templates": False,
        },
    }


def assert_no_prompt_in_skill_paths(skill_paths: list[str] | None) -> None:
    """Invariant helper for tests / projection guards."""
    for path in skill_paths or []:
        if str(path).startswith(".prompt/") or "/.prompt/" in str(path):
            raise AssertionError(f".prompt leaked into skill_paths: {path}")
