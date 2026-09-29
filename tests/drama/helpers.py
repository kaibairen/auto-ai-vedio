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
