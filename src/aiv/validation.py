from __future__ import annotations

import re

from aiv.curriculum import CHAR_LIMIT, TITLE_LIMIT_B
from aiv.errors import AppError

EP_RE = re.compile(r"^EP\d{2,}$")
PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
ACTOR_RE = re.compile(r"^[^\s]{1,128}$")


def count_chars(text: str) -> int:
    """Mechanical 字数: non-whitespace Unicode code points."""
    return sum(1 for ch in text if not ch.isspace())


def validate_project_id(project_id: str) -> str:
    if not PROJECT_RE.match(project_id):
        raise AppError(400, "invalid_project_id", "project_id must be alphanumeric/[_-]", project_id=project_id)
    return project_id


def validate_ep(ep: str) -> str:
    ep = ep.strip().upper()
    if not EP_RE.match(ep):
        raise AppError(400, "invalid_episode", "episode id must look like EP01", ep=ep)
    return ep


def validate_path(path: str) -> str:
    path = path.strip().upper()
    if path not in {"A", "B"}:
        raise AppError(400, "invalid_path", "path must be A (口水话) or B (长文章)", path=path)
    return path


def validate_actor(actor: str | None, *, required: bool = False) -> str:
    value = (actor or "").strip()
    if not value:
        if required:
            raise AppError(400, "actor_required", "gate confirm must record actor → confirmed_by")
        return ""
    if not ACTOR_RE.match(value):
        raise AppError(400, "invalid_actor", "actor must be a single non-empty token", actor=value)
    return value


def validate_char_limit(path: str, text: str, *, field: str = "body") -> int:
    limit = CHAR_LIMIT[path]
    n = count_chars(text)
    if n > limit:
        raise AppError(
            400,
            "char_limit",
            f"{field} exceeds path {path} limit {limit}",
            path=path,
            field=field,
            chars=n,
            limit=limit,
        )
    if n == 0:
        raise AppError(400, "empty_text", f"{field} is empty", field=field)
    return n


def validate_title_b(title: str) -> int:
    n = count_chars(title)
    if n == 0:
        raise AppError(400, "empty_text", "title is empty", field="title")
    if n > TITLE_LIMIT_B:
        raise AppError(
            400,
            "title_limit",
            f"path B title exceeds {TITLE_LIMIT_B} chars",
            chars=n,
            limit=TITLE_LIMIT_B,
        )
    return n


def reject_force_pass(payload: dict | None) -> None:
    if not payload:
        return
    if "force_pass" in payload and payload["force_pass"] is not None:
        raise AppError(
            400,
            "force_pass_forbidden",
            "ForcePass=never; no force_pass on G1 confirm",
        )
