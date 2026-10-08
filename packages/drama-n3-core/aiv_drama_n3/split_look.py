"""Standalone full-body and head-grid look generate.

Separate from generate-look / assemble_gold_a_sheet_prompt / the Gold-A 3+6 合板.
Card wardrobe / immutable / height are read the same way as generate-look.
Does not flip usable_for_n4. Does not expose a model or skip-flash switch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from aiv_drama.errors import AppError
from aiv_drama.store import atomic_write_text
from aiv_drama_n3.gold_sheet import (
    card_identity_fields,
    format_negatives,
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

SplitKind = Literal["fullbody", "heads"]

# ----- image 1: three full-body views only (not the Gold-A 合板) -----

FULLBODY_STYLE = (
    "统一画风：高端写实棚拍定妆，电影级人像质感，soft studio lighting，真实皮肤纹理与布料材质，"
    "photographic portrait look，商业写真向；横版三全身并排构图，白底干净棚拍；"
    "禁二次元、赛璐璐、动漫卡通、萌系大眼；禁豆包拟人IP插画与矢量吉祥物立绘感。"
)

FULLBODY_RECIPE = """\
横版三全身并排图，纯白干净棚拍背景。以参考图角色为唯一身份锚点：脸型轮廓（下颌线、颧骨、下巴形状）、眼型、眉形、鼻梁与鼻翼、嘴唇厚薄与嘴角形状、年龄气质必须严格一致；发际线与发型尽量一致。只允许同一个角色，禁止换脸、禁止五官漂移。

版式（单张图，仅三张全身并排，干净无实线，统一光影与色彩）：
从左到右并排三张完整全身站姿：正面、侧面、背面。
每一张都必须从头顶到脚底完整入画，双脚与鞋底必须完整可见，禁止裁切脚踝或脚。
中性站姿，手臂自然下垂。同一人、同一服装、同一光影。

质感与画质：高端写实棚拍/电影级人像质感，眼睛清晰锐利对焦，真实皮肤微观质感（毛孔与细纹，不磨皮不塑料），全图曝光与色彩一致，8K细节，轻胶片颗粒，超干净白底，脚下干净柔和投影。

强约束：画面内不允许任何可读文字（不要 FRONT/SIDE 等标签），不要字幕、不要logo、不要UI叠层、不要水印块；不要卡通二次元；不要多余人物；不要畸形手指/多肢体/脸崩。本图只输出三张全身并排。"""

FULLBODY_EN_IDENTITY = (
    "Use the attached reference photo as the ONLY identity anchor for the face. "
    "Match facial structure, features, age, and hairstyle from the reference. "
    "Output a single landscape image of three full-body views side by side. "
    "The whole figure from the top of the head to the feet must be in frame; do not crop the feet."
)

FULLBODY_OUTPUT_LINE = "输出单张三全身并排图，从头顶到脚底完整入画，禁止裁脚"

FULLBODY_KIND = "fullbody_three_views"
FULLBODY_ROLE = "fullbody_sheet"

# ----- image 2: 2×3 head grid only (not the Gold-A 合板) -----

HEADS_STYLE = (
    "统一画风：高端写实棚拍定妆，电影级人像质感，soft studio lighting，真实皮肤纹理与布料材质，"
    "photographic portrait look，商业写真向；2×3 头部网格构图，白底干净棚拍；"
    "禁二次元、赛璐璐、动漫卡通、萌系大眼；禁豆包拟人IP插画与矢量吉祥物立绘感。"
)

HEADS_RECIPE = """\
横版头部网格，纯白干净棚拍背景。以参考图角色为唯一身份锚点：脸型轮廓（下颌线、颧骨、下巴形状）、眼型、眉形、鼻梁与鼻翼、嘴唇厚薄与嘴角形状、年龄气质必须严格一致；发际线与发型尽量一致。只允许同一个角色，禁止换脸、禁止五官漂移。

版式（单张图，仅 2×3 网格，干净无实线，统一光影与色彩）：
2×3 网格六张头图，从左到右、从上到下顺序：正、背、左45、右45、笑、生气。
1）正
2）背
3）左45
4）右45
5）笑
6）生气
六张必须是同一张脸同一发际线。

质感与画质：高端写实棚拍/电影级人像质感，眼睛清晰锐利对焦，真实皮肤微观质感（毛孔与细纹，不磨皮不塑料），全图各分区曝光与色彩一致，8K细节，轻胶片颗粒，超干净白底。

