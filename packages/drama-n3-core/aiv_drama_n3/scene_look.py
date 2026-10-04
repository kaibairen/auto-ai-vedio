"""Opt-in SCENE plate generate. Separate track from CHAR look commands.

Prompt is name + one_line only. No face ref. Reuses the Seedream/flash chain.
Does not flip usable_for_n4. Does not expose a model or skip-flash switch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.store import atomic_write_text
from aiv_drama_n3.cards import SCENE_REF_ROLE, has_usable_ref
from aiv_drama_n3.gold_sheet import format_negatives, md5_bytes, md5_text
from aiv_drama_n3.seedream import (
    ARK_IMAGES_URL,
    SEEDREAM_SKU_CHAIN,
    SEEDREAM_SKU_PRIMARY,
    SHEET_SIZE,
    generate_seedream_sheet,
    recorded_ark_request,
)
from aiv_schema.models import NODE_DN3

SCENE_PLATE_KIND = "scene_plate"
SCENE_PLATE_ROLE = SCENE_REF_ROLE

SCENE_PLATE_STYLE = (
    "统一画风：高端写实电影场景定妆，空间本体清晰可读，"
    "photographic location plate，商业影视勘景向；横版单张场景参考板；"
    "禁二次元、赛璐璐、动漫卡通；禁豆包拟人IP插画与矢量场景立绘感。"
)

SCENE_PLATE_RECIPE = """\
横版单张场景参考板，只画空间本身：室内外结构、尺度、可复用空镜头陈设与材质。
禁止可读文字、字幕、logo、UI叠层、水印；禁止把事件名画成招牌。
画面内不要出现可识别人物；这是空场参考板，供后续镜头作环境锚点。
同一空间、统一光影与色彩，8K细节，轻胶片颗粒。"""

SCENE_PLATE_EN = (
    "Output a single landscape location plate of the named space. "
    "No people. No readable text. No logos."
)

SCENE_PLATE_OUTPUT = "输出单张横版场景参考板"

SCENE_NAME_PREFIX = "场景："
SCENE_ONE_LINE_PREFIX = "空间功能："

SCENE_PROMPT_ORDER = (
    "style_final",
    "recipe_scene_plate",
    "name_one_line",
    "negatives",
    "en_plate",
    "output_sheet_line",
)

# Template literals only (not card-filled text). Episode tokens stay out.
TEMPLATE_BAN_TOKENS = (
    "奶蛙",
    "程序员",
    "王子",
    "皇冠",
    "深夜IDE",
    "只改眼皮",
    "遮挡",
    "不透明长裙",
)


def _join_prompt(blocks: list[str]) -> str:
    return "\n\n".join(blocks) + "\n"


def _require_scene_card(card: dict[str, Any]) -> str:
    kind = (card.get("kind") or "").strip()
    ident = (card.get("id") or "").strip()
    if kind == "character" or ident.startswith("CHAR-"):
        raise AppError(
            422,
            "char_look_forbidden",
            "场景参考板仅 SCENE；CHAR 走 generate-look / generate-fullbody / generate-heads",
            node=NODE_DN3,
            id=ident,
        )
    if kind != "scene" and not ident.startswith("SCENE-"):
        raise AppError(422, "validation", "generate-scene requires a SCENE card", node=NODE_DN3, id=ident)
    if not ident:
        raise AppError(422, "validation", "SCENE card id is required", node=NODE_DN3)
    return ident


def _name_one_line(card: dict[str, Any]) -> tuple[str, str]:
    name = str(card.get("name") or "").strip()
    one_line = str(card.get("one_line") or "").strip()
    if not name or not one_line:
        raise AppError(
            422,
            "card_incomplete",
            "SCENE 卡必须有 name 与 one_line",
            node=NODE_DN3,
            card_id=card.get("id"),
            field="one_line" if name else "name",
        )
    return name, one_line


def _name_one_line_block(card: dict[str, Any]) -> str:
    name, one_line = _name_one_line(card)
    return f"{SCENE_NAME_PREFIX}{name}\n{SCENE_ONE_LINE_PREFIX}{one_line}"


def assemble_scene_plate_prompt(card: dict[str, Any] | None) -> str:
    """Location plate from scene name + one_line only. No face, no wardrobe."""
    card = card or {}
    _require_scene_card(card)
    blocks = [
        SCENE_PLATE_STYLE,
        SCENE_PLATE_RECIPE,
        _name_one_line_block(card),
        format_negatives(),
        f"{SCENE_PLATE_EN}\n{SCENE_PLATE_OUTPUT}",
    ]
    return _join_prompt(blocks)


def assemble_scene_plate_sections(card: dict[str, Any] | None) -> list[tuple[str, str]]:
    card = card or {}
    _require_scene_card(card)
    return [
        ("style_final", SCENE_PLATE_STYLE),
        ("recipe_scene_plate", SCENE_PLATE_RECIPE),
        ("name_one_line", _name_one_line_block(card)),
        ("negatives", format_negatives()),
        ("en_plate", SCENE_PLATE_EN),
        ("output_sheet_line", SCENE_PLATE_OUTPUT),
    ]


def record_scene_plate_ref(card: dict[str, Any], *, path: str, md5: str) -> dict[str, Any]:
    """Write role=plate onto a SCENE card only. Character cards are not modified."""
    _require_scene_card(card)
    path = str(path or "").strip()
    md5 = str(md5 or "").strip()
    if not path or not md5:
        raise AppError(422, "validation", "scene plate ref needs path and md5", node=NODE_DN3, id=card.get("id"))
    refs = [
        ref
        for ref in (card.get("refs") or [])
        if not (isinstance(ref, dict) and (ref.get("role") or "").strip() == SCENE_PLATE_ROLE)
    ]
    refs.append(
        {
            "path": path,
            "md5": md5,
            "role": SCENE_PLATE_ROLE,
            "missing_file": False,
        }
    )
    card["refs"] = refs
    card["missing_ref"] = not has_usable_ref(card)
    card["weak_binding"] = card["missing_ref"]
    return card


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def generate_scene_plate(
    *,
    card: dict[str, Any],
    out_dir: str | Path,
    api_key: str | None,
    dry_run: bool = False,
    endpoint: str = ARK_IMAGES_URL,
    post: Any | None = None,
    get: Any | None = None,
) -> dict[str, Any]:
    """Assemble a scene plate, optionally call Ark. No face ref. Flash-first chain.

    Always uses SEEDREAM_SKU_CHAIN (flash first). No model override. No skip-flash.
    Does not call generate_gold_a_sheet / generate_split_look.
    Live writes the image and records role=plate on the given scene card.
    """
    ident = _require_scene_card(card)
    prompt = assemble_scene_plate_prompt(card)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    prompt_path = dest / f"{ident}-scene-plate-prompt.txt"
    atomic_write_text(prompt_path, prompt)
    prompt_md5 = md5_text(prompt)
    recorded = recorded_ark_request(
        model=SEEDREAM_SKU_PRIMARY,
        prompt=prompt,
        size=SHEET_SIZE,
        endpoint=endpoint,
    )
    look: dict[str, Any] = {
        "ok": True,
        "node": NODE_DN3,
        "kind": SCENE_PLATE_KIND,
        "role": SCENE_PLATE_ROLE,
        "card_id": ident,
        "aspect": "3:2",
        "size": SHEET_SIZE,
        "sku_chain": list(SEEDREAM_SKU_CHAIN),
        "prompt_path": str(prompt_path),
        "prompt_md5": prompt_md5,
        "prompt_chars": len(prompt),
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
        recorded_path = dest / f"{ident}-scene-plate-ark-request.recorded.json"
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
    result = generate_seedream_sheet(
        api_key=api_key,
        prompt=prompt,
        image_data_url=None,
        endpoint=endpoint,
        post=post,
        get=get,
    )
    sheet_path = dest / f"{ident}-scene-plate.jpg"
    _write_bytes(sheet_path, result["bytes"])
    look["sheet_path"] = str(sheet_path)
    look["sheet_md5"] = md5_bytes(result["bytes"])
    look["model"] = result["model"]
    look["attempts"] = result["attempts"]
    look["dry_run"] = False
    record_scene_plate_ref(card, path=look["sheet_path"], md5=look["sheet_md5"])
    look["refs"] = list(card.get("refs") or [])
    return look
