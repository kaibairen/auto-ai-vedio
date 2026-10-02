"""One-card look generate orchestration (no usable flip, no N4 write)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import now_iso
from aiv_drama_look.materialize import materialize_look_bytes, read_meta
from aiv_drama_look.paths import default_role, default_view, looks_absdir, validate_role, validate_view
from aiv_drama_look.prompt import assemble_look_prompt
from aiv_drama_look.provider.base import FrozenParams, ImageProvider, default_frozen_params
from aiv_drama_look.refs import append_ref
from aiv_drama_look.seed import seed_for_card
from aiv_drama_look.sku import (
    DEFAULT_SKU,
    MAX_DRAWS_PER_CARD,
    MAX_DRAWS_PER_EPISODE,
    resolve_sku,
)
from aiv_schema.models import NODE_DN3


def ensure_cost_cap(look_state: dict[str, Any] | None, card_id: str) -> None:
    state = look_state or {}
    by_card = dict(state.get("by_card") or {})
    episode_count = int(state.get("episode_count") or 0)
    card_count = int(by_card.get(card_id) or 0)
    if card_count >= MAX_DRAWS_PER_CARD:
        raise AppError(
            409,
            "look_cost_cap",
            f"单角色/轮出图已达 {MAX_DRAWS_PER_CARD} 张帽，停抽改卡/提示",
            card_id=card_id,
            node=NODE_DN3,
        )
    if episode_count >= MAX_DRAWS_PER_EPISODE:
        raise AppError(
            409,
            "look_cost_cap",
            f"集级出图已达 {MAX_DRAWS_PER_EPISODE} 张帽（≈¥3.84 flash），停抽",
            node=NODE_DN3,
        )


def record_draw(look_state: dict[str, Any] | None, card_id: str, sku: str) -> dict[str, Any]:
    state = dict(look_state or {})
    by_card = dict(state.get("by_card") or {})
    by_card[card_id] = int(by_card.get(card_id) or 0) + 1
    draws = list(state.get("draws") or [])
    draws.append({"card_id": card_id, "sku": sku, "at": now_iso()})
    state["by_card"] = by_card
    state["draws"] = draws[-64:]
    state["episode_count"] = int(state.get("episode_count") or 0) + 1
    return state


def generate_look_for_card(
    *,
    episode_dir: Path,
    episode_id: str,
    card: dict[str, Any],
    image_provider: ImageProvider,
    view: str | None = None,
    role: str | None = None,
    sku: str | None = None,
    settings_sku: str | None = None,
    style_ref: str | None = None,
    settings_style: str | None = None,
    seed: int | None = None,
    upgrade_reason: str | None = None,
    look_state: dict[str, Any] | None = None,
    frozen: FrozenParams | None = None,
) -> dict[str, Any]:
    kind = card.get("kind") or "character"
    card_id = card["id"]
    chosen_view = validate_view(view or default_view(kind))
    chosen_role = validate_role(kind, role or default_role(kind))
    ensure_cost_cap(look_state, card_id)

    existing_meta = read_meta(looks_absdir(episode_dir, kind, card_id))
    chosen_sku, upgrade_meta = resolve_sku(
        sku,
        settings_sku=settings_sku or DEFAULT_SKU,
        current_sku=(existing_meta or {}).get("sku"),
        upgrade_reason=upgrade_reason,
    )
    chosen_seed = seed_for_card(card_id, kind, existing_meta=existing_meta, requested=seed)
    assembled = assemble_look_prompt(
        card,
        view=chosen_view,
        style_ref=style_ref,
        settings_style=settings_style,
    )
    params = frozen or default_frozen_params(watermark=False)
    result = image_provider.generate(
        assembled["prompt"],
        [],
        params,
        chosen_seed,
        sku=chosen_sku,
    )
    if not result.images:
        raise AppError(502, "provider", "look provider returned no images", node=NODE_DN3)
    meta = {
        "sku": result.sku or chosen_sku,
        "seed": result.seed if result.seed is not None else chosen_seed,
        "frozen_params": params.as_dict(),
        "prompt_hash": assembled["prompt_hash"],
        "created_at": now_iso(),
        "provider": result.provider,
        "seed_replay": result.seed_replay,
    }
    if upgrade_meta:
        meta.update(upgrade_meta)
    written = materialize_look_bytes(
        episode_dir=episode_dir,
        episode_id=episode_id,
        card=card,
        role=chosen_role,
        view=chosen_view,
        data=result.images[0],
        meta=meta,
    )
    updated = append_ref(card, written["ref"])
    return {
        "card": updated,
        "ref": written["ref"],
        "rel_path": written["rel_path"],
        "abs_path": written["abs_path"],
        "md5": written["md5"],
        "meta": written["meta"],
        "prompt": assembled,
        "look_state": record_draw(look_state, card_id, result.sku or chosen_sku),
        "usable_for_n4_flipped": False,
        "seed": meta["seed"],
        "sku": result.sku or chosen_sku,
        "provider": result.provider,
        "seed_replay": result.seed_replay,
    }
