"""Request models for gaps 10–18. extra=forbid → unknown fields are 422."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OutputKind = Literal[
    "image",
    "segment_video",
    "rough_cut",
    "subtitle",
    "audio_mix",
    "audio_stem",
    "tts_line",
]
OpenItemState = Literal["blocks_l2", "waiting_on_user", "non_blocking", "closed"]
ReviewLevel = Literal["L1", "L2", "L3"]
ReviewVerdict = Literal["pass", "conditional", "fail"]
CostOperation = Literal["seedream", "seedance", "tts", "llm"]


class SegmentVideoRequest(BaseModel):
    model_config = {"extra": "forbid"}

    prompt_sha256: str = Field(min_length=1)
    ref_md5s: list[str] = Field(default_factory=list)
    tool_profile: Literal["seedance_2"] = "seedance_2"
    actor: str | None = None


class OutputRegisterRequest(BaseModel):
    model_config = {"extra": "forbid"}

    kind: OutputKind
    path: str = Field(min_length=1)
    md5: str = Field(min_length=32, max_length=32)
    bytes: int = Field(ge=0)
    parent_md5: str | None = None
    actor: str | None = None


class RoughCutRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str = Field(min_length=1)
    video_stream_md5: str = Field(min_length=32, max_length=32)
    audio_md5: str = Field(min_length=32, max_length=32)
    subtitle_md5: str | None = None
    parent_version: str | None = None
    actor: str | None = None


class SeamMeasureRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str | None = None
    ruleset_md5: str = Field(min_length=32, max_length=32)
    actor: str | None = None


class SubtitleInPoint(BaseModel):
    model_config = {"extra": "forbid"}

    line_no: int = Field(ge=1)
    in_s: float
    out_s: float


class SubtitleWriteRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str | None = None
    body_sha256: str = Field(min_length=64, max_length=64)
    in_points: list[SubtitleInPoint] = Field(default_factory=list)
    actor: str | None = None


class AudioBedSource(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1)
    md5: str = Field(min_length=32, max_length=32)
    license: str = Field(min_length=1)


class AudioBedRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str = Field(min_length=1)
    spec_md5: str = Field(min_length=32, max_length=32)
    sources: list[AudioBedSource] = Field(default_factory=list)
    actor: str | None = None


class AudioVoiceRequest(BaseModel):
    model_config = {"extra": "forbid"}

    version: str = Field(min_length=1)
    line_no: int = Field(ge=1)
    take_md5: str = Field(min_length=32, max_length=32)
    in_s: float
    actor: str | None = None


class ReviewCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    level: ReviewLevel
    subject_md5: str = Field(min_length=32, max_length=32)
    verdict: ReviewVerdict
    actor: str = Field(min_length=1)


class OpenItemCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    review_id: str = Field(min_length=1)
    item_no: int = Field(ge=1)
    state: OpenItemState
    owner: str = Field(min_length=1)
    text: str = Field(min_length=1)


class OpenItemCloseRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    file_md5: str = Field(min_length=32, max_length=32)


class OpenItemConclusionRequest(BaseModel):
    """Record a conclusion text. Does not close and does not grant user identity."""

    model_config = {"extra": "forbid"}

    conclusion: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    user: bool = False  # ignored; identity must already be recorded


class OpenItemConsentRequest(BaseModel):
    """Prior user identity for an open item. Same class as redraw-consent."""

    model_config = {"extra": "forbid"}

    user: bool
    actor: str | None = None


class RedrawConsentRequest(BaseModel):
    """User redraw consent. Engineering cannot grant this on generate-look."""

    model_config = {"extra": "forbid"}

    user: bool
    actor: str | None = None


class CostEntryRequest(BaseModel):
    model_config = {"extra": "forbid"}

    provider: str = Field(min_length=1)
    operation: CostOperation
    amount: float
    currency: str = "CNY"
    ref_id: str = Field(min_length=1)
    actor: str | None = None
    episode_id: str | None = None
