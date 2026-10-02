"""Look Mode A/B for N5a (NOTE-AIV-036-LOOK-MODE-AB + ACCEPT P-CHAR).

P-CHAR: shot CHAR usable_for_n4=true means a human-reviewed look sheet (合板),
not necessarily a face file. This package does **not** flip usable_for_n4.

Mode A (face-ref): face/full path+md5 may be used as img2img identity.
Mode B (card-text): thick-card appearance+immutable is enough.
**Forbidden**: treat missing face file as a hard N5a block on the Mode B path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiv_drama_n3.cards import all_cards, is_char_id, is_none_id
from aiv_drama_n3.library import resolve_ref_file

MODE_A = "A"
MODE_B = "B"


def _nonempty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(str(x).strip() for x in value if str(x).strip())
    if isinstance(value, dict):
        return "；".join(str(v).strip() for v in value.values() if str(v).strip())
    return str(value).strip()


def has_face_or_full_ref(card: dict[str, Any]) -> bool:
    for ref in card.get("refs") or []:
        if not isinstance(ref, dict):
            continue
        role = (ref.get("role") or "").strip()
        path = (ref.get("path") or "").strip()
        md5 = (ref.get("md5") or "").strip()
        if role in {"face", "full"} and path and md5:
            return True
    return False


def is_thick_char_card(card: dict[str, Any]) -> bool:
    appearance = _nonempty(card.get("wardrobe")) or _nonempty(card.get("appearance"))
    immutable = _nonempty(card.get("immutable"))
    return bool(appearance and immutable)


def look_mode_for_char(card: dict[str, Any]) -> str:
    """Mode A iff a face/full ref is declared. Else Mode B (card-text)."""
    if has_face_or_full_ref(card):
        return MODE_A
    return MODE_B


def resolve_face_file(card: dict[str, Any], settings: Any | None = None) -> Path | None:
    for ref in card.get("refs") or []:
        if not isinstance(ref, dict):
            continue
        if (ref.get("role") or "").strip() not in {"face", "full"}:
            continue
        path = (ref.get("path") or "").strip()
        if not path:
            continue
        if settings is not None:
            found = resolve_ref_file(settings, path)
            if found is not None:
                return found
        raw = Path(path)
        if raw.is_file():
            return raw
    return None


def missing_face_is_hard_block(*, mode: str) -> bool:
    """Mode B: never. Mode A: face may be used; still not an N5a generate hard gate."""
    if mode == MODE_B:
        return False
    return False


def char_look_report(
    rec: dict[str, Any],
    lines: list[dict[str, Any]],
    settings: Any | None = None,
) -> dict[str, Any]:
    """Observability only. Does not 409 Mode B for a missing face file."""
    index = {c["id"]: c for c in all_cards(rec.get("n3")) if c.get("id")}
    modes: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    shot_chars: list[str] = []
    for line in lines:
        for cid in line.get("char_ids") or []:
            if is_none_id(cid) or not is_char_id(cid) or cid in shot_chars:
                continue
            shot_chars.append(cid)
            card = index.get(cid)
            if not card:
                warnings.append(
                    {
                        "id": cid,
                        "code": "char_card_absent",
                        "message": "镜引用 CHAR 无本集卡；仍用 jsonl 正文出格（不挡 Mode B）",
                    }
                )
                modes[cid] = MODE_B
                continue
            mode = look_mode_for_char(card)
            modes[cid] = mode
            face = resolve_face_file(card, settings)
            if mode == MODE_B:
                if not is_thick_char_card(card):
                    warnings.append(
                        {
                            "id": cid,
                            "code": "mode_b_thin_card",
                            "message": "Mode B：厚卡 appearance/immutable 偏薄；缺 face 不作硬挡",
                        }
                    )
                warnings.append(
                    {
                        "id": cid,
                        "code": "mode_b_no_face_ok",
                        "message": "Mode B 厚卡文案定妆即可；禁止把缺 face 文件写成 N5a 硬挡",
                    }
                )
            elif face is None:
                warnings.append(
                    {
                        "id": cid,
                        "code": "mode_a_face_missing_file",
                        "message": "Mode A 声明了 face/full 但文件不在盘；回退 t2i，不造假脸",
                    }
                )
    return {
        "look_modes": modes,
        "shot_char_ids": shot_chars,
        "warnings": warnings,
        "face_required": False,
        "p_char": "usable_for_n4=true means human-reviewed look sheet (合板), not necessarily a face file",
    }
