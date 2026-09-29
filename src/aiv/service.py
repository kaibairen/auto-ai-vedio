from __future__ import annotations

import uuid
from typing import Any

from aiv.artifact import (
    compose_markdown,
    parse_title_body,
    read_n1_markdown,
    sha256_file,
    write_n1_markdown,
)
from aiv.config import Settings
from aiv.curriculum import (
    PATH_B_SKIP_REASON,
    allowed_steps,
    char_limit,
    frameworks_for,
    is_last_step,
    is_skipped,
    next_step_after,
    prompt_relpath,
    resolve_frameworks,
    skipped_steps,
    step_spec,
    steps_for,
)
from aiv.errors import AppError
from aiv.models import (
    DraftPayload,
    GateConfirm,
    SessionCreate,
    SubmitPayload,
    next_edges_after_g1,
)
from aiv.providers import get_provider
from aiv.providers.base import GenerateRequest
from aiv.store import Store, utcnow
from aiv.validation import (
    count_chars,
    reject_force_pass,
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

    # --- episode ---

    def create_episode(self, project_id: str, ep: str = "EP01", title: str | None = None) -> dict[str, Any]:
        project_id = validate_project_id(project_id)
        ep = validate_ep(ep)
        path = self.store.episode_dir(project_id, ep)
        path.mkdir(parents=True, exist_ok=True)
        self.store.aiv_dir(project_id, ep).mkdir(parents=True, exist_ok=True)
        existing = self.store.read_json(self.store.episode_meta_path(project_id, ep))
        if existing:
            return self.get_episode(project_id, ep)
        meta = {
            "project_id": project_id,
            "episode": ep,
            "title": title or "",
            "status": "draft",
            "pipeline_profile": None,
            "gates": {"g1": "idle"},
            "n1": {"state": "idle", "locked": False, "version": 0, "node_run": "idle"},
            "blocked_decisions": [],
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        self.store.write_json(self.store.episode_meta_path(project_id, ep), meta)
        return self.get_episode(project_id, ep)

    def get_episode(self, project_id: str, ep: str) -> dict[str, Any]:
        project_id = validate_project_id(project_id)
        ep = validate_ep(ep)
        meta = self.store.read_json(self.store.episode_meta_path(project_id, ep))
        if not meta:
            raise AppError(404, "episode_not_found", "episode does not exist", ep=ep)
        view = self._n1_view(project_id, ep, consumer="authoring", missing_ok=True)
        meta = {**meta, "n1_summary": {
            "state": view.get("state"),
            "locked": view.get("locked"),
            "path": view.get("path"),
            "current_step": view.get("current_step"),
        }}
        if view.get("locked"):
            meta["next_edges"] = [e.model_dump() for e in next_edges_after_g1()]
        return meta

    # --- session ---

    def create_session(self, project_id: str, ep: str, body: SessionCreate) -> dict[str, Any]:
        project_id = validate_project_id(project_id)
        ep = validate_ep(ep)
        path = validate_path(body.path)
        self.create_episode(project_id, ep)
        existing = self._load_session(project_id, ep)
        if existing and existing.get("state") == "locked":
            raise AppError(
                409,
                "n1_locked",
                "N1 is locked; reject G1 or PUT a new draft (version++) before a new session",
                locked=True,
            )
        prompt = self.settings.prompt_path(path)
        if not prompt.is_file():
            raise AppError(500, "prompt_missing", "curriculum prompt not found", path=str(prompt))
        session = {
            "session_id": str(uuid.uuid4()),
            "project_id": project_id,
            "episode": ep,
            "path": path,
            "provider": body.provider,
            "state": "stepping",
            "current_step": 1,
            "completed_steps": [],
            "skipped_steps": skipped_steps(path),
            "raw": "",
            "source_ref": body.source_ref or ".aiv/raw.txt",
            "analysis": None,
            "frameworks": [],
            "titles": [],
            "candidates": [],
            "draft": None,
            "prompt_source": prompt_relpath(path),
            "prompt_sha256": sha256_file(prompt),
            "actor": validate_actor(body.actor),
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        self._save_session(project_id, ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="in_progress",
            gates={"g1": "idle"},
            n1={"state": "stepping", "locked": False, "version": 0, "node_run": "running", "path": path},
        )
        return self.get_n1(project_id, ep, consumer="authoring")

    def submit_step(self, project_id: str, ep: str, step: int, payload: SubmitPayload) -> dict[str, Any]:
        session = self._require_session(project_id, ep)
        if session.get("state") == "locked":
            raise AppError(409, "n1_locked", "cannot submit steps after G1 pass", locked=True)
        path = session["path"]
        if is_skipped(path, step):
            raise AppError(
                400,
                "source_defect_skip",
                PATH_B_SKIP_REASON,
                path=path,
                step=3,
                allowed_steps=allowed_steps(path, session["completed_steps"]),
            )
        allowed = allowed_steps(path, session["completed_steps"])
        if step not in allowed:
            raise AppError(
                409,
                "step_not_allowed",
                f"cannot submit step {step}; only {allowed} is open (no multi-step jump)",
                current_step=session.get("current_step"),
                allowed_steps=allowed,
                completed_steps=session.get("completed_steps"),
            )

        spec = step_spec(path, step)
        raw_text = (payload.text or "").strip()
        if spec.kind == "collect_raw":
            if not raw_text:
                raise AppError(400, "raw_required", "step 1 requires text")
            session["raw"] = raw_text
            self.store.raw_path(project_id, ep).write_text(raw_text, encoding="utf-8")
            session["source_ref"] = ".aiv/raw.txt"

        if spec.kind == "choose_framework":
            resolved = resolve_frameworks(path, payload.frameworks)
            if not resolved:
                raise AppError(400, "framework_required", "select at least one framework", accepts=spec.accepts)
            session["frameworks"] = [f.name for f in resolved]

        if spec.kind == "reconstruct":
            resolved = resolve_frameworks(path, payload.frameworks)
            if not resolved:
                # default recommend first non-defective
                rec = next((f for f in frameworks_for(path) if not f.defective), frameworks_for(path)[0])
                resolved = [rec]
            session["frameworks"] = [f.name for f in resolved]
            if payload.title:
                validate_title_b(payload.title)
            if payload.pick is not None and session.get("titles"):
                if payload.pick < 0 or payload.pick >= len(session["titles"]):
                    raise AppError(400, "bad_pick", "title pick out of range")

        if spec.kind == "optimize" and path == "A":
            if payload.pick is None:
                raise AppError(400, "pick_required", "step 5 requires pick of a candidate index")
            if not session.get("candidates"):
                raise AppError(400, "candidates_missing", "run step 4 before optimize")
            if payload.pick < 0 or payload.pick >= len(session["candidates"]):
                raise AppError(400, "bad_pick", "candidate pick out of range")

        prompt_file = self.settings.prompt_path(path)
        provider = get_provider(session.get("provider") or "fixture", self.settings)
        gen = provider.generate(
            GenerateRequest(
                path=path,
                step=step,
                kind=spec.kind,
                raw=session.get("raw") or raw_text,
                notes=payload.notes,
                analysis=session.get("analysis"),
                frameworks=session.get("frameworks") or payload.frameworks,
                titles=session.get("titles") or [],
                candidates=session.get("candidates") or [],
                pick=payload.pick,
                title=payload.title,
                prompt_text=prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else "",
                prompt_relpath=prompt_relpath(path),
            )
        )

        output: dict[str, Any] = {"kind": gen.kind, "message": gen.message}
        if gen.analysis:
            session["analysis"] = gen.analysis
            output["analysis"] = gen.analysis
        if gen.frameworks:
            session["frameworks"] = gen.frameworks
            output["frameworks"] = gen.frameworks
        if gen.titles:
            for t in gen.titles:
                validate_title_b(t)
            session["titles"] = gen.titles
            output["titles"] = gen.titles
        if gen.candidates:
            cleaned = []
            for i, c in enumerate(gen.candidates):
                body = c.get("body") or ""
                n = validate_char_limit(path, body, field=f"candidate[{i}].body")
                item = {
                    "index": i,
                    "title": c.get("title") or "",
                    "body": body,
                    "chars": n,
                    "framework": c.get("framework") or "",
                }
                cleaned.append(item)
            session["candidates"] = cleaned
            output["candidates"] = cleaned
        if gen.draft_body:
            n = validate_char_limit(path, gen.draft_body, field="draft.body")
            if path == "B" and gen.draft_title:
                validate_title_b(gen.draft_title)
            session["draft"] = {
                "title": gen.draft_title or "",
                "body": gen.draft_body,
                "chars": n,
                "framework": (gen.frameworks[0] if gen.frameworks else (session.get("frameworks") or [""])[0]),
            }
            output["draft"] = session["draft"]

        completed = list(session["completed_steps"])
        if step not in completed:
            completed.append(step)
        session["completed_steps"] = completed
        nxt = next_step_after(path, completed)
        session["current_step"] = nxt if nxt is not None else step
        session["updated_at"] = utcnow()

        if is_last_step(path, step) and session.get("draft"):
            self._write_draft_file(project_id, ep, session, locked=False, confirmed_by="")
            session["state"] = "awaiting_gate"
            self._patch_episode(
                project_id,
                ep,
                status="awaiting_gate",
                gates={"g1": "pending"},
                n1={
                    "state": "awaiting_gate",
                    "locked": False,
                    "version": self._artifact_version(project_id, ep),
                    "node_run": "needs_gate",
                    "path": path,
                },
            )
        else:
            session["state"] = "stepping"
            self._patch_episode(
                project_id,
                ep,
                status="in_progress",
                n1={"state": "stepping", "locked": False, "node_run": "running", "path": path},
            )

        self._save_session(project_id, ep, session)
        view = self.get_n1(project_id, ep, consumer="authoring")
        view["step_result"] = {
            "step": step,
            "kind": spec.kind,
            "output": output,
            "next_step": session["current_step"] if session["state"] == "stepping" else None,
        }
        return view

    def put_draft(self, project_id: str, ep: str, payload: DraftPayload) -> dict[str, Any]:
        session = self._require_session(project_id, ep)
        path = session["path"]
        if payload.markdown:
            title, body = parse_title_body(payload.markdown)
            markdown = payload.markdown
        else:
            title = (payload.title or (session.get("draft") or {}).get("title") or "").strip()
            body = (payload.body or "").strip()
            if not body:
                raise AppError(400, "empty_text", "draft body is required")
            markdown = compose_markdown(title, body)
        n = validate_char_limit(path, body if body else parse_title_body(markdown)[1], field="draft.body")
        if path == "B" and title:
            validate_title_b(title)
        fw = payload.framework or (session.get("frameworks") or [""])[0] or (session.get("draft") or {}).get("framework") or ""
        session["draft"] = {"title": title, "body": parse_title_body(markdown)[1], "chars": n, "framework": fw}
        was_locked = session.get("state") == "locked"
        session["state"] = "awaiting_gate"
        session["updated_at"] = utcnow()
        confirmed_by = ""
        self._write_draft_file(
            project_id,
            ep,
            session,
            locked=False,
            confirmed_by=confirmed_by,
            bump_if_locked=was_locked or self._artifact_locked(project_id, ep),
        )
        self._save_session(project_id, ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="awaiting_gate",
            gates={"g1": "pending"},
            n1={
                "state": "awaiting_gate",
                "locked": False,
                "version": self._artifact_version(project_id, ep),
                "node_run": "needs_gate",
                "path": path,
            },
        )
        return self.get_n1(project_id, ep, consumer="authoring")

    def get_n1(self, project_id: str, ep: str, *, consumer: str = "authoring") -> dict[str, Any]:
        return self._n1_view(project_id, ep, consumer=consumer, missing_ok=False)

    def confirm_g1(self, project_id: str, ep: str, body: GateConfirm, raw_payload: dict | None = None) -> dict[str, Any]:
        reject_force_pass(raw_payload if raw_payload is not None else body.model_dump())
        if body.decision not in {"pass", "reject"}:
            raise AppError(400, "invalid_decision", "decision must be pass or reject")
        actor = validate_actor(body.actor, required=True)
        session = self._require_session(project_id, ep)

        if body.decision == "reject":
            return self._reject_g1(project_id, ep, session, actor, body)

        # pass
        draft = session.get("draft")
        art = self.store.artifact_path(project_id, ep)
        if not draft and not art.is_file():
            raise AppError(400, "draft_missing", "write a draft (complete steps or PUT n1/draft) before G1 pass")
        if not draft and art.is_file():
            meta, md = read_n1_markdown(art)
            title, body_text = parse_title_body(md)
            draft = {
                "title": title,
                "body": body_text,
                "chars": meta.get("chars") or count_chars(body_text),
                "framework": meta.get("framework") or "",
            }
            session["draft"] = draft
        validate_char_limit(session["path"], draft["body"], field="draft.body")
        if session["path"] == "B" and draft.get("title"):
            validate_title_b(draft["title"])
        if body.artifact_version is not None:
            current_v = self._artifact_version(project_id, ep)
            if current_v and body.artifact_version != current_v:
                raise AppError(
                    409,
                    "version_conflict",
                    "artifact_version does not match current draft",
                    artifact_version=current_v,
                )
        session["state"] = "locked"
        session["updated_at"] = utcnow()
        self._write_draft_file(project_id, ep, session, locked=True, confirmed_by=actor, keep_version=True)
        self._save_session(project_id, ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="in_progress",
            gates={"g1": "passed"},
            n1={
                "state": "locked",
                "locked": True,
                "version": self._artifact_version(project_id, ep),
                "node_run": "passed",
                "path": session["path"],
                "confirmed_by": actor,
            },
            blocked_decisions=["D2"],
            gate_log_entry={
                "gate": "g1",
                "decision": "pass",
                "actor": actor,
                "notes": body.notes,
                "at": utcnow(),
            },
        )
        view = self.get_n1(project_id, ep, consumer="authoring")
        view["next_edges"] = [e.model_dump() for e in next_edges_after_g1()]
        view["auto_advanced"] = False
        return view

    def _reject_g1(
        self,
        project_id: str,
        ep: str,
        session: dict[str, Any],
        actor: str,
        body: GateConfirm,
    ) -> dict[str, Any]:
        path = session["path"]
        if body.rollback_to is not None:
            target = body.rollback_to
            if is_skipped(path, target):
                raise AppError(400, "source_defect_skip", PATH_B_SKIP_REASON, step=3)
            if target not in steps_for(path) and target != 1:
                raise AppError(400, "bad_rollback", "rollback_to is not a valid path step", step=target)
            session["completed_steps"] = [s for s in session.get("completed_steps", []) if s < target]
            session["current_step"] = target
            session["state"] = "stepping"
            if target <= 4:
                session["candidates"] = []
            if target <= (5 if path == "B" else 4):
                session["draft"] = None
        else:
            session["state"] = "awaiting_gate" if session.get("draft") else "stepping"

        was_locked = self._artifact_locked(project_id, ep)
        if session.get("draft"):
            self._write_draft_file(
                project_id,
                ep,
                session,
                locked=False,
                confirmed_by="",
                bump_if_locked=was_locked,
            )
        session["updated_at"] = utcnow()
        self._save_session(project_id, ep, session)
        self._patch_episode(
            project_id,
            ep,
            status="in_progress" if session["state"] == "stepping" else "awaiting_gate",
            gates={"g1": "rejected"},
            n1={
                "state": session["state"],
                "locked": False,
                "version": self._artifact_version(project_id, ep),
                "node_run": "running" if session["state"] == "stepping" else "needs_gate",
                "path": path,
            },
            gate_log_entry={
                "gate": "g1",
                "decision": "reject",
                "actor": actor,
                "notes": body.notes,
                "rollback_to": body.rollback_to,
                "at": utcnow(),
            },
        )
        return self.get_n1(project_id, ep, consumer="authoring")

    def demo(self, project_id: str, ep: str, path: str, actor: str = "bot:demo") -> dict[str, Any]:
        """One-shot fixture walk + G1 pass. Used by CLI and docs."""
        path = validate_path(path)
        self.create_episode(project_id, ep)
        self.create_session(project_id, ep, SessionCreate(path=path, provider="fixture", actor=actor))
        if path == "A":
            raw = (
                "就是那个咖啡渣别扔啊，我妈说能除臭还能当肥料，"
                "我以前一直当垃圾倒了，后来才知道还能去油污，真的很神奇，"
                "你们可以试试，记得评论区说说你们还有啥妙用。"
            )
            self.submit_step(project_id, ep, 1, SubmitPayload(text=raw))
            self.submit_step(project_id, ep, 2, SubmitPayload(confirm=True))
            self.submit_step(project_id, ep, 3, SubmitPayload(frameworks=["惊喜揭秘型"]))
            self.submit_step(project_id, ep, 4, SubmitPayload(confirm=True))
            self.submit_step(project_id, ep, 5, SubmitPayload(pick=0))
        else:
            raw = (
                "很多人把长文章直接念完，观众三秒就滑走。"
                "真正能留下的口播，是把文章压成一个痛点、一个转折、一个行动。"
                "不要同时讲十个观点。先承认读者的难处，再给一个今晚就能做的动作，"
                "最后只留一个评论区问题。这样六百字的专栏也能变成一分钟口播。"
            )
            self.submit_step(project_id, ep, 1, SubmitPayload(text=raw))
            self.submit_step(project_id, ep, 2, SubmitPayload(confirm=True))
            self.submit_step(project_id, ep, 4, SubmitPayload(confirm=True))
            self.submit_step(project_id, ep, 5, SubmitPayload(frameworks=["痛点共鸣式"], pick=0))
            self.submit_step(project_id, ep, 6, SubmitPayload(notes="钩子再短一点"))
        return self.confirm_g1(
            project_id,
            ep,
            GateConfirm(decision="pass", actor=actor, notes="fixture demo"),
            raw_payload={"decision": "pass", "actor": actor, "notes": "fixture demo"},
        )

    # --- internals ---

    def _n1_view(
        self,
        project_id: str,
        ep: str,
        *,
        consumer: str,
        missing_ok: bool,
    ) -> dict[str, Any]:
        project_id = validate_project_id(project_id)
        ep = validate_ep(ep)
        session = self._load_session(project_id, ep)
        art = self.store.artifact_path(project_id, ep)
        artifact = None
        locked = False
        if art.is_file():
            meta, md = read_n1_markdown(art)
            title, body = parse_title_body(md)
            locked = bool(meta.get("locked"))
            artifact = {
                "rel_path": self.store.rel_artifact(ep),
                "abs_path": str(art),
                "exists": True,
                "frontmatter": {k: meta.get(k) for k in (
                    "node", "path", "framework", "chars", "source_ref", "confirmed_by", "locked", "version"
                )},
                "title": title,
                "body": body,
                "markdown": md,
                "chars": meta.get("chars") if meta.get("chars") is not None else count_chars(body),
            }
        if consumer == "downstream":
            if not art.is_file() or not locked:
                raise AppError(
                    409,
                    "n1_not_locked",
                    "downstream read of N1 定稿 requires locked=true (G1 pass)",
                    locked=False,
                    version=(artifact or {}).get("frontmatter", {}).get("version") if artifact else 0,
                )
            return {
                "consumer": "downstream",
                "locked": True,
                "artifact": artifact,
                "next_edges": [e.model_dump() for e in next_edges_after_g1()],
            }
        if session is None:
            if missing_ok:
                return {
                    "state": "idle",
                    "locked": locked,
                    "path": None,
                    "current_step": None,
                    "allowed_steps": [],
                    "artifact": artifact,
                }
            raise AppError(404, "session_not_found", "no N1 session; POST n1/sessions first", ep=ep)

        path = session["path"]
        current = session.get("current_step")
        spec = None
        if session.get("state") == "stepping" and current:
            spec = step_spec(path, current).model_dump()
        view: dict[str, Any] = {
            "session_id": session["session_id"],
            "project_id": project_id,
            "episode": ep,
            "path": path,
            "provider": session.get("provider"),
            "state": session.get("state"),
            "locked": locked or session.get("state") == "locked",
            "current_step": current,
            "allowed_steps": allowed_steps(path, session.get("completed_steps") or [], locked=session.get("state") == "locked"),
            "completed_steps": session.get("completed_steps") or [],
            "skipped_steps": session.get("skipped_steps") or skipped_steps(path),
            "step_spec": spec,
            "analysis": session.get("analysis"),
            "frameworks": session.get("frameworks") or [],
            "titles": session.get("titles") or [],
            "candidates": session.get("candidates") or [],
            "draft": session.get("draft"),
            "artifact": artifact,
            "gate": {
                "id": "g1",
                "name": "N1 口播确认",
                "status": "passed"
                if session.get("state") == "locked"
                else ("pending" if session.get("state") == "awaiting_gate" else "idle"),
                "confirm_path": f"/api/v0/projects/{project_id}/episodes/{ep}/gates/g1/confirm",
            },
            "prompt_source": session.get("prompt_source") or prompt_relpath(path),
            "char_limit": char_limit(path),
            "next_edges": [e.model_dump() for e in next_edges_after_g1()]
            if session.get("state") == "locked"
            else [],
            "auto_advanced": False,
        }
        return view

    def _write_draft_file(
        self,
        project_id: str,
        ep: str,
        session: dict[str, Any],
        *,
        locked: bool,
        confirmed_by: str,
        bump_if_locked: bool = False,
        keep_version: bool = False,
    ) -> None:
        draft = session.get("draft") or {}
        title = draft.get("title") or ""
        body = draft.get("body") or ""
        markdown = compose_markdown(title, body)
        art = self.store.artifact_path(project_id, ep)
        version = 1
        if art.is_file():
            meta, _ = read_n1_markdown(art)
            version = int(meta.get("version") or 1)
            if bump_if_locked and meta.get("locked"):
                version += 1
            elif not keep_version and not meta.get("locked"):
                version = int(meta.get("version") or 1)
        chars = count_chars(body)
        fw = draft.get("framework") or (session.get("frameworks") or [""])[0]
        meta = {
            "node": "N1",
            "path": session["path"],
            "framework": fw,
            "chars": chars,
            "source_ref": session.get("source_ref") or ".aiv/raw.txt",
            "confirmed_by": confirmed_by,
            "locked": locked,
            "version": version,
        }
        write_n1_markdown(art, meta, markdown)

    def _artifact_version(self, project_id: str, ep: str) -> int:
        art = self.store.artifact_path(project_id, ep)
        if not art.is_file():
            return 0
        meta, _ = read_n1_markdown(art)
        return int(meta.get("version") or 0)

    def _artifact_locked(self, project_id: str, ep: str) -> bool:
        art = self.store.artifact_path(project_id, ep)
        if not art.is_file():
            return False
        meta, _ = read_n1_markdown(art)
        return bool(meta.get("locked"))

    def _load_session(self, project_id: str, ep: str) -> dict[str, Any] | None:
        return self.store.read_json(self.store.session_path(project_id, ep))

    def _require_session(self, project_id: str, ep: str) -> dict[str, Any]:
        session = self._load_session(project_id, ep)
        if not session:
            raise AppError(404, "session_not_found", "no N1 session; POST n1/sessions first")
        return session

    def _save_session(self, project_id: str, ep: str, session: dict[str, Any]) -> None:
        self.store.write_json(self.store.session_path(project_id, ep), session)

    def _patch_episode(
        self,
        project_id: str,
        ep: str,
        *,
        status: str | None = None,
        gates: dict | None = None,
        n1: dict | None = None,
        blocked_decisions: list[str] | None = None,
        gate_log_entry: dict | None = None,
    ) -> None:
        path = self.store.episode_meta_path(project_id, ep)
        meta = self.store.read_json(path) or {
            "project_id": project_id,
            "episode": ep,
            "status": "draft",
            "gates": {},
            "n1": {},
        }
        if status:
            meta["status"] = status
        if gates:
            meta.setdefault("gates", {}).update(gates)
        if n1:
            meta.setdefault("n1", {}).update(n1)
        if blocked_decisions is not None:
            meta["blocked_decisions"] = blocked_decisions
        if gate_log_entry:
            meta.setdefault("gate_log", []).append(gate_log_entry)
        meta["updated_at"] = utcnow()
        self.store.write_json(path, meta)
