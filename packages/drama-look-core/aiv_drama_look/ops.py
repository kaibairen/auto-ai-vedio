"""DramaService mixin: generate look for one thickened card."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import now_iso
from aiv_drama_look.generate import generate_look_for_card
from aiv_drama_look.models import LookGenerateRequest
from aiv_drama_look.provider.select import build_image_provider
from aiv_drama_look.sku import DEFAULT_SKU
from aiv_drama_n3.cards import all_cards, has_usable_ref
from aiv_drama_n3.library import KIND_CHAR, parse_kind
from aiv_drama_n3.looks import ensure_looks_card_dirs
from aiv_drama_n3.refs import refresh_n3_ref_flags
from aiv_drama_n3.validate import CARDS_EMPTY_MESSAGE, CAST_ONLY_MESSAGE, reject_force_keys_n3
from aiv_schema.models import NODE_DN3


class DramaLookOps:
    """Hang looks + refs. Does not flip usable_for_n4. Does not write N4 jsonl."""

    def generate_look(
        self,
        project_id: str,
        ep: str,
        body: LookGenerateRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        image_provider: Any | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        if isinstance(raw, dict) and raw.get("usable_for_n4") is True:
            raise AppError(
                400,
                "validation",
                "look generate 禁止翻转 usable_for_n4（仅挂起面三轴）",
                field="usable_for_n4",
                node=NODE_DN3,
            )
        req = body or LookGenerateRequest(id="")
        if req.watermark is True:
            raise AppError(422, "validation", "入库水印默认关；禁止 watermark=true", node=NODE_DN3, field="watermark")
        cached = self._idem_get(idempotency_key, f"look_generate:{project_id}:{ep}:{req.id}:{req.ref or ''}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        self._require_n3_unlock(rec, req.unlock_edit)
        cards = (rec.get("n3") or {}).get("cards")
        if not cards or not cards.get("materialized"):
            raise AppError(422, "cards_empty", CARDS_EMPTY_MESSAGE, node=NODE_DN3)
        kind = parse_kind(req.id, None)
        card = self._find_card(rec, req.id, kind)
        if card is None:
            raise AppError(422, "card_id_not_in_cast", CAST_ONLY_MESSAGE, id=req.id, node=NODE_DN3)

        settings = self.settings
        provider = image_provider or build_image_provider(settings, req.provider, sku=req.sku)
        episode_dir = self.store.episode_dir(project_id, rec["episode"]["episode_id"])
        look_state = deepcopy((rec.get("n3") or {}).get("look") or {})
        result = generate_look_for_card(
            episode_dir=episode_dir,
            episode_id=rec["episode"]["episode_id"],
            card=card,
            image_provider=provider,
            view=req.view,
            role=req.role,
            sku=req.sku,
            settings_sku=getattr(settings, "look_sku", None) or DEFAULT_SKU,
            style_ref=req.style_ref,
            settings_style=getattr(settings, "look_style_ref", None),
            seed=req.seed,
            upgrade_reason=req.upgrade_reason,
            look_state=look_state,
            ref=req.ref,
        )
        updated = result["card"]
        bucket = "characters" if kind == KIND_CHAR else "scenes"
        cards[bucket] = [updated if c.get("id") == req.id else c for c in cards.get(bucket) or []]
        cards["version"] = (cards.get("version") or 0) + 1
        cards["stale"] = False
        cards["updated_at"] = now_iso()
        cards["updated_by"] = req.actor
        # Hang only. Do not compute-flip usable_for_n4 to true.
        refresh_n3_ref_flags(rec.get("n3"))
        cards["usable_for_n4"] = False
        ensure_looks_card_dirs(episode_dir, kind, req.id)
        rec["n3"]["look"] = result["look_state"]
        rec["episode"]["versions"]["cards"] = cards["version"]
        rec["episode"]["next_edges"] = [NODE_DN3]
        self._touch_episode(rec)
        self._commit(rec)

        env = self.n3_envelope(
            rec,
            extra={
                "look": {
                    "path": result["rel_path"],
                    "md5": result["md5"],
                    "role": result["ref"]["role"],
                    "sku": result["sku"],
                    "seed": result["seed"],
                    "provider": result["provider"],
                    "seed_replay": result["seed_replay"],
                    "prompt_hash": result["prompt"]["prompt_hash"],
                    "view": result["meta"].get("view"),
                    "usable_for_n4_flipped": False,
                },
                "usable_for_n4": False,
                "provider": result["provider"],
            },
        )
        env["usable_for_n4"] = False
        env["cards"]["usable_for_n4"] = False
        # Honesty: hanging a face does not by itself green N4.
        if env.get("cards"):
            for hung in all_cards({"cards": env["cards"]}):
                hung.pop("usable_for_n4", None)
        env["has_usable_ref"] = has_usable_ref(updated)
        return self._idem_put(idempotency_key, f"look_generate:{project_id}:{ep}:{req.id}:{req.ref or ''}", env)
