from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.config import SHOT_CAP_HARD, Settings
from aiv_drama.errors import AppError
from aiv_drama.ids import next_id, require_known_or_omit
from aiv_drama.models import (
    AttachRequest,
    CastWrite,
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
)
from aiv_drama.projection import (
    assert_no_secrets,
    write_brief,
    write_cast,
    write_episode_json,
    write_library_character,
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
from aiv_schema.models import GATE_G1B, NODE_DN0, NODE_DN1, NODE_DN2, PIPELINE_DRAMA


def _key(project_id: str, ep: str) -> str:
    return f"{project_id}/{ep}"


class DramaService:
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
            gate = rec["gate"]
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
                    }
                },
                "next_edges": list(rec["episode"].get("next_edges") or []),
                "lane_preference": (rec.get("brief") or {}).get("lane_preference", "unset"),
                "stale": {"d_n2": NODE_DN2 in (rec["episode"].get("stale_downstream") or [])},
                "stale_downstream": list(rec["episode"].get("stale_downstream") or []),
                "locks": deepcopy(rec["episode"]["locks"]),
            }
            write_episode_json(episode_dir, meta)
            assert_no_secrets(episode_dir)
            rec["projection_dirty"] = False
        except Exception:  # noqa: BLE001
            rec["projection_dirty"] = True
            self._save()
            raise
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
        return {
            "ok": True,
            "episode": deepcopy(rec["episode"]),
            "next_edges": list(rec["episode"].get("next_edges") or []),
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
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }

    def outline_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        if not rec.get("outline"):
            raise AppError(404, "not_found", "outline not found", node=NODE_DN1)
        return {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN1,
            "outline": deepcopy(rec["outline"]),
            "cast": deepcopy(rec["cast"]) if rec.get("cast") else None,
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }

    def cast_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        if not rec.get("cast"):
            raise AppError(404, "not_found", "cast not found", node=NODE_DN1)
        return {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN1,
            "cast": deepcopy(rec["cast"]),
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }

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
                "locks": {"g1b": False},
                "versions": {"brief": 0, "outline": 0, "cast": 0, "episode": 1},
                "stale_downstream": [],
                "next_edges": [],
                "created_at": ts,
                "updated_at": ts,
            },
            "brief": None,
            "outline": None,
            "cast": None,
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
            "allocated_char_ids": [],
            "allocated_scene_ids": [],
            "char_counter": 0,
            "scene_counter": 0,
            "source_skills": [],
            "d_n2_jobs": [],
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

    # ----- library (dogfood seed; not list/search) ----------------------------------

    def put_library_character(self, project_id: str, character_id: str, body: LibraryCharacterWrite) -> dict[str, Any]:
        self._require_active_project(project_id)
        key = f"{project_id}/{character_id}@{body.version}"
        record = {
            "id": character_id,
            "version": body.version,
            "name": body.name,
            "one_line": body.one_line,
            "project_id": project_id,
            "updated_at": now_iso(),
        }
        self.store.state["library"][key] = record
        write_library_character(self.store.library_dir(project_id, character_id, body.version), record)
        self._save()
        return {"ok": True, "character": record, "node": NODE_DN0}

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
        lane = body.lane_preference or (current or {}).get("lane_preference") or "unset"
        ids = body.preattached_character_ids
        if ids is None:
            ids = list((current or {}).get("preattached_character_ids") or [])
        version = ((current or {}).get("version") or 0) + 1
        rec["brief"] = {
            "episode_id": rec["episode"]["episode_id"],
            "pipeline_profile": PIPELINE_DRAMA,
            "title_intent": body.title_intent,
            "pin": body.pin,
            "setting_notes": body.setting_notes,
            "lane_preference": lane,
            "preattached_character_ids": ids,
            "version": version,
            "updated_at": now_iso(),
            "updated_by": body.actor,
        }
        if self._g1b_locked(rec) and body.confirm_stale_outline:
            self._add_stale(rec, NODE_DN2)
        if rec["episode"]["status"] == "draft":
            rec["episode"]["status"] = "in_progress"
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"put_brief:{project_id}:{ep}", self.brief_envelope(rec))

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

    def _merge_generated_cast(
        self,
        rec: dict[str, Any],
        draft: GeneratedDraft,
        project_id: str,
    ) -> dict[str, Any]:
        existing_by_id = {c["id"]: c for c in ((rec.get("cast") or {}).get("characters") or [])}
        existing_scenes = {s["id"]: s for s in ((rec.get("cast") or {}).get("scenes") or [])}
        characters: list[dict[str, Any]] = []
        used_names: set[str] = set()

        for row in draft.characters:
            ident = self._alloc_char(rec)
            prev = existing_by_id.get(ident)
            ref = deepcopy(prev.get("library_ref")) if prev and prev.get("library_ref") else None
            characters.append(
                {
                    "id": ident,
                    "name": row.get("name") or "未命名",
                    "one_line": row.get("one_line") or "待补一句话",
                    "library_ref": ref,
                }
            )
            used_names.add((row.get("name") or "").strip())

        # keep previously attached rows not overwritten
        for ident, prev in existing_by_id.items():
            if prev.get("library_ref") and ident not in {c["id"] for c in characters}:
                characters.append(deepcopy(prev))

        preattached = list((rec.get("brief") or {}).get("preattached_character_ids") or [])
        have_ids = {c["id"] for c in characters}
        for cid in preattached:
            lib = self._latest_library(project_id, cid)
            existing = next((c for c in characters if c["id"] == cid), None)
            if existing:
                if not existing.get("library_ref") and lib:
                    existing["library_ref"] = {"id": lib["id"], "version": lib["version"]}
                continue
            # append preattached row
            if cid not in rec["allocated_char_ids"]:
                self._register_char(rec, cid)
            if lib:
                characters.append(
                    {
                        "id": cid,
                        "name": lib["name"],
                        "one_line": lib["one_line"],
                        "library_ref": {"id": lib["id"], "version": lib["version"]},
                    }
                )
            else:
                characters.append(
                    {
                        "id": cid,
                        "name": cid,
                        "one_line": "预挂角色",
                        "library_ref": None,
                    }
                )
            have_ids.add(cid)

        scenes: list[dict[str, Any]] = []
        for row in draft.scenes:
            ident = self._alloc_scene(rec)
            prev = existing_scenes.get(ident)
            scenes.append(
                {
                    "id": ident,
                    "name": row.get("name") or "未命名场景",
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
        brief = rec.get("brief")
        if not brief:
            raise AppError(422, "brief_incomplete", "title_intent and pin both empty", node=NODE_DN0)
        require_brief_ready(brief.get("title_intent"), brief.get("pin"))
        req = body or OutlineGenerateRequest()
        lane = self._resolve_lane(rec, req.lane)
        shot_cap = require_shot_cap(req.shot_cap)
        provider = get_provider(req.provider, self.settings)
        draft = provider.generate(episode_id=rec["episode"]["episode_id"], lane=lane, shot_cap=shot_cap, brief=brief)
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
        rec["cast"] = self._merge_generated_cast(rec, draft, project_id)
        rec["gate"]["state"] = "ready"
        rec["gate"]["locked"] = False
        rec["episode"]["status"] = "awaiting_g1b"
        rec["episode"]["next_edges"] = []
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"generate:{project_id}:{ep}", self.outline_envelope(rec))

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
            out.append({"id": ident, "name": row.name, "one_line": row.one_line, "library_ref": ref})
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
        self._touch_episode(rec)
        self._commit(rec)
        return self._idem_put(idempotency_key, f"detach:{project_id}:{ep}:{body.character_id}", self.cast_envelope(rec))

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
