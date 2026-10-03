from __future__ import annotations

import logging
import unicodedata
from copy import deepcopy
from typing import Any

from aiv_drama.config import SHOT_CAP_HARD, Settings
from aiv_drama.copy_contract import catalog_public, evaluate
from aiv_drama.errors import AppError
from aiv_drama.ids import next_id, require_known_or_omit
from aiv_drama.intent import (
    INTENT_LANE_CONFLICT,
    INTENT_STALE,
    INTENT_UNCONFIRMED,
    MSG_LANE_CONFLICT,
    MSG_STALE,
    MSG_UNCONFIRMED,
    NODE_INTENT,
    PLACEHOLDER_ONE_LINES,
    analyze_lane_conflict,
    can_confirm,
    compute_intent_fingerprint,
    ensure_intent,
    infer_card_lane,
    is_protagonist_row,
    maybe_clear_intent_on_must_change,
    photography_keys_present,
    reject_confirm_draft_hero,
    resolve_hero_one_line,
)
from aiv_drama.models import (
    AttachRequest,
    CastWrite,
    ClearDramaIntentRequest,
    ConfirmDramaIntentRequest,
    DetachRequest,
    DramaBriefWrite,
    EpisodeCreate,
    EpisodePatch,
    GeneratedDraft,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
    OutlineResetRequest,
    OutlineWrite,
    ProjectCreate,
    ProjectPatch,
    SidecarAddCharacterRequest,
)
from aiv_drama.projection import (
    assert_no_secrets,
    write_brief,
    write_cast,
    write_episode_json,
    write_outline,
)
from aiv_drama.provider import get_provider
from aiv_drama.store import JsonStore
from aiv_drama.validate import (
    brief_ready,
    check_if_match,
    now_iso,
    reject_dual_skill,
    reject_force_keys,
    reject_outline_prompts,
    require_brief_ready,
    require_outline_beats,
    require_shot_cap,
    validate_ep,
)
from aiv_drama_n2.named_cast import (
    CAST_CHANGED_HINT,
    SIDECAR_ONE_LINE,
    is_a_tier_prince_name,
    is_banlist_name,
    is_bare_brand,
    is_protected_lead,
    is_registerable_name,
    prefer_spatial_scene_name,
    normalize_name,
)
from aiv_drama_n2.ops import DramaN2Ops
from aiv_drama_n2.projection import write_storyboard_csv, write_storyboard_md
from aiv_drama_n3.projection import write_episode_cards
from aiv_drama_n3.templates import assert_no_prompt_in_skill_paths, n3_observability
from aiv_drama_n3.validate import usable_for_n4
from aiv_drama_n4.ops import DramaN4Ops
from aiv_schema.models import GATE_G1B, GATE_G2, GATE_G3, NODE_DN0, NODE_DN1, NODE_DN2, NODE_DN3, NODE_DN4, PIPELINE_DRAMA

logger = logging.getLogger(__name__)


def _key(project_id: str, ep: str) -> str:
    return f"{project_id}/{ep}"


def normalize_cast_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip())
    return " ".join(text.split())


def lane_identity_warnings(lane: str, cards: list[dict[str, Any]]) -> list[str]:
    """L1: warn when preattach gender/identity clashes with lane. Never 422 on generate."""
    warnings: list[str] = []
    if lane not in {"female", "male"}:
        return warnings
    for card in cards:
        inferred = infer_card_lane(card)
        if inferred and inferred != lane:
            cid = card.get("id") or "?"
            name = card.get("name") or cid
            warnings.append(
                f"lane {lane} may clash with preattached {cid} ({name}); "
                "outline kept the preattach — G1b may FAIL; not a 422"
            )
    return warnings


