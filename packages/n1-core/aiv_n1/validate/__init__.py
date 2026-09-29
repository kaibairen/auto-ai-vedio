from __future__ import annotations

import re
import unicodedata

from aiv_n1.errors import AppError

EP_RE = re.compile(r"^EP\d{2,}$")
PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
CHAR_LIMIT = {"A": 400, "B": 500}
TITLE_LIMIT_B = 20


def count_chars(text: str) -> int:
    """NFC code-point length after strip. Internal whitespace counts. See docs/n1.md."""
    return len(unicodedata.normalize("NFC", (text or "").strip()))


def draft_chars(title: str, body: str) -> int:
    """Title + body plain text, no ［标题］ / 文案内容： labels."""
    return count_chars(title) + count_chars(body)


def validate_project_id(project_id: str) -> str:
    if not PROJECT_RE.match(project_id):
        raise AppError(400, "validation", "invalid project_id", project_id=project_id)
    return project_id


def validate_ep(ep: str) -> str:
    ep = ep.strip().upper()
    if not EP_RE.match(ep):
        raise AppError(400, "validation", "episode id must look like EP01", ep=ep)
    return ep


def validate_path(path: str) -> str:
    path = (path or "A").strip().upper()
    if path not in {"A", "B"}:
        raise AppError(400, "validation", "path must be A or B", path=path)
    return path


def validate_actor(actor: str | None, *, required: bool = False) -> str:
    value = (actor or "").strip()
    if not value:
        if required:
            raise AppError(400, "validation", "actor required for G1 pass → confirmed_by")
        return ""
    if any(ch.isspace() for ch in value) or len(value) > 128:
        raise AppError(400, "validation", "actor must be a single token", actor=value)
    return value


def validate_char_limit(path: str, n: int, *, field: str = "body") -> int:
    limit = CHAR_LIMIT[path]
    if n > limit:
        raise AppError(
            422,
            "chars_limit",
            f"{field} exceeds path {path} limit {limit}",
            limit=limit,
            actual=n,
            field=field,
            path=path,
        )
    if n == 0:
        raise AppError(422, "validation", f"{field} is empty", field=field)
    return n


def validate_title_b(title: str) -> int:
    n = count_chars(title)
    if n == 0:
        raise AppError(422, "validation", "title is empty", field="title")
    if n > TITLE_LIMIT_B:
        raise AppError(422, "validation", "path B title exceeds 20 chars", actual=n, limit=TITLE_LIMIT_B)
    return n


def reject_force(payload: dict | None) -> None:
    if not payload:
        return
    if payload.get("force") is True or payload.get("force_pass") is not None:
        raise AppError(400, "validation", "ForcePass=never; force/force_pass is forbidden")
