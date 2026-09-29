from __future__ import annotations

from typing import Any

from aiv_drama.config import SKILL_PATHS, Settings
from aiv_drama.models import GeneratedDraft


class FixtureProvider:
    """Deterministic D-N1 draft. No network, no API key."""

    name = "fixture"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        *,
        episode_id: str,
        lane: str,
        shot_cap: int,
        brief: dict[str, Any],
    ) -> GeneratedDraft:
        title = (brief.get("title_intent") or "").strip()
        pin = brief.get("pin") or {}
        if not title and isinstance(pin, dict):
            title = (pin.get("logline") or pin.get("raw") or pin.get("conflict") or "未命名题材").strip()
        title = title or "未命名题材"
        notes = (brief.get("setting_notes") or "").strip()
        setting = notes or ("架空古代边关" if lane == "female" else "都市底层翻盘")
        n = episode_id.lstrip("EP").lstrip("0") or "1"

        if lane == "female":
            chars = [
                {"name": "林晚", "one_line": "被流放的庶女 / 重生女主"},
                {"name": "谢衡", "one_line": "边关主将，旧识"},
            ]
            scenes = [
                {"name": "边关营帐", "one_line": "开场受辱与立规"},
                {"name": "校场", "one_line": "身份反转主爽"},
            ]
            body = f"""# 第 {n} 集大纲

- 题材 / 赛道：女频 · 身份反转 · {title}
- 设定：{setting}
- 主要人物（姓名 · 一句话身份）：林晚 · 被流放的庶女/重生女主；谢衡 · 边关主将
- 场景清单（场景名 · 一句话）：边关营帐 · 开场流放；校场 · 翻盘立威
- 桥段序列：
  1. 开篇钩子：林晚被押至边关，当众受辱（镜1–2）
  2. 立规：她用旧部暗记反将押解官，营帐内立住脚跟
  3. 中段加压（40–60%）：谢衡误认她为替死鬼，当众质疑
  4. 主爽（70–85%）：林晚亮出令牌，身份反转，校场肃静
  5. 集尾悬念：城外狼烟起，观众想看她下一集如何守关
- 爽点 / 钩子位置：钩子镜1–2；中段 40–60%；主爽 70–85%；集尾悬念末镜
- 预计镜头数上限：{shot_cap}
"""
        else:
            chars = [
                {"name": "陈铮", "one_line": "被贬边军的废物少爷"},
                {"name": "赵缺", "one_line": "克扣军饷的副将"},
            ]
            scenes = [
                {"name": "城门校场", "one_line": "当众受辱与立威"},
                {"name": "夜巡城墙", "one_line": "预知兑现、反杀"},
            ]
            body = f"""# 第 {n} 集大纲

- 题材 / 赛道：男频 · 身份/预知 · {title}
- 设定：{setting}
- 主要人物（姓名 · 一句话身份）：陈铮 · 被贬边军的废物少爷；赵缺 · 克扣军饷的副将
- 场景清单（场景名 · 一句话）：城门校场 · 当众受辱；夜巡城墙 · 反杀立威
- 桥段序列：
  1. 开篇钩子：陈铮披罪旗入城，赵缺当众折辱（镜1–2）
  2. 立规：他按预知避开伏击，第一次打脸
  3. 中段加压（40–60%）：军心动摇，旧部被扣为人质
  4. 主爽（70–85%）：夜巡揭克扣账册，当众反将赵缺
  5. 集尾悬念：北营调令到，观众想看他下一集如何接盘死局
- 爽点 / 钩子位置：钩子镜1–2；中段 40–60%；主爽 70–85%；集尾悬念末镜
- 预计镜头数上限：{shot_cap}
"""

        return GeneratedDraft(
            body_md=body.strip() + "\n",
            lane=lane,  # type: ignore[arg-type]
            shot_cap=shot_cap,
            characters=chars,
            scenes=scenes,
            source_skills=[SKILL_PATHS[lane]],
        )
