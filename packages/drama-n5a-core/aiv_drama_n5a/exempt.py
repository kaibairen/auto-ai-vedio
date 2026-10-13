"""SCENE look is not exempt on N5a.

Tip SoT (`scene_look_forbidden`): gold-A is CHAR-only; SCENE is a separate track.
检 G4 (场) stays pending/hard for every episode, including EP01.
Does not flip SCENE usable_for_n4. Does not green N4.
"""

from __future__ import annotations

from typing import Any


def scene_look_exempt(rec: dict[str, Any] | None = None, ep: str | None = None) -> bool:
    """Always false. EP01 is not auto-EXEMPT; explicit flags are ignored."""
    del rec, ep
    return False


def scene_exempt_label(rec: dict[str, Any] | None = None, ep: str | None = None) -> str | None:
    del rec, ep
    return None
