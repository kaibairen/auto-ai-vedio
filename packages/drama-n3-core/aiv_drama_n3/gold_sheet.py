"""Gold-A 3:2 CHAR turnaround-sheet prompt contract (BRIEF-AIV-032).

STYLE终句 and RECIPE §4 body are frozen SoT strings — do not rewrite.
Wardrobe / immutable / height come only from thick-card fields.
Never invent CHAR clothing or sheet body text.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from aiv_drama.errors import AppError
from aiv_schema.models import NODE_DN3

# ----- frozen SoT (ADDENDUM-AIV-031-STYLE-BANANA-PHOTOREAL-v0 · 一字不改) -----

STYLE_BANANA_PHOTOREAL_FINAL = (
    "统一画风：高端写实棚拍定妆，电影级人像质感，soft studio lighting，真实皮肤纹理与布料材质，"
    "photographic portrait look，商业写真向；3:2 横版角色设定合板构图，白底干净棚拍；"
    "禁二次元、赛璐璐、动漫卡通、萌系大眼；禁豆包拟人IP插画与矢量吉祥物立绘感。"
)

# RECIPE-AIV-031-BANANA-LOCAL-v0 §4 turnaround template · 一字不改（含教材「两张大图」笔误）
RECIPE_TURNAROUND_TEMPLATE = """\
3:2 横版角色设定卡/转面板（turnaround sheet / model sheet），纯白干净棚拍背景。以参考图角色为唯一身份锚点：脸型轮廓（下颌线、颧骨、下巴形状）、眼型、眉形、鼻梁与鼻翼、嘴唇厚薄与嘴角形状、年龄气质必须严格一致；发际线与发型尽量一致。只允许同一个角色，禁止换脸、禁止五官漂移。

版式（单张合成图，干净网格，无实线，统一光影与色彩）：
左侧（约60%宽度）：两张大图上下排列：
1）全身正视站姿（中性站姿，手臂自然下垂）
2）全身90°侧视站姿（中性站姿，手臂自然下垂）
3）全身90°背视站姿（中性站姿，手臂自然下垂）

右侧（约40%宽度）：2×3 网格六张头部小图：
1）头部正面（neutral）
2）头部背面按这张角色卡的遮挡画。角色卡没写遮挡时，露出后脑头型
3）头部左45°（neutral）
4）头部右45°（neutral）
5）表情特写：开心只抬眼皮，嘴保持这张角色卡写的嘴型，不许另改嘴
6）表情特写：生气只把眼皮压低，眉和嘴保持角色卡，不许皱眉，不许改嘴型

质感与画质：高端写实棚拍/电影级人像质感，眼睛清晰锐利对焦，真实皮肤微观质感（毛孔与细纹，不磨皮不塑料），全图各分区曝光与色彩一致，8K细节，轻胶片颗粒，超干净白底，脚下干净柔和投影。

