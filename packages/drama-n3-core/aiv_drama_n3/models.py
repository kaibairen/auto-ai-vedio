from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class N3MaterializeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str | None = None
    unlock_edit: bool = False


class N3AttachRequest(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    kind: Literal["character", "scene"] | None = None
    actor: str | None = None


class N3PromoteRequest(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    kind: Literal["character", "scene"] | None = None
    actor: str | None = None
    note: str | None = None


class N3ForkRequest(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    kind: Literal["character", "scene"] | None = None
    actor: str | None = None


class LibraryAssetRefIn(BaseModel):
    model_config = {"extra": "forbid"}

    path: str = Field(min_length=1)
    md5: str | None = None
    role: str | None = None


class LibrarySceneWrite(BaseModel):
    """Thin SCENE stub seed. No invented KEEP template path."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    one_line: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    tags: list[str] = Field(default_factory=list)
    refs: list[LibraryAssetRefIn] = Field(default_factory=list)


class LibraryCharacterWriteN3(BaseModel):
    """Optional richer seed used by N3 library PUT (backward-compatible extras)."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    one_line: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    tags: list[str] = Field(default_factory=list)
    refs: list[LibraryAssetRefIn] = Field(default_factory=list)