强约束：画面内不允许任何可读文字（不要 FRONT/SIDE 等标签），不要字幕、不要logo、不要UI叠层、不要水印块；不要卡通二次元；不要多余人物；不要畸形手指/多肢体/脸崩。本图只输出 2×3 头部网格。"""

HEADS_EN_IDENTITY = (
    "Use the attached reference photo as the ONLY identity anchor for the face. "
    "Match facial structure, features, age, and hairstyle from the reference. "
    "Output a single 2x3 head-shot grid image."
)

HEADS_OUTPUT_LINE = "输出单张2×3头部网格"

HEADS_KIND = "head_grid_2x3"
HEADS_ROLE = "head_grid"

# Template literals only (not card-filled text). Episode / costume / extra-ban tokens stay out.
TEMPLATE_BAN_TOKENS = (
    "奶蛙",
    "程序员",
    "王子",
    "皇冠",
    "只改眼皮",
    "遮挡",
    "不透明长裙",
)

FULLBODY_PROMPT_ORDER = (
    "style_final",
    "recipe_fullbody",
    "wardrobe",
    "immutable",
    "height",
    "negatives",
    "en_identity_anchor",
    "output_sheet_line",
)

HEADS_PROMPT_ORDER = (
    "style_final",
    "recipe_heads",
    "wardrobe",
    "immutable",
    "height",
    "negatives",
    "en_identity_anchor",
    "output_sheet_line",
)


def _require_char_card(card: dict[str, Any]) -> str:
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
    return ident


def _identity_blocks(card: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    fields = card_identity_fields(card)
    if not fields["wardrobe"] and not fields["immutable"]:
        raise AppError(
            422,
            "look_card_incomplete",
            "厚卡缺 wardrobe/appearance 与 immutable；禁助手自写合板服装正文",
            node=NODE_DN3,
            card_id=card.get("id"),
        )
    identity_lines = [line for line in (fields["wardrobe"], fields["immutable"]) if line]
    return fields, identity_lines


def _join_prompt(blocks: list[str]) -> str:
    return "\n\n".join(blocks) + "\n"


def assemble_fullbody_prompt(card: dict[str, Any] | None) -> str:
    """Three full-body views only. Appearance from the thick card, same fields as generate-look."""
    card = card or {}
    fields, identity_lines = _identity_blocks(card)
    blocks = [FULLBODY_STYLE, FULLBODY_RECIPE]
    if identity_lines:
        blocks.append("\n".join(identity_lines))
    if fields["height"]:
        blocks.append(fields["height"])
    blocks.append(format_negatives())
    blocks.append(f"{FULLBODY_EN_IDENTITY}\n{FULLBODY_OUTPUT_LINE}")
    return _join_prompt(blocks)


def assemble_heads_prompt(card: dict[str, Any] | None) -> str:
    """2×3 head grid only. Appearance from the thick card, same fields as generate-look."""
    card = card or {}
    fields, identity_lines = _identity_blocks(card)
    blocks = [HEADS_STYLE, HEADS_RECIPE]
    if identity_lines:
        blocks.append("\n".join(identity_lines))
    if fields["height"]:
        blocks.append(fields["height"])
    blocks.append(format_negatives())
    blocks.append(f"{HEADS_EN_IDENTITY}\n{HEADS_OUTPUT_LINE}")
    return _join_prompt(blocks)


def assemble_fullbody_sections(card: dict[str, Any] | None) -> list[tuple[str, str]]:
    card = card or {}
    fields = card_identity_fields(card)
    sections: list[tuple[str, str]] = [
        ("style_final", FULLBODY_STYLE),
        ("recipe_fullbody", FULLBODY_RECIPE),
    ]
    if fields["wardrobe"]:
        sections.append(("wardrobe", fields["wardrobe"]))
    if fields["immutable"]:
        sections.append(("immutable", fields["immutable"]))
    if fields["height"]:
        sections.append(("height", fields["height"]))
    sections.append(("negatives", format_negatives()))
    sections.append(("en_identity_anchor", FULLBODY_EN_IDENTITY))
    sections.append(("output_sheet_line", FULLBODY_OUTPUT_LINE))
    return sections


def assemble_heads_sections(card: dict[str, Any] | None) -> list[tuple[str, str]]:
    card = card or {}
    fields = card_identity_fields(card)
    sections: list[tuple[str, str]] = [
        ("style_final", HEADS_STYLE),
        ("recipe_heads", HEADS_RECIPE),
    ]
    if fields["wardrobe"]:
        sections.append(("wardrobe", fields["wardrobe"]))
    if fields["immutable"]:
        sections.append(("immutable", fields["immutable"]))
    if fields["height"]:
        sections.append(("height", fields["height"]))
    sections.append(("negatives", format_negatives()))
    sections.append(("en_identity_anchor", HEADS_EN_IDENTITY))
    sections.append(("output_sheet_line", HEADS_OUTPUT_LINE))
    return sections


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _stem_for(kind: SplitKind, ident: str) -> tuple[str, str, str, str, str]:
    if kind == "fullbody":
        return (
            FULLBODY_KIND,
            FULLBODY_ROLE,
            f"{ident}-fullbody-prompt.txt",
            f"{ident}-fullbody-sheet.jpg",
            f"{ident}-fullbody-ark-request.recorded.json",
        )
    return (
        HEADS_KIND,
        HEADS_ROLE,
        f"{ident}-heads-prompt.txt",
        f"{ident}-heads-sheet.jpg",
        f"{ident}-heads-ark-request.recorded.json",
    )


def generate_split_look(
    *,
    kind: SplitKind,
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
    """Assemble one split prompt, bind face md5, optionally call Ark.

    Always uses SEEDREAM_SKU_CHAIN (flash first). No model override. No skip-flash.
    Does not call generate_gold_a_sheet or assemble_gold_a_sheet_prompt.
    """
    if kind not in {"fullbody", "heads"}:
        raise AppError(422, "validation", "split look kind must be fullbody or heads", node=NODE_DN3)
    ident = _require_char_card(card)
    bind = verify_face_ref_md5(
        face_ref,
        expected_md5=normalize_md5(expected_md5),
        card=card,
    )
    prompt = assemble_fullbody_prompt(card) if kind == "fullbody" else assemble_heads_prompt(card)
    look_kind, look_role, prompt_name, sheet_name, recorded_name = _stem_for(kind, ident)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    prompt_path = dest / prompt_name
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
        "kind": look_kind,
        "role": look_role,
        "split_kind": kind,
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
        recorded_path = dest / recorded_name
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
        models=(SEEDREAM_SKU_PRIMARY,),
        endpoint=endpoint,
        post=post,
        get=get,
    )
    sheet_path = dest / sheet_name
    _write_bytes(sheet_path, result["bytes"])
    look["sheet_path"] = str(sheet_path)
    look["sheet_md5"] = md5_bytes(result["bytes"])
    look["model"] = result["model"]
    look["attempts"] = result["attempts"]
    look["dry_run"] = False
    return look
