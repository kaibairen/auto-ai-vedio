from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.models import LibraryCharacterWrite
from aiv_drama.secrets import reject_retry_flag, reject_secret_fields
from aiv_drama.validate import now_iso
from aiv_drama_n3.cards import all_cards, is_scene_id, materialize_cards
from aiv_drama_n3.crop import crop_view
from aiv_drama_n3.library import (
    KIND_CHAR,
    KIND_SCENE,
    apply_library_to_card,
    card_to_library_record,
    character_store_key,
    normalize_refs,
    parse_kind,
    resolve_ref_file,
    scene_store_key,
)
from aiv_drama_n3.gold_sheet import LOOK_KIND, LOOK_ROLE
from aiv_drama_n3.look_generate import generate_gold_a_sheet
from aiv_drama_n3.models import (
    LibrarySceneWrite,
    N3AttachRequest,
    N3ForkRequest,
    N3GenerateLookRequest,
    N3MaterializeRequest,
    N3PromoteRequest,
    N3ThickenRequest,
)
from aiv_drama_n3.seedream import ARK_IMAGES_URL
from aiv_drama_n3.thicken import normalize_thicken_provider, thicken_cards
from aiv_drama_n3.policy import default_project_scope, hanging_bundle, project_scope_capability
from aiv_drama_n3.projection import write_character_schema, write_episode_cards, write_scene_schema
from aiv_drama_n3.templates import assert_no_prompt_in_skill_paths, n3_observability
from aiv_drama_n3.validate import (
    CARDS_EMPTY_MESSAGE,
    CAST_ONLY_MESSAGE,
    G3_FORCE_MESSAGE,
    UPSTREAM_G2_MESSAGE,
    collect_n3_issues,
    raise_hard,
    reject_force_keys_n3,
    reject_image_gen_n3,
    usable_for_n4,
)
from aiv_schema.models import GATE_G2, GATE_G3, NODE_DN2, NODE_DN3, NODE_DN4, PIPELINE_DRAMA


def empty_gate_g3() -> dict[str, Any]:
    return {
        "gate_id": GATE_G3,
        "state": "idle",
        "locked": False,
        "version": 0,
        "last_decision": None,
        "note": None,
        "actor": None,
        "decided_at": None,
    }


def empty_n3_cards(rec: dict[str, Any]) -> dict[str, Any]:
    cast = rec.get("cast") or {}
    sb = rec.get("storyboard") or {}
    return {
        "episode_id": rec["episode"]["episode_id"],
        "pipeline_profile": PIPELINE_DRAMA,
        "characters": [],
        "scenes": [],
        "version": 0,
        "upstream_cast_version": cast.get("version") or 0,
        "upstream_storyboard_version": sb.get("version") or 0,
        "stale": False,
        "locked": False,
        "confirmed_by": None,
        "usable_for_n4": False,
        "materialized": False,
        "updated_at": None,
        "updated_by": None,
    }


