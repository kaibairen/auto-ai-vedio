from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StoryboardRowWrite(BaseModel):
    model_config = {"extra": "forbid"}

    shot_id: str | None = None
    bridge_id: str
    seq: int = Field(ge=1)
    duration_s: int = Field(ge=1)
    shot_size: str
    camera: str
    action: str = Field(min_length=1)
    char_ids: list[str]
    scene_id: str
    dialogue: str | None = None
    transition: str | None = None
    dynamic_level: str | None = None
    tool_duration_bucket: str | None = None
    grid_strict: bool = False
    notes: str | None = None


class StoryboardWrite(BaseModel):
    model_config = {"extra": "forbid"}

    rows: list[StoryboardRowWrite]
    tool_profile: Literal["seedance_2", "kling", "hailuo", "veo"] | None = None
    storyboard_skill: Literal["borrowed_dongman", "custom", "unset"] | None = None
    unlock_edit: bool = False
    actor: str | None = None


class StoryboardGenerateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    provider: Literal["fixture", "llm", "skill"] | None = None
    tool_profile: Literal["seedance_2", "kling", "hailuo", "veo"] | None = None
    storyboard_skill: Literal["borrowed_dongman", "custom"] = "borrowed_dongman"
    unlock_edit: bool = False
    actor: str | None = None
    shot_cap_override: int | None = Field(default=None, ge=1, le=12)


class StoryboardReorderRequest(BaseModel):
    model_config = {"extra": "forbid"}

    shot_ids: list[str] = Field(min_length=1, max_length=12)
    actor: str | None = None


class StoryboardResetRequest(BaseModel):
    model_config = {"extra": "forbid"}

    unlock_edit: bool = False
    actor: str | None = None


class StoryboardValidateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str | None = None
