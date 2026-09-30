from __future__ import annotations

from typing import Any

from aiv_drama.config import Settings
from aiv_drama_n2.validate import STORYBOARD_SKILL_PATH, extract_bridge_ids


class FixtureStoryboardProvider:
    """Deterministic D-N2 draft from locked outline+cast. No network, no API key.

    O2: tags storyboard_skill=borrowed_dongman; does not inject Seedance 出片 Skill.
    O1: no independent script resource.
    """

    name = "fixture"
    skill_relpath = STORYBOARD_SKILL_PATH

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        *,
        episode_id: str,
        outline: dict[str, Any],
        cast: dict[str, Any],
        shot_cap: int,
        tool_profile: str | None,
    ) -> list[dict[str, Any]]:
        bridges = extract_bridge_ids(outline.get("body_md") or "") or ["B1"]
        chars = [c["id"] for c in (cast.get("characters") or []) if c.get("id")]
        scenes = [s["id"] for s in (cast.get("scenes") or []) if s.get("id")]
        lead = chars[0] if chars else "NONE"
        support = chars[1] if len(chars) > 1 else lead
        scene = scenes[0] if scenes else "NONE"
        alt_scene = scenes[1] if len(scenes) > 1 else scene
        bucket = "seedance:5" if tool_profile == "seedance_2" else None
        duration = 5 if tool_profile in {None, "seedance_2"} else {"kling": 5, "hailuo": 6, "veo": 8}.get(tool_profile, 5)
        if tool_profile == "kling":
            bucket = "kling:5"
        elif tool_profile == "hailuo":
            bucket = "hailuo:6"
            duration = 6
        elif tool_profile == "veo":
            bucket = "veo:8"
            duration = 8

        templates = [
            ("MS", "PUSH", "开场立住冲突，推门入画", lead, scene, None, "cut", "基础", "angle:eye"),
            ("CU", "STATIC", "眼神一凛，压住场面", lead, scene, "你终于来了", "cut", "基础", "subtitle:yes"),
            ("LS", "TRACK", "跟至场中立规", lead, scene, None, "cut", "基础", "angle:eye"),
            ("MS", "PAN_H", "对手施压，中段加压", support, alt_scene, None, "cut", "中度", "angle:eye"),
            ("CU", "PUSH", "亮出底牌，主爽翻转", lead, alt_scene, None, "cut", "中度", "angle:low"),
            ("ECU", "STATIC", "集尾钩子特写，悬念落点", lead, alt_scene, None, "cut", "基础", "subtitle:yes"),
        ]
        # Map templates onto bridges (repeat last bridge if more shots than bridges).
        count = min(shot_cap, max(len(bridges), 1), len(templates))
        # Prefer covering every bridge at least once.
        count = min(shot_cap, max(count, min(len(bridges), shot_cap)))
        rows: list[dict[str, Any]] = []
        for i in range(count):
            size, camera, action, cid, sid, dialogue, transition, dynamic, notes = templates[i % len(templates)]
            bridge = bridges[i] if i < len(bridges) else bridges[-1]
            char_ids = [cid] if cid != "NONE" else ["NONE"]
            rows.append(
                {
                    "shot_id": f"S{i + 1:02d}",
                    "bridge_id": bridge,
                    "seq": i + 1,
                    "duration_s": duration,
                    "shot_size": size,
                    "camera": camera,
                    "action": action,
                    "char_ids": char_ids,
                    "scene_id": sid,
                    "dialogue": dialogue,
                    "transition": transition,
                    "dynamic_level": dynamic,
                    "tool_duration_bucket": bucket,
                    "grid_strict": size in {"CU", "ECU"},
                    "notes": notes,
                }
            )
        # If more bridges than templates, add one coverage shot per remaining bridge.
        if len(bridges) > count and count < shot_cap:
            for extra in bridges[count:]:
                if len(rows) >= shot_cap:
                    break
                n = len(rows) + 1
                rows.append(
                    {
                        "shot_id": f"S{n:02d}",
                        "bridge_id": extra,
                        "seq": n,
                        "duration_s": duration,
                        "shot_size": "MS",
                        "camera": "STATIC",
                        "action": f"{episode_id} 桥段 {extra} 补镜",
                        "char_ids": [lead] if lead != "NONE" else ["NONE"],
                        "scene_id": scene,
                        "dialogue": None,
                        "transition": "cut",
                        "dynamic_level": "基础",
                        "tool_duration_bucket": bucket,
                        "grid_strict": False,
                        "notes": "angle:eye",
                    }
                )
        return rows
