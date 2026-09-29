from __future__ import annotations

import uuid
from typing import Any

from aiv_n1.artifact import (
    compose_markdown,
    has_required_format,
    parse_title_body,
    read_n1_markdown,
    sha256_file,
    write_n1_markdown,
)
from aiv_n1.config import DEFAULT_PROJECT_ID, Settings
from aiv_n1.errors import AppError
from aiv_n1.gates.g1 import confirm_payload_forbidden, require_n1_locked
from aiv_n1.models import DraftPayload, SessionCreate, StepSubmit, next_edges_after_g1
from aiv_n1.provider import get_provider
from aiv_n1.provider.base import GenerateRequest
from aiv_n1.steps import (
    PATH_B_SKIP_REASON,
    first_step,
    frameworks_for,
    last_step,
    next_step,
    prompt_relpath,
    resolve_frameworks,
    step_spec,
    steps_for,
)
from aiv_n1.store import Store, utcnow
from aiv_n1.validate import (
    CHAR_LIMIT,
    draft_chars,
    validate_actor,
    validate_char_limit,
    validate_ep,
    validate_path,
    validate_project_id,
    validate_title_b,
)


class N1Service:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = Store(settings)

    def create_episode(self, project_id: str, ep: str = "EP01", title: str | None = None) -> dict[str, Any]:
        project_id = validate_project_id(project_id or DEFAULT_PROJECT_ID)
        ep = validate_ep(ep)
        self.store.episode_dir(ep).mkdir(parents=True, exist_ok=True)
        self.store.aiv_dir(ep).mkdir(parents=True, exist_ok=True)
        existing = self.store.read_json(self.store.episode_meta_path(ep))
        if existing:
            return self.envelope(project_id, ep, include_session=False)
        meta = {
            "project_id": project_id,
            "episode": ep,
            "title": title or "",
            "status": "draft",  # BE coarse
            "pipeline_profile": None,  # provisional:P-D2
            "nodes": {"n1": "n1_pending"},  # ENG fine state; do not mix with status
            "gates": {"g1": "idle"},
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        self.store.write_json(self.store.episode_meta_path(ep), meta)
        return self.envelope(project_id, ep, include_session=False)

    def create_session(self, project_id: str, ep: str, body: SessionCreate) -> dict[str, Any]:
        project_id = validate_project_id(project_id or DEFAULT_PROJECT_ID)
        ep = validate_ep(ep)
        path = validate_path(body.path)
        self.create_episode(project_id, ep)
        existing = self._load_session(ep)
        if existing and existing.get("status") == "locked" and not body.reset:
            raise AppError(409, "locked", "N1 is locked; reject G1 before a new session")
        if existing and existing.get("status") == "locked" and body.reset:
            raise AppError(409, "locked", "cannot reset a locked session; G1 reject first")
        prompt = self.settings.prompt_path(path)
        if not prompt.is_file():
            raise AppError(500, "not_found", "curriculum prompt missing", path=str(prompt))
        session = {
            "session_id": str(uuid.uuid4()),
            "episode_id": ep,
            "project_id": project_id,
            "path": path,
            "status": "active",
            "current_step": first_step(path),
            "completed_steps": [],
            "skipped_steps": ["b3_skipped"] if path == "B" else [],
            "provider": (
                "fixture"
                if body.provider == "fixture" or not self.settings.openai_api_key
                else "openai_compat"
            ),
            "version": 1,
            "defects": ["missing_step_3", "framework_7_8_corrupt"] if path == "B" else [],
            "defect_note": PATH_B_SKIP_REASON if path == "B" else None,
            "raw": "",
            "raw_ref": ".aiv/n1-raw.txt",
            "extract": None,
            "frameworks_selected": [],
            "titles": [],
            "candidates": [],
            "draft": None,
            "artifact_rel": "N1-口播定稿.md",
            "prompt_source": prompt_relpath(path),
            "prompt_sha256": sha256_file(prompt),
            "actor_last": validate_actor(body.actor),
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        self._save_session(ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="in_progress",
            n1="n1_pending",
            gates={"g1": "idle"},
        )
        return self.envelope(project_id, ep)

    def put_raw(self, project_id: str, ep: str, raw_text: str, actor: str | None = None) -> dict[str, Any]:
        session = self._require_session(ep)
        if session.get("status") == "locked":
            raise AppError(409, "locked", "cannot write raw after G1 pass")
        if not (raw_text or "").strip():
            raise AppError(422, "validation", "raw_text is required")
        payload = StepSubmit(raw_text=raw_text, actor=actor)
        if session["current_step"] not in {"a1_raw", "b1_raw"}:
            session["raw"] = raw_text.strip()
            self.store.raw_path(ep).write_text(session["raw"], encoding="utf-8")
            self._save_session(ep, session)
            return self.envelope(project_id, ep)
        return self.submit_step(project_id, ep, session["current_step"], payload)

    def submit_step(self, project_id: str, ep: str, step: str, payload: StepSubmit) -> dict[str, Any]:
        session = self._require_session(ep)
        if session.get("status") == "locked":
            raise AppError(409, "locked", "cannot submit steps after G1 pass")
        expected = session["current_step"]
        if step != expected:
            raise AppError(409, "step_order", f"cannot submit {step}", expected=expected, got=step)
        path = session["path"]
        spec = step_spec(step)
        raw_text = (payload.raw_text or payload.text or "").strip()

        if spec["kind"] == "collect_raw":
            if not raw_text:
                raise AppError(422, "validation", "raw_text is required")
            session["raw"] = raw_text
            self.store.raw_path(ep).write_text(raw_text, encoding="utf-8")
            session["raw_ref"] = ".aiv/n1-raw.txt"

        if spec["kind"] == "skipped_source_defect":
            if not (payload.ack_defect or payload.ack_source_gap):
                raise AppError(422, "validation", "ack_defect=true required to skip source-gap step 3")
            session["defects"] = sorted(set((session.get("defects") or []) + ["missing_step_3"]))
            session["defect_note"] = PATH_B_SKIP_REASON
            # titles generated so b4 has candidates
            gen = self._generate(session, step, spec["kind"], payload)
            if gen.titles:
                session["titles"] = gen.titles
            self._complete_step(session, step)
            self._save_session(ep, session)
            self._patch_episode(project_id, ep, status="in_progress", n1="n1_pending")
            return self.envelope(project_id, ep)

        if spec["kind"] == "choose_framework":
            values = list(payload.frameworks or [])
            if payload.framework:
                values.append(payload.framework)
            resolved = resolve_frameworks(path, values)
            if not resolved:
                raise AppError(422, "validation", "select at least one framework")
            session["frameworks_selected"] = [f["name"] for f in resolved]

        if spec["kind"] == "reconstruct":
            values = list(payload.frameworks or [])
            if payload.framework:
                values.append(payload.framework)
            resolved = resolve_frameworks(path, values)
            if not resolved:
                rec = next((f for f in frameworks_for(path) if not f["defective"]), frameworks_for(path)[0])
                resolved = [rec]
            session["frameworks_selected"] = [f["name"] for f in resolved]
            if any(f["defective"] for f in resolved):
                session["defects"] = sorted(set((session.get("defects") or []) + ["framework_7_8_corrupt"]))
            if payload.human_revised_frameworks or payload.manual_revised:
                session["human_revised_frameworks"] = True

        if spec["kind"] == "optimize" and path == "A":
            cid = payload.candidate_id
            if cid is None and payload.pick is not None and session.get("candidates"):
                try:
                    cid = session["candidates"][payload.pick]["id"]
                except (IndexError, KeyError):
                    cid = None
            if not cid:
                raise AppError(422, "validation", "candidate_id is required")
            if not any(c.get("id") == cid for c in session.get("candidates") or []):
                raise AppError(422, "validation", "unknown candidate_id", candidate_id=cid)
            payload.candidate_id = cid

        if spec["kind"] == "generate_titles":
            if payload.title:
                validate_title_b(payload.title)
            if payload.title_id and session.get("titles"):
                if not any(t.get("id") == payload.title_id for t in session["titles"]):
                    raise AppError(422, "validation", "unknown title_id")
            elif not session.get("titles"):
                # first entry to b4 without titles: generate then require pick on same
                # response — if no title_id, generate and stay? BE says submit title_id.
                pass

        gen = self._generate(session, step, spec["kind"], payload)
        if gen.extract:
            session["extract"] = {**gen.extract, "approved": (payload.decision or "approve") != "revise"}
        if gen.frameworks:
            session["frameworks_selected"] = gen.frameworks
        if gen.titles:
            for t in gen.titles:
                validate_title_b(t["title"])
            session["titles"] = gen.titles
        if gen.candidates:
            cleaned = []
            for c in gen.candidates:
                n = draft_chars(c.get("title") or "", c.get("body") or "")
                validate_char_limit(path, n, field=f"candidate[{c.get('id')}].chars")
                item = {**c, "chars": n}
                cleaned.append(item)
            session["candidates"] = cleaned
        edits = payload.edits or {}
        if gen.draft_body or edits.get("body") or spec["kind"] == "optimize":
            title = edits.get("title") or payload.title or gen.draft_title or (session.get("draft") or {}).get("title") or ""
            body = edits.get("body") or gen.draft_body or (session.get("draft") or {}).get("body") or ""
            if spec["kind"] == "optimize" and path == "B" and not body:
                # refine existing
                body = (session.get("draft") or {}).get("body") or gen.draft_body or ""
            if body:
                if path == "B" and title:
                    validate_title_b(title)
                n = draft_chars(title, body)
                validate_char_limit(path, n, field="draft.chars")
                fw = (session.get("frameworks_selected") or [""])[0]
                session["draft"] = {"title": title, "body": body, "chars": n, "framework": fw}

        if spec["kind"] == "generate_titles" and (payload.title_id or payload.title):
            if payload.title:
                session["draft"] = {
                    **(session.get("draft") or {}),
                    "title": payload.title,
                    "body": (session.get("draft") or {}).get("body") or "",
                    "chars": draft_chars(payload.title, (session.get("draft") or {}).get("body") or ""),
                    "framework": (session.get("frameworks_selected") or [""])[0],
                }
            elif payload.title_id:
                picked = next(t for t in session["titles"] if t["id"] == payload.title_id)
                session["selected_title_id"] = payload.title_id
                session["draft"] = {
                    **(session.get("draft") or {}),
                    "title": picked["title"],
                    "body": (session.get("draft") or {}).get("body") or "",
                    "chars": draft_chars(picked["title"], (session.get("draft") or {}).get("body") or ""),
                    "framework": (session.get("frameworks_selected") or [""])[0],
                }

        # b4: if titles just generated and no pick yet, stay on b4
        if spec["kind"] == "generate_titles" and not (payload.title_id or payload.title):
            if not session.get("titles"):
                raise AppError(422, "validation", "title_id or title required")
            # generated this turn — if we didn't have titles before generate, require another submit
            session["updated_at"] = utcnow()
            if payload.title_id or payload.title:
                pass
            else:
                # titles now present; stay on b4 until pick
                if step not in session["completed_steps"]:
                    # do not complete until pick
                    self._save_session(ep, session)
                    return self.envelope(project_id, ep)

        if spec["kind"] == "analyze" and (payload.decision or "approve") == "revise":
            session["updated_at"] = utcnow()
            self._save_session(ep, session)
            return self.envelope(project_id, ep)

        write_draft = spec["kind"] in {"optimize"} or (
            spec["kind"] == "reconstruct" and session.get("draft")
        )
        if write_draft and session.get("draft") and step == last_step(path):
            self._write_draft_file(project_id, ep, session, locked=False, confirmed_by="")
            self._complete_step(session, step)
            session["status"] = "awaiting_g1"
            self._save_session(ep, session)
            self._patch_episode(project_id, ep, status="awaiting_gate", n1="n1_pending", gates={"g1": "pending"})
            return self.envelope(project_id, ep)

        if spec["kind"] == "generate_titles" and not (payload.title_id or payload.title):
            self._save_session(ep, session)
            return self.envelope(project_id, ep)

        self._complete_step(session, step)
        session["status"] = "active"
        self._save_session(ep, session)
        self._patch_episode(project_id, ep, status="in_progress", n1="n1_pending")
        return self.envelope(project_id, ep)

    def put_draft(self, project_id: str, ep: str, payload: DraftPayload) -> dict[str, Any]:
        session = self._require_session(ep)
        if session.get("status") == "locked" or self._artifact_locked(ep):
            raise AppError(409, "locked", "PUT draft forbidden after G1 pass")
        path = session["path"]
        if payload.markdown:
            if not has_required_format(payload.markdown):
                raise AppError(422, "validation", "draft markdown needs ［标题］ and 文案内容：")
            title, body = parse_title_body(payload.markdown)
        else:
            title = (payload.title or "").strip()
            body = (payload.body or "").strip()
            if body.startswith("文案内容："):
                body = body[len("文案内容：") :].strip()
            if not body:
                raise AppError(422, "validation", "draft body is required")
        if path == "B" and title:
            validate_title_b(title)
        n = draft_chars(title, body)
        validate_char_limit(path, n, field="draft.chars")
        fw = payload.framework or (session.get("frameworks_selected") or [""])[0]
        session["draft"] = {"title": title, "body": body, "chars": n, "framework": fw}
        session["status"] = "awaiting_g1"
        session["updated_at"] = utcnow()
        self._write_draft_file(project_id, ep, session, locked=False, confirmed_by="")
        self._save_session(ep, session)
        self._patch_episode(project_id, ep, status="awaiting_gate", n1="n1_pending", gates={"g1": "pending"})
        return self.envelope(project_id, ep)

    def get_n1(self, project_id: str, ep: str, *, view: str = "full") -> dict[str, Any]:
        return self.envelope(project_id, ep, view=view)

    def get_artifact_downstream(self, project_id: str, ep: str) -> dict[str, Any]:
        ep = validate_ep(ep)
        art = self.store.artifact_path(ep)
        meta: dict[str, Any] = {}
        if art.is_file():
            meta, _ = read_n1_markdown(art)
        require_n1_locked(meta)
        return self.envelope(project_id, ep, view="artifact")

    def confirm_g1(self, project_id: str, ep: str, raw: dict[str, Any]) -> dict[str, Any]:
        confirm_payload_forbidden(raw)
        decision = (raw.get("decision") or raw.get("result") or raw.get("action") or "").strip().lower()
        if decision not in {"pass", "reject"}:
            raise AppError(400, "validation", "decision must be pass or reject")
        actor = validate_actor(raw.get("actor"), required=(decision == "pass"))
        session = self._require_session(ep)
        if decision == "reject":
            return self._reject_g1(project_id, ep, session, actor, raw)

        if session.get("status") == "locked":
            return self.envelope(project_id, ep)

        draft = session.get("draft")
        if not draft and self.store.artifact_path(ep).is_file():
            meta, md = read_n1_markdown(self.store.artifact_path(ep))
            title, body = parse_title_body(md)
            draft = {"title": title, "body": body, "chars": meta.get("chars") or draft_chars(title, body), "framework": meta.get("framework") or ""}
            session["draft"] = draft
        if not draft:
            raise AppError(409, "conflict", "draft missing; cannot G1 pass")
        n = draft_chars(draft.get("title") or "", draft.get("body") or "")
        validate_char_limit(session["path"], n, field="draft.chars")
        md = compose_markdown(draft.get("title") or "", draft.get("body") or "")
        if not has_required_format(md):
            raise AppError(422, "validation", "draft needs ［标题］ and 文案内容：")
        if not (draft.get("framework") or (session.get("frameworks_selected") or [""])[0]):
            raise AppError(422, "validation", "framework required to lock")
        session["status"] = "locked"
        session["updated_at"] = utcnow()
        session["actor_last"] = actor
        self._write_draft_file(project_id, ep, session, locked=True, confirmed_by=actor, keep_version=True)
        self._save_session(ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="in_progress",  # G1 pass ≠ done (ENG §6)
            n1="n1_locked",
            gates={"g1": "passed"},
            blocked_decisions=["D2"],
            gate_log={"gate": "g1", "decision": "pass", "actor": actor, "notes": raw.get("notes") or raw.get("note"), "at": utcnow()},
        )
        env = self.envelope(project_id, ep)
        env["next_edges"] = next_edges_after_g1()
        env["auto_advanced"] = False
        return env

    def demo(self, project_id: str, ep: str, path: str, actor: str = "bot:demo") -> dict[str, Any]:
        path = validate_path(path)
        self.create_episode(project_id, ep)
        self.create_session(project_id, ep, SessionCreate(path=path, provider="fixture", actor=actor))  # type: ignore[arg-type]
        if path == "A":
            raw = (
                "就是那个咖啡渣别扔啊，我妈说能除臭还能当肥料，"
                "我以前一直当垃圾倒了，后来才知道还能去油污，真的很神奇，"
                "你们可以试试，记得评论区说说你们还有啥妙用。"
            )
            self.submit_step(project_id, ep, "a1_raw", StepSubmit(raw_text=raw))
            self.submit_step(project_id, ep, "a2_extract", StepSubmit(decision="approve"))
            self.submit_step(project_id, ep, "a3_framework", StepSubmit(frameworks=["惊喜揭秘型"]))
            self.submit_step(project_id, ep, "a4_candidates", StepSubmit(decision="continue"))
            self.submit_step(project_id, ep, "a5_finalize", StepSubmit(candidate_id="c1"))
        else:
            raw = (
                "很多人把长文章直接念完，观众三秒就滑走。"
                "真正能留下的口播，是把文章压成一个痛点、一个转折、一个行动。"
                "不要同时讲十个观点。先承认读者的难处，再给一个今晚就能做的动作。"
            )
            self.submit_step(project_id, ep, "b1_raw", StepSubmit(raw_text=raw))
            self.submit_step(project_id, ep, "b2_analyze", StepSubmit(decision="approve"))
            self.submit_step(project_id, ep, "b3_skipped", StepSubmit(ack_defect=True))
            self.submit_step(project_id, ep, "b4_titles", StepSubmit(title_id="t1"))
            self.submit_step(project_id, ep, "b5_framework_draft", StepSubmit(framework="痛点共鸣式"))
            self.submit_step(project_id, ep, "b6_finalize", StepSubmit(decision="approve"))
        return self.confirm_g1(project_id, ep, {"decision": "pass", "actor": actor, "notes": "fixture demo"})

    def envelope(
        self,
        project_id: str,
        ep: str,
        *,
        view: str = "full",
        include_session: bool = True,
    ) -> dict[str, Any]:
        project_id = validate_project_id(project_id or DEFAULT_PROJECT_ID)
        ep = validate_ep(ep)
        session = self._load_session(ep)
        artifact = self._artifact_view(ep)
        locked = bool((artifact or {}).get("frontmatter", {}).get("locked"))
        out: dict[str, Any] = {
            "ok": True,
            "episode_id": ep,
            "node": "N1",
            "project_id": project_id,
            "next_edges": next_edges_after_g1() if locked else [],
            "auto_advanced": False,
        }
        if include_session and session:
            out["session"] = self._session_public(session, locked=locked)
        elif include_session:
            out["session"] = {
                "episode_id": ep,
                "status": "idle",
                "current_step": None,
                "path": None,
            }
        if view in {"full", "artifact"}:
            out["artifact"] = artifact
        if view == "session":
            out.pop("artifact", None)
        return out

    def _session_public(self, session: dict[str, Any], *, locked: bool) -> dict[str, Any]:
        path = session["path"]
        current = session.get("current_step")
        spec = step_spec(current) if current and session.get("status") == "active" else None
        if spec and spec.get("kind") in {"choose_framework", "reconstruct"}:
            spec = {**spec, "frameworks": frameworks_for(path)}
        return {
            "session_id": session.get("session_id"),
            "episode_id": session.get("episode_id"),
            "path": path,
            "status": "locked" if locked else session.get("status"),
            "step": current,
            "current_step": current,
            "completed_steps": session.get("completed_steps") or [],
            "skipped_steps": ["3", "b3_skipped"] if path == "B" else [],
            "defects": session.get("defects") or [],
            "defect_note": session.get("defect_note"),
            "provider": session.get("provider"),
            "version": session.get("version") or 1,
            "raw_ref": session.get("raw_ref"),
            "extract": session.get("extract"),
            "frameworks_selected": session.get("frameworks_selected") or [],
            "titles": session.get("titles") or [],
            "candidates": session.get("candidates") or [],
            "draft": session.get("draft"),
            "artifact_rel": session.get("artifact_rel") or "N1-口播定稿.md",
            "actor_last": session.get("actor_last") or "",
            "updated_at": session.get("updated_at"),
            "step_spec": spec,
            "char_limit": CHAR_LIMIT[path],
            "prompt_source": session.get("prompt_source") or prompt_relpath(path),
            "blocked_reason": None,
            "source_gap_ack": "missing_step_3" in (session.get("defects") or [])
            and "b3_skipped" in (session.get("completed_steps") or []),
        }

    def _generate(self, session: dict[str, Any], step: str, kind: str, payload: StepSubmit):
        path = session["path"]
        prompt_file = self.settings.prompt_path(path)
        provider = get_provider(session.get("provider") or "fixture", self.settings)
        title = None
        if payload.title:
            title = payload.title
        elif payload.title_id and session.get("titles"):
            hit = next((t for t in session["titles"] if t["id"] == payload.title_id), None)
            title = hit["title"] if hit else None
        edits = payload.edits or {}
        return provider.generate(
            GenerateRequest(
                path=path,
                step=step,
                kind=kind,
                raw=session.get("raw") or payload.raw_text or "",
                notes=payload.notes or "",
                extract=session.get("extract"),
                frameworks=session.get("frameworks_selected") or [],
                titles=session.get("titles") or [],
                candidates=session.get("candidates") or [],
                candidate_id=payload.candidate_id,
                title=edits.get("title") or title,
                prompt_text=prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else "",
            )
        )

    def _complete_step(self, session: dict[str, Any], step: str) -> None:
        completed = list(session.get("completed_steps") or [])
        if step not in completed:
            completed.append(step)
        session["completed_steps"] = completed
        nxt = next_step(session["path"], completed)
        session["current_step"] = nxt
        session["updated_at"] = utcnow()

    def _write_draft_file(
        self,
        project_id: str,
        ep: str,
        session: dict[str, Any],
        *,
        locked: bool,
        confirmed_by: str,
        keep_version: bool = False,
    ) -> None:
        draft = session.get("draft") or {}
        markdown = compose_markdown(draft.get("title") or "", draft.get("body") or "")
        art = self.store.artifact_path(ep)
        version = 1
        if art.is_file():
            meta, _ = read_n1_markdown(art)
            version = int(meta.get("version") or 1)
            if keep_version:
                version = int(meta.get("version") or 1)
        chars = draft_chars(draft.get("title") or "", draft.get("body") or "")
        fw = draft.get("framework") or (session.get("frameworks_selected") or [""])[0]
        meta = {
            "node": "N1",
            "path": session["path"],
            "framework": fw,
            "chars": chars,
            "source_ref": session.get("raw_ref") or ".aiv/n1-raw.txt",
            "confirmed_by": confirmed_by,
            "locked": locked,
            "version": version,
            "defects": session.get("defects") or [],
            "provider": session.get("provider") or "fixture",
        }
        write_n1_markdown(art, meta, markdown)

    def _artifact_view(self, ep: str) -> dict[str, Any] | None:
        art = self.store.artifact_path(ep)
        if not art.is_file():
            return None
        meta, md = read_n1_markdown(art)
        title, body = parse_title_body(md)
        return {
            "rel_path": self.store.rel_artifact(ep),
            "abs_path": str(art),
            "exists": True,
            "frontmatter": {
                k: meta.get(k)
                for k in ("node", "path", "framework", "chars", "source_ref", "confirmed_by", "locked", "version", "defects", "provider")
            },
            "title": title,
            "body": body,
            "markdown": md,
            "chars": meta.get("chars") if meta.get("chars") is not None else draft_chars(title, body),
        }

    def _artifact_locked(self, ep: str) -> bool:
        art = self.store.artifact_path(ep)
        if not art.is_file():
            return False
        meta, _ = read_n1_markdown(art)
        return bool(meta.get("locked"))

    def _reject_g1(
        self,
        project_id: str,
        ep: str,
        session: dict[str, Any],
        actor: str,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        path = session["path"]
        target = raw.get("rollback_to") or raw.get("reject_to") or last_step(path)
        if target not in steps_for(path):
            target = last_step(path)
        session["completed_steps"] = [s for s in session.get("completed_steps") or [] if s != target and steps_for(path).index(s) < steps_for(path).index(target)]
        session["current_step"] = target
        session["status"] = "active"
        session["actor_last"] = actor
        session["updated_at"] = utcnow()
        if session.get("draft"):
            self._write_draft_file(project_id, ep, session, locked=False, confirmed_by="")
        self._save_session(ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="in_progress",
            n1="n1_pending",
            gates={"g1": "rejected"},
            gate_log={"gate": "g1", "decision": "reject", "actor": actor, "rollback_to": target, "at": utcnow()},
        )
        return self.envelope(project_id, ep)

    def _load_session(self, ep: str) -> dict[str, Any] | None:
        return self.store.read_json(self.store.session_path(ep))

    def _require_session(self, ep: str) -> dict[str, Any]:
        session = self._load_session(ep)
        if not session:
            raise AppError(404, "not_found", "no N1 session; POST n1/sessions first")
        return session

    def _save_session(self, ep: str, session: dict[str, Any]) -> None:
        self.store.write_json(self.store.session_path(ep), session)

    def _patch_episode(
        self,
        project_id: str,
        ep: str,
        *,
        status: str | None = None,
        n1: str | None = None,
        gates: dict | None = None,
        blocked_decisions: list[str] | None = None,
        gate_log: dict | None = None,
    ) -> None:
        path = self.store.episode_meta_path(ep)
        meta = self.store.read_json(path) or {"project_id": project_id, "episode": ep, "status": "draft", "nodes": {}, "gates": {}}
        if status:
            meta["status"] = status
        if n1:
            meta.setdefault("nodes", {})["n1"] = n1
        if gates:
            meta.setdefault("gates", {}).update(gates)
        if blocked_decisions is not None:
            meta["blocked_decisions"] = blocked_decisions
        if gate_log:
            meta.setdefault("gate_log", []).append(gate_log)
        meta["updated_at"] = utcnow()
        self.store.write_json(path, meta)
