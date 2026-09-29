from __future__ import annotations

from aiv.models import Framework, StepSpec

# Mechanical limits from NODE-SPEC / koubo prompts (教材).
CHAR_LIMIT = {"A": 400, "B": 500}
TITLE_LIMIT_B = 20

# Path B source defect: `.prompt/koubo-长文章.md` jumps 2 → 4 (no step 3).
# Wizard skips step 3. Do not rewrite the prompt file to "fix" the curriculum.
PATH_B_SKIPPED_STEPS = (3,)
PATH_B_SKIP_REASON = (
    "source defect in .prompt/koubo-长文章.md: missing step 3 "
    "(and frameworks 7/8 are garbled). Wizard skips step 3; "
    "prompt file is read-only and is not rewritten."
)

PATH_A_FRAMEWORKS: list[Framework] = [
    Framework(id="surprise", name="惊喜揭秘型", summary="钩子→引入→问题展开→转折→揭秘→呼吁行动"),
    Framework(id="story", name="故事叙述型", summary="钩子→人物介绍→冲突/事件→高潮→转折→结局和教训"),
    Framework(id="data", name="数据惊人型", summary="钩子→引入→惊人数据→解释意义→悬念→互动提问"),
    Framework(id="tips", name="生活技巧分享型", summary="钩子→问题引入→解决方案→实操演示→转折→互动呼吁"),
    Framework(id="challenge", name="日常挑战型", summary="钩子→挑战介绍→规则→执行→悬念→邀请参与"),
]

# Names kept as in the source prompt, including defective 7/8.
PATH_B_FRAMEWORKS: list[Framework] = [
    Framework(id="pain", name="痛点共鸣式", summary="引入痛点→共鸣故事→解决方法→情感总结→呼吁行动"),
    Framework(id="heal", name="温暖治愈式", summary="温馨开头→感人故事→情感分析→治愈方法→结尾感悟"),
    Framework(id="suspense", name="悬念引导式", summary="悬念开头→情感铺垫→高潮转折→解决方案→呼吁行动"),
    Framework(id="celebrity", name="名人故事式", summary="引入名人→故事细节→情感共鸣→启示与感悟→鼓励分享"),
    Framework(id="contrast", name="反差对比式", summary="对比开头→详细描述→反差分析→解决方法→呼吁行动"),
    Framework(id="detail", name="小细节打动式", summary="引入细节→细节故事→情感放大→共鸣总结→呼吁分享"),
    Framework(
        id="dialogue",
        name="情感对话式",
        summary="源缺陷：教材条目不完整（对话展开后与框架八串行）",
        defective=True,
    ),
    Framework(
        id="memory",
        name="回忆怀/日式",
        summary="源缺陷：教材标题与条目错乱（怀旧/对话块串行）",
        defective=True,
    ),
    Framework(id="growth", name="困境成长式", summary="困境开头→困境故事→成长转折→解决方法→鼓励成长"),
    Framework(id="inspire", name="励志启示式", summary="励志开头→励志故事→情感共鸣→鼓励建议→呼吁行动"),
]

_STEP_A: dict[int, dict] = {
    1: {
        "kind": "collect_raw",
        "label": "第1步：提供日常「口水话」文字。提交后询问是否进行下一步。",
        "accepts": ["text"],
    },
    2: {
        "kind": "analyze",
        "label": "第2步：确认核心要点、关键词、表达逻辑或金句（忠于原意，禁止夸大虚构）。",
        "accepts": ["confirm", "notes"],
    },
    3: {
        "kind": "choose_framework",
        "label": "第3步：从 5 种口播框架中选择 1 个或多个。",
        "accepts": ["frameworks"],
    },
    4: {
        "kind": "generate_candidates",
        "label": "第4步：按已选框架各写一篇情绪化口播，每篇不超过 400 字。",
        "accepts": ["confirm", "notes"],
    },
    5: {
        "kind": "optimize",
        "label": "第5步：选择一篇并优化，输出［标题］+ 文案内容。",
        "accepts": ["pick", "notes", "title"],
    },
}

