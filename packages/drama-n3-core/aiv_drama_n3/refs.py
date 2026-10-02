"""AIV-031 refs[{path,md5,role}] mount helpers.

MUST: path ∧ md5 ∧ role. Ban hotlink URLs. Recompute md5 on write.
missing_file when path missing or md5 mismatch.
Never writes usable_for_n4=true.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n3.looks import dest_looks_file
from aiv_schema.models import NODE_DN3

CHAR_USABLE_ROLES = frozenset({"face", "full"})
CHAR_MUST_ROLES = frozenset({"face"})
PROVENANCE_ROLES = frozenset({"style_ref", "web_source"})
ALLOWED_ROLES = CHAR_USABLE_ROLES | PROVENANCE_ROLES | frozenset({"plate", "look"})

HOTLINK_RE = re.compile(r"^(?:https?|ftp)://", re.IGNORECASE)
DATA_URL_RE = re.compile(r"^data:", re.IGNORECASE)

HOTLINK_MESSAGE = "refs[].path 只允许 looks 树本地路径，禁止热链 URL"
REF_INCOMPLETE_MESSAGE = "每条 ref 必须同时有 path、md5、role"


def is_hotlink_url(path: str | None) -> bool:
    raw = (path or "").strip()
    if not raw:
        return False
    return bool(HOTLINK_RE.match(raw) or DATA_URL_RE.match(raw))


def reject_hotlink_path(path: str | None) -> str:
    raw = (path or "").strip()
    if is_hotlink_url(raw):
        raise AppError(
            400,
            "hotlink_ref_forbidden",
            HOTLINK_MESSAGE,
            field="path",
            path=raw,
            node=NODE_DN3,
        )
    return raw


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def md5_file(path: Path) -> str:
    return md5_bytes(path.read_bytes())


def require_ref_fields(raw: dict[str, Any], *, require_md5: bool = True) -> tuple[str, str, str]:
    if not isinstance(raw, dict):
        raise AppError(422, "ref_incomplete", REF_INCOMPLETE_MESSAGE, node=NODE_DN3)
    path = reject_hotlink_path(raw.get("path"))
    md5 = (raw.get("md5") or "").strip()
    role = (raw.get("role") or "").strip()
    if not path or not role or (require_md5 and not md5):
        raise AppError(
            422,
            "ref_incomplete",
            REF_INCOMPLETE_MESSAGE,
            field="refs",
            node=NODE_DN3,
        )
    return path, md5, role


def resolve_ref_file(
    settings: Any,
    rel: str,
    *,
    episode_dir: Path | None = None,
) -> Path | None:
    raw = (rel or "").strip()
    if not raw or is_hotlink_url(raw):
        return None
    path = Path(raw)
    if path.is_absolute() and path.is_file():
        return path
    candidates: list[Path] = []
    if episode_dir is not None:
        ep_dir = Path(episode_dir)
        candidates.append(ep_dir / raw)
        parts = Path(raw).parts
        if len(parts) >= 3 and parts[0] == "episodes":
            # episodes/<ep>/n3/looks/... → episode_dir / n3/looks/...
            candidates.append(ep_dir.joinpath(*parts[2:]))
    for root in (getattr(settings, "data_dir", None), getattr(settings, "repo_root", None)):
        if root is None:
            continue
        candidates.append(Path(root) / raw)
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand
    return None


def missing_file_for(
    settings: Any,
    path: str,
    md5: str,
    *,
    episode_dir: Path | None = None,
) -> bool:
    """True when file is absent or on-disk md5 ≠ declared md5."""
    if not path or is_hotlink_url(path):
        return True
    found = resolve_ref_file(settings, path, episode_dir=episode_dir)
    if found is None:
        return True
    if md5 and md5_file(found) != md5:
        return True
    return False


def normalize_look_ref(
    settings: Any,
    raw: dict[str, Any],
    *,
    episode_dir: Path | None = None,
    recompute_md5: bool = False,
) -> dict[str, Any]:
    """Strict mount shape. require path+md5+role unless recompute_md5 and file exists."""
    path = reject_hotlink_path((raw.get("path") if isinstance(raw, dict) else None) or "")
    if not path:
        raise AppError(422, "ref_incomplete", REF_INCOMPLETE_MESSAGE, field="path", node=NODE_DN3)
    role = ((raw.get("role") if isinstance(raw, dict) else None) or "").strip()
    if not role:
        raise AppError(422, "ref_incomplete", REF_INCOMPLETE_MESSAGE, field="role", node=NODE_DN3)
    found = resolve_ref_file(settings, path, episode_dir=episode_dir)
    declared = ((raw.get("md5") if isinstance(raw, dict) else None) or "").strip()
    actual = md5_file(found) if found is not None else ""
    if recompute_md5 and found is not None:
        md5 = actual
    else:
        md5 = declared
        if not md5:
            raise AppError(422, "ref_incomplete", REF_INCOMPLETE_MESSAGE, field="md5", node=NODE_DN3)
    if found is None:
        missing = True
    elif md5 and actual != md5:
        missing = True
    else:
        missing = False
    return {
        "path": path,
        "md5": md5,
        "role": role,
        "missing_file": missing,
    }


def normalize_look_refs(
    settings: Any,
    refs: list[dict[str, Any]] | None,
    *,
    episode_dir: Path | None = None,
    recompute_md5: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in refs or []:
        if not isinstance(raw, dict):
            raise AppError(422, "ref_incomplete", REF_INCOMPLETE_MESSAGE, node=NODE_DN3)
        out.append(normalize_look_ref(settings, raw, episode_dir=episode_dir, recompute_md5=recompute_md5))
    return out


def mount_local_file_as_ref(
    episode_dir: Path,
    episode_id: str,
    card: dict[str, Any],
    source: Path,
    *,
    role: str,
    view: str | None = None,
) -> dict[str, Any]:
    """Copy a local fixture/file into the looks tree and return {path,md5,role}.

    Recomputes md5 from written bytes. Rejects hotlink sources. Never sets usable.
    """
    src = Path(source)
    if is_hotlink_url(str(source)):
        raise AppError(400, "hotlink_ref_forbidden", HOTLINK_MESSAGE, field="source_path", node=NODE_DN3)
    if not src.is_file():
        raise AppError(
            422,
            "validation",
            "挂载源文件不存在（须本地 fixture/文件，禁热链）",
            field="source_path",
            path=str(source),
            node=NODE_DN3,
        )
    kind = card.get("kind") or "character"
    ident = card.get("id") or ""
    dest, rel = dest_looks_file(episode_dir, episode_id, kind, ident, role, view)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    digest = md5_file(dest)
    return {
        "path": rel,
        "md5": digest,
        "role": (role or "").strip(),
        "missing_file": False,
    }


def upsert_card_ref(card: dict[str, Any], mounted: dict[str, Any]) -> dict[str, Any]:
    """Replace same-role ref or append. Refresh missing_ref. Never touch usable_for_n4."""
    role = (mounted.get("role") or "").strip()
    refs = [r for r in (card.get("refs") or []) if isinstance(r, dict)]
    kept = [r for r in refs if (r.get("role") or "").strip() != role]
    kept.append(
        {
            "path": mounted["path"],
            "md5": mounted["md5"],
            "role": role,
            "missing_file": bool(mounted.get("missing_file", False)),
        }
    )
    card["refs"] = kept
    refresh_card_ref_flags(card)
    card.pop("usable_for_n4", None)
    return card


def _ref_disk_ok(ref: dict[str, Any]) -> bool:
    path = (ref.get("path") or "").strip()
    md5 = (ref.get("md5") or "").strip()
    if not path or not md5:
        return False
    if is_hotlink_url(path):
        return False
    if ref.get("missing_file", False):
        return False
    return True


def has_usable_ref(card: dict[str, Any]) -> bool:
    """CHAR: path+md5+role∈{face,full}+missing_file≠true. style_ref/web_source never count."""
    kind = card.get("kind")
    for ref in card.get("refs") or []:
        if not isinstance(ref, dict) or not _ref_disk_ok(ref):
            continue
        role = (ref.get("role") or "").strip()
        if role in PROVENANCE_ROLES:
            continue
        if kind == "character" and role not in CHAR_USABLE_ROLES:
            continue
        return True
    return False


def has_must_face(card: dict[str, Any]) -> bool:
    """CHAR MUST face: usable face ref. SCENE: any non-provenance usable ref."""
    kind = card.get("kind")
    for ref in card.get("refs") or []:
        if not isinstance(ref, dict) or not _ref_disk_ok(ref):
            continue
        role = (ref.get("role") or "").strip()
        if role in PROVENANCE_ROLES:
            continue
        if kind == "character":
            if role in CHAR_MUST_ROLES:
                return True
            continue
        return True
    return False


def refresh_card_ref_flags(card: dict[str, Any]) -> dict[str, Any]:
    """refs empty or CHAR lacking MUST face → missing_ref (+ weak_binding). No usable flip."""
    missing = not has_must_face(card)
    card["missing_ref"] = missing
    card["weak_binding"] = missing
    return card


def refresh_n3_ref_flags(n3: dict[str, Any] | None) -> None:
    cards = (n3 or {}).get("cards") or {}
    for card in list(cards.get("characters") or []) + list(cards.get("scenes") or []):
        if isinstance(card, dict):
            refresh_card_ref_flags(card)
