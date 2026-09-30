"""libraries/ schema helpers + attach/promote working-copy merge."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

from aiv_drama_n3.cards import binding_label, has_usable_ref, infer_kind
from aiv_drama_n3.policy import default_project_scope, project_scope_capability

KIND_CHAR = "character"
KIND_SCENE = "scene"


def library_key(project_id: str, kind: str, ident: str, version: int) -> str:
    prefix = "CHAR" if kind == KIND_CHAR else "SCENE"
    return f"{project_id}/{prefix}/{ident}@{version}"


def character_store_key(project_id: str, character_id: str, version: int) -> str:
    """Legacy N0/N1 key — keep characters addressable for existing attach."""
    return f"{project_id}/{character_id}@{version}"


def scene_store_key(project_id: str, scene_id: str, version: int) -> str:
    return f"{project_id}/SCENE/{scene_id}@{version}"


def md5_file(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def resolve_ref_file(settings: Any, rel: str) -> Path | None:
    raw = Path(rel)
    if raw.is_absolute() and raw.is_file():
        return raw
    for root in (getattr(settings, "data_dir", None), getattr(settings, "repo_root", None)):
        if root is None:
            continue
        cand = Path(root) / rel
        if cand.is_file():
            return cand
    return None


def normalize_refs(settings: Any, refs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in refs or []:
        if not isinstance(raw, dict):
            continue
        path = (raw.get("path") or "").strip()
        if not path:
            continue
        md5 = (raw.get("md5") or "").strip()
        found = resolve_ref_file(settings, path)
        if found and not md5:
            md5 = md5_file(found)
        item = {
            "path": path,
            "md5": md5 or None,
            "role": raw.get("role"),
            "missing_file": found is None,
        }
        out.append(item)
    return out


def index_payload(record: dict[str, Any], versions: list[int]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "one_line": record.get("one_line"),
        "kind": record.get("kind") or KIND_CHAR,
        "versions": sorted(set(versions)),
        "tags": list(record.get("tags") or []),
        "project_scope": record.get("project_scope") or default_project_scope(),
        "project_scope_capability": record.get("project_scope_capability") or project_scope_capability(),
        "latest_version": max(versions) if versions else record.get("version"),
    }


def apply_library_to_card(card: dict[str, Any], lib: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(card)
    ref = {"id": lib["id"], "version": lib["version"]}
    out["library_ref"] = ref
    out["origin"] = "attached"
    out["binding"] = binding_label(ref)
    if lib.get("name"):
        out["name"] = lib["name"]
    if lib.get("one_line"):
        out["one_line"] = lib["one_line"]
    if lib.get("refs"):
        out["refs"] = deepcopy(lib["refs"])
    out["missing_ref"] = not has_usable_ref(out)
    out["weak_binding"] = out["missing_ref"]
    out["decision"] = None
    return out


def card_to_library_record(
    project_id: str,
    card: dict[str, Any],
    version: int,
    *,
    kind: str,
) -> dict[str, Any]:
    return {
        "id": card["id"],
        "version": version,
        "kind": kind,
        "name": card.get("name"),
        "one_line": card.get("one_line"),
        "project_id": project_id,
        "project_scope": default_project_scope(),
        "project_scope_capability": project_scope_capability(),
        "tags": list(card.get("status_tags") or []),
        "refs": deepcopy(card.get("refs") or []),
        "source": "promote_stub",
        "auto_promote": False,
    }


def parse_kind(ident: str, kind: str | None) -> str:
    if kind in {KIND_CHAR, KIND_SCENE}:
        return kind
    inferred = infer_kind(ident)
    if inferred:
        return inferred
    return KIND_CHAR
