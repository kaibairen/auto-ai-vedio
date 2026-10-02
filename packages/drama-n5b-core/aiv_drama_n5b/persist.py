"""clips/<shot_id>.mp4 + .meta.json writers. Never invent clip bytes."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.store import atomic_write_text
from aiv_drama_n5b.constants import FAKE_PIXEL_MARKERS, FAKE_PIXELS_MESSAGE
from aiv_schema.models import NODE_DN5B

SHOT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def clips_dir(episode_dir: Path) -> Path:
    return Path(episode_dir) / "clips"


def clip_mp4_path(episode_dir: Path, shot_id: str) -> Path:
    return clips_dir(episode_dir) / f"{_safe_shot(shot_id)}.mp4"


def clip_meta_path(episode_dir: Path, shot_id: str) -> Path:
    return clips_dir(episode_dir) / f"{_safe_shot(shot_id)}.meta.json"


def clip_relpaths(shot_id: str) -> dict[str, str]:
    sid = _safe_shot(shot_id)
    return {"mp4": f"clips/{sid}.mp4", "meta": f"clips/{sid}.meta.json"}


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def looks_like_fake_pixels(data: bytes) -> bool:
    if not data:
        return True
    head = data[:4096]
    return any(marker in head for marker in FAKE_PIXEL_MARKERS)


def _safe_shot(shot_id: str) -> str:
    sid = (shot_id or "").strip()
    if not sid or not SHOT_ID_RE.match(sid) or ".." in sid:
        raise AppError(422, "validation", "shot_id 非法", node=NODE_DN5B, shot_id=shot_id)
    return sid


def write_clip_bytes(episode_dir: Path, shot_id: str, data: bytes) -> dict[str, Any]:
    """Write caller-provided bytes only. Empty / colorbar markers → BLOCK."""
    if not data:
        raise AppError(422, "validation", "clip bytes empty; 禁发明像素", node=NODE_DN5B, shot_id=shot_id)
    if looks_like_fake_pixels(data):
        raise AppError(422, "fake_pixels_forbidden", FAKE_PIXELS_MESSAGE, node=NODE_DN5B, shot_id=shot_id)
    path = clip_mp4_path(episode_dir, shot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    digest = md5_bytes(data)
    return {"path": str(path), "relpath": clip_relpaths(shot_id)["mp4"], "md5": digest, "bytes": len(data)}


def write_clip_meta(episode_dir: Path, shot_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Require SKU + job_id + md5. Does not invent an mp4."""
    sid = _safe_shot(shot_id)
    sku = (meta.get("SKU") or meta.get("sku") or "").strip()
    job_id = (meta.get("job_id") or meta.get("id") or "").strip()
    digest = (meta.get("md5") or "").strip()
    if not sku or not job_id or not digest:
        raise AppError(
            422,
            "validation",
            "clip meta 须含 SKU · job_id · md5",
            node=NODE_DN5B,
            shot_id=sid,
        )
    payload = {
        "shot_id": sid,
        "SKU": sku,
        "job_id": job_id,
        "md5": digest,
        "path": meta.get("path") or clip_relpaths(sid)["mp4"],
    }
    for key in ("seed", "duration", "ratio", "resolution", "status"):
        if key in meta:
            payload[key] = meta[key]
    path = clip_meta_path(episode_dir, sid)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {"path": str(path), "relpath": clip_relpaths(sid)["meta"], "meta": payload}


def read_clip_meta(episode_dir: Path, shot_id: str) -> dict[str, Any] | None:
    path = clip_meta_path(episode_dir, shot_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def list_clip_inventory(episode_dir: Path) -> list[dict[str, Any]]:
    root = clips_dir(episode_dir)
    if not root.is_dir():
        return []
    shots = sorted({p.stem.replace(".meta", "") for p in root.glob("*.meta.json")} | {p.stem for p in root.glob("*.mp4")})
    out: list[dict[str, Any]] = []
    for sid in shots:
        mp4 = clip_mp4_path(episode_dir, sid)
        meta = read_clip_meta(episode_dir, sid)
        item: dict[str, Any] = {
            "shot_id": sid,
            "mp4": clip_relpaths(sid)["mp4"] if mp4.is_file() else None,
            "meta": clip_relpaths(sid)["meta"] if meta else None,
            "SKU": (meta or {}).get("SKU"),
            "job_id": (meta or {}).get("job_id"),
            "md5": (meta or {}).get("md5"),
            "complete": False,
            "md5_ok": False,
            "fake_pixels": False,
        }
        if mp4.is_file():
            raw = mp4.read_bytes()
            item["fake_pixels"] = looks_like_fake_pixels(raw)
            file_md5 = md5_bytes(raw)
            item["file_md5"] = file_md5
            item["md5_ok"] = bool(item["md5"] and item["md5"] == file_md5)
            item["complete"] = bool(
                item["mp4"]
                and item["meta"]
                and item["SKU"]
                and item["job_id"]
                and item["md5_ok"]
                and not item["fake_pixels"]
            )
        out.append(item)
    return out
