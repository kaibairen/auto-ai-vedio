from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aiv_schema.models import LibraryRef


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class EpisodeCreate(BaseModel):
    episode_id: str
    pipeline_profile: Literal["drama"]
    title: str | None = None
    aspect_ratio: str | None = None
    target_duration_sec: int | None = None


class EpisodePatch(BaseModel):
    title: str | None = None
    aspect_ratio: str | None = None
    target_duration_sec: int | None = None


class PinObject(BaseModel):
    logline: str | None = None
    protagonist: str | None = None
    conflict: str | None = None
    genre_tags: list[str] | None = None
    raw: str | None = None

    model_config = {"extra": "allow"}


class DramaBriefWrite(BaseModel):
    title_intent: str | None = None
    pin: dict[str, Any] | None = None
    setting_notes: str | None = None
    lane_preference: Literal["female", "male", "unset"] | None = None
    preattached_character_ids: list[str] | None = None
    confirm_stale_outline: bool = False
    actor: str | None = None


class OutlineGenerateRequest(BaseModel):
    lane: Literal["female", "male"] | None = None
    provider: Literal["fixture", "llm"] | None = None
    shot_cap: int | None = Field(default=None, ge=1)
    actor: str | None = None


class OutlineWrite(BaseModel):
    body_md: str = Field(min_length=1)
    shot_cap: int | None = Field(default=None, ge=1)
    unlock_edit: bool = False
    actor: str | None = None


class OutlineResetRequest(BaseModel):
    clear_cast: bool = False
    unlock_edit: bool = False
    actor: str | None = None


class CastRowIn(BaseModel):
    id: str | None = None
    name: str
    one_line: str
    library_ref: LibraryRef | None = None


class CastWrite(BaseModel):
    lane: Literal["female", "male"] | None = None
    characters: list[CastRowIn]
    scenes: list[CastRowIn]
    unlock_edit: bool = False
    actor: str | None = None


class AttachRequest(BaseModel):
    character_id: str
    version: int = Field(ge=1)
    unlock_edit: bool = False
    actor: str | None = None


class DetachRequest(BaseModel):
    character_id: str
    unlock_edit: bool = False
    actor: str | None = None


class SidecarAddCharacterRequest(BaseModel):
    """O2: add a named CHAR after G1b lock without unlocking the gate or rewriting outline."""

    name: str = Field(min_length=1, max_length=64)
    one_line: str | None = None
    actor: str | None = None


class LibraryCharacterWrite(BaseModel):
    """Dogfood seed (OpenAPI has no list/search). Not promote/fork."""

    name: str = Field(min_length=1)
    one_line: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)


class GeneratedDraft(BaseModel):
    body_md: str
    lane: Literal["female", "male"]
    shot_cap: int
    characters: list[dict[str, Any]]
    scenes: list[dict[str, Any]]
    source_skills: list[str]