_STEP_B: dict[int, dict] = {
    1: {
        "kind": "collect_raw",
        "label": "第1步：提供爆款长文章。提交后询问是否进行下一步。",
        "accepts": ["text"],
    },
    2: {
        "kind": "analyze",
        "label": "第2步：拆解文章结构、关键词、风格；确认理解是否准确。",
        "accepts": ["confirm", "notes"],
    },
    3: {
        "kind": "skipped_source_defect",
        "label": "第3步：教材缺步，向导跳过（不改 .prompt/koubo-长文章.md）。",
        "accepts": [],
        "skipped": True,
        "skip_reason": PATH_B_SKIP_REASON,
    },
    4: {
        "kind": "generate_titles",
        "label": "第4步：输出 3 个情绪化爆款标题（各不超过 20 字）供选择。",
        "accepts": ["confirm", "notes"],
    },
    5: {
        "kind": "reconstruct",
        "label": "第5步：先看 10 个写作框架并选择，再生成不超过 500 字的口播重构。",
        "accepts": ["frameworks", "pick", "title", "notes"],
    },
    6: {
        "kind": "optimize",
        "label": "第6步：再次优化，输出不超过 500 字的定稿（强标题、钩子、单 CTA）。",
        "accepts": ["notes", "title"],
    },
}


def char_limit(path: str) -> int:
    return CHAR_LIMIT[path]


def prompt_relpath(path: str) -> str:
    return ".prompt/koubo-口水话.md" if path == "A" else ".prompt/koubo-长文章.md"


def frameworks_for(path: str) -> list[Framework]:
    return PATH_A_FRAMEWORKS if path == "A" else PATH_B_FRAMEWORKS


def steps_for(path: str) -> list[int]:
    if path == "A":
        return [1, 2, 3, 4, 5]
    return [1, 2, 4, 5, 6]


def all_declared_steps(path: str) -> list[int]:
    return [1, 2, 3, 4, 5] if path == "A" else [1, 2, 3, 4, 5, 6]


def skipped_steps(path: str) -> list[int]:
    return list(PATH_B_SKIPPED_STEPS) if path == "B" else []


def is_skipped(path: str, step: int) -> bool:
    return path == "B" and step in PATH_B_SKIPPED_STEPS


def is_last_step(path: str, step: int) -> bool:
    seq = steps_for(path)
    return bool(seq) and step == seq[-1]


def next_step_after(path: str, completed: list[int]) -> int | None:
    done = set(completed)
    for step in steps_for(path):
        if step not in done:
            return step
    return None


def allowed_steps(path: str, completed: list[int], *, locked: bool = False) -> list[int]:
    if locked:
        return []
    nxt = next_step_after(path, completed)
    return [nxt] if nxt is not None else []


def resolve_frameworks(path: str, values: list[str]) -> list[Framework]:
    catalog = frameworks_for(path)
    by_id = {f.id: f for f in catalog}
    by_name = {f.name: f for f in catalog}
    # also allow "1" / "框架一"
    by_index = {str(i + 1): f for i, f in enumerate(catalog)}
    out: list[Framework] = []
    seen: set[str] = set()
    for raw in values:
        key = raw.strip()
        if not key:
            continue
        found = by_id.get(key) or by_name.get(key) or by_index.get(key)
        if found is None:
            continue
        if found.id in seen:
            continue
        seen.add(found.id)
        out.append(found)
    return out


def step_spec(path: str, step: int) -> StepSpec:
    table = _STEP_A if path == "A" else _STEP_B
    raw = table.get(step)
    if raw is None:
        raise KeyError(f"unknown step {step} for path {path}")
    skipped = bool(raw.get("skipped"))
    return StepSpec(
        step=step,
        kind=raw["kind"],
        label=raw["label"],
        accepts=list(raw["accepts"]),
        skipped=skipped,
        skip_reason=raw.get("skip_reason"),
        char_limit=char_limit(path) if raw["kind"] in {"generate_candidates", "reconstruct", "optimize"} else None,
        frameworks=frameworks_for(path)
        if raw["kind"] in {"choose_framework", "reconstruct"}
        else None,
    )
