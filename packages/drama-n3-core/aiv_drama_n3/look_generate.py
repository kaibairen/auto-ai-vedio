"""Shared gold-A look-generate: assemble + bind + Ark single-sheet.

CLI standalone and DramaN3Ops / HTTP / workbench call this function.
Does not flip usable_for_n4. Does not attach the sheet as face/full.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.store import atomic_write_text
from aiv_drama_n3.gold_sheet import (
    LOOK_KIND,
    LOOK_ROLE,
    assemble_gold_a_sheet_prompt,
    md5_bytes,
    md5_text,
    normalize_md5,
    verify_face_ref_md5,
)
from aiv_drama_n3.seedream import (
    ARK_IMAGES_URL,
    SEEDREAM_SKU_CHAIN,
    SEEDREAM_SKU_PRIMARY,
    SHEET_SIZE,
    face_to_data_url,
    generate_seedream_sheet,
    recorded_ark_request,
)
from aiv_schema.models import NODE_DN3


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def generate_gold_a_sheet(
    *,
    card: dict[str, Any],
    face_ref: str | Path,
    out_dir: str | Path,
    api_key: str | None,
    expected_md5: str | None = None,
    dry_run: bool = False,
    endpoint: str = ARK_IMAGES_URL,
    post: Any | None = None,
    get: Any | None = None,
) -> dict[str, Any]:
    """Assemble prompt, bind face md5, optionally call Ark. Shared by CLI + HTTP.

    usable_for_n4 on the look record is always false. No sequential_image_generation.
    No CU/LS split. No key in the returned envelope.
    """
    kind = (card.get("kind") or "character").strip()
    ident = (card.get("id") or "CHAR").strip()
    if kind == "scene" or ident.startswith("SCENE-"):
        raise AppError(
            422,
            "scene_look_forbidden",
            "金样 A 合板仅 CHAR；SCENE 另轨",
            node=NODE_DN3,
            id=ident,
        )
    bind = verify_face_ref_md5(
        face_ref,
        expected_md5=normalize_md5(expected_md5),
        card=card,
    )
    prompt = assemble_gold_a_sheet_prompt(card)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    prompt_path = dest / f"{ident}-doubao-sheet-prompt.txt"
    atomic_write_text(prompt_path, prompt)
    prompt_md5 = md5_text(prompt)
    face_path = Path(bind["path"])
    recorded = recorded_ark_request(
        model=SEEDREAM_SKU_PRIMARY,
        prompt=prompt,
        face_md5=bind["md5"],
        image_bytes_len=face_path.stat().st_size,
        size=SHEET_SIZE,
        endpoint=endpoint,
    )
    look: dict[str, Any] = {
        "ok": True,
        "node": NODE_DN3,
        "kind": LOOK_KIND,
        "role": LOOK_ROLE,
        "card_id": ident,
        "aspect": "3:2",
        "size": SHEET_SIZE,
        "sku_chain": list(SEEDREAM_SKU_CHAIN),
        "prompt_path": str(prompt_path),
        "prompt_md5": prompt_md5,
        "prompt_chars": len(prompt),
        "face_ref_path": bind["path"],
        "face_ref_md5": bind["md5"],
        "sheet_path": None,
        "sheet_md5": None,
        "model": None,
        "dry_run": bool(dry_run),
        "usable_for_n4": False,
        "sequential_image_generation": False,
        "split_cu_ls": False,
        "recorded": recorded,
        "attempts": [],
    }
    if dry_run:
        recorded_path = dest / f"{ident}-ark-request.recorded.json"
        atomic_write_text(recorded_path, json.dumps(recorded, ensure_ascii=False, indent=2) + "\n")
        look["recorded_path"] = str(recorded_path)
        return look
    if not api_key:
        raise AppError(
            422,
            "provider",
            "ARK_API_KEY missing; live generate blocked (use --dry-run or set key — never echo)",
            node=NODE_DN3,
        )
    data_url = face_to_data_url(face_path)
    result = generate_seedream_sheet(
        api_key=api_key,
        prompt=prompt,
        image_data_url=data_url,
        endpoint=endpoint,
        post=post,
        get=get,
    )
    sheet_path = dest / f"{ident}-turnaround-sheet-3x2.jpg"
    _write_bytes(sheet_path, result["bytes"])
    look["sheet_path"] = str(sheet_path)
    look["sheet_md5"] = md5_bytes(result["bytes"])
    look["model"] = result["model"]
    look["attempts"] = result["attempts"]
    look["dry_run"] = False
    return look
