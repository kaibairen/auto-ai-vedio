"""CAM 景别 / 一镜一主运镜词表. English N2 enums → one Chinese camera word."""

from __future__ import annotations

from aiv_drama_n2.validate import CAMERAS, SHOT_SIZES

SHOT_SIZE_ZH: dict[str, str] = {
    "ELS": "大远景",
    "LS": "远景",
    "MS": "中景",
    "CU": "特写",
    "ECU": "大特写",
}

CAMERA_ZH: dict[str, str] = {
    "STATIC": "固定镜头",
    "POV": "主观镜头",
    "HANDHELD": "手持",
    "OTS": "过肩",
    "DEEP_FOCUS": "深焦",
    "PUSH": "推镜头",
    "PULL": "拉镜头",
    "PAN_H": "横摇",
    "PAN_V": "竖摇",
    "TRUCK": "横移",
    "TRACK": "跟镜头",
    "CRANE_UP": "升镜头",
    "CRANE_DOWN": "降镜头",
    "ORBIT": "环绕",
    "ROLL": "旋转",
    "DOLLY_ZOOM": "滑动变焦",
    "WHIP_PUSH": "急推",
    "WHIP_PULL": "急拉",
    "STATIC_TO_MOVE": "由静到动",
}


def shot_size_zh(code: str | None) -> str:
    key = (code or "").strip()
    return SHOT_SIZE_ZH.get(key, key or "中景")


def camera_zh(code: str | None) -> str:
    """Exactly one main camera word. Unknown codes pass through as a single token."""
    key = (code or "").strip()
    return CAMERA_ZH.get(key, key or "固定镜头")


def known_shot_size(code: str | None) -> bool:
    return (code or "") in SHOT_SIZES


def known_camera(code: str | None) -> bool:
    return (code or "") in CAMERAS


def camera_slot(shot_size: str | None, camera: str | None) -> str:
    return f"{shot_size_zh(shot_size)}，{camera_zh(camera)}"
