from __future__ import annotations

from aiv_drama.intent import analyze_lane_conflict, resolve_hero_one_line
from aiv_drama.models import (
    ConfirmDramaIntentRequest,
    DramaBriefWrite,
    EpisodeCreate,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
    ProjectCreate,
)
from aiv_drama.service import DramaService


def seed_project_episode(
    svc: DramaService,
    *,
    title: str | None = "被流放的庶女在边关翻盘",
    lane: str | None = "female",
    with_library: bool = True,
    hero_one_line: str | None = "重生女主",
):
    proj = svc.create_project(ProjectCreate(name="短剧狗粮-01"))["project"]
    pid = proj["id"]
    if with_library:
        svc.put_library_character(
            pid,
            "CHAR-01",
            LibraryCharacterWrite(name="林晚", one_line="重生女主", version=3),
        )
    svc.create_episode(pid, EpisodeCreate(episode_id="EP01", pipeline_profile="drama", title="第一集"))
    if title is not None:
        svc.put_brief(
            pid,
            "EP01",
            DramaBriefWrite(
                title_intent=title,
                lane_preference=lane or "unset",  # type: ignore[arg-type]
                hero_one_line=hero_one_line,
            ),
        )
    return pid


def persist_and_confirm_intent(
    svc: DramaService,
    pid: str,
    *,
    ep: str = "EP01",
    lane: str | None = None,
    actor: str = "eng-018a",
    follow_precast: bool = True,
):
    rec = svc._rec(pid, ep)
    brief = rec.get("brief") or {}
    cards = svc._resolve_preattached_characters(pid, rec)
    pref = brief.get("lane_preference")
    write: dict = {}
    if pref not in {"female", "male"} and lane in {"female", "male"}:
        write["lane_preference"] = lane
        pref = lane
    if follow_precast:
        conflict = analyze_lane_conflict(pref, cards)
        if conflict["conflict"] and conflict["suggested_lane"]:
            write["lane_preference"] = conflict["suggested_lane"]
    if not resolve_hero_one_line(brief, cards):
        write["hero_one_line"] = "重生女主"
    if write:
        svc.put_brief(
            pid,
            ep,
            DramaBriefWrite(
                title_intent=brief.get("title_intent") or "一句",
                pin=brief.get("pin"),
                setting_notes=brief.get("setting_notes"),
                lane_preference=write.get("lane_preference") or pref or "unset",  # type: ignore[arg-type]
                hero_one_line=write.get("hero_one_line") or brief.get("hero_one_line"),
                preattached_character_ids=brief.get("preattached_character_ids"),
            ),
        )
    return svc.confirm_intent(pid, ep, ConfirmDramaIntentRequest(actor=actor), raw={"actor": actor})


def generate_ready(svc: DramaService, pid: str, lane: str = "female"):
    persist_and_confirm_intent(svc, pid, lane=lane)
    return svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane=lane, provider="fixture"),
        raw={"lane": lane, "provider": "fixture"},
    )


def lock_g1b(svc: DramaService, pid: str, ep: str = "EP01", actor: str = "yangzhou"):
    generate_ready(svc, pid)
    return svc.confirm_gate(pid, ep, {"decision": "pass", "actor": actor})


def sample_row(
    *,
    shot_id: str = "S01",
    bridge_id: str = "B1",
    seq: int = 1,
    char_ids: list[str] | None = None,
    scene_id: str = "SCENE-01",
    **kw,
) -> dict:
    row = {
        "shot_id": shot_id,
        "bridge_id": bridge_id,
        "seq": seq,
        "duration_s": 5,
        "shot_size": "MS",
        "camera": "PUSH",
        "action": "推门入室环顾",
        "char_ids": char_ids if char_ids is not None else ["CHAR-01"],
        "scene_id": scene_id,
        "dialogue": None,
        "transition": "cut",
        "dynamic_level": "基础",
        "tool_duration_bucket": None,
        "grid_strict": False,
        "notes": "angle:eye",
    }
    row.update(kw)
    return row
