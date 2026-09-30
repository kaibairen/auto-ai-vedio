from __future__ import annotations

from aiv_drama.models import (
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
            DramaBriefWrite(title_intent=title, lane_preference=lane or "unset"),  # type: ignore[arg-type]
        )
    return pid


def generate_ready(svc: DramaService, pid: str, lane: str = "female"):
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
