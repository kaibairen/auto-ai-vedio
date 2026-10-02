"""D-N5a generate-grid + gate G4. Extends DramaN4Ops. Does not implement N5b Job."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import now_iso
from aiv_drama_n3.gold_sheet import md5_bytes
from aiv_drama_n3.seedream import ARK_IMAGES_URL, SEEDREAM_SKU_CHAIN, SEEDREAM_SKU_PRIMARY, face_to_data_url
from aiv_drama_n4.ops import DramaN4Ops
from aiv_drama_n5a.checklist import apply_gate_to_checklist, build_checklist
from aiv_drama_n5a.exempt import scene_look_exempt
from aiv_drama_n5a.gates import (
    empty_gate_g4,
    empty_n5a,
    g4_locked,
    n4_assemble_version,
    reject_n5b_submit,
    require_g4_for_n5b,
    require_grid_for_g4_pass,
    require_jsonl_for_generate,
)
from aiv_drama_n5a.image import (
    assert_real_image_bytes,
    generate_grid_image,
    recorded_grid_request,
)
from aiv_drama_n5a.look_mode import (
    MODE_A,
    MODE_B,
    char_look_report,
    look_mode_for_char,
    resolve_face_file,
)
from aiv_drama_n5a.models import N5aGenerateRequest
from aiv_drama_n5a.projection import (
    checklist_relpath,
    evidence_relpath,
    grid_filename,
    grid_relpath,
    grids_dir,
    next_grid_version,
    read_checklist_yaml,
    write_checklist_yaml,
    write_evidence_json,
    write_grid_png,
)
from aiv_drama_n5a.prompt import GRID_PROMPT_PATHS, assemble_grid_prompt, select_lines
from aiv_drama_n5a.validate import normalize_layout, reject_force_keys_n5a
from aiv_schema.models import GATE_G4, NODE_DN5A, NODE_DN5B, PIPELINE_DRAMA


class DramaN5aOps(DramaN4Ops):
    """N5a min loop. Does not auto-open N5b. Does not flip usable_for_n4."""

    def _ensure_n5a_fields(self, rec: dict[str, Any]) -> None:
        rec["episode"]["versions"].setdefault("grids", 0)
        rec["episode"]["locks"].setdefault("g4", False)
        rec.setdefault("d_n5a_jobs", [])
        rec.setdefault("d_n5b_jobs", [])
        if rec.get("n5a") is None:
            rec["n5a"] = None
        if not rec.get("gate_g4"):
            rec["gate_g4"] = empty_gate_g4()
        self._refresh_n5a_stale(rec)

    def _stale_n4(self, rec: dict[str, Any]) -> None:
        super()._stale_n4(rec)
        self._stale_n5a(rec)

    def _stale_n5a(self, rec: dict[str, Any]) -> None:
        n5a = rec.get("n5a")
        if not n5a:
            return
        n5a["stale"] = True
        if rec.get("gate_g4"):
            rec["gate_g4"]["locked"] = False
            if rec["gate_g4"].get("state") == "passed":
                rec["gate_g4"]["state"] = "ready"
            rec["episode"]["locks"]["g4"] = False
        if NODE_DN5A not in (rec["episode"].get("stale_downstream") or []):
            rec["episode"].setdefault("stale_downstream", []).append(NODE_DN5A)

    def _refresh_n5a_stale(self, rec: dict[str, Any]) -> None:
        n5a = rec.get("n5a")
        if not n5a:
            return
        if int(n5a.get("upstream_assemble_version") or 0) != n4_assemble_version(rec):
            self._stale_n5a(rec)

    def _n5a_endpoint(self) -> str:
        base = getattr(self.settings, "ark_base_url", None) or ARK_IMAGES_URL.rsplit("/images", 1)[0]
        return f"{base.rstrip('/')}/images/generations"

    def _checklist_path(self, project_id: str, ep: str) -> Path:
        return grids_dir(self.store.episode_dir(project_id, ep)) / f"{ep}_g4-checklist.yaml"

    def _evidence_path(self, project_id: str, ep: str) -> Path:
        return grids_dir(self.store.episode_dir(project_id, ep)) / f"{ep}_g4-evidence.json"

    def n5a_envelope(
        self,
        rec: dict[str, Any],
        *,
        warnings: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        checklist: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        n5a = deepcopy(rec.get("n5a") or empty_n5a(rec))
        g4 = deepcopy(rec.get("gate_g4") or empty_gate_g4())
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN5A,
            "n5a": n5a,
            "gate": g4,
            "started": bool(n5a.get("started")),
            "stale": bool(n5a.get("stale")),
            "layout": n5a.get("layout"),
            "grid_version": n5a.get("grid_version") or 0,
            "path": n5a.get("grid_relpath"),
            "grid_path": n5a.get("grid_relpath"),
            "md5": n5a.get("md5"),
            "sku": n5a.get("sku"),
            "checklist_path": n5a.get("checklist_relpath"),
            "evidence_path": n5a.get("evidence_relpath"),
            "look_modes": dict(n5a.get("look_modes") or {}),
            "scene_exempt": bool(n5a.get("scene_exempt") or scene_look_exempt(rec)),
            "g4_locked": g4_locked(rec),
            "g4_verdict": g4.get("last_decision"),
            "fake_pixels": False,
            "threshold_hard_gated": False,
            "auto_open_dn5b": False,
            "n5b_submit": False,
            "docs_pass": False,
            "usable_for_n4_flipped": False,
            "p_char": "usable_for_n4=true means human-reviewed look sheet (合板), not a face file",
            "mode_b_face_required": False,
            "prompt_paths": [GRID_PROMPT_PATHS.get(int(n5a.get("layout") or 9), GRID_PROMPT_PATHS[9])],
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }
        if checklist is not None:
            env["checklist"] = checklist
        if warnings:
            env["warnings"] = warnings
        if extra:
            env.update(extra)
        return env

    def get_n5a(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        checklist = read_checklist_yaml(self._checklist_path(project_id, rec["episode"]["episode_id"]))
        return self.n5a_envelope(rec, checklist=checklist)

    def get_n5a_status(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        n5a = rec.get("n5a") or empty_n5a(rec)
        g4 = rec.get("gate_g4") or empty_gate_g4()
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN5A,
            "started": bool(n5a.get("started")),
            "stale": bool(n5a.get("stale")),
            "layout": n5a.get("layout"),
            "grid_version": n5a.get("grid_version") or 0,
            "path": n5a.get("grid_relpath"),
            "md5": n5a.get("md5"),
            "sku": n5a.get("sku"),
            "g4_locked": g4_locked(rec),
            "g4_verdict": g4.get("last_decision"),
            "g4_actor": g4.get("actor"),
            "scene_exempt": bool(n5a.get("scene_exempt") or scene_look_exempt(rec)),
            "look_modes": dict(n5a.get("look_modes") or {}),
            "fake_pixels": False,
            "auto_open_dn5b": False,
            "docs_pass": False,
        }

    def get_gate_g4(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        env = self.n5a_envelope(rec, checklist=read_checklist_yaml(self._checklist_path(project_id, rec["episode"]["episode_id"])))
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN5A,
            "gate": deepcopy(rec.get("gate_g4") or empty_gate_g4()),
            "g4_locked": env["g4_locked"],
            "path": env.get("path"),
            "md5": env.get("md5"),
            "checklist": env.get("checklist"),
            "docs_pass": False,
        }

    def _pick_face_data_url(self, rec: dict[str, Any], report: dict[str, Any]) -> tuple[str | None, str | None, str]:
        """Mode A may attach a real face file. Mode B never requires one."""
        from aiv_drama_n3.cards import all_cards

        index = {c["id"]: c for c in all_cards(rec.get("n3")) if c.get("id")}
        for cid in report.get("shot_char_ids") or []:
            card = index.get(cid)
            if not card:
                continue
            if look_mode_for_char(card) != MODE_A:
                continue
            face = resolve_face_file(card, self.settings)
            if face is None:
                continue
            return face_to_data_url(face), md5_bytes(face.read_bytes()), MODE_A
        return None, None, MODE_B

    def generate_n5a_grid(
        self,
        project_id: str,
        ep: str,
        body: N5aGenerateRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        post: Any | None = None,
        get: Any | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n5a(raw)
        req = body or N5aGenerateRequest.model_validate(
            {k: v for k, v in (raw or {}).items() if k in {"actor", "layout", "shots", "dry_run"}}
            if raw
            else {}
        )
        cached = self._idem_get(idempotency_key, f"n5a_generate:{project_id}:{ep}:{req.layout}:{int(req.dry_run)}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        if rec["episode"].get("pipeline_profile") != PIPELINE_DRAMA:
            raise AppError(422, "wrong_profile", "pipeline_profile must be drama", node=NODE_DN5A)
        ep_id = rec["episode"]["episode_id"]
        layout = normalize_layout(req.layout)
        episode_dir = self.store.episode_dir(project_id, ep_id)
        lines = require_jsonl_for_generate(episode_dir, ep_id)
        chosen = select_lines(lines, shots=list(req.shots or []), layout=layout)
        report = char_look_report(rec, chosen, self.settings)
        prompt = assemble_grid_prompt(rec, chosen, layout=layout)
        image_url, face_md5, used_mode = self._pick_face_data_url(rec, report)
        endpoint = self._n5a_endpoint()
        recorded = recorded_grid_request(
            model=SEEDREAM_SKU_PRIMARY,
            prompt=prompt,
            look_mode=used_mode,
            has_image=bool(image_url),
            face_md5=face_md5,
            endpoint=endpoint,
        )
        folder = grids_dir(episode_dir)
        folder.mkdir(parents=True, exist_ok=True)
        if req.dry_run:
            evidence = {
                "ok": True,
                "dry_run": True,
                "written_grid": False,
                "fake_pixels": False,
                "sku_chain": list(SEEDREAM_SKU_CHAIN),
                "recorded": recorded,
                "look_modes": report["look_modes"],
                "face_required": False,
                "mode_b_face_hard_block": False,
                "attempts": [],
                "key_redacted": True,
            }
            write_evidence_json(self._evidence_path(project_id, ep_id), evidence)
            checklist = build_checklist(
                rec=rec,
                ep=ep_id,
                layout=layout,
                grid_relpath=None,
                md5=None,
                sku=None,
                look_modes=report["look_modes"],
                precheck={"P-A1": "pending", "P-A2": "pending", "P-A3": "pending"},
            )
            write_checklist_yaml(self._checklist_path(project_id, ep_id), checklist)
            n5a = empty_n5a(rec)
            n5a.update(
                {
                    "started": False,
                    "dry_run": True,
                    "layout": layout,
                    "look_modes": report["look_modes"],
                    "scene_exempt": scene_look_exempt(rec, ep_id),
                    "evidence_relpath": evidence_relpath(ep_id),
                    "checklist_relpath": checklist_relpath(ep_id),
                    "upstream_assemble_version": n4_assemble_version(rec),
                    "generated_at": now_iso(),
                    "generated_by": req.actor,
                }
            )
            rec["n5a"] = n5a
            rec["gate_g4"] = rec.get("gate_g4") or empty_gate_g4()
            rec["gate_g4"]["state"] = "ready"
            rec["gate_g4"]["locked"] = False
            rec["episode"]["locks"]["g4"] = False
            self._touch_episode(rec)
            self._commit(rec)
            env = self.n5a_envelope(
                rec,
                warnings=report["warnings"] or None,
                checklist=checklist,
                extra={"written": False, "dry_run": True, "recorded": recorded, "prompt_chars": len(prompt)},
            )
            return self._idem_put(idempotency_key, f"n5a_generate:{project_id}:{ep}:{layout}:1", env)

        api_key = getattr(self.settings, "ark_api_key", None)
        try:
            result = generate_grid_image(
                api_key=api_key or "",
                prompt=prompt,
                image_data_url=image_url,
                endpoint=endpoint,
                post=post,
                get=get,
            )
        except AppError:
            raise
        payload = result["bytes"]
        assert_real_image_bytes(payload)
        digest = md5_bytes(payload)
        version = next_grid_version(episode_dir, ep_id, layout)
        dest = folder / grid_filename(ep_id, layout, version)
        write_grid_png(dest, payload)
        rel = grid_relpath(ep_id, layout, version)
        sku = result["model"]
        evidence = {
            "ok": True,
            "dry_run": False,
            "written_grid": True,
            "fake_pixels": False,
            "provider": "ark",
            "sku": sku,
            "sku_chain": list(SEEDREAM_SKU_CHAIN),
            "attempts": result.get("attempts") or [],
            "md5": digest,
            "bytes_len": len(payload),
            "size": result.get("size"),
            "path": rel,
            "look_modes": report["look_modes"],
            "look_mode_used": used_mode,
            "has_image_ref": bool(image_url),
            "face_required": False,
            "mode_b_face_hard_block": False,
            "scene_exempt": scene_look_exempt(rec, ep_id),
            "key_redacted": True,
            "recorded": recorded,
        }
        write_evidence_json(self._evidence_path(project_id, ep_id), evidence)
        checklist = build_checklist(
            rec=rec,
            ep=ep_id,
            layout=layout,
            grid_relpath=rel,
            md5=digest,
            sku=sku,
            look_modes=report["look_modes"],
            precheck={"P-A1": "PASS", "P-A2": "PASS", "P-A3": "PASS"},
            fake_pixels=False,
        )
        write_checklist_yaml(self._checklist_path(project_id, ep_id), checklist)
        ts = now_iso()
        n5a = empty_n5a(rec)
        n5a.update(
            {
                "started": True,
                "stale": False,
                "grid_version": version,
                "layout": layout,
                "grid_relpath": rel,
                "checklist_relpath": checklist_relpath(ep_id),
                "evidence_relpath": evidence_relpath(ep_id),
                "md5": digest,
                "sku": sku,
                "look_modes": report["look_modes"],
                "scene_exempt": scene_look_exempt(rec, ep_id),
                "fake_pixels": False,
                "dry_run": False,
                "upstream_assemble_version": n4_assemble_version(rec),
                "generated_at": ts,
                "generated_by": req.actor,
            }
        )
        rec["n5a"] = n5a
        rec["gate_g4"] = rec.get("gate_g4") or empty_gate_g4()
        rec["gate_g4"]["state"] = "ready"
        rec["gate_g4"]["locked"] = False
        rec["gate_g4"]["last_decision"] = None
        rec["episode"]["locks"]["g4"] = False
        rec["episode"]["versions"]["grids"] = version
        rec["episode"]["next_edges"] = [NODE_DN5A]
        stale = rec["episode"].setdefault("stale_downstream", [])
        if NODE_DN5A in stale:
            stale.remove(NODE_DN5A)
        rec["d_n5a_jobs"] = [
            {
                "kind": "generate-grid",
                "layout": layout,
                "grid_version": version,
                "path": rel,
                "md5": digest,
                "sku": sku,
                "at": ts,
                "actor": req.actor,
            }
        ]
        self._touch_episode(rec)
        self._commit(rec)
        env = self.n5a_envelope(
            rec,
            warnings=report["warnings"] or None,
            checklist=checklist,
            extra={
                "written": True,
                "dry_run": False,
                "attempts": result.get("attempts") or [],
                "prompt_chars": len(prompt),
                "shot_ids": [row.get("shot_id") for row in chosen],
            },
        )
        return self._idem_put(idempotency_key, f"n5a_generate:{project_id}:{ep}:{layout}:0", env)

    def confirm_gate_g4(
        self,
        project_id: str,
        ep: str,
        raw: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n5a(raw)
        extra = set((raw or {}).keys()) - {"verdict", "decision", "note", "actor", "idempotency_key"}
        if extra:
            raise AppError(400, "validation", "unexpected fields on G4 confirm", fields=sorted(extra), node=NODE_DN5A)
        cached = self._idem_get(idempotency_key or (raw or {}).get("idempotency_key"), f"confirm_g4:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        verdict = (raw.get("verdict") or raw.get("decision") or "").strip()
        actor = (raw.get("actor") or "").strip()
        if verdict not in {"pass", "rework"}:
            raise AppError(422, "validation", "verdict must be pass|rework", node=NODE_DN5A, gate=GATE_G4)
        if not actor:
            raise AppError(422, "validation", "actor is required", node=NODE_DN5A, gate=GATE_G4)
        ep_id = rec["episode"]["episode_id"]
        episode_dir = self.store.episode_dir(project_id, ep_id)
        checklist = read_checklist_yaml(self._checklist_path(project_id, ep_id))
        ts = now_iso()
        if verdict == "pass":
            require_grid_for_g4_pass(rec=rec, episode_dir=episode_dir, checklist=checklist)
            rec["gate_g4"]["state"] = "passed"
            rec["gate_g4"]["locked"] = True
            rec["gate_g4"]["last_decision"] = "pass"
            rec["episode"]["locks"]["g4"] = True
            rec["episode"]["next_edges"] = [NODE_DN5A]
        else:
            rec["gate_g4"]["state"] = "rework"
            rec["gate_g4"]["locked"] = False
            rec["gate_g4"]["last_decision"] = "rework"
            rec["episode"]["locks"]["g4"] = False
            rec["episode"]["next_edges"] = [NODE_DN5A]
        rec["gate_g4"]["note"] = raw.get("note")
        rec["gate_g4"]["actor"] = actor
        rec["gate_g4"]["decided_at"] = ts
        rec["gate_g4"]["version"] = int(rec["gate_g4"].get("version") or 0) + 1
        if checklist:
            checklist = apply_gate_to_checklist(
                checklist, verdict=verdict, actor=actor, note=raw.get("note"), decided_at=ts
            )
            write_checklist_yaml(self._checklist_path(project_id, ep_id), checklist)
        self._touch_episode(rec)
        self._commit(rec)
        env = self.get_gate_g4(project_id, ep)
        return self._idem_put(idempotency_key or (raw or {}).get("idempotency_key"), f"confirm_g4:{project_id}:{ep}", env)

    def submit_n5b(
        self,
        project_id: str,
        ep: str,
        raw: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n5a(raw)
        rec = self._rec(project_id, ep)
        reject_n5b_submit(rec)
        raise AssertionError("unreachable")

    def get_n5b_status(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        require_g4_for_n5b(rec)
        raise AppError(
            404,
            "n5b_not_implemented",
            "N5b 出片 Job 本 PR 不做",
            node=NODE_DN5B,
            gate=GATE_G4,
        )
