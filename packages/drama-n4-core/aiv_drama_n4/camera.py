"""CAM N4 lexicon: N2 closed-set codes → one executable Chinese phrase.

SoT: DESIGN-026-CAM-N4-CAMERA-LEX-v0. One main camera per shot.
Does not invent light, does not expand the N2 enum.
"""

from __future__ import annotations

from aiv_drama_n2.validate import CAMERAS, CLASS_D_CAMERAS, CLASS_D_DURATION_FLOOR, SHOT_SIZES

SHOT_SIZE_ZH: dict[str, str] = {
    "ELS": "远景，环境为主，主体极小",
    "LS": "全景，主体全身可见",
    "MS": "中景，膝上或腰上",
    "CU": "近景，胸以上",
    "ECU": "特写，眼/手/物局部",
}

CAMERA_ZH: dict[str, str] = {
    "STATIC": "固定机位，镜头锁定",
    "POV": "主观视角镜头",
    "HANDHELD": "手持跟拍，轻微晃动",
    "OTS": "过肩镜头",
    "DEEP_FOCUS": "深焦，前后景均清晰",
    "PUSH": "镜头缓推靠近主体",
    "PULL": "镜头后拉远离主体",
    "PAN_H": "水平横摇",
    "PAN_V": "垂直摇移",
    "TRUCK": "横向平移",
    "TRACK": "跟随主体移动",
    "CRANE_UP": "镜头升起",
    "CRANE_DOWN": "镜头下降",
    "ORBIT": "环绕主体运镜",
    "ROLL": "镜头旋转滚动",
    "DOLLY_ZOOM": "滑动变焦（希区柯克变焦）",
    "WHIP_PUSH": "急推爆发",
    "WHIP_PULL": "急拉抽离",
    "STATIC_TO_MOVE": "先固定再启动运动",
}

ANGLE_ZH: dict[str, str] = {
    "high": "俯拍",
    "low": "仰拍",
    "macro": "微距",
}

SPEED_ZH: dict[str, str] = {
    "slow": "缓慢地",
    "fast": "快速地",
}

SAFE_ZONE_NOTE: dict[str, str] = {
    "CU": "面部安全区：双眼眉颏完整入画，头顶留白，勿切眼切颏",
    "ECU": "面部安全区：双眼眉颏完整入画，头顶留白，勿切眼切颏",
    "MS": "主体胸腰完整，左右勿贴边",
    "LS": "全身/环境完整，底边预留字幕带",
    "ELS": "全身/环境完整，底边预留字幕带",
}

PORTRAIT_ASPECTS = frozenset({"9:16"})


def known_shot_size(code: str | None) -> bool:
    return (code or "") in SHOT_SIZES


def known_camera(code: str | None) -> bool:
    return (code or "") in CAMERAS


def is_class_d(camera: str | None) -> bool:
    return (camera or "") in CLASS_D_CAMERAS


def class_d_floor() -> int:
    return CLASS_D_DURATION_FLOOR


def parse_notes(notes: str | None) -> dict[str, str | None]:
    out: dict[str, str | None] = {"angle": None, "speed": None}
    if not notes:
        return out
    for token in notes.replace(",", " ").split():
        if ":" not in token:
            continue
        key, value = token.split(":", 1)
        key = key.strip().lower()
        value = value.strip().lower()
        if key in out and value:
            out[key] = value
    return out


def shot_size_lex(code: str | None) -> str:
    key = (code or "").strip()
    return SHOT_SIZE_ZH.get(key, "")


def camera_lex(code: str | None, *, notes: str | None = None) -> str:
    """Exactly one main-camera phrase plus optional speed/angle modifiers."""
    key = (code or "").strip()
    phrase = CAMERA_ZH.get(key, "")
    if not phrase:
        return ""
    parsed = parse_notes(notes)
    prefix: list[str] = []
    speed = parsed.get("speed")
    if speed in SPEED_ZH:
        prefix.append(SPEED_ZH[speed])
    angle = parsed.get("angle")
    if angle in ANGLE_ZH:
        prefix.append(ANGLE_ZH[angle])
    if prefix:
        return "，".join([*prefix, phrase])
    return phrase


def camera_slot(shot_size: str | None, camera: str | None, *, notes: str | None = None) -> str:
    parts = [p for p in (shot_size_lex(shot_size), camera_lex(camera, notes=notes)) if p]
    return "，".join(parts)


def safe_zone_note(shot_size: str | None, aspect: str | None) -> str:
    if (aspect or "").strip() not in PORTRAIT_ASPECTS:
        return ""
    return SAFE_ZONE_NOTE.get((shot_size or "").strip(), "")


def static_fast_conflict(camera: str | None, notes: str | None) -> bool:
    return (camera or "").strip() == "STATIC" and parse_notes(notes).get("speed") == "fast"


# Back-compat aliases used by older unit tests / docs.
shot_size_zh = shot_size_lex
camera_zh = camera_lex