class DramaService(DramaN4Ops, DramaN2Ops):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = JsonStore(settings)

    # ----- persistence / projection -------------------------------------------------

    def _save(self) -> None:
        self.store.save()

    def _project(self, project_id: str) -> dict[str, Any]:
        proj = self.store.state["projects"].get(project_id)
        if not proj:
            raise AppError(404, "not_found", "project not found", project_id=project_id)
        return proj

    def _rec(self, project_id: str, ep: str) -> dict[str, Any]:
        self._project(project_id)
        rec = self.store.state["episodes"].get(_key(project_id, ep))
        if not rec:
            raise AppError(404, "not_found", "episode not found", project_id=project_id, episode_id=ep)
        self._ensure_n2_fields(rec)
        self._ensure_n3_fields(rec)
        self._ensure_n4_fields(rec)
        return rec

    def _require_active_project(self, project_id: str) -> dict[str, Any]:
        proj = self._project(project_id)
        if proj["status"] == "archived":
            raise AppError(409, "conflict", "project archived", project_id=project_id)
        return proj

    def _require_writable_episode(self, rec: dict[str, Any]) -> None:
        if rec["episode"]["status"] == "abandoned":
            raise AppError(409, "episode_abandoned", "episode abandoned", episode_id=rec["episode"]["episode_id"])
        proj = self._project(rec["episode"]["project_id"])
        if proj["status"] == "archived":
            raise AppError(409, "conflict", "project archived", project_id=proj["id"])

    def _g1b_locked(self, rec: dict[str, Any]) -> bool:
        outline = rec.get("outline") or {}
        return bool(outline.get("locked"))

    def _unlock(self, rec: dict[str, Any]) -> None:
        if rec.get("outline"):
            rec["outline"]["locked"] = False
            rec["outline"]["confirmed_by"] = None
        if rec.get("cast"):
            rec["cast"]["locked"] = False
            rec["cast"]["confirmed_by"] = None
        rec["gate"]["locked"] = False
        rec["gate"]["state"] = "ready" if rec.get("outline") else "idle"
        rec["episode"]["locks"]["g1b"] = False
        if rec["episode"]["status"] == "locked_g1b":
            rec["episode"]["status"] = "awaiting_g1b" if rec.get("outline") else "in_progress"
        rec["episode"]["next_edges"] = []
        self._add_stale(rec, NODE_DN2)
        self._mark_storyboard_stale(rec)

    def _add_stale(self, rec: dict[str, Any], node: str) -> None:
        stale = rec["episode"].setdefault("stale_downstream", [])
        if node not in stale:
            stale.append(node)

    def _require_unlock(self, rec: dict[str, Any], unlock_edit: bool) -> None:
        self._require_writable_episode(rec)
        if self._g1b_locked(rec):
            if not unlock_edit:
                raise AppError(409, "locked", "locked; set unlock_edit to edit", node=NODE_DN1, gate=GATE_G1B)
            self._unlock(rec)

    def _touch_episode(self, rec: dict[str, Any]) -> None:
        rec["episode"]["updated_at"] = now_iso()
        rec["episode"]["versions"]["brief"] = (rec.get("brief") or {}).get("version") or 0
        rec["episode"]["versions"]["outline"] = (rec.get("outline") or {}).get("version") or 0
        rec["episode"]["versions"]["cast"] = (rec.get("cast") or {}).get("version") or 0
        rec["episode"]["versions"]["storyboard"] = (rec.get("storyboard") or {}).get("version") or 0
        rec["episode"]["versions"]["cards"] = ((rec.get("n3") or {}).get("cards") or {}).get("version") or 0
        rec["episode"]["versions"]["prompts"] = (rec.get("n4") or {}).get("assemble_version") or 0

    def _project_disk(self, rec: dict[str, Any]) -> None:
        ep = rec["episode"]["episode_id"]
        project_id = rec["episode"]["project_id"]
        episode_dir = self.store.episode_dir(project_id, ep)
        try:
            if rec.get("brief"):
                write_brief(episode_dir, ep, rec["brief"])
            if rec.get("outline"):
                write_outline(episode_dir, ep, rec["outline"], rec.get("source_skills"))
            if rec.get("cast"):
                write_cast(episode_dir, ep, rec["cast"])
            sb = rec.get("storyboard")
            if sb is not None and (sb.get("version") or 0) > 0:
                write_storyboard_csv(episode_dir, ep, sb)
                write_storyboard_md(episode_dir, ep, sb)
            gate = rec["gate"]
            g2 = rec.get("gate_g2") or {}
            g3 = rec.get("gate_g3") or {}
            stale_nodes = rec["episode"].get("stale_downstream") or []
            meta = {
                "episode_id": ep,
                "project_id": project_id,
                "pipeline_profile": PIPELINE_DRAMA,
                "status": rec["episode"]["status"],
                "versions": deepcopy(rec["episode"]["versions"]),
                "gates": {
                    GATE_G1B: {
                        "status": gate.get("state"),
                        "state": gate.get("state"),
                        "locked": gate.get("locked"),
                        "decision": gate.get("last_decision"),
                        "actor": gate.get("actor"),
                        "note": gate.get("note"),
                        "updated_at": gate.get("decided_at"),
                    },
                    GATE_G2: {
                        "status": g2.get("state"),
                        "state": g2.get("state"),
                        "locked": g2.get("locked"),
                        "decision": g2.get("last_decision"),
                        "actor": g2.get("actor"),
                        "note": g2.get("note"),
                        "updated_at": g2.get("decided_at"),
                    },
                    GATE_G3: {
                        "status": g3.get("state"),
                        "state": g3.get("state"),
                        "locked": g3.get("locked"),
                        "decision": g3.get("last_decision"),
                        "actor": g3.get("actor"),
                        "note": g3.get("note"),
                        "updated_at": g3.get("decided_at"),
                    },
                },
                "next_edges": list(rec["episode"].get("next_edges") or []),
                "lane_preference": (rec.get("brief") or {}).get("lane_preference", "unset"),
                "intent": self._intent_view(rec),
                "stale": {
                    "d_n2": NODE_DN2 in stale_nodes or bool((sb or {}).get("stale")),
                    "d_n3": NODE_DN3 in stale_nodes,
                    "d_n4": NODE_DN4 in stale_nodes or bool((rec.get("n4") or {}).get("stale")),
                },
                "stale_downstream": list(stale_nodes),
                "locks": deepcopy(rec["episode"]["locks"]),
                "projection_dirty": False,
            }
            if sb:
                skill_paths = [p for p in (sb.get("skill_paths") or []) if p and p != "none"]
                src = rec.get("source_storyboard_skill")
                if src and src not in skill_paths:
                    skill_paths.append(src)
                meta["storyboard_meta"] = {
                    "storyboard_skill": sb.get("storyboard_skill"),
                    "shot_cap": sb.get("shot_cap"),
                    "upstream_outline_version": sb.get("upstream_outline_version"),
                    "upstream_cast_version": sb.get("upstream_cast_version"),
                    "skill_paths": skill_paths,
                    "tool_profile": sb.get("tool_profile"),
                    "skill_trace": deepcopy(sb.get("skill_trace") or rec.get("n2_request", {}).get("skill_trace") or {}),
                    "skill_excerpt": (sb.get("skill_excerpt") or "")[:2000],
                }
            if rec.get("n3"):
                write_episode_cards(episode_dir, rec.get("n3"))
                obs = n3_observability(self.settings.repo_root)
                thicken = (rec.get("n3") or {}).get("thicken") or {}
                thicken_skills = list(thicken.get("skill_paths") or [])
                assert_no_prompt_in_skill_paths(thicken_skills)
                # F3: template_paths / prompt_paths only — never merge .prompt into skill_paths.
                meta["n3_meta"] = {
                    "usable_for_n4": usable_for_n4(rec.get("n3"), g3_locked=bool(g3.get("locked"))),
                    "template_paths": list(obs["template_paths"]),
                    "prompt_paths": list(obs["prompt_paths"]),
                    "cards_version": ((rec.get("n3") or {}).get("cards") or {}).get("version") or 0,
                    "scene_template": (thicken.get("scene_template") or {}).get("status") or "deferred",
                }
                if thicken:
                    meta["n3_meta"]["thicken_skill_paths"] = thicken_skills
                    meta["n3_meta"]["thicken_prompt_paths"] = list(thicken.get("prompt_paths") or [])
                    meta["n3_meta"]["fixture_hits"] = int(thicken.get("fixture_hits") or 0)
                    meta["n3_meta"]["model"] = thicken.get("model")
            n4 = rec.get("n4") or {}
            if n4.get("started") or n4.get("assemble_version"):
                meta["n4_meta"] = {
                    "started": bool(n4.get("started")),
                    "stale": bool(n4.get("stale")),
                    "assemble_version": n4.get("assemble_version") or 0,
                    "fingerprint": n4.get("fingerprint"),
                    "tool_profile": n4.get("tool_profile"),
                    "artifact": n4.get("artifact"),
                    "usable_for_n4": usable_for_n4(rec.get("n3"), g3_locked=bool(g3.get("locked"))),
                }
            write_episode_json(episode_dir, meta)
            assert_no_secrets(episode_dir)
            rec["projection_dirty"] = False
        except Exception:  # noqa: BLE001
            rec["projection_dirty"] = True
            self._save()
            return
        self._save()

    def _commit(self, rec: dict[str, Any] | None = None) -> None:
        self._save()
        if rec is not None:
            self._project_disk(rec)

    def _idem_get(self, key: str | None, op: str) -> Any | None:
        if not key:
            return None
        return self.store.state["idempotency"].get(f"{op}:{key}")

    def _idem_put(self, key: str | None, op: str, value: Any) -> Any:
        if key:
            self.store.state["idempotency"][f"{op}:{key}"] = value
            self._save()
        return value

    # ----- envelopes ----------------------------------------------------------------

    def project_envelope(self, project_id: str) -> dict[str, Any]:
        return {"ok": True, "project": deepcopy(self._project(project_id))}

    def episode_envelope(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        episode = deepcopy(rec["episode"])
        intent = self._intent_view(rec)
        episode["intent"] = intent
        return {
            "ok": True,
            "episode": episode,
            "intent": intent,
            "lane_preference": (rec.get("brief") or {}).get("lane_preference", "unset"),
            "next_edges": list(rec["episode"].get("next_edges") or []),
            "projection_dirty": bool(rec.get("projection_dirty")),
        }

    def brief_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        if not rec.get("brief"):
            raise AppError(404, "not_found", "brief not found", node=NODE_DN0)
        return {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN0,
            "brief": deepcopy(rec["brief"]),
            "intent": self._intent_view(rec),
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }

    def outline_envelope(self, rec: dict[str, Any], *, warnings: list[str] | None = None) -> dict[str, Any]:
        if not rec.get("outline"):
            raise AppError(404, "not_found", "outline not found", node=NODE_DN1)
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN1,
            "outline": deepcopy(rec["outline"]),
            "cast": deepcopy(rec["cast"]) if rec.get("cast") else None,
            "next_edges": list(rec["episode"].get("next_edges") or []),
            "skill_paths": list(rec.get("source_skills") or []),
        }
        if warnings:
            env["warnings"] = list(warnings)
        if rec.get("projection_dirty"):
            env["projection_dirty"] = True
        return env

    def _set_cast_change_hint(
        self,
        rec: dict[str, Any],
        *,
        added: list[dict[str, Any]],
        source: str,
        cast_version_old: int | None = None,
    ) -> None:
        new_ver = (rec.get("cast") or {}).get("version") or 0
        old_ver = new_ver - 1 if cast_version_old is None else cast_version_old
        if old_ver < 0:
            old_ver = 0
        rec["cast_change_hint"] = {
            **CAST_CHANGED_HINT,
            "added": added,
            "source": source,
            "cast_version": new_ver,
            "cast_version_old": old_ver,
            "cast_version_new": new_ver,
            "g1b_still_locked": True,
            "outline_unchanged": True,
        }

    def _clear_cast_change_hint(self, rec: dict[str, Any]) -> None:
        rec.pop("cast_change_hint", None)

    def _hint_fields(self, rec: dict[str, Any]) -> dict[str, Any]:
        hint = rec.get("cast_change_hint")
        if not hint:
            return {}
        return {"cast_changed": True, "hints": [deepcopy(hint)]}

    def cast_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        if not rec.get("cast"):
            raise AppError(404, "not_found", "cast not found", node=NODE_DN1)
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN1,
            "cast": deepcopy(rec["cast"]),
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }
        env.update(self._hint_fields(rec))
        return env

    def gate_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        edges = list(rec["episode"].get("next_edges") or [])
        return {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN1,
            "gate": deepcopy(rec["gate"]),
            "outline": deepcopy(rec["outline"]) if rec.get("outline") else None,
            "cast": deepcopy(rec["cast"]) if rec.get("cast") else None,
            "next_edges": edges,
        }

    def _intent_view(self, rec: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(ensure_intent(rec))

    def _fingerprint_cards(self, rec: dict[str, Any]) -> list[dict[str, Any]]:
        # Intent fingerprint stays on the episode-cast spelling so a library
        # rename does not 422 intent_stale before generate can apply it.
        return self._resolve_preattached_characters(
            rec["episode"]["project_id"], rec, prefer_library=False
        )

    def _compute_fingerprint(self, rec: dict[str, Any]) -> str:
        return compute_intent_fingerprint(rec.get("brief") or {}, self._fingerprint_cards(rec))

    def _maybe_clear_intent(self, rec: dict[str, Any], before_fp: str | None) -> bool:
        after_fp = self._compute_fingerprint(rec)
        return maybe_clear_intent_on_must_change(rec, before_fp, after_fp)

    def _intent_preview(self, rec: dict[str, Any]) -> dict[str, Any]:
        brief = rec.get("brief") or {}
        cards = self._fingerprint_cards(rec)
        lane = brief.get("lane_preference") or "unset"
        conflict = analyze_lane_conflict(lane, cards)
        title_ok = brief_ready(brief.get("title_intent"), brief.get("pin"))
        fingerprint_current = compute_intent_fingerprint(brief, cards)
        return {
            **conflict,
            "can_confirm": can_confirm(lane=lane, brief=brief, cards=cards, title_ok=title_ok),
            "fingerprint_current": fingerprint_current,
            "hero_one_line": resolve_hero_one_line(brief, cards),
        }

    def intent_envelope(self, rec: dict[str, Any], *, preview: bool = True) -> dict[str, Any]:
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_INTENT,
            "intent": self._intent_view(rec),
        }
        if preview:
            env.update(self._intent_preview(rec))
        return env

    def _require_intent_for_generate(self, rec: dict[str, Any]) -> None:
        intent = ensure_intent(rec)
        if intent.get("confirmed") is not True:
            raise AppError(422, INTENT_UNCONFIRMED, MSG_UNCONFIRMED, node=NODE_INTENT)
        current = self._compute_fingerprint(rec)
        stored = intent.get("fingerprint")
        if not stored or current != stored:
            raise AppError(
                422,
                INTENT_STALE,
                MSG_STALE,
                node=NODE_INTENT,
                stored=stored,
                current=current,
            )

    # ----- projects / episodes ------------------------------------------------------

    def create_project(self, body: ProjectCreate, *, idempotency_key: str | None = None) -> dict[str, Any]:
        cached = self._idem_get(idempotency_key, "create_project")
        if cached:
            return cached
        self.store.state["counters"]["project"] += 1
        n = self.store.state["counters"]["project"]
        project_id = f"proj_{n:02d}"
        ts = now_iso()
        self.store.state["projects"][project_id] = {
            "id": project_id,
            "name": body.name,
            "status": "active",
            "created_at": ts,
            "updated_at": ts,
            "version": 1,
        }
        env = self.project_envelope(project_id)
        self._save()
        return self._idem_put(idempotency_key, "create_project", env)

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self.project_envelope(project_id)

    def patch_project(
        self,
        project_id: str,
        body: ProjectPatch,
        *,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = self._idem_get(idempotency_key, f"patch_project:{project_id}")
        if cached:
            return cached
        proj = self._project(project_id)
        check_if_match(if_match, proj["version"], "project")
        if body.name:
            proj["name"] = body.name
        proj["version"] += 1
        proj["updated_at"] = now_iso()
        env = self.project_envelope(project_id)
        self._save()
        return self._idem_put(idempotency_key, f"patch_project:{project_id}", env)

    def archive_project(self, project_id: str) -> dict[str, Any]:
        proj = self._project(project_id)
        proj["status"] = "archived"
        proj["version"] += 1
        proj["updated_at"] = now_iso()
        self._save()
        return self.project_envelope(project_id)

    def create_episode(
        self,
        project_id: str,
        body: EpisodeCreate,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = self._idem_get(idempotency_key, f"create_episode:{project_id}:{body.episode_id}")
        if cached:
            return cached
        self._require_active_project(project_id)
        ep = validate_ep(body.episode_id)
        if body.pipeline_profile != PIPELINE_DRAMA:
            raise AppError(422, "validation", "pipeline_profile must be drama", pipeline_profile=body.pipeline_profile)
        key = _key(project_id, ep)
        if key in self.store.state["episodes"]:
            raise AppError(409, "conflict", "episode already exists", episode_id=ep)
        ts = now_iso()
        rec = {
            "episode": {
                "episode_id": ep,
                "project_id": project_id,
                "pipeline_profile": PIPELINE_DRAMA,
                "title": body.title,
                "status": "draft",
                "aspect_ratio": body.aspect_ratio,
                "target_duration_sec": body.target_duration_sec,
                "locks": {"g1b": False, "g2": False, "g3": False},
                "versions": {"brief": 0, "outline": 0, "cast": 0, "storyboard": 0, "cards": 0, "prompts": 0, "episode": 1},
                "stale_downstream": [],
                "next_edges": [],
                "created_at": ts,
                "updated_at": ts,
            },
            "brief": None,
            "outline": None,
            "cast": None,
            "storyboard": None,
            "gate": {
                "gate_id": GATE_G1B,
                "state": "idle",
                "locked": False,
                "version": 0,
                "last_decision": None,
                "note": None,
                "actor": None,
                "decided_at": None,
            },
            "gate_g2": {
                "gate_id": GATE_G2,
                "state": "idle",
                "locked": False,
                "version": 0,
                "last_decision": None,
                "note": None,
                "actor": None,
                "decided_at": None,
            },
            "gate_g3": {
                "gate_id": GATE_G3,
                "state": "idle",
                "locked": False,
                "version": 0,
                "last_decision": None,
                "note": None,
                "actor": None,
                "decided_at": None,
            },
            "n3": None,
            "n4": None,
            "d_n4_jobs": [],
            "library_ops": [],
            "allocated_char_ids": [],
            "allocated_scene_ids": [],
            "char_counter": 0,
            "scene_counter": 0,
            "source_skills": [],
            "d_n2_jobs": [],
            "d_n3_jobs": [],
            "intent": {
                "confirmed": False,
                "fingerprint": None,
                "confirmed_at": None,
                "confirmed_by": None,
            },
            "projection_dirty": False,
        }
        self.store.state["episodes"][key] = rec
        self._commit(rec)
        return self._idem_put(idempotency_key, f"create_episode:{project_id}:{ep}", self.episode_envelope(project_id, ep))

    def get_episode(self, project_id: str, ep: str) -> dict[str, Any]:
        validate_ep(ep)
        return self.episode_envelope(project_id, ep)

    def patch_episode(
        self,
        project_id: str,
        ep: str,
        body: EpisodePatch,
        *,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        validate_ep(ep)
        cached = self._idem_get(idempotency_key, f"patch_episode:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        check_if_match(if_match, rec["episode"]["versions"]["episode"], "episode")
        if body.title is not None:
            rec["episode"]["title"] = body.title
        if body.aspect_ratio is not None:
            rec["episode"]["aspect_ratio"] = body.aspect_ratio
        if body.target_duration_sec is not None:
            rec["episode"]["target_duration_sec"] = body.target_duration_sec
        rec["episode"]["versions"]["episode"] += 1
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"patch_episode:{project_id}:{ep}", self.episode_envelope(project_id, ep))

    def abandon_episode(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, validate_ep(ep))
        rec["episode"]["status"] = "abandoned"
        rec["episode"]["versions"]["episode"] += 1
        self._touch_episode(rec)
        self._commit(rec)
        return self.episode_envelope(project_id, ep)

    # ----- library resolve (put/schema writes live on DramaN3Ops) --------------------

    def _resolve_library(self, project_id: str, character_id: str, version: int) -> dict[str, Any]:
        key = f"{project_id}/{character_id}@{version}"
        rec = self.store.state["library"].get(key)
        if not rec:
            raise AppError(
                404,
                "not_found",
                "character not in project library (D12)",
                character_id=character_id,
                version=version,
                project_id=project_id,
                provisional="D12",
            )
        return rec

    def _latest_library(self, project_id: str, character_id: str) -> dict[str, Any] | None:
        prefix = f"{project_id}/{character_id}@"
        matches = [v for k, v in self.store.state["library"].items() if k.startswith(prefix)]
        if not matches:
            return None
        return max(matches, key=lambda r: r["version"])

    # ----- brief D-N0 ---------------------------------------------------------------

    def get_brief(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, validate_ep(ep))
        return self.brief_envelope(rec)

    def put_brief(
        self,
        project_id: str,
        ep: str,
        body: DramaBriefWrite,
        *,
        raw: dict[str, Any] | None = None,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        reject_dual_skill(raw)
        cached = self._idem_get(idempotency_key, f"put_brief:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        current = rec.get("brief")
        check_if_match(if_match, (current or {}).get("version") or 0, "brief")
        require_brief_ready(body.title_intent, body.pin)
        if self._g1b_locked(rec) and not body.confirm_stale_outline:
            raise AppError(
                409,
                "downstream_locked",
                "outline locked; set confirm_stale_outline to write brief",
                node=NODE_DN1,
            )
        before_fp = self._compute_fingerprint(rec) if current else None
        lane = body.lane_preference or (current or {}).get("lane_preference") or "unset"
        ids = body.preattached_character_ids
        if ids is None:
            ids = list((current or {}).get("preattached_character_ids") or [])
        if "hero_one_line" in body.model_fields_set:
            hero_one_line = body.hero_one_line
        else:
            hero_one_line = (current or {}).get("hero_one_line")
        version = ((current or {}).get("version") or 0) + 1
        rec["brief"] = {
            "episode_id": rec["episode"]["episode_id"],
            "pipeline_profile": PIPELINE_DRAMA,
            "title_intent": body.title_intent,
            "pin": body.pin,
            "setting_notes": body.setting_notes,
            "lane_preference": lane,
            "preattached_character_ids": ids,
            "hero_one_line": hero_one_line,
            "version": version,
            "updated_at": now_iso(),
            "updated_by": body.actor,
        }
        if self._g1b_locked(rec) and body.confirm_stale_outline:
            self._add_stale(rec, NODE_DN2)
            self._mark_storyboard_stale(rec)
        if rec["episode"]["status"] == "draft":
            rec["episode"]["status"] = "in_progress"
        self._maybe_clear_intent(rec, before_fp)
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"put_brief:{project_id}:{ep}", self.brief_envelope(rec))

    def get_intent(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, validate_ep(ep))
        return self.intent_envelope(rec)

    def check_intent(
        self,
        project_id: str,
        ep: str,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        return self.intent_envelope(rec)

    def confirm_intent(
        self,
        project_id: str,
        ep: str,
        body: ConfirmDramaIntentRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        incoming = raw if isinstance(raw, dict) else {}
        reject_force_keys(incoming)
        reject_confirm_draft_hero(incoming)
        photography_keys_present(incoming)  # ignored; never a confirm hard gate
        cached = self._idem_get(idempotency_key, f"intent_confirm:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        brief = rec.get("brief")
        if not brief:
            raise AppError(422, "brief_incomplete", "title_intent and pin both empty", node=NODE_DN0)
        require_brief_ready(brief.get("title_intent"), brief.get("pin"))
        lane = brief.get("lane_preference")
        if lane not in {"female", "male"}:
            raise AppError(
                422,
                "lane_required",
                "select female|male before confirm",
                provisional="D3",
                node=NODE_INTENT,
            )
        cards = self._fingerprint_cards(rec)
        if not resolve_hero_one_line(brief, cards):
            raise AppError(
                422,
                "validation",
                "hero_one_line must be persisted on brief or cast before confirm",
                node=NODE_INTENT,
                field="hero_one_line",
            )
        conflict = analyze_lane_conflict(lane, cards)
        if conflict["conflict"]:
            raise AppError(
                422,
                INTENT_LANE_CONFLICT,
                MSG_LANE_CONFLICT,
                node=NODE_INTENT,
                suggested_lane=conflict["suggested_lane"],
                current_lane=conflict["current_lane"],
                preattach_lanes=conflict["preattach_lanes"],
            )
        fingerprint = self._compute_fingerprint(rec)
        req = body or ConfirmDramaIntentRequest()
        expected = req.expected_fingerprint or incoming.get("expected_fingerprint")
        if expected and expected != fingerprint:
            raise AppError(
                422,
                INTENT_STALE,
                MSG_STALE,
                node=NODE_INTENT,
                stored=expected,
                current=fingerprint,
            )
        actor = (req.actor or incoming.get("actor") or "").strip() or None
        rec["intent"] = {
            "confirmed": True,
            "fingerprint": fingerprint,
            "confirmed_at": now_iso(),
            "confirmed_by": actor,
        }
        self._touch_episode(rec)
        self._commit(rec)
        env = self.intent_envelope(rec)
        return self._idem_put(idempotency_key, f"intent_confirm:{project_id}:{ep}", env)

    def clear_intent(
        self,
        project_id: str,
        ep: str,
        body: ClearDramaIntentRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        incoming = raw if isinstance(raw, dict) else {}
        reject_force_keys(incoming)
        cached = self._idem_get(idempotency_key, f"intent_clear:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        rec["intent"] = {
            "confirmed": False,
            "fingerprint": None,
            "confirmed_at": None,
            "confirmed_by": None,
        }
        self._touch_episode(rec)
        self._commit(rec)
        env = self.intent_envelope(rec)
        return self._idem_put(idempotency_key, f"intent_clear:{project_id}:{ep}", env)

    # ----- outline / cast D-N1 ------------------------------------------------------

    def get_outline(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, validate_ep(ep))
        return self.outline_envelope(rec)

    def _resolve_lane(self, rec: dict[str, Any], request_lane: str | None) -> str:
        if request_lane in {"female", "male"}:
            return request_lane
        pref = (rec.get("brief") or {}).get("lane_preference")
        if pref in {"female", "male"}:
            return pref
        raise AppError(
            422,
            "lane_required",
            "select female|male before generate",
            provisional="D3",
            node=NODE_DN1,
        )

    def _alloc_char(self, rec: dict[str, Any]) -> str:
        used = set(rec["allocated_char_ids"])
        ident, n = next_id(used, "CHAR", rec["char_counter"])
        rec["char_counter"] = n
        rec["allocated_char_ids"].append(ident)
        return ident

    def _alloc_scene(self, rec: dict[str, Any]) -> str:
        used = set(rec["allocated_scene_ids"])
        ident, n = next_id(used, "SCENE", rec["scene_counter"])
        rec["scene_counter"] = n
        rec["allocated_scene_ids"].append(ident)
        return ident

    def _register_char(self, rec: dict[str, Any], ident: str) -> None:
        if ident not in rec["allocated_char_ids"]:
            rec["allocated_char_ids"].append(ident)
        n = int(ident.split("-")[-1]) if ident.split("-")[-1].isdigit() else 0
        rec["char_counter"] = max(rec["char_counter"], n)

    def _register_scene(self, rec: dict[str, Any], ident: str) -> None:
        if ident not in rec["allocated_scene_ids"]:
            rec["allocated_scene_ids"].append(ident)
        n = int(ident.split("-")[-1]) if ident.split("-")[-1].isdigit() else 0
        rec["scene_counter"] = max(rec["scene_counter"], n)

    def _empty_cast(self, rec: dict[str, Any], lane: str | None) -> dict[str, Any]:
        return {
            "episode": rec["episode"]["episode_id"],
            "lane": lane,
            "characters": [],
            "scenes": [],
            "version": 0,
            "locked": False,
            "confirmed_by": None,
            "updated_at": now_iso(),
        }

    def _preattached_ids(self, rec: dict[str, Any]) -> list[str]:
        return list((rec.get("brief") or {}).get("preattached_character_ids") or [])

    def _library_wins_identity(
        self,
        lib: dict[str, Any] | None,
        existing: dict[str, Any] | None,
        cid: str,
    ) -> tuple[str, str]:
        """Library name/one_line win over a stale episode-cast row."""
        lib_name = ((lib or {}).get("name") or "").strip()
        lib_line = ((lib or {}).get("one_line") or "").strip()
        ex_name = ((existing or {}).get("name") or "").strip()
        ex_line = ((existing or {}).get("one_line") or "").strip()
        return lib_name or ex_name or cid, lib_line or ex_line or "预挂角色"

    def _resolve_preattached_characters(
        self,
        project_id: str,
        rec: dict[str, Any],
        *,
        prefer_library: bool = True,
    ) -> list[dict[str, Any]]:
        existing = {c["id"]: c for c in ((rec.get("cast") or {}).get("characters") or [])}
        cards: list[dict[str, Any]] = []
        seen: set[str] = set()
        for cid in self._preattached_ids(rec):
            if cid in seen:
                continue
            seen.add(cid)
            lib = self._latest_library(project_id, cid)
            ex = existing.get(cid)
            if prefer_library:
                name, one_line = self._library_wins_identity(lib, ex, cid)
            else:
                name = ((ex or {}).get("name") or "").strip() or ((lib or {}).get("name") or "").strip() or cid
                one_line = (
                    ((ex or {}).get("one_line") or "").strip()
                    or ((lib or {}).get("one_line") or "").strip()
                    or "预挂角色"
                )
            ref = None
            if ex and ex.get("library_ref"):
                ref = deepcopy(ex["library_ref"])
            elif lib:
                ref = {"id": lib["id"], "version": lib["version"]}
            card: dict[str, Any] = {"id": cid, "name": name, "one_line": one_line}
            if ref is not None:
                card["library_ref"] = ref
            if ex and ex.get("is_hero") is not None:
                card["is_hero"] = ex["is_hero"]
            cards.append(card)
        return cards

    def _seed_preattached_row(
        self,
        rec: dict[str, Any],
        project_id: str,
        cid: str,
        existing: dict[str, Any] | None,
    ) -> dict[str, Any]:
        lib = self._latest_library(project_id, cid)
        if cid not in rec["allocated_char_ids"]:
            self._register_char(rec, cid)
        if existing:
            row = deepcopy(existing)
            if not row.get("library_ref") and lib:
                row["library_ref"] = {"id": lib["id"], "version": lib["version"]}
            if lib:
                name, one_line = self._library_wins_identity(lib, row, cid)
                row["name"] = name
                row["one_line"] = one_line
            return row
        if lib:
            return {
                "id": cid,
                "name": lib["name"],
                "one_line": lib["one_line"],
                "library_ref": {"id": lib["id"], "version": lib["version"]},
            }
        return {
            "id": cid,
            "name": cid,
            "one_line": "预挂角色",
            "library_ref": None,
        }

    def _merge_generated_cast(
        self,
        rec: dict[str, Any],
        draft: GeneratedDraft,
        project_id: str,
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        notes = warnings if warnings is not None else []
        existing_by_id = {c["id"]: c for c in ((rec.get("cast") or {}).get("characters") or [])}
        existing_scenes = {s["id"]: s for s in ((rec.get("cast") or {}).get("scenes") or [])}
        preattached = self._preattached_ids(rec)
        preattached_set = set(preattached)

        characters: list[dict[str, Any]] = []
        used_names: dict[str, dict[str, Any]] = {}
        have_ids: set[str] = set()

        def _index(row: dict[str, Any]) -> None:
            characters.append(row)
            have_ids.add(row["id"])
            key = normalize_cast_name(row.get("name") or "")
            if key and key not in used_names:
                used_names[key] = row

        # Keepers: existing library-backed rows and explicit preattach ids (name fold reads this table).
        for ident, prev in existing_by_id.items():
            if prev.get("library_ref") or ident in preattached_set:
                _index(self._seed_preattached_row(rec, project_id, ident, prev))

        for cid in preattached:
            if cid in have_ids:
                continue
            _index(self._seed_preattached_row(rec, project_id, cid, existing_by_id.get(cid)))

        # Leftover generated spelling of a renamed preattach folds onto that id;
        # the library name/one_line already on the row stay.
        for ident, prev in existing_by_id.items():
            if ident not in have_ids:
                continue
            old_key = normalize_cast_name(prev.get("name") or "")
            if old_key and old_key not in used_names:
                used_names[old_key] = next(c for c in characters if c["id"] == ident)

        bound = [c for c in characters if c.get("library_ref")]
        lead: dict[str, Any] | None = next((c for c in bound if is_protagonist_row(c)), None)
        if lead is None:
            for cid in preattached:
                row = next((c for c in characters if c["id"] == cid and c.get("library_ref")), None)
                if row:
                    lead = row
                    break
        if lead is None and bound:
            lead = bound[0]

        for row in draft.characters:
            name = (row.get("name") or "").strip() or "未命名"
            if name != "未命名" and is_banlist_name(name) and not is_protected_lead(name) and not is_a_tier_prince_name(name):
                msg = f"skipped banlist CHAR {name!r} (B-ACT/B-TAG/B-FRAG/B-GEN)"
                logger.warning(msg)
                notes.append(msg)
                continue
            one_line = (row.get("one_line") or "").strip() or "待补一句话"
            key = normalize_cast_name(name)
            if key and key in used_names:
                target = used_names[key]
                if (target.get("one_line") or "").strip() in PLACEHOLDER_ONE_LINES:
                    target["one_line"] = one_line
                # never overwrite library_ref
                msg = f"folded generated name {name!r} onto {target['id']}"
                logger.warning(msg)
                notes.append(msg)
                continue
            if lead and is_protagonist_row(row) and normalize_cast_name(lead.get("name") or "") != key:
                msg = (
                    f"soft-suppressed parallel protagonist {name!r} "
                    f"(kept preattached {lead['id']} {lead.get('name')!r})"
                )
                logger.warning(msg)
                notes.append(msg)
                continue
            ident = self._alloc_char(rec)
            prev = existing_by_id.get(ident)
            ref = deepcopy(prev.get("library_ref")) if prev and prev.get("library_ref") else None
            _index(
                {
                    "id": ident,
                    "name": name,
                    "one_line": one_line,
                    "library_ref": ref,
                }
            )

        scenes: list[dict[str, Any]] = []
        for row in draft.scenes:
            ident = self._alloc_scene(rec)
            prev = existing_scenes.get(ident)
            scene_name = prefer_spatial_scene_name(row.get("name") or "未命名场景")
            scenes.append(
                {
                    "id": ident,
                    "name": scene_name or "未命名场景",
                    "one_line": row.get("one_line") or "待补一句话",
                    "library_ref": deepcopy(prev.get("library_ref")) if prev and prev.get("library_ref") else None,
                }
            )
        if not scenes:
            for ident, prev in existing_scenes.items():
                scenes.append(deepcopy(prev))

        prev_ver = (rec.get("cast") or {}).get("version") or 0
        return {
            "episode": rec["episode"]["episode_id"],
            "lane": draft.lane,
            "characters": characters,
            "scenes": scenes,
            "version": prev_ver + 1,
            "locked": False,
            "confirmed_by": None,
            "updated_at": now_iso(),
        }

    def generate_outline(
        self,
        project_id: str,
        ep: str,
        body: OutlineGenerateRequest | None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        incoming = raw if isinstance(raw, dict) else {}
        reject_force_keys(incoming)
        reject_dual_skill(incoming)
        cached = self._idem_get(idempotency_key, f"generate:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_unlock(rec, unlock_edit=False)
        self._require_intent_for_generate(rec)
        brief = rec.get("brief")
        if not brief:
            raise AppError(422, "brief_incomplete", "title_intent and pin both empty", node=NODE_DN0)
        require_brief_ready(brief.get("title_intent"), brief.get("pin"))
        req = body or OutlineGenerateRequest()
        lane = self._resolve_lane(rec, req.lane)
        shot_cap = require_shot_cap(req.shot_cap)
        provider = get_provider(req.provider, self.settings)
        brief_for_gen = deepcopy(brief)
        cards = self._resolve_preattached_characters(project_id, rec)
        brief_for_gen["preattached_characters"] = cards
        warnings = lane_identity_warnings(lane, cards)
        for item in warnings:
            logger.warning(item)
        draft = provider.generate(
            episode_id=rec["episode"]["episode_id"],
            lane=lane,
            shot_cap=shot_cap,
            brief=brief_for_gen,
        )
        reject_outline_prompts(draft.body_md)
        require_shot_cap(draft.shot_cap)
        rec["source_skills"] = list(draft.source_skills)
        prev_outline_ver = (rec.get("outline") or {}).get("version") or 0
        rec["outline"] = {
            "body_md": draft.body_md,
            "lane": draft.lane,
            "shot_cap": draft.shot_cap,
            "version": prev_outline_ver + 1,
            "locked": False,
            "confirmed_by": None,
            "updated_at": now_iso(),
            "job_id": None,
        }
        rec["cast"] = self._merge_generated_cast(rec, draft, project_id, warnings=warnings)
        rec["gate"]["state"] = "ready"
        rec["gate"]["locked"] = False
        rec["episode"]["status"] = "awaiting_g1b"
        rec["episode"]["next_edges"] = []
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(
            idempotency_key,
            f"generate:{project_id}:{ep}",
            self.outline_envelope(rec, warnings=warnings),
        )

    def put_outline(
        self,
        project_id: str,
        ep: str,
        body: OutlineWrite,
        *,
        raw: dict[str, Any] | None = None,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        cached = self._idem_get(idempotency_key, f"put_outline:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        if not rec.get("outline"):
            raise AppError(404, "not_found", "outline not found", node=NODE_DN1)
        check_if_match(if_match, rec["outline"]["version"], "outline")
        self._require_unlock(rec, body.unlock_edit)
        reject_outline_prompts(body.body_md)
        if body.shot_cap is not None:
            rec["outline"]["shot_cap"] = require_shot_cap(body.shot_cap)
        rec["outline"]["body_md"] = body.body_md
        rec["outline"]["version"] += 1
        rec["outline"]["updated_at"] = now_iso()
        rec["outline"]["locked"] = False
        rec["gate"]["state"] = "ready"
        rec["episode"]["status"] = "awaiting_g1b"
        rec["episode"]["next_edges"] = []
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"put_outline:{project_id}:{ep}", self.outline_envelope(rec))

    def reset_outline(
        self,
        project_id: str,
        ep: str,
        body: OutlineResetRequest | None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        cached = self._idem_get(idempotency_key, f"reset:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        if not rec.get("outline"):
            raise AppError(404, "not_found", "outline not found", node=NODE_DN1)
        req = body or OutlineResetRequest()
        self._require_unlock(rec, req.unlock_edit)
        rec["outline"]["body_md"] = ""
        rec["outline"]["version"] += 1
        rec["outline"]["updated_at"] = now_iso()
        rec["outline"]["locked"] = False
        rec["outline"]["confirmed_by"] = None
        rec["outline"]["job_id"] = None
        if req.clear_cast and rec.get("cast"):
            rec["cast"]["characters"] = []
            rec["cast"]["scenes"] = []
            rec["cast"]["version"] += 1
            rec["cast"]["updated_at"] = now_iso()
        rec["gate"]["state"] = "ready"
        rec["episode"]["status"] = "awaiting_g1b"
        rec["episode"]["next_edges"] = []
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"reset:{project_id}:{ep}", self.outline_envelope(rec))

    def get_cast(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, validate_ep(ep))
        return self.cast_envelope(rec)

    def _rows_from_write(self, rec: dict[str, Any], rows: list[Any], kind: str) -> list[dict[str, Any]]:
        allocated = set(rec["allocated_char_ids"] if kind == "CHAR" else rec["allocated_scene_ids"])
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if not (row.name or "").strip() or not (row.one_line or "").strip():
                raise AppError(422, "validation", f"{kind} name and one_line are required")
            if kind == "CHAR":
                char_name = normalize_name(row.name)
                if (
                    (is_banlist_name(char_name) or is_bare_brand(char_name))
                    and not is_protected_lead(char_name)
                    and not is_a_tier_prince_name(char_name)
                    and not is_registerable_name(char_name)
                ):
                    raise AppError(
                        422,
                        "validation",
                        "B-class / banlist name cannot open CHAR",
                        name=char_name,
                        node=NODE_DN1,
                    )
            known = require_known_or_omit(row.id, allocated, kind)
            if known is None:
                ident = self._alloc_char(rec) if kind == "CHAR" else self._alloc_scene(rec)
            else:
                ident = known
            if ident in seen:
                raise AppError(422, "validation", f"duplicate {kind} id", id=ident)
            seen.add(ident)
            ref = None
            if row.library_ref is not None:
                lib = self._resolve_library(rec["episode"]["project_id"], row.library_ref.id, row.library_ref.version)
                ref = {"id": lib["id"], "version": lib["version"]}
            item: dict[str, Any] = {"id": ident, "name": row.name, "one_line": row.one_line, "library_ref": ref}
            if row.is_hero is not None:
                item["is_hero"] = row.is_hero
            out.append(item)
        return out

    def put_cast(
        self,
        project_id: str,
        ep: str,
        body: CastWrite,
        *,
        raw: dict[str, Any] | None = None,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        cached = self._idem_get(idempotency_key, f"put_cast:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        if not rec.get("cast"):
            rec["cast"] = self._empty_cast(rec, body.lane)
        check_if_match(if_match, rec["cast"]["version"], "cast")
        self._require_unlock(rec, body.unlock_edit)
        before_fp = self._compute_fingerprint(rec)
        rec["cast"]["characters"] = self._rows_from_write(rec, body.characters, "CHAR")
        rec["cast"]["scenes"] = self._rows_from_write(rec, body.scenes, "SCENE")
        if body.lane:
            rec["cast"]["lane"] = body.lane
        rec["cast"]["version"] += 1
        rec["cast"]["updated_at"] = now_iso()
        rec["cast"]["locked"] = False
        if rec.get("outline"):
            rec["gate"]["state"] = "ready"
            rec["episode"]["status"] = "awaiting_g1b"
        rec["episode"]["next_edges"] = []
        self._maybe_clear_intent(rec, before_fp)
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"put_cast:{project_id}:{ep}", self.cast_envelope(rec))

    def attach_character(
        self,
        project_id: str,
        ep: str,
        body: AttachRequest,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        cached = self._idem_get(idempotency_key, f"attach:{project_id}:{ep}:{body.character_id}@{body.version}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        lib = self._resolve_library(project_id, body.character_id, body.version)
        if not rec.get("cast"):
            rec["cast"] = self._empty_cast(rec, (rec.get("brief") or {}).get("lane_preference") if (rec.get("brief") or {}).get("lane_preference") in {"female", "male"} else None)
        self._require_unlock(rec, body.unlock_edit)
        before_fp = self._compute_fingerprint(rec)
        self._register_char(rec, body.character_id)
        chars = rec["cast"]["characters"]
        existing = next((c for c in chars if c["id"] == body.character_id or (c.get("library_ref") or {}).get("id") == body.character_id), None)
        ref = {"id": lib["id"], "version": lib["version"]}
        if existing:
            existing["library_ref"] = ref
            if existing.get("name") in {None, "", existing.get("id")}:
                existing["name"] = lib["name"]
            if existing.get("one_line") in {None, "", "预挂角色"}:
                existing["one_line"] = lib["one_line"]
        else:
            chars.append(
                {
                    "id": body.character_id,
                    "name": lib["name"],
                    "one_line": lib["one_line"],
                    "library_ref": ref,
                }
            )
        if rec.get("brief"):
            ids = rec["brief"].setdefault("preattached_character_ids", [])
            if body.character_id not in ids:
                ids.append(body.character_id)
        rec["cast"]["version"] += 1
        rec["cast"]["updated_at"] = now_iso()
        rec["cast"]["locked"] = False
        rec["episode"]["next_edges"] = []
        self._maybe_clear_intent(rec, before_fp)
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(
            idempotency_key,
            f"attach:{project_id}:{ep}:{body.character_id}@{body.version}",
            self.cast_envelope(rec),
        )

    def detach_character(
        self,
        project_id: str,
        ep: str,
        body: DetachRequest,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        cached = self._idem_get(idempotency_key, f"detach:{project_id}:{ep}:{body.character_id}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        if not rec.get("cast"):
            raise AppError(404, "not_found", "cast not found", node=NODE_DN1)
        self._require_unlock(rec, body.unlock_edit)
        before_fp = self._compute_fingerprint(rec)
        found = False
        for row in rec["cast"]["characters"]:
            ref = row.get("library_ref") or {}
            if row["id"] == body.character_id or ref.get("id") == body.character_id:
                row["library_ref"] = None
                found = True
        if rec.get("brief"):
            ids = rec["brief"].get("preattached_character_ids") or []
            rec["brief"]["preattached_character_ids"] = [i for i in ids if i != body.character_id]
        if not found:
            raise AppError(404, "not_found", "character not attached", character_id=body.character_id)
        rec["cast"]["version"] += 1
        rec["cast"]["updated_at"] = now_iso()
        rec["episode"]["next_edges"] = []
        self._maybe_clear_intent(rec, before_fp)
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"detach:{project_id}:{ep}:{body.character_id}", self.cast_envelope(rec))

    def sidecar_add_character(
        self,
        project_id: str,
        ep: str,
        body: SidecarAddCharacterRequest,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """O2: add a named CHAR without unlocking G1b or rewriting locked outline body."""
        reject_force_keys(raw)
        cached = self._idem_get(idempotency_key, f"sidecar_add:{project_id}:{ep}:{body.name}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        if not rec.get("cast"):
            raise AppError(404, "not_found", "cast not found", node=NODE_DN1)
        name = normalize_name(body.name)
        if not name:
            raise AppError(422, "validation", "name is required", node=NODE_DN1)
        if (
            (is_banlist_name(name) or is_bare_brand(name))
            and not is_protected_lead(name)
            and not is_a_tier_prince_name(name)
        ):
            raise AppError(
                422,
                "validation",
                "B-class / banlist name cannot open CHAR",
                name=name,
                node=NODE_DN1,
            )
        existing = next(
            (
                c
                for c in rec["cast"]["characters"]
                if normalize_name(str(c.get("name") or "")) == name
            ),
            None,
        )
        if not existing:
            ident = self._alloc_char(rec)
            old_ver = rec["cast"].get("version") or 0
            rec["cast"]["characters"].append(
                {
                    "id": ident,
                    "name": name,
                    "one_line": (body.one_line or "").strip() or SIDECAR_ONE_LINE,
                    "library_ref": None,
                }
            )
            rec["cast"]["version"] = old_ver + 1
            rec["cast"]["updated_at"] = now_iso()
            self._set_cast_change_hint(
                rec,
                added=[{"id": ident, "name": name}],
                source="sidecar",
                cast_version_old=old_ver,
            )
        # O2: do not unlock/un-confirm G1b; do not mutate outline body.
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(
            idempotency_key,
            f"sidecar_add:{project_id}:{ep}:{body.name}",
            self.cast_envelope(rec),
        )

    # ----- gate G1b -----------------------------------------------------------------

    def get_gate(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, validate_ep(ep))
        return self.gate_envelope(rec)

    def _validate_pass(self, rec: dict[str, Any]) -> None:
        outline = rec.get("outline")
        cast = rec.get("cast")
        if not outline or not (outline.get("body_md") or "").strip():
            raise AppError(422, "outline_empty", "outline needs a numbered 桥段 sequence", node=NODE_DN1)
        reject_outline_prompts(outline["body_md"])
        require_outline_beats(outline["body_md"])
        require_shot_cap(outline.get("shot_cap") or SHOT_CAP_HARD)
        if not cast:
            raise AppError(422, "cast_incomplete", "need ≥1 character and ≥1 scene", node=NODE_DN1)
        chars = cast.get("characters") or []
        scenes = cast.get("scenes") or []
        if len(chars) < 1 or len(scenes) < 1:
            raise AppError(422, "cast_incomplete", "need ≥1 character and ≥1 scene", node=NODE_DN1)
        ids = [c["id"] for c in chars] + [s["id"] for s in scenes]
        if len(ids) != len(set(ids)):
            raise AppError(422, "validation", "cast ids must be unique")
        project_id = rec["episode"]["project_id"]
        for row in chars + scenes:
            ref = row.get("library_ref")
            if ref:
                try:
                    self._resolve_library(project_id, ref["id"], ref["version"])
                except AppError as exc:
                    if exc.code == "not_found":
                        raise AppError(
                            422,
                            "library_ref_unresolved",
                            "library_ref not in project library",
                            id=ref["id"],
                            version=ref["version"],
                            provisional="D12",
                        ) from exc
                    raise

    def confirm_gate(
        self,
        project_id: str,
        ep: str,
        raw: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        reject_dual_skill(raw)
        extra = set(raw.keys()) - {"decision", "note", "actor", "idempotency_key"}
        if extra:
            # additionalProperties=false; force keys already rejected
            raise AppError(400, "validation", "unexpected fields on gate confirm", fields=sorted(extra))
        cached = self._idem_get(idempotency_key or raw.get("idempotency_key"), f"confirm:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        decision = raw.get("decision")
        actor = (raw.get("actor") or "").strip()
        if decision not in {"pass", "reject"}:
            raise AppError(422, "validation", "decision must be pass|reject")
        if not actor:
            raise AppError(422, "validation", "actor is required")
        note = raw.get("note")
        ts = now_iso()
        if decision == "pass":
            self._validate_pass(rec)
            confirm_lane = (rec.get("outline") or {}).get("lane") or (rec.get("brief") or {}).get("lane_preference")
            for item in lane_identity_warnings(
                confirm_lane or "",
                self._resolve_preattached_characters(project_id, rec),
            ):
                logger.warning(item)
            rec["outline"]["locked"] = True
            rec["outline"]["confirmed_by"] = actor
            rec["cast"]["locked"] = True
            rec["cast"]["confirmed_by"] = actor
            rec["gate"]["state"] = "passed"
            rec["gate"]["locked"] = True
            rec["gate"]["last_decision"] = "pass"
            rec["gate"]["note"] = note
            rec["gate"]["actor"] = actor
            rec["gate"]["decided_at"] = ts
            rec["gate"]["version"] = rec["outline"]["version"]
            rec["episode"]["locks"]["g1b"] = True
            rec["episode"]["status"] = "locked_g1b"
            rec["episode"]["next_edges"] = [NODE_DN2]
            rec["episode"]["stale_downstream"] = []
            # candidates only — never create a D-N2 job
            rec["d_n2_jobs"] = []
        else:
            rec["gate"]["state"] = "rejected"
            rec["gate"]["locked"] = False
            rec["gate"]["last_decision"] = "reject"
            rec["gate"]["note"] = note
            rec["gate"]["actor"] = actor
            rec["gate"]["decided_at"] = ts
            rec["gate"]["version"] = (rec.get("outline") or {}).get("version") or rec["gate"]["version"]
            rec["episode"]["locks"]["g1b"] = False
            rec["episode"]["next_edges"] = []
            if rec.get("outline"):
                rec["outline"]["locked"] = False
                rec["outline"]["confirmed_by"] = None
                rec["episode"]["status"] = "awaiting_g1b"
            if rec.get("cast"):
                rec["cast"]["locked"] = False
                rec["cast"]["confirmed_by"] = None
        rec["outline"]["updated_at"] = ts if rec.get("outline") else None
        if rec.get("cast"):
            rec["cast"]["updated_at"] = ts
        self._touch_episode(rec)
        self._commit(rec)
        env = self.gate_envelope(rec)
        return self._idem_put(idempotency_key or raw.get("idempotency_key"), f"confirm:{project_id}:{ep}", env)

    def get_downstream(self, project_id: str, ep: str) -> dict[str, Any]:
        """Read-only surface for D-N2 consumers. Does not start D-N2."""
        rec = self._rec(project_id, validate_ep(ep))
        if not self._g1b_locked(rec):
            raise AppError(
                409,
                "upstream_unlocked",
                "D-N1 not locked",
                node=NODE_DN1,
                gate=GATE_G1B,
            )
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN1,
            "consumer": NODE_DN2,
            "started": False,
            "jobs": list(rec.get("d_n2_jobs") or []),
            "outline": deepcopy(rec["outline"]),
            "cast": deepcopy(rec["cast"]),
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }

    def evaluate_copy_contract(self, project_id: str, ep: str, raw: dict[str, Any] | None) -> dict[str, Any]:
        """018d GAP-COPY overlay. Does not rewrite generate / adsorb / G2."""
        incoming = raw if isinstance(raw, dict) else {}
        reject_force_keys(incoming)
        rec = self._rec(project_id, validate_ep(ep))
        return evaluate(incoming, rec=rec)

    def error_catalog(self) -> dict[str, Any]:
        return catalog_public()
