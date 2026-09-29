from __future__ import annotations

import re

from aiv.curriculum import CHAR_LIMIT, TITLE_LIMIT_B, frameworks_for
from aiv.providers.base import GenerateRequest, GenerateResponse
from aiv.validation import count_chars

_CLAUSE = re.compile(r"[，。！？\n;；]")
_STOP = set("的了吗啊吧呢是在有和与或就把被让到从对为这那我你他她它还也都很可一个")
_PREFIXES = ("就是", "那个", "这个", "然后", "所以", "其实", "我觉得", "很多人")


def _clip(text: str, limit: int) -> str:
    buf: list[str] = []
    n = 0
    for ch in text:
        add = 0 if ch.isspace() else 1
        if n + add > limit:
            break
        buf.append(ch)
        n += add
    return "".join(buf).rstrip()


def _strip_prefixes(text: str) -> str:
    s = text.strip()
    changed = True
    while changed:
        changed = False
        for p in _PREFIXES:
            if s.startswith(p):
                s = s[len(p) :]
                changed = True
    return s


def _topic(raw: str) -> str:
    words = _seed_words(raw)
    return words[0] if words else "这段原料"


def _seed_words(raw: str) -> list[str]:
    grams: list[str] = []
    for clause in _CLAUSE.split(raw or ""):
        s = _strip_prefixes(clause)
        hans = "".join(ch for ch in s if "\u4e00" <= ch <= "\u9fff")
        for n in (3, 2, 4):
            if len(hans) >= n:
                g = hans[:n]
                if g[0] not in _STOP and g not in grams:
                    grams.append(g)
        if len(grams) >= 6:
            return grams
    latin = re.findall(r"[A-Za-z0-9]{2,}", raw or "")
    for w in latin:
        if w not in grams:
            grams.append(w)
        if len(grams) >= 6:
            break
    return grams or ["核心观点"]


class FixtureProvider:
    """Deterministic provider so tests/demo run without API keys."""

    name = "fixture"

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        topic = _topic(req.raw)
        keys = _seed_words(req.raw)
        limit = CHAR_LIMIT[req.path]
        if req.kind == "collect_raw":
            return GenerateResponse(
                kind="ack",
                message=f"已收到原料（{count_chars(req.raw)} 字）。是否进行下一步？",
            )
        if req.kind == "analyze":
            analysis = {
                "core_points": keys[:3],
                "keywords": keys,
                "logic": "提出现象 → 补充细节 → 给出可用建议",
                "golden": keys[0] if keys else topic,
                "faithful": True,
            }
            return GenerateResponse(
                kind="analysis",
                message="以下为忠于原意的拆解，未添加虚构情节。是否准确？确认后进行下一步。",
                analysis=analysis,
            )
        if req.kind == "choose_framework":
            names = req.frameworks or [frameworks_for(req.path)[0].name]
            return GenerateResponse(
                kind="frameworks",
                message="已记录所选框架。是否进行下一步，据此写口播？",
                frameworks=names,
            )
        if req.kind == "generate_candidates":
            chosen = req.frameworks or [f.name for f in frameworks_for("A")[:5]]
            candidates = []
            for i, name in enumerate(chosen[:5] if chosen else frameworks_for("A")):
                title, body = _path_a_piece(topic, keys, name if isinstance(name, str) else name, i)
                candidates.append(
                    {
                        "index": i,
                        "title": title,
                        "body": _clip(body, limit),
                        "chars": count_chars(_clip(body, limit)),
                        "framework": name if isinstance(name, str) else str(name),
                    }
                )
            # Always 5 pieces for path A (教材). Repeat last framework if fewer selected.
            catalog = [f.name for f in frameworks_for("A")]
            while req.path == "A" and len(candidates) < 5:
                i = len(candidates)
                name = catalog[i % len(catalog)]
                title, body = _path_a_piece(topic, keys, name, i)
                candidates.append(
                    {
                        "index": i,
                        "title": title,
                        "body": _clip(body, limit),
                        "chars": count_chars(_clip(body, limit)),
                        "framework": name,
                    }
                )
            return GenerateResponse(
                kind="candidates",
                message="已生成候选口播。请选一篇进入优化，或说明修改要求。",
                candidates=candidates,
            )
        if req.kind == "generate_titles":
            titles = [
                _clip(f"别再忽略{keys[0]}", TITLE_LIMIT_B),
                _clip(f"{keys[0]}背后的真相", TITLE_LIMIT_B),
                _clip(f"看完想立刻试试{keys[0][:4]}", TITLE_LIMIT_B),
            ]
            return GenerateResponse(
                kind="titles",
                message="3 个爆款标题如下。下一步请选标题并指定写作框架。",
                titles=titles,
            )
        if req.kind == "reconstruct":
            fw = (req.frameworks[0] if req.frameworks else frameworks_for("B")[0].name)
            title = req.title or (req.titles[req.pick or 0] if req.titles else f"关于{topic}")
            title = _clip(title, TITLE_LIMIT_B)
            body = _path_b_piece(topic, keys, fw)
            body = _clip(body, limit)
            return GenerateResponse(
                kind="draft",
                message="已按所选框架重构口播。是否进入第 6 步优化？",
                draft_title=title,
                draft_body=body,
                frameworks=[fw],
            )
        if req.kind == "optimize":
            if req.path == "A":
                pick = req.pick if req.pick is not None else 0
                if req.candidates and 0 <= pick < len(req.candidates):
                    chosen = req.candidates[pick]
                    title = req.title or chosen.get("title") or topic
                    body = chosen.get("body") or ""
                    fw = chosen.get("framework") or ""
                else:
                    title = req.title or topic
                    body = ""
                    fw = req.frameworks[0] if req.frameworks else ""
                note = req.notes.strip()
                if note:
                    body = f"{body}\n（按你的要求调整：{note}）"
                if not body:
                    title, body = _path_a_piece(topic, keys, fw or "惊喜揭秘型", 0)
                body = _clip(body, limit)
                return GenerateResponse(
                    kind="draft",
                    message="已输出定稿格式。确认后走门 G1（POST gates/g1/confirm）。",
                    draft_title=title,
                    draft_body=body,
                    frameworks=[fw] if fw else req.frameworks,
                )
            # path B optimize
            title = req.title or (req.titles[0] if req.titles else _clip(f"关于{topic}", TITLE_LIMIT_B))
            title = _clip(title, TITLE_LIMIT_B)
            fw = req.frameworks[0] if req.frameworks else frameworks_for("B")[0].name
            body = _path_b_piece(topic, keys, fw, tighter=True)
            if req.notes.strip():
                body = f"{body}\n（按你的要求调整：{req.notes.strip()}）"
            body = _clip(body, limit)
            return GenerateResponse(
                kind="draft",
                message="已输出不超过 500 字的优化定稿。确认后走门 G1。",
                draft_title=title,
                draft_body=body,
                frameworks=[fw],
            )
        return GenerateResponse(kind="ack", message="ok")