强约束：画面内不允许任何可读文字（不要 FRONT/SIDE 等标签），不要字幕、不要logo、不要UI叠层、不要水印块；不要卡通二次元；不要多余人物；不要畸形手指/多肢体/脸崩；六张小图必须是同一张脸同一发际线。"""

# ADDENDUM negative patch (two source lines; joined for the 禁令 row as eng-031 gold)
STYLE_NEGATIVE_LINE_1 = (
    "no anime, no cel shading, no cartoon coloring, no 2D illustration look, "
    "no oversized anime eyes, no moe face,"
)
STYLE_NEGATIVE_LINE_2 = (
    "no doubao-style mascot anthro, no chibi, no clean vector character art as identity, "
    "no brand logo watermark, no readable text on image"
)

# eng-031 SUCCESS prompt · EN identity anchor (一字不改)
EN_IDENTITY_ANCHOR = (
    "Use the attached reference photo as the ONLY identity anchor for the face. "
    "Match facial structure, features, age, and hairstyle from the reference. "
    "Output a single 3:2 landscape turnaround sheet image."
)

OUTPUT_SHEET_LINE = "输出单张3:2横版合板"

WARDROBE_PREFIX = "角色穿着："
IMMUTABLE_PREFIX = "不可变："
NEGATIVES_PREFIX = "禁令："

# BIND / gold face (NOTE-AIV-031-BANANA-MATERIAL-BIND-v0). Not auto-required.
GOLD_A_FACE_REF_MD5 = "a8c70f3b4cb7855284d3d4d2bd3c906d"
# Human-reviewed gold sheet (eng-031). New dogfood md5 may differ.
GOLD_A_SHEET_MD5 = "a46b88eb54508c8240381afcf1d78241"

PROMPT_ORDER = (
    "style_final",
    "recipe_turnaround",
    "wardrobe",
    "immutable",
    "height",
    "negatives",
    "en_identity_anchor",
    "output_sheet_line",
)

LOOK_KIND = "gold_a_turnaround_sheet"
LOOK_ROLE = "turnaround_sheet"


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def md5_text(text: str) -> str:
    return md5_bytes(text.encode("utf-8"))


def format_negatives() -> str:
    joined = f"{STYLE_NEGATIVE_LINE_1} {STYLE_NEGATIVE_LINE_2}"
    return f"{NEGATIVES_PREFIX}{joined}"


def _nonempty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(x).strip() for x in value if str(x).strip()]
        return "；".join(parts)
    return str(value).strip()


def extract_wardrobe(card: dict[str, Any]) -> str:
    text = _nonempty(card.get("wardrobe")) or _nonempty(card.get("appearance"))
    if not text:
        return ""
    if text.startswith(WARDROBE_PREFIX):
        return text
    return f"{WARDROBE_PREFIX}{text}"


def extract_immutable(card: dict[str, Any]) -> str:
    text = _nonempty(card.get("immutable"))
    if not text:
        return ""
    if text.startswith(IMMUTABLE_PREFIX):
        return text
    return f"{IMMUTABLE_PREFIX}{text}"


def extract_height_sentence(card: dict[str, Any]) -> str:
    sentence = _nonempty(card.get("height_sentence"))
    if sentence:
        return sentence
    height = _nonempty(card.get("height"))
    if not height:
        return ""
    if height.startswith("人物身高"):
        return height
    if height.startswith("身高"):
        return f"人物{height}"
    return f"人物身高{height}"


def card_identity_fields(card: dict[str, Any]) -> dict[str, str]:
    """Wardrobe / immutable / height from the thick card only. Empty ≠ invented."""
    return {
        "wardrobe": extract_wardrobe(card),
        "immutable": extract_immutable(card),
        "height": extract_height_sentence(card),
    }


def assemble_gold_a_sheet_prompt(card: dict[str, Any] | None) -> str:
    """Shared prompt assemble. CLI and workbench/HTTP must call this function.

    Order (BRIEF-AIV-032):
      1. STYLE终句  2. RECIPE§4  3. wardrobe/immutable from card
      4. height if present  5. negatives  6. EN identity  7. 输出单张3:2横版合板
    """
    card = card or {}
    fields = card_identity_fields(card)
    if not fields["wardrobe"] and not fields["immutable"]:
        raise AppError(
            422,
            "look_card_incomplete",
            "厚卡缺 wardrobe/appearance 与 immutable；禁助手自写合板服装正文",
            node=NODE_DN3,
            card_id=card.get("id"),
        )
    blocks = [STYLE_BANANA_PHOTOREAL_FINAL, RECIPE_TURNAROUND_TEMPLATE]
    identity_lines = [line for line in (fields["wardrobe"], fields["immutable"]) if line]
    if identity_lines:
        blocks.append("\n".join(identity_lines))
    if fields["height"]:
        blocks.append(fields["height"])
    blocks.append(format_negatives())
    blocks.append(f"{EN_IDENTITY_ANCHOR}\n{OUTPUT_SHEET_LINE}")
    return "\n\n".join(blocks) + "\n"


def assemble_sections(card: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Machine-checkable order for tests. Same strings as assemble_gold_a_sheet_prompt."""
    card = card or {}
    fields = card_identity_fields(card)
    sections: list[tuple[str, str]] = [
        ("style_final", STYLE_BANANA_PHOTOREAL_FINAL),
        ("recipe_turnaround", RECIPE_TURNAROUND_TEMPLATE),
    ]
    if fields["wardrobe"]:
        sections.append(("wardrobe", fields["wardrobe"]))
    if fields["immutable"]:
        sections.append(("immutable", fields["immutable"]))
    if fields["height"]:
        sections.append(("height", fields["height"]))
    sections.append(("negatives", format_negatives()))
    sections.append(("en_identity_anchor", EN_IDENTITY_ANCHOR))
    sections.append(("output_sheet_line", OUTPUT_SHEET_LINE))
    return sections


def load_look_card(path: str | Path) -> dict[str, Any]:
    raw_path = Path(path)
    if not raw_path.is_file():
        raise AppError(422, "look_card_incomplete", f"char card not found: {raw_path}", node=NODE_DN3)
    text = raw_path.read_text(encoding="utf-8")
    suffix = raw_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise AppError(
            422,
            "look_card_incomplete",
            "card file must be .yaml / .yml / .json",
            node=NODE_DN3,
            path=str(raw_path),
        )
    if not isinstance(data, dict):
        raise AppError(422, "look_card_incomplete", "card file must be a mapping", node=NODE_DN3)
    return data


def card_expected_face_md5(card: dict[str, Any] | None) -> str | None:
    for ref in (card or {}).get("refs") or []:
        if not isinstance(ref, dict):
            continue
        role = (ref.get("role") or "").strip()
        md5 = (ref.get("md5") or "").strip().lower()
        if role in {"face", "style_ref"} and md5:
            return md5
    explicit = _nonempty((card or {}).get("face_md5") or (card or {}).get("expected_face_md5"))
    return explicit.lower() or None


def verify_face_ref_md5(
    face_ref: str | Path,
    *,
    expected_md5: str | None = None,
    card: dict[str, Any] | None = None,
) -> dict[str, str]:
    """BIND gate: readable face file + md5, before generate."""
    path = Path(face_ref)
    if not path.is_file():
        raise AppError(
            422,
            "material_bind",
            "脸 ref 不可读；材料绑定门未过，禁 generate",
            node=NODE_DN3,
            path=str(path),
        )
    digest = md5_bytes(path.read_bytes())
    wanted = (expected_md5 or "").strip().lower() or card_expected_face_md5(card)
    if wanted and digest != wanted:
        raise AppError(
            422,
            "material_bind",
            "脸 ref md5 与期望不一致；材料绑定门未过，禁 generate",
            node=NODE_DN3,
            expected_md5=wanted,
            actual_md5=digest,
        )
    return {"path": str(path.resolve()), "md5": digest}


_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def normalize_md5(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    if not text:
        return None
    if not _HEX32.match(text):
        raise AppError(422, "validation", "expected_md5 must be 32-char hex", node=NODE_DN3)
    return text
