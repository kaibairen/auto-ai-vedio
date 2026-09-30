"""F3 · N3 observability uses template_paths / prompt_paths only.

Never write .prompt into D-N1 / D-N2 skill_paths. 018b is not reopened.
SCENE card templates are DEFER — do not invent KEEP paths.
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
