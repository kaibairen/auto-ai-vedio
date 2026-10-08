from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SegmentVideoRequest(BaseModel):
    model_config = {"extra": "forbid"}

    prompt_sha256: str = Field(min_length=1)
    ref_md5s: list[str] = Field(default_factory=list)
    tool_profile: Literal["seedance_2"]
    actor: str | None = None
    user_consent: bool = False


class OutputRegisterRequest(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["image", "segment_video", "rough_cut", "subtitle", "audio_mix", "audio_stem", "tts_line"]
    path: str = Field(min_length=1)
    md5: str = Field(min_length=1)
    bytes: int = Field(ge=0)
    parent_md5: str | None = None
    actor: str | None = None


class RoughCutRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str = Field(min_length=1)
    video_stream_md5: str = Field(min_length=1)
    audio_md5: str = Field(min_length=1)
    subtitle_md5: str | None = None
    parent_version: str | None = None
    actor: str | None = None


class SeamMeasureRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str | None = None
    ruleset_md5: str = Field(min_length=1)
    actor: str | None = None


class SubtitleInPoint(BaseModel):
    model_config = {"extra": "forbid"}

    line_no: int
    in_s: float
    out_s: float


class SubtitlePutRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str | None = None
    body_sha256: str = Field(min_length=1)
    in_points: list[SubtitleInPoint]
    actor: str | None = None


class AudioBedSource(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1)
    md5: str = Field(min_length=1)
    license: str = Field(min_length=1)


class AudioBedRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str = Field(min_length=1)
    spec_md5: str = Field(min_length=1)
    sources: list[AudioBedSource]
    actor: str | None = None


class AudioVoiceRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str = Field(min_length=1)
    line_no: int
    take_md5: str = Field(min_length=1)
    in_s: float
    actor: str | None = None


class ReviewRequest(BaseModel):
    model_config = {"extra": "forbid"}

    level: Literal["L1", "L2", "L3"]
    subject_md5: str = Field(min_length=1)
    verdict: Literal["pass", "conditional", "fail"]
    actor: str = Field(min_length=1)


class OpenItemRequest(BaseModel):
    model_config = {"extra": "forbid"}

    review_id: str = Field(min_length=1)
    item_no: int
    state: Literal["blocks_l2", "waiting_on_user", "non_blocking", "closed"]
    owner: str | None = None
    text: str = Field(min_length=1)


class OpenItemCloseRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    file_md5: str = Field(min_length=1)


class CostEntryRequest(BaseModel):
    model_config = {"extra": "forbid"}

    provider: str = Field(min_length=1)
    operation: Literal["seedream", "seedance", "tts", "llm"]
    amount: float
    currency: str = Field(min_length=1)
    ref_id: str = Field(min_length=1)
    actor: str | None = None
