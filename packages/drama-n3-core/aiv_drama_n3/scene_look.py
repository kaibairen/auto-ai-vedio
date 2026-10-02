"""SCENE look hard-gate policy (U-033 / AIV-036).

Episode/project scoped. Not a global forever kill of SCENE look.
ForcePass=never — this is not a bypass key.

Product pin (NOTE-AIV-036-SCENE-EXEMPT-EP01, md5 3c58b933f94633bfde9b5a323b916132):
``proj_01`` / ``EP01`` · all SCENE-* on that episode · CHAR usable stays hard.

Explicit ``episode.scene_look`` / ``episode.scene_look_exempt`` is an auditable
override (including rollback to ``required``). It is not ForcePass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiv_drama_n3.cards import all_cards, has_usable_ref, is_char_id, is_scene_id

SCENE_LOOK_REQUIRED = "required"
SCENE_LOOK_OPTIONAL = "optional"
SCENE_LOOK_EXEMPT = "exempt"
SCENE_LOOK_MODES = frozenset({SCENE_LOOK_REQUIRED, SCENE_LOOK_OPTIONAL, SCENE_LOOK_EXEMPT})

# NOTE-AIV-036 §2 machine field. Value is the exempt episode id.
SCENE_LOOK_EXEMPT_KEY = "SCENE-LOOK-EXEMPT"
EXEMPT_NOTE_ID = "NOTE-AIV-036-SCENE-EXEMPT-EP01"
EXEMPT_NOTE_MD5 = "3c58b933f94633bfde9b5a323b916132"
EXEMPT_ASSIGN = "AIV-036-ENG-033-IMPL"

# Product pin: only this (project, episode) pair. Not proj_* / EP* globally.
PINNED_SCENE_LOOK_EXEMPT_SCOPES: frozenset[tuple[str, str]] = frozenset({("proj_01", "EP01")})
PINNED_EXEMPT_EPISODE_ID = "EP01"
PINNED_EXEMPT_PROJECT_ID = "proj_01"

SCENE_LOOK_EXEMPT_COPY_ZH = "本集已书面豁免场景 look：无定场图不挡开提示词拼装；场靠厚卡与分镜文案。"
SCENE_LOOK_EXEMPT_COPY_EN = (
    "This episode has a written SCENE-look exemption: missing plates do not "
    "block prompt assemble; scenes use thick-card + shot copy."
)
CHAR_HARD_COPY_ZH = "须本集目标人物定妆 usable 通过；缺脸或未人审仍拦截。"
CHAR_HARD_COPY_EN = "Target CHAR usable (face/full) remains a hard gate; missing face still blocks."
CHAR_USABLE_FALSE_MESSAGE = "usable_for_n4=false · 人物缺合格脸图或 usable=false，拒绝写盘"
SCENE_OPTIONAL_WARN = SCENE_LOOK_EXEMPT_COPY_ZH

SOURCE_PIN = "pin"
SOURCE_EPISODE_FLAG = "episode_flag"
SOURCE_DEFAULT = "default"


@dataclass(frozen=True)
class SceneLookPolicy:
    mode: str
    project_id: str | None
    episode_id: str | None
    source: str
    note_id: str | None = None
    scene_ids: tuple[str, ...] = ()

    @property
    def scene_optional(self) -> bool:
        return self.mode in {SCENE_LOOK_OPTIONAL, SCENE_LOOK_EXEMPT}

    @property
    def exempt_machine_value(self) -> str | None:
        if not self.scene_optional:
            return None
        return self.episode_id or PINNED_EXEMPT_EPISODE_ID


def is_scene_card(card: dict[str, Any] | None) -> bool:
    if not card:
        return False
    if card.get("kind") == "scene":
        return True
    return is_scene_id(card.get("id"))


def is_char_card(card: dict[str, Any] | None) -> bool:
    if not card:
        return False
    if card.get("kind") == "character":
        return True
    return is_char_id(card.get("id"))


def scene_ids_from_n3(n3: dict[str, Any] | None) -> tuple[str, ...]:
    out: list[str] = []
    for card in all_cards(n3):
        if not is_scene_card(card):
            continue
        ident = card.get("id")
        if ident and ident not in out:
            out.append(ident)
    return tuple(out)


def hard_usable_cards(n3: dict[str, Any] | None, policy: SceneLookPolicy) -> list[dict[str, Any]]:
    """Cards that still AND into usable_for_n4. SCENE dropped on optional/exempt."""
    cards = all_cards(n3)
    if policy.scene_optional:
        return [card for card in cards if is_char_card(card)]
    return cards


def _scope(rec: dict[str, Any] | None, *, project_id: str | None, episode_id: str | None) -> tuple[str | None, str | None]:
    if rec:
        ep = rec.get("episode") or {}
        project_id = project_id or ep.get("project_id")
        episode_id = episode_id or ep.get("episode_id")
        n3 = rec.get("n3") or {}
        cards = n3.get("cards") or {}
        episode_id = episode_id or cards.get("episode_id")
    return project_id, episode_id


def _normalize_mode(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    text = str(raw).strip().lower()
    if text in SCENE_LOOK_MODES:
        return text
    return None


def _explicit_mode(rec: dict[str, Any] | None) -> str | None:
    """Auditable episode/n3 marker. Not a ForcePass key."""
    if not rec:
        return None
    n3 = rec.get("n3") or {}
    blobs = (rec.get("episode") or {}, n3, n3.get("cards") or {})
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        mode = _normalize_mode(blob.get("scene_look") or blob.get("scene_look_mode"))
        if mode:
            return mode
        flag = blob.get("scene_look_exempt")
        if flag is True:
            return SCENE_LOOK_EXEMPT
        if flag is False:
            return SCENE_LOOK_REQUIRED
    return None


def resolve_scene_look_policy(
    rec: dict[str, Any] | None = None,
    *,
    project_id: str | None = None,
    episode_id: str | None = None,
    scene_look: str | None = None,
    n3: dict[str, Any] | None = None,
) -> SceneLookPolicy:
    """Resolve SCENE look gate mode. Default is required (old hard-AND)."""
    project_id, episode_id = _scope(rec, project_id=project_id, episode_id=episode_id)
    cards_n3 = n3 if n3 is not None else (rec or {}).get("n3")
    scenes = scene_ids_from_n3(cards_n3)

    explicit = _normalize_mode(scene_look) or _explicit_mode(rec)
    if explicit:
        return SceneLookPolicy(
            mode=explicit,
            project_id=project_id,
            episode_id=episode_id,
            source=SOURCE_EPISODE_FLAG,
            note_id=EXEMPT_NOTE_ID if explicit != SCENE_LOOK_REQUIRED else None,
            scene_ids=scenes,
        )
    if project_id and episode_id and (project_id, episode_id) in PINNED_SCENE_LOOK_EXEMPT_SCOPES:
        return SceneLookPolicy(
            mode=SCENE_LOOK_EXEMPT,
            project_id=project_id,
            episode_id=episode_id,
            source=SOURCE_PIN,
            note_id=EXEMPT_NOTE_ID,
            scene_ids=scenes,
        )
    return SceneLookPolicy(
        mode=SCENE_LOOK_REQUIRED,
        project_id=project_id,
        episode_id=episode_id,
        source=SOURCE_DEFAULT,
        note_id=None,
        scene_ids=scenes,
    )


def scene_ref_honesty(n3: dict[str, Any] | None) -> list[dict[str, Any]]:
    """SCENE cards without a usable plate. Honesty only — never flips usable=true."""
    out: list[dict[str, Any]] = []
    for card in all_cards(n3):
        if not is_scene_card(card) or has_usable_ref(card):
            continue
        out.append(
            {
                "id": card.get("id"),
                "kind": card.get("kind") or "scene",
                "name": card.get("name"),
                "reason": "missing_ref",
            }
        )
    return out


def scene_look_envelope_fields(
    policy: SceneLookPolicy,
    *,
    scene_missing_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Honesty fields for G3/N4 envelopes. Does not flip card usable flags."""
    fields: dict[str, Any] = {
        "scene_look": policy.mode,
        "scene_look_source": policy.source,
        "scene_look_scope": {
            "project_id": policy.project_id,
            "episode_id": policy.episode_id,
            "scenes": list(policy.scene_ids),
        },
    }
    if policy.scene_optional:
        fields[SCENE_LOOK_EXEMPT_KEY] = policy.exempt_machine_value
        fields["scene_look_note"] = policy.note_id or EXEMPT_NOTE_ID
        fields["scene_look_copy"] = SCENE_LOOK_EXEMPT_COPY_ZH
    if scene_missing_refs:
        fields["scene_missing_refs"] = list(scene_missing_refs)
    return fields