def _path_a_piece(topic: str, keys: list[str], framework: str, idx: int) -> tuple[str, str]:
    k0 = keys[0] if keys else "这件事"
    k1 = keys[1] if len(keys) > 1 else "一个细节"
    hooks = [
        f"每天被随手丢掉的{k0}，其实藏着你不知道的用处。",
        f"他只是普通人，可一次和{k0}有关的小事，把结果全改了。",
        f"你天天碰到{k0}，却很少有人把数字说清楚。",
        f"别再为{k0}发愁，有个小办法多数人没用过。",
        f"给自己 7 天，只盯住{k0}这一件事。",
    ]
    hook = hooks[idx % 5]
    body = (
        f"{hook}"
        f"很多人只看见表面，真正被忽略的是{k1}。"
        f"先看现象，再做一步：把{k0}用起来，而不是扔掉。"
        f"转折在于，省事的不是再买新工具，而是改这一个习惯。"
        f"框架是{framework}。"
        f"你还用过{k0}做什么？评论区只留一个做法。"
    )
    title = f"{k0}别再浪费"
    return title, body


def _path_b_piece(topic: str, keys: list[str], framework: str, *, tighter: bool = False) -> str:
    k0 = keys[0] if keys else "这件事"
    k1 = keys[1] if len(keys) > 1 else "一个细节"
    extra = "" if tighter else f"原文题眼是「{topic}」。"
    return (
        f"先把痛点说透：很多人卡在{k0}上，不是不懂，是缺一句能照做的话。"
        f"{extra}"
        f"文章拆开以后，真正能带走的只有{k1}这一层。"
        f"我按「{framework}」重写成口播：开头三秒给钩子，中间只讲一个转折，结尾只留一个行动。"
        f"不要同时做三件事。今天只做这一件：把{k0}落到一个能评论区回复的动作上。"
        f"如果你也有类似经历，扣1，我把步骤写在置顶。"
    )
