from __future__ import annotations

from typing import Any

# Path B source defect: .prompt/koubo-长文章.md has no step 3.
# Wizard exposes b3_skipped; does not rewrite the prompt. provisional:P-D1
PATH_B_SKIP_REASON = (
    "source defect in .prompt/koubo-长文章.md: missing step 3 "
    "(frameworks 7/8 garbled). Session records defects; prompt file is read-only."
)

PATH_A_STEPS = ["a1_raw", "a2_extract", "a3_framework", "a4_candidates", "a5_finalize"]
PATH_B_STEPS = [
    "b1_raw",
    "b2_analyze",
    "b3_skipped",
    "b4_titles",
    "b5_framework_draft",
    "b6_finalize",
]

PATH_A_FRAMEWORKS = [
    {"id": "surprise", "name": "惊喜揭秘型", "summary": "钩子→引入→问题展开→转折→揭秘→呼吁行动", "defective": False},
    {"id": "story", "name": "故事叙述型", "summary": "钩子→人物介绍→冲突→高潮→转折→结局和教训", "defective": False},
    {"id": "data", "name": "数据惊人型", "summary": "钩子→引入→惊人数据→解释意义→悬念→互动提问", "defective": False},
    {"id": "tips", "name": "生活技巧分享型", "summary": "钩子→问题引入→解决方案→实操→转折→互动呼吁", "defective": False},
    {"id": "challenge", "name": "日常挑战型", "summary": "钩子→挑战介绍→规则→执行→悬念→邀请参与", "defective": False},
]

PATH_B_FRAMEWORKS = [
    {"id": "pain", "name": "痛点共鸣式", "short": "痛点共鸣", "summary": "引入痛点→共鸣故事→解决方法→情感总结→呼吁行动", "defective": False},
    {"id": "heal", "name": "温暖治愈式", "short": "温暖治愈", "summary": "温馨开头→感人故事→情感分析→治愈方法→结尾感悟", "defective": False},
    {"id": "suspense", "name": "悬念引导式", "short": "悬念引导", "summary": "悬念开头→情感铺垫→高潮转折→解决方案→呼吁行动", "defective": False},
    {"id": "celebrity", "name": "名人故事式", "short": "名人故事", "summary": "引入名人→故事细节→情感共鸣→启示与感悟→鼓励分享", "defective": False},
    {"id": "contrast", "name": "反差对比式", "short": "反差对比", "summary": "对比开头→详细描述→反差分析→解决方法→呼吁行动", "defective": False},
    {"id": "detail", "name": "小细节打动式", "short": "小细节打动", "summary": "引入细节→细节故事→情感放大→共鸣总结→呼吁分享", "defective": False},
    {
        "id": "dialogue",
        "name": "情感对话式",
        "short": "情感对话",
        "summary": "源缺陷：教材条目不完整，与框架八串行",
        "defective": True,
    },
    {
        "id": "memory",
        "name": "回忆怀/日式",
        "short": "回忆怀旧",
        "summary": "源缺陷：教材标题与条目错乱",
        "defective": True,
    },
    {"id": "growth", "name": "困境成长式", "short": "困境成长", "summary": "困境开头→成长转折→解决方法→鼓励成长", "defective": False},
    {"id": "inspire", "name": "励志启示式", "short": "励志启示", "summary": "励志开头→情感共鸣→鼓励建议→呼吁行动", "defective": False},
]

_SPECS: dict[str, dict[str, Any]] = {
    "a1_raw": {"kind": "collect_raw", "label": "第1步：提供日常「口水话」文字。", "accepts": ["raw_text"]},
    "a2_extract": {"kind": "analyze", "label": "第2步：确认核心要点、关键词、金句（忠于原意）。", "accepts": ["decision", "notes"]},
    "a3_framework": {"kind": "choose_framework", "label": "第3步：从 5 种口播框架中选择。", "accepts": ["frameworks", "framework"]},
    "a4_candidates": {"kind": "generate_candidates", "label": "第4步：生成 5 篇口播（各 ≤400 字）。", "accepts": ["decision"]},
    "a5_finalize": {"kind": "optimize", "label": "第5步：选一篇并优化定稿。", "accepts": ["candidate_id", "edits"]},
    "b1_raw": {"kind": "collect_raw", "label": "第1步：提供爆款长文章。", "accepts": ["raw_text"]},
    "b2_analyze": {"kind": "analyze", "label": "第2步：拆解结构、关键词、风格并确认。", "accepts": ["decision", "notes"]},
    "b3_skipped": {
        "kind": "skipped_source_defect",
        "label": "第3步：教材缺步（源缺陷）。已知晓后继续，不改 .prompt/koubo-长文章.md。",
        "accepts": ["ack_defect", "ack_source_gap"],
        "skipped": True,
        "skip_reason": PATH_B_SKIP_REASON,
    },
    "b4_titles": {"kind": "generate_titles", "label": "第4步：选择 3 个爆款标题之一（各 ≤20 字）。", "accepts": ["title_id", "title"]},
    "b5_framework_draft": {
        "kind": "reconstruct",
        "label": "第5步：选写作框架并生成 ≤500 字口播。",
        "accepts": ["framework", "frameworks", "human_revised_frameworks"],
    },
    "b6_finalize": {"kind": "optimize", "label": "第6步：优化定稿（强标题、钩子、单 CTA）。", "accepts": ["decision", "edits"]},
}


def steps_for(path: str) -> list[str]:
    return list(PATH_A_STEPS if path == "A" else PATH_B_STEPS)


def first_step(path: str) -> str:
    return steps_for(path)[0]


def last_step(path: str) -> str:
    return steps_for(path)[-1]


def next_step(path: str, completed: list[str]) -> str | None:
    done = set(completed)
    for step in steps_for(path):
        if step not in done:
            return step
    return None


def prompt_relpath(path: str) -> str:
    return ".prompt/koubo-口水话.md" if path == "A" else ".prompt/koubo-长文章.md"


def frameworks_for(path: str) -> list[dict[str, Any]]:
    return PATH_A_FRAMEWORKS if path == "A" else PATH_B_FRAMEWORKS


def resolve_frameworks(path: str, values: list[str]) -> list[dict[str, Any]]:
    catalog = frameworks_for(path)
    by: dict[str, dict[str, Any]] = {}
    for i, f in enumerate(catalog):
        by[f["id"]] = f
        by[f["name"]] = f
        by[str(i + 1)] = f
        if f.get("short"):
            by[f["short"]] = f
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        key = (raw or "").strip()
        found = by.get(key)
        if found and found["id"] not in seen:
            seen.add(found["id"])
            out.append(found)
    return out


def step_spec(step: str) -> dict[str, Any]:
    raw = _SPECS.get(step)
    if not raw:
        raise KeyError(step)
    return {"step": step, **raw}
