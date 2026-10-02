"""Write looks tree, compute md5, write meta.json. Never empty placeholders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.store import atomic_write_text
from aiv_drama.validate import now_iso
from aiv_drama_look.paths import looks_abspath, looks_relpath, reject_hotlink_path, web_refs_dir
from aiv_drama_look.refs import make_ref, md5_bytes
from aiv_schema.models import NODE_DN3

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    if not data:
        raise AppError(422, "validation", "禁空文件占位", path=str(path), node=NODE_DN3)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def read_meta(card_dir: Path) -> dict[str, Any] | None:
    path = card_dir / "meta.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def write_meta(card_dir: Path, payload: dict[str, Any]) -> Path:
    path = card_dir / "meta.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def materialize_look_bytes(
    *,
    episode_dir: Path,
    episode_id: str,
    card: dict[str, Any],
    role: str,
    view: str,
    data: bytes,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Write PNG under looks/, md5, return ref dict. Does not touch usable_for_n4."""
    if not data:
        raise AppError(422, "validation", "禁空文件占位 / 跳过 md5", node=NODE_DN3)
    kind = card.get("kind") or "character"
    card_id = card["id"]
    abs_path = looks_abspath(episode_dir, kind, card_id, role, view)
    atomic_write_bytes(abs_path, data)
    digest = md5_bytes(data)
    if md5_bytes(abs_path.read_bytes()) != digest:
        raise AppError(502, "provider", "look 落盘后 md5 不一致", node=NODE_DN3)
    rel = looks_relpath(episode_id, kind, card_id, role, view)
    reject_hotlink_path(rel)
    web_refs_dir(episode_dir, kind, card_id).mkdir(parents=True, exist_ok=True)
    record = {
        "sku": meta.get("sku"),
        "seed": meta.get("seed"),
        "frozen_params": meta.get("frozen_params") or {},
        "prompt_hash": meta.get("prompt_hash"),
        "created_at": meta.get("created_at") or now_iso(),
        "provider": meta.get("provider"),
        "card_id": card_id,
        "kind": kind,
        "view": view,
        "role": role,
        "path": rel,
        "md5": digest,
        "filename": abs_path.name,
        "seed_replay": meta.get("seed_replay") or "ok",
        "usable_for_n4_flipped": False,
        "watermark": False,
    }
    if meta.get("sku_from") or meta.get("sku_to") or meta.get("reason"):
        record["sku_from"] = meta.get("sku_from")
        record["sku_to"] = meta.get("sku_to")
        record["reason"] = meta.get("reason")
    write_meta(abs_path.parent, record)
    return {
        "ref": make_ref(path=rel, md5=digest, role=role),
        "abs_path": str(abs_path),
        "rel_path": rel,
        "md5": digest,
        "meta": record,
        "png_magic": data[:8] == PNG_MAGIC,
    }