class DramaN3Ops:
    """D-N3 unit cards + G3 thin gate + library attach/promote stubs."""

    def _ensure_n3_fields(self, rec: dict[str, Any]) -> None:
        rec["episode"]["versions"].setdefault("cards", 0)
        rec["episode"]["locks"].setdefault("g3", False)
        rec.setdefault("d_n4_jobs", [])
        rec.setdefault("n3", None)
        if not rec.get("gate_g3"):
            rec["gate_g3"] = empty_gate_g3()
        rec.setdefault("library_ops", [])

    def _g2_locked(self, rec: dict[str, Any]) -> bool:
        sb = rec.get("storyboard") or {}
        g2 = rec.get("gate_g2") or {}
        return bool(sb.get("locked") and g2.get("locked") and g2.get("last_decision") == "pass")

    def _require_g2_for_n3(self, rec: dict[str, Any]) -> None:
        if rec["episode"].get("pipeline_profile") != PIPELINE_DRAMA:
            raise AppError(422, "wrong_profile", "pipeline_profile must be drama", node=NODE_DN3)
        if not self._g2_locked(rec):
            raise AppError(
                409,
                "upstream_unlocked",
                UPSTREAM_G2_MESSAGE,
                node=NODE_DN2,
                gate=GATE_G2,
            )

    def _stale_n3(self, rec: dict[str, Any]) -> None:
        n3 = rec.get("n3")
        if n3 and n3.get("cards"):
            n3["cards"]["stale"] = True
            n3["cards"]["locked"] = False
            n3["cards"]["confirmed_by"] = None
            n3["cards"]["usable_for_n4"] = False
            for card in all_cards(n3):
                card["decision"] = None
        if rec.get("gate_g3"):
            rec["gate_g3"]["locked"] = False
            if rec["gate_g3"].get("state") == "passed":
                rec["gate_g3"]["state"] = "ready"
        rec["episode"]["locks"]["g3"] = False
        if NODE_DN3 not in (rec["episode"].get("stale_downstream") or []):
            rec["episode"].setdefault("stale_downstream", []).append(NODE_DN3)

    def _require_storyboard_unlock(self, rec: dict[str, Any], unlock_edit: bool) -> None:
        super()._require_storyboard_unlock(rec, unlock_edit)  # type: ignore[misc]
        if not (rec.get("storyboard") or {}).get("locked"):
            self._stale_n3(rec)

    def _finish_storyboard(self, rec: dict[str, Any], sb: dict[str, Any], *, actor: str | None, bump: bool = True) -> None:
        super()._finish_storyboard(rec, sb, actor=actor, bump=bump)  # type: ignore[misc]
        self._stale_n3(rec)

    def _require_n3_unlock(self, rec: dict[str, Any], unlock_edit: bool) -> None:
        self._require_writable_episode(rec)
        cards = (rec.get("n3") or {}).get("cards") or {}
        if cards.get("locked"):
            if not unlock_edit:
                raise AppError(409, "locked", "G3 已锁定；改卡须 unlock_edit", node=NODE_DN3, gate=GATE_G3)
            self._stale_n3(rec)

    def _n3_obs(self) -> dict[str, Any]:
        return n3_observability(self.settings.repo_root)

    def _cards_view(self, rec: dict[str, Any]) -> dict[str, Any]:
        n3 = rec.get("n3")
        if n3 and n3.get("cards"):
            view = deepcopy(n3["cards"])
        else:
            view = empty_n3_cards(rec)
        view["usable_for_n4"] = usable_for_n4(rec.get("n3"), g3_locked=bool((rec.get("gate_g3") or {}).get("locked")))
        return view

    def _refresh_usable(self, rec: dict[str, Any]) -> None:
        n3 = rec.get("n3")
        if not n3 or not n3.get("cards"):
            return
        n3["cards"]["usable_for_n4"] = usable_for_n4(n3, g3_locked=bool(rec["gate_g3"].get("locked")))

    def n3_envelope(
        self,
        rec: dict[str, Any],
        *,
        warnings: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        obs = self._n3_obs()
        edges = list(rec["episode"].get("next_edges") or [])
        if rec["gate_g3"].get("locked"):
            edges = [NODE_DN4]
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN3,
            "cards": self._cards_view(rec),
            "storyboard_crop": crop_view(rec.get("storyboard")),
            "gate": deepcopy(rec["gate_g3"]),
            "next_edges": edges,
            "stale_downstream": list(rec["episode"].get("stale_downstream") or []),
            "usable_for_n4": usable_for_n4(rec.get("n3"), g3_locked=bool(rec["gate_g3"].get("locked"))),
            "template_paths": list(obs["template_paths"]),
            "prompt_paths": list(obs["prompt_paths"]),
            "scene_template": deepcopy(obs["scene_template"]),
            "seedance_param_ref": deepcopy(obs["seedance_param_ref"]),
            "library_policy": hanging_bundle(),
            "docs_pass": False,
            "auto_open_dn4": False,
        }
        looks = (rec.get("n3") or {}).get("looks")
        if looks:
            env["looks"] = deepcopy(looks)
        thicken = (rec.get("n3") or {}).get("thicken")
        if thicken:
            skill_paths = list(thicken.get("skill_paths") or [])
            assert_no_prompt_in_skill_paths(skill_paths)
            env["thicken_skill_paths"] = skill_paths
            env["thicken_prompt_paths"] = list(thicken.get("prompt_paths") or [])
            env["model"] = thicken.get("model")
            env["fixture_hits"] = int(thicken.get("fixture_hits") or 0)
            env["provider"] = thicken.get("provider") or "llm"
            if thicken.get("scene_template"):
                env["scene_template"] = deepcopy(thicken["scene_template"])
        if rec.get("projection_dirty"):
            env["projection_dirty"] = True
        if warnings:
            env["warnings"] = warnings
        if extra:
            env.update(extra)
        return env

    def gate_g3_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        env = self.n3_envelope(rec)
        return {
            "ok": True,
            "project_id": env["project_id"],
            "episode_id": env["episode_id"],
            "node": NODE_DN3,
            "gate": env["gate"],
            "cards": env["cards"],
            "usable_for_n4": env["usable_for_n4"],
            "next_edges": env["next_edges"],
            "warnings": env.get("warnings") or [],
            "template_paths": env["template_paths"],
            "prompt_paths": env["prompt_paths"],
            "auto_open_dn4": False,
        }

    def _put_library_op(self, rec: dict[str, Any], op: str, payload: dict[str, Any]) -> None:
        rec.setdefault("library_ops", []).append(
            {"op": op, "at": now_iso(), **payload, "skipped_g3": False, "auto_passed_g3": False}
        )

    def get_n3(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        issues = collect_n3_issues(rec)
        warns = [i for i in issues if i.get("severity") == "warn"]
        return self.n3_envelope(rec, warnings=warns or None)

    def get_n3_cards(self, project_id: str, ep: str) -> dict[str, Any]:
        return self.get_n3(project_id, ep)

    def get_n3_crop(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        obs = self._n3_obs()
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN3,
            "storyboard_crop": crop_view(rec.get("storyboard")),
            "template_paths": list(obs["template_paths"]),
            "prompt_paths": list(obs["prompt_paths"]),
            "readonly": True,
        }

    def materialize_n3_cards(
        self,
        project_id: str,
        ep: str,
        body: N3MaterializeRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        cached = self._idem_get(idempotency_key, f"n3_materialize:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        req = body or N3MaterializeRequest()
        self._require_n3_unlock(rec, req.unlock_edit)
        prev = (rec.get("n3") or {}).get("cards")
        characters, scenes, skipped = materialize_cards(rec.get("cast"), rec.get("storyboard"), prev)
        cards = empty_n3_cards(rec)
        cards["characters"] = characters
        cards["scenes"] = scenes
        cards["materialized"] = True
        cards["version"] = ((prev or {}).get("version") or 0) + 1
        cards["stale"] = False
        cards["locked"] = False
        cards["confirmed_by"] = None
        cards["updated_at"] = now_iso()
        cards["updated_by"] = req.actor
        rec["n3"] = {"cards": cards}
        rec["gate_g3"]["state"] = "ready" if (characters or scenes) else "idle"
        rec["gate_g3"]["locked"] = False
        rec["episode"]["locks"]["g3"] = False
        rec["episode"]["next_edges"] = [NODE_DN3]
        rec["episode"]["versions"]["cards"] = cards["version"]
        self._refresh_usable(rec)
        self._touch_episode(rec)
        self._commit(rec)
        issues = collect_n3_issues(rec)
        warns = [i for i in issues if i.get("severity") == "warn"] + skipped
        return self._idem_put(
            idempotency_key,
            f"n3_materialize:{project_id}:{ep}",
            self.n3_envelope(rec, warnings=warns or None),
        )

    def thicken_n3_cards(
        self,
        project_id: str,
        ep: str,
        body: N3ThickenRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        reject_image_gen_n3(raw)
        req = body or N3ThickenRequest()
        provider = normalize_thicken_provider(req.provider)
        if provider != "llm":
            raise AppError(
                422,
                "provider",
                "N3 thicken requires provider=llm; fixture is not a success path (fixture_hits must stay 0)",
                node=NODE_DN3,
                provider=req.provider,
            )
        selected = [i for i in (req.ids or []) if i]
        idem_tail = f"{project_id}:{ep}:" + (",".join(selected) if selected else "*")
        cached = self._idem_get(idempotency_key, f"n3_thicken:{idem_tail}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        self._require_n3_unlock(rec, req.unlock_edit)
        cards = (rec.get("n3") or {}).get("cards")
        if not cards or not cards.get("materialized"):
            raise AppError(422, "cards_empty", CARDS_EMPTY_MESSAGE, node=NODE_DN3)
        characters = list(cards.get("characters") or [])
        scenes = list(cards.get("scenes") or [])
        by_id = {c.get("id"): c for c in characters + scenes}
        if selected:
            missing = [ident for ident in selected if ident not in by_id]
            if missing:
                raise AppError(
                    422,
                    "card_id_not_in_cast",
                    CAST_ONLY_MESSAGE,
                    id=missing[0],
                    ids=missing,
                    node=NODE_DN3,
                )
            targets = [by_id[ident] for ident in selected]
        else:
            targets = characters + scenes
        snap_fn = getattr(self, "generation_blocked", None)
        if callable(snap_fn):
            snap = snap_fn(project_id, rec["episode"]["episode_id"])
        else:
            snap_fn = getattr(self, "cost_snapshot_project", None)
            if not callable(snap_fn):
                raise AppError(
                    409,
                    "over_cap",
                    "spend snapshot unavailable; thicken refused",
                    blocked=True,
                )
            snap = snap_fn(project_id)
        if snap.get("blocked"):
            raise AppError(
                409,
                "over_cap",
                "spend ceiling reached; generation is blocked",
                spent=snap.get("spent"),
                cap=snap.get("cap"),
                remaining=snap.get("remaining"),
                blocked=True,
            )
        result = thicken_cards(
            self.settings,
            episode_id=rec["episode"]["episode_id"],
            cards=targets,
            storyboard=rec.get("storyboard"),
            include_bio_skill=bool(req.include_bio_skill),
        )
        applied = {c.get("id"): c for c in result["cards"]}
        cards["characters"] = [applied.get(c.get("id"), c) for c in characters]
        cards["scenes"] = [applied.get(s.get("id"), s) for s in scenes]
        cards["version"] = (cards.get("version") or 0) + 1
        cards["stale"] = False
        cards["updated_at"] = now_iso()
        cards["updated_by"] = req.actor
        # Text thicken must not flip usable / write refs / start N4.
        self._refresh_usable(rec)
        rec["n3"]["thicken"] = {
            "provider": "llm",
            "model": result["model"],
            "fixture_hits": 0,
            "prompt_paths": list(result["prompt_paths"]),
            "skill_paths": list(result["skill_paths"]),
            "scene_template": deepcopy(result["scene_template"]),
            "thickened_ids": [c.get("id") for c in result["cards"]],
            "include_bio_skill": bool(req.include_bio_skill),
        }
        assert_no_prompt_in_skill_paths(rec["n3"]["thicken"]["skill_paths"])
        rec["episode"]["versions"]["cards"] = cards["version"]
        rec["episode"]["next_edges"] = [NODE_DN3]
        rec["gate_g3"]["state"] = "ready" if (cards.get("characters") or cards.get("scenes")) else "idle"
        rec["gate_g3"]["locked"] = False
        rec["episode"]["locks"]["g3"] = False
        self._touch_episode(rec)
        self._commit(rec)
        issues = collect_n3_issues(rec)
        warns = [i for i in issues if i.get("severity") == "warn"]
        extra = {
            "thicken_skill_paths": list(result["skill_paths"]),
            "thicken_prompt_paths": list(result["prompt_paths"]),
            "prompt_paths": list(result["prompt_paths"]) or list(self._n3_obs()["prompt_paths"]),
            "model": result["model"],
            "fixture_hits": 0,
            "provider": "llm",
            "scene_template": deepcopy(result["scene_template"]),
            "thickened_ids": [c.get("id") for c in result["cards"]],
        }
        return self._idem_put(
            idempotency_key,
            f"n3_thicken:{idem_tail}",
            self.n3_envelope(rec, warnings=warns or None, extra=extra),
        )

    def generate_n3_look(
        self,
        project_id: str,
        ep: str,
        body: N3GenerateLookRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        post: Any | None = None,
        get: Any | None = None,
    ) -> dict[str, Any]:
        """Gold-A 3:2 single sheet. Shared generate_gold_a_sheet. Never flips usable_for_n4.

        Live attempts (success or failure) count toward a cumulative cap of 2.
        One call hits one SKU. Empty Idempotency-Key is not a second free attempt.
        """
        reject_force_keys_n3(raw)
        reject_secret_fields(raw)
        reject_retry_flag(raw)
        if isinstance(raw, dict) and "sequential_image_generation" in raw:
            raise AppError(
                400,
                "validation",
                "forbidden: sequential_image_generation",
                node=NODE_DN3,
                field="sequential_image_generation",
            )
        req = body or N3GenerateLookRequest.model_validate(raw or {})
        idem_op = f"n3_look:{project_id}:{ep}:{req.id}:{int(req.dry_run)}"
        cached = self._idem_get(idempotency_key, idem_op)
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        self._require_writable_episode(rec)
        if not req.dry_run:
            require_budget = getattr(self, "_require_generation_budget", None)
            if callable(require_budget):
                require_budget(project_id, rec["episode"]["episode_id"])
            require_look = getattr(self, "require_look_attempt_available", None)
            if callable(require_look):
                require_look(rec)
        cards = (rec.get("n3") or {}).get("cards")
        if not cards or not cards.get("materialized"):
            raise AppError(422, "cards_empty", CARDS_EMPTY_MESSAGE, node=NODE_DN3)
        kind = parse_kind(req.id, None)
        if kind != KIND_CHAR:
            raise AppError(
                422,
                "scene_look_forbidden",
                "金样 A 合板仅 CHAR；SCENE 另轨",
                id=req.id,
                node=NODE_DN3,
            )
        card = self._find_card(rec, req.id, KIND_CHAR)
        if card is None:
            raise AppError(422, "card_id_not_in_cast", CAST_ONLY_MESSAGE, id=req.id, node=NODE_DN3)
        face = (req.face_ref or "").strip()
        if not face:
            for ref in card.get("refs") or []:
                if not isinstance(ref, dict):
                    continue
                if (ref.get("role") or "").strip() in {"face", "style_ref"} and (ref.get("path") or "").strip():
                    face = ref["path"].strip()
                    break
        if not face:
            raise AppError(
                422,
                "material_bind",
                "缺脸 ref；材料绑定门未过，禁 generate",
                node=NODE_DN3,
                id=req.id,
            )
        resolved = resolve_ref_file(self.settings, face)
        if resolved is not None:
            face = str(resolved)
        ep_id = rec["episode"]["episode_id"]
        out_dir = Path(req.out_dir) if req.out_dir else self.store.episode_dir(project_id, ep_id) / "looks" / req.id
        endpoint = f"{getattr(self.settings, 'ark_base_url', None) or ARK_IMAGES_URL.rsplit('/images', 1)[0]}/images/generations"
        try:
            look = generate_gold_a_sheet(
                card=card,
                face_ref=face,
                expected_md5=req.expected_md5,
                out_dir=out_dir,
                api_key=getattr(self.settings, "ark_api_key", None),
                dry_run=bool(req.dry_run),
                endpoint=endpoint,
                post=post,
                get=get,
            )
        except AppError as exc:
            if (not req.dry_run) and exc.code not in {
                "material_bind",
                "look_card_incomplete",
                "scene_look_forbidden",
                "cards_empty",
                "card_id_not_in_cast",
                "force_pass_forbidden",
                "validation",
                "attempt_cap",
                "over_cap",
                "redraw_needs_user",
                "locked",
                "upstream_unlocked",
                "episode_abandoned",
                "not_found",
                "wrong_profile",
            }:
                record = getattr(self, "record_look_attempt", None)
                if callable(record):
                    used = record(rec, ok=False, card_id=req.id)
                    self._touch_episode(rec)
                    self._commit(rec)
                    exc.details["attempts_used"] = used
                put_err = getattr(self, "_idem_put_error", None)
                if callable(put_err):
                    put_err(idempotency_key, idem_op, exc)
            raise
        used = 0
        if not req.dry_run:
            record = getattr(self, "record_look_attempt", None)
            if callable(record):
                used = record(rec, ok=True, card_id=req.id)
        else:
            used_fn = getattr(self, "look_attempts_used", None)
            used = int(used_fn(rec) if callable(used_fn) else 0)
        look["attempts_used"] = used
        rec["n3"].setdefault("looks", {})
        rec["n3"]["looks"][req.id] = {k: v for k, v in look.items() if k != "ok"}
        slim = {
            "kind": LOOK_KIND,
            "role": LOOK_ROLE,
            "sheet_path": look.get("sheet_path"),
            "sheet_md5": look.get("sheet_md5"),
            "prompt_path": look.get("prompt_path"),
            "prompt_md5": look.get("prompt_md5"),
            "face_ref_md5": look.get("face_ref_md5"),
            "usable_for_n4": False,
            "dry_run": look.get("dry_run"),
            "model": look.get("model"),
        }
        existing = [x for x in (card.get("looks") or []) if isinstance(x, dict) and x.get("kind") != LOOK_KIND]
        card["looks"] = existing + [slim]
        cards["updated_at"] = now_iso()
        cards["updated_by"] = req.actor
        # Sidecar look write: do not unlock G3, do not bump cards.version, do not touch refs.
        self._refresh_usable(rec)
        self._touch_episode(rec)
        self._commit(rec)
        issues = collect_n3_issues(rec)
        warns = [i for i in issues if i.get("severity") == "warn"]
        extra = {
            "look": look,
            "look_usable_for_n4": False,
            "auto_flipped_usable": False,
            "attempts_used": used,
        }
        return self._idem_put(
            idempotency_key,
            idem_op,
            self.n3_envelope(rec, warnings=warns or None, extra=extra),
        )

    def _find_card(self, rec: dict[str, Any], ident: str, kind: str) -> dict[str, Any] | None:
        cards = (rec.get("n3") or {}).get("cards") or {}
        bucket = "characters" if kind == KIND_CHAR else "scenes"
        return next((c for c in (cards.get(bucket) or []) if c.get("id") == ident), None)

    def _ensure_materialized_for_id(self, rec: dict[str, Any], ident: str, kind: str, actor: str | None) -> None:
        if rec.get("n3") and rec["n3"].get("cards") and rec["n3"]["cards"].get("materialized"):
            return
        characters, scenes, _skipped = materialize_cards(rec.get("cast"), rec.get("storyboard"), None)
        cards = empty_n3_cards(rec)
        cards["characters"] = characters
        cards["scenes"] = scenes
        cards["materialized"] = True
        cards["version"] = 1
        cards["updated_at"] = now_iso()
        cards["updated_by"] = actor
        rec["n3"] = {"cards": cards}
        rec["episode"]["versions"]["cards"] = 1

    def attach_n3_card(
        self,
        project_id: str,
        ep: str,
        body: N3AttachRequest,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        cached = self._idem_get(idempotency_key, f"n3_attach:{project_id}:{ep}:{body.id}@{body.version}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        self._require_writable_episode(rec)
        kind = parse_kind(body.id, body.kind)
        cast = rec.get("cast") or {}
        allowed = {c.get("id") for c in (cast.get("characters") if kind == KIND_CHAR else cast.get("scenes")) or []}
        if body.id not in allowed:
            raise AppError(422, "card_id_not_in_cast", CAST_ONLY_MESSAGE, id=body.id, node=NODE_DN3)
        lib = self._resolve_library_asset(project_id, body.id, body.version, kind)
        if rec.get("gate_g3", {}).get("locked"):
            self._stale_n3(rec)
        self._ensure_materialized_for_id(rec, body.id, kind, body.actor)
        card = self._find_card(rec, body.id, kind)
        if card is None:
            raise AppError(422, "card_id_not_in_cast", CAST_ONLY_MESSAGE, id=body.id, node=NODE_DN3)
        updated = apply_library_to_card(card, lib)
        bucket = "characters" if kind == KIND_CHAR else "scenes"
        cards = rec["n3"]["cards"]
        cards[bucket] = [updated if c.get("id") == body.id else c for c in cards.get(bucket) or []]
        cards["version"] = (cards.get("version") or 0) + 1
        cards["locked"] = False
        cards["confirmed_by"] = None
        cards["stale"] = False
        cards["updated_at"] = now_iso()
        cards["updated_by"] = body.actor
        rec["gate_g3"]["locked"] = False
        rec["episode"]["locks"]["g3"] = False
        rec["episode"]["next_edges"] = [NODE_DN3]
        rec["episode"]["versions"]["cards"] = cards["version"]
        self._refresh_usable(rec)
        self._put_library_op(rec, "attach", {"id": body.id, "version": body.version, "kind": kind})
        self._touch_episode(rec)
        self._commit(rec)
        issues = collect_n3_issues(rec)
        warns = [i for i in issues if i.get("severity") == "warn"]
        extra = {
            "attached": {"id": body.id, "version": body.version, "kind": kind, "binding": updated["binding"]},
            "g3_skipped": False,
            "note": "attach ≠ 跳过本集 G3",
        }
        return self._idem_put(
            idempotency_key,
            f"n3_attach:{project_id}:{ep}:{body.id}@{body.version}",
            self.n3_envelope(rec, warnings=warns or None, extra=extra),
        )

    def promote_n3_card(
        self,
        project_id: str,
        ep: str,
        body: N3PromoteRequest,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        if isinstance(raw, dict) and raw.get("auto_promote"):
            raise AppError(
                400,
                "auto_promote_forbidden",
                "禁止静默 auto-promote（D13 待挂起；默认手动 promote）",
                node=NODE_DN3,
            )
        cached = self._idem_get(idempotency_key, f"n3_promote:{project_id}:{ep}:{body.id}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        self._require_writable_episode(rec)
        kind = parse_kind(body.id, body.kind)
        card = self._find_card(rec, body.id, kind)
        if card is None:
            raise AppError(404, "not_found", "本集工作副本卡不存在；请先 materialize/attach", id=body.id, node=NODE_DN3)
        g3_before = deepcopy(rec.get("gate_g3") or empty_gate_g3())
        latest = self._latest_library_asset(project_id, body.id, kind)
        next_ver = (latest.get("version") if latest else 0) + 1
        record = card_to_library_record(project_id, card, next_ver, kind=kind)
        record["updated_at"] = now_iso()
        record["refs"] = normalize_refs(self.settings, record.get("refs"))
        self._write_library_asset(project_id, record, kind)
        self._put_library_op(rec, "promote", {"id": body.id, "version": next_ver, "kind": kind, "note": body.note})
        # Explicit: promote must not auto-mark G3 pass/locked.
        rec["gate_g3"] = g3_before
        rec["episode"]["locks"]["g3"] = bool(g3_before.get("locked"))
        self._touch_episode(rec)
        self._commit(rec)
        extra = {
            "promoted": {"id": body.id, "version": next_ver, "kind": kind},
            "g3_auto_passed": False,
            "gate_g3_unchanged": rec["gate_g3"].get("locked") == g3_before.get("locked")
            and rec["gate_g3"].get("state") == g3_before.get("state"),
            "note": "promote ≠ 产品 PASS；入库记录 ≠ 本集 G3 通过",
        }
        return self._idem_put(
            idempotency_key,
            f"n3_promote:{project_id}:{ep}:{body.id}",
            self.n3_envelope(rec, extra=extra),
        )

    def fork_n3_card(
        self,
        project_id: str,
        ep: str,
        body: N3ForkRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        rec = self._rec(project_id, ep)
        self._require_g2_for_n3(rec)
        return {
            "ok": True,
            "stub": True,
            "operation": "fork",
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN3,
            "id": body.id,
            "hanging": hanging_bundle()["d15_fork"],
            "chosen": None,
            "written": False,
            "message": "fork 未裁定（D15 待挂起）；本拍不写死同 CHAR 变体 vs 新 ID",
        }

    def get_gate_g3(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        return self.gate_g3_envelope(rec)

    def confirm_gate_g3(
        self,
        project_id: str,
        ep: str,
        raw: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n3(raw)
        extra = set((raw or {}).keys()) - {"decision", "note", "actor", "idempotency_key"}
        if extra:
            raise AppError(400, "validation", "unexpected fields on G3 confirm", fields=sorted(extra), node=NODE_DN3)
        cached = self._idem_get(idempotency_key or raw.get("idempotency_key"), f"confirm_g3:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        self._require_g2_for_n3(rec)
        cards = (rec.get("n3") or {}).get("cards")
        if not cards or not cards.get("materialized"):
            raise AppError(422, "cards_empty", CARDS_EMPTY_MESSAGE, node=NODE_DN3)
        if cards.get("stale"):
            raise AppError(
                409,
                "stale_upstream",
                "cast/分镜已升版；请重新物化本集 cards",
                stale=["d_n3"],
                node=NODE_DN3,
            )
        decision = raw.get("decision")
        actor = (raw.get("actor") or "").strip()
        if decision not in {"pass", "reject"}:
            raise AppError(422, "validation", "decision must be pass|reject", node=NODE_DN3)
        if not actor:
            raise AppError(422, "validation", "actor is required", node=NODE_DN3)
        note = raw.get("note")
        ts = now_iso()
        issues = collect_n3_issues(rec, for_pass=(decision == "pass"))
        warns = [i for i in issues if i.get("severity") == "warn"]
        if decision == "pass":
            raise_hard(issues)
            cards["locked"] = True
            cards["confirmed_by"] = actor
            cards["version"] = (cards.get("version") or 0) + 1
            cards["updated_at"] = ts
            cards["updated_by"] = actor
            for card in all_cards(rec.get("n3")):
                card["decision"] = "confirm"
            rec["gate_g3"]["state"] = "passed"
            rec["gate_g3"]["locked"] = True
            rec["gate_g3"]["last_decision"] = "pass"
            rec["gate_g3"]["note"] = note
            rec["gate_g3"]["actor"] = actor
            rec["gate_g3"]["decided_at"] = ts
            rec["gate_g3"]["version"] = cards["version"]
            rec["episode"]["locks"]["g3"] = True
            rec["episode"]["next_edges"] = [NODE_DN4]
            rec["d_n4_jobs"] = []
        else:
            rec["gate_g3"]["state"] = "rejected"
            rec["gate_g3"]["locked"] = False
            rec["gate_g3"]["last_decision"] = "reject"
            rec["gate_g3"]["note"] = note
            rec["gate_g3"]["actor"] = actor
            rec["gate_g3"]["decided_at"] = ts
            rec["gate_g3"]["version"] = cards.get("version") or rec["gate_g3"]["version"]
            rec["episode"]["locks"]["g3"] = False
            rec["episode"]["next_edges"] = [NODE_DN3]
            cards["locked"] = False
            cards["confirmed_by"] = None
            cards["updated_at"] = ts
            for card in all_cards(rec.get("n3")):
                card["decision"] = "reject"
        self._refresh_usable(rec)
        rec["episode"]["versions"]["cards"] = cards.get("version") or 0
        self._touch_episode(rec)
        self._commit(rec)
        env = self.gate_g3_envelope(rec)
        if warns:
            env["warnings"] = warns
        return self._idem_put(idempotency_key or raw.get("idempotency_key"), f"confirm_g3:{project_id}:{ep}", env)

    def get_dn4_consumer(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        if not rec["gate_g3"].get("locked"):
            raise AppError(
                409,
                "upstream_unlocked",
                "D-N3 G3 未锁定；不可宣称可进 N4",
                node=NODE_DN3,
                gate=GATE_G3,
            )
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN3,
            "consumer": NODE_DN4,
            "started": False,
            "jobs": list(rec.get("d_n4_jobs") or []),
            "usable_for_n4": usable_for_n4(rec.get("n3"), g3_locked=True),
            "next_edges": list(rec["episode"].get("next_edges") or []),
            "note": "G3 pass ≠ usable_for_n4；本拍不实施 N4",
        }

    # ----- library schema (021c) ---------------------------------------------------

    def _library_versions(self, project_id: str, ident: str, kind: str) -> list[int]:
        if kind == KIND_CHAR:
            prefix = f"{project_id}/{ident}@"
            matches = [v for k, v in self.store.state["library"].items() if k.startswith(prefix)]
        else:
            prefix = f"{project_id}/SCENE/{ident}@"
            matches = [v for k, v in self.store.state.setdefault("library_scenes", {}).items() if k.startswith(prefix)]
        return sorted({int(m["version"]) for m in matches})

    def _latest_library_asset(self, project_id: str, ident: str, kind: str) -> dict[str, Any] | None:
        if kind == KIND_CHAR:
            return self._latest_library(project_id, ident)
        prefix = f"{project_id}/SCENE/{ident}@"
        matches = [v for k, v in self.store.state.setdefault("library_scenes", {}).items() if k.startswith(prefix)]
        if not matches:
            return None
        return max(matches, key=lambda r: r["version"])

    def _resolve_library_asset(self, project_id: str, ident: str, version: int, kind: str) -> dict[str, Any]:
        if kind == KIND_CHAR:
            rec = self._resolve_library(project_id, ident, version)
            rec = deepcopy(rec)
            rec["refs"] = normalize_refs(self.settings, rec.get("refs"))
            rec.setdefault("kind", KIND_CHAR)
            return rec
        key = scene_store_key(project_id, ident, version)
        rec = self.store.state.setdefault("library_scenes", {}).get(key)
        if not rec:
            raise AppError(
                404,
                "not_found",
                "scene not in project library (D12)",
                scene_id=ident,
                version=version,
                project_id=project_id,
                provisional="D12",
            )
        rec = deepcopy(rec)
        rec["refs"] = normalize_refs(self.settings, rec.get("refs"))
        return rec

    def _write_library_asset(self, project_id: str, record: dict[str, Any], kind: str) -> None:
        ident = record["id"]
        version = record["version"]
        record.setdefault("project_scope", default_project_scope())
        record.setdefault("project_scope_capability", project_scope_capability())
        record["refs"] = normalize_refs(self.settings, record.get("refs"))
        if kind == KIND_CHAR:
            key = character_store_key(project_id, ident, version)
            self.store.state["library"][key] = record
            from aiv_drama.projection import write_library_character

            write_library_character(self.store.library_dir(project_id, ident, version), record)
            versions = self._library_versions(project_id, ident, KIND_CHAR)
            write_character_schema(self.store.library_character_root(project_id, ident), record, versions)
        else:
            key = scene_store_key(project_id, ident, version)
            self.store.state.setdefault("library_scenes", {})[key] = record
            versions = self._library_versions(project_id, ident, KIND_SCENE)
            write_scene_schema(self.store.library_scene_root(project_id, ident), record, versions)
        self._save()

    def put_library_character(self, project_id: str, character_id: str, body: LibraryCharacterWrite) -> dict[str, Any]:
        self._require_active_project(project_id)
        extra_refs = []
        extra_tags: list[str] = []
        if hasattr(body, "model_fields_set"):
            raw = body.model_dump()
            extra_refs = list(raw.get("refs") or [])
            extra_tags = list(raw.get("tags") or [])
        record = {
            "id": character_id,
            "version": body.version,
            "kind": KIND_CHAR,
            "name": body.name,
            "one_line": body.one_line,
            "project_id": project_id,
            "project_scope": default_project_scope(),
            "project_scope_capability": project_scope_capability(),
            "tags": extra_tags,
            "refs": normalize_refs(self.settings, extra_refs),
            "updated_at": now_iso(),
        }
        key = character_store_key(project_id, character_id, body.version)
        self.store.state["library"][key] = record
        from aiv_drama.projection import write_library_character

        write_library_character(self.store.library_dir(project_id, character_id, body.version), record)
        versions = self._library_versions(project_id, character_id, KIND_CHAR)
        write_character_schema(self.store.library_character_root(project_id, character_id), record, versions)
        self._save()
        return {"ok": True, "character": record, "node": "D-N0", "library_policy": hanging_bundle()}

    def put_library_scene(self, project_id: str, scene_id: str, body: LibrarySceneWrite) -> dict[str, Any]:
        self._require_active_project(project_id)
        if not is_scene_id(scene_id):
            raise AppError(422, "validation", "scene_id must match SCENE-##", scene_id=scene_id)
        record = {
            "id": scene_id,
            "version": body.version,
            "kind": KIND_SCENE,
            "name": body.name,
            "one_line": body.one_line,
            "project_id": project_id,
            "project_scope": default_project_scope(),
            "project_scope_capability": project_scope_capability(),
            "tags": list(body.tags or []),
            "refs": normalize_refs(self.settings, [r.model_dump() for r in (body.refs or [])]),
            "template_status": "deferred",
            "template_path": None,
            "updated_at": now_iso(),
        }
        self._write_library_asset(project_id, record, KIND_SCENE)
        return {"ok": True, "scene": record, "node": NODE_DN3, "library_policy": hanging_bundle()}

    def get_library(self, project_id: str) -> dict[str, Any]:
        self._project(project_id)
        chars = [v for k, v in self.store.state["library"].items() if k.startswith(f"{project_id}/")]
        scenes = [v for k, v in self.store.state.setdefault("library_scenes", {}).items() if k.startswith(f"{project_id}/")]
        return {
            "ok": True,
            "project_id": project_id,
            "project_scope": default_project_scope(),
            "project_scope_capability": project_scope_capability(),
            "characters": sorted(chars, key=lambda r: (r.get("id") or "", r.get("version") or 0)),
            "scenes": sorted(scenes, key=lambda r: (r.get("id") or "", r.get("version") or 0)),
            "library_policy": hanging_bundle(),
            "note": "project-scoped 默认可覆盖假设；D12 chosen=null；无 list/search 跨项目。",
        }

    def get_library_policy(self, project_id: str) -> dict[str, Any]:
        self._project(project_id)
        return {
            "ok": True,
            "project_id": project_id,
            "project_scope": default_project_scope(),
            "project_scope_capability": project_scope_capability(),
            "library_policy": hanging_bundle(),
        }
