"""SCENE-LOOK-EXEMPT (NOTE-AIV-036 · EP01).

G4 检 G4 场项 → N/A. CHAR identity items stay hard.
Does not flip SCENE usable_for_n4. Does not green N4.
"""

from __future__ import annotations

from typing import Any

EXEMPT_EPISODES = frozenset({"EP01"})
EXEMPT_FLAG = "SCENE-LOOK-EXEMPT"
SCENE_NA_REASON = "N/A·EXEMPT"


def scene_look_exempt(rec: dict[str, Any] | None, ep: str | None = None) -> bool:
    """True for EP01 or an explicit episode flag. Not a global SCENE-look repeal."""
    episode_id = ep
    if rec:
        episode = rec.get("episode") or {}
        episode_id = episode_id or episode.get("episode_id")
        if episode.get("scene_look_exempt") is True:
            return True
        flags = episode.get("exempt") or rec.get("exempt") or {}
        if isinstance(flags, dict) and flags.get("scene_look"):
            return True
    return str(episode_id or "") in EXEMPT_EPISODES


def scene_exempt_label(rec: dict[str, Any] | None, ep: str | None = None) -> str | None:
    if not scene_look_exempt(rec, ep):
        return None
    ident = ep or ((rec or {}).get("episode") or {}).get("episode_id") or "EP01"
    return f"{EXEMPT_FLAG}={ident}"
