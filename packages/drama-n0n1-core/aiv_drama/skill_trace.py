"""018b skill-trace: whitelist, path sanitize, short excerpt + hash.

Empty-injection scheme (locked · distinguishable from 漏记):

- ``recorded`` — ``skill_trace="recorded"``, ``skill_paths`` nonempty,
  ``skill_trace_reason`` is null.
- ``none`` — ``skill_trace="none"``, ``skill_paths=[]``,
  ``skill_trace_reason`` required (e.g. ``fixture_no_skill``,
  ``whitelist_empty``, ``not_generated``, ``manual_write``, ``reset``,
  ``custom_no_skill_injection``, ``whitelist_unavailable``,
  ``provider_skipped``).
- Missing ``skill_trace`` on a generate/GET payload is 漏记 (contract debt),
  not the same as explicit ``none``.

Do **not** use a ``skill_paths: ["none"]`` sentinel.

Hash lock: sha256 hex of the **full file UTF-8 bytes** when
``repo_root / path`` is readable; otherwise sha256 of the excerpt UTF-8 bytes.

Observability prefers a **short excerpt + hash** (``text`` default 480 chars,
hard cap 2000 Unicode chars per path). ``chars`` is the full-file length;
``start``/``end`` mark the excerpt span. Volume-limited callers may set
``text=null`` and keep hash+span.

Unauthorized host absolute paths (``/Users/``, ``/home/``, ``~``, Windows
drive) are remapped to repo-relative / ``mirror:<name>/…`` when possible,
otherwise **dropped** — never written to API, projection, or dogfood export.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

SKILL_EXCERPT_TEXT_LIMIT = 2000
SKILL_EXCERPT_SHORT_LIMIT = 480
SKILL_EXCERPT_JOIN_LIMIT = 2000

STORYBOARD_KEEP_PATHS = (
    ".skill/writing/动态漫-转分镜/SKILL.md",
    ".skill/writing/动态漫-转分镜/动态漫剧本转分镜生成指南.md",
)
SEEDANCE_INJECT_PREFIX = ".skill/generation/Seedance2.0-分镜/"

DEFAULT_REPO_RELATIVE_ALLOW = (
    ".skill/writing/女频短剧编剧/",
    ".skill/writing/男频短剧编剧/",
    ".skill/writing/动态漫-转分镜/",
)
DEFAULT_INJECT_BLACKLIST = (SEEDANCE_INJECT_PREFIX,)
DEFAULT_DENY_ABSOLUTE = ("/Users/", "/home/")

HOST_ABS_RE = re.compile(
    r"(?:^|[\s\"'`=])(?:/Users/|/home/|~/)|(?:^|[\s\"'`=])[A-Za-z]:[\\/]|\\\\Users\\\\"
)
WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class MirrorSpec:
    name: str
    prefix: str
    physical_root: Path | None = None


@dataclass(frozen=True)
class SkillWhitelist:
    repo_relative_allow: tuple[str, ...]
    inject_blacklist: tuple[str, ...]
    deny_absolute_prefixes: tuple[str, ...]
    mirrors: tuple[MirrorSpec, ...]
    source: str

    def allows(self, rel: str) -> bool:
        return any(rel == p.rstrip("/") or rel.startswith(p) for p in self.repo_relative_allow)

    def blacklisted(self, rel: str) -> bool:
        return any(rel == p.rstrip("/") or rel.startswith(p) or p in rel for p in self.inject_blacklist)


def default_whitelist() -> SkillWhitelist:
    return SkillWhitelist(
        repo_relative_allow=DEFAULT_REPO_RELATIVE_ALLOW,
        inject_blacklist=DEFAULT_INJECT_BLACKLIST,
        deny_absolute_prefixes=DEFAULT_DENY_ABSOLUTE,
        mirrors=(MirrorSpec(name="local-learn", prefix="mirror:local-learn/"),),
        source="default",
    )


def _as_tuple(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(x) for x in raw if str(x).strip())


def whitelist_from_payload(payload: Mapping[str, Any], *, source: str) -> SkillWhitelist:
    mirrors: list[MirrorSpec] = []
    for item in payload.get("authorized_mirrors") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        prefix = str(item.get("relative_export_prefix") or (f"mirror:{name}/" if name else "")).strip()
        root_raw = item.get("physical_root")
        root = Path(str(root_raw)).resolve() if root_raw else None
        if name and prefix:
            mirrors.append(MirrorSpec(name=name, prefix=prefix, physical_root=root))
    allow = _as_tuple(payload.get("repo_relative_allow")) or DEFAULT_REPO_RELATIVE_ALLOW
    extra = os.environ.get("AIV_SKILL_WHITELIST_PATHS", "")
    if extra.strip():
        allow = allow + tuple(p.strip() for p in extra.split(",") if p.strip())
    deny = _as_tuple(payload.get("deny_absolute_prefixes")) or DEFAULT_DENY_ABSOLUTE
    deny_extra = _as_tuple(payload.get("inject_blacklist"))
    blacklist = deny_extra or DEFAULT_INJECT_BLACKLIST
    return SkillWhitelist(
        repo_relative_allow=allow,
        inject_blacklist=blacklist,
        deny_absolute_prefixes=deny,
        mirrors=tuple(mirrors) or (MirrorSpec(name="local-learn", prefix="mirror:local-learn/"),),
        source=source,
    )


def load_whitelist(repo_root: Path) -> SkillWhitelist:
    """Load LEARN/ENG whitelist file; fall back to KEEP prefixes. Never invent dirty paths."""
    env = (os.environ.get("AIV_SKILL_WHITELIST_FILE") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path(repo_root) / "fixtures" / "drama" / "skill-whitelist.json")
    for path in candidates:
        try:
            if not path.is_file():
                if env and path == Path(env):
                    return SkillWhitelist(
                        repo_relative_allow=(),
                        inject_blacklist=DEFAULT_INJECT_BLACKLIST,
                        deny_absolute_prefixes=DEFAULT_DENY_ABSOLUTE,
                        mirrors=(),
                        source="unavailable",
                    )
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            return whitelist_from_payload(payload, source=str(path))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            if env and path == Path(env):
                return SkillWhitelist(
                    repo_relative_allow=(),
                    inject_blacklist=DEFAULT_INJECT_BLACKLIST,
                    deny_absolute_prefixes=DEFAULT_DENY_ABSOLUTE,
                    mirrors=(),
                    source="unavailable",
                )
            continue
    return default_whitelist()


def looks_like_host_abs(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if raw.startswith("~") or raw.startswith("/Users/") or raw.startswith("/home/"):
        return True
    if WIN_ABS_RE.match(raw) or raw.startswith("\\\\Users\\\\") or raw.startswith("\\Users\\"):
        return True
    return bool(HOST_ABS_RE.search(raw))


def contains_host_abs(blob: str) -> bool:
    return bool(HOST_ABS_RE.search(blob or ""))


def _posix(text: str) -> str:
    return text.replace("\\", "/").strip()


def sanitize_export_path(
    raw: str,
    *,
    repo_root: Path,
    whitelist: SkillWhitelist | None = None,
) -> str | None:
    """Return a safe repo-relative or mirror-tagged path, or None to drop."""
    wl = whitelist or load_whitelist(repo_root)
    text = _posix(str(raw or ""))
    if not text:
        return None
    root = Path(repo_root).resolve()

    if text.startswith("mirror:"):
        if ".." in text.split("/"):
            return None
        return text

    candidate: Path | None = None
    if text.startswith("/") or WIN_ABS_RE.match(text):
        candidate = Path(text)
    else:
        if text.startswith("~/"):
            return None
        if ".." in Path(text).parts:
            return None
        rel = text[2:] if text.startswith("./") else text
        if wl.blacklisted(rel) or not wl.allows(rel):
            return None
        if looks_like_host_abs(rel):
            return None
        return rel

    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None

    try:
        rel_path = resolved.relative_to(root)
        rel = rel_path.as_posix()
        if ".." in rel_path.parts:
            return None
        if wl.blacklisted(rel) or not wl.allows(rel):
            return None
        return rel
    except ValueError:
        pass

    for mirror in wl.mirrors:
        if not mirror.physical_root:
            continue
        try:
            rel_path = resolved.relative_to(mirror.physical_root.resolve())
        except ValueError:
            continue
        if ".." in rel_path.parts:
            return None
        return f"{mirror.prefix}{rel_path.as_posix()}"
    return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_excerpt(
    rel_path: str,
    repo_root: Path,
    *,
    text_limit: int = SKILL_EXCERPT_SHORT_LIMIT,
) -> dict[str, Any]:
    cap = max(0, min(int(text_limit), SKILL_EXCERPT_TEXT_LIMIT))
    full = Path(repo_root) / rel_path
    if full.is_file():
        raw = full.read_text(encoding="utf-8")
        digest = sha256_text(raw)
        snippet = raw[:cap]
        return {
            "path": rel_path,
            "chars": len(raw),
            "hash": digest,
            "start": 0,
            "end": len(snippet),
            "text": snippet or None,
        }
    digest = sha256_text("")
    return {
        "path": rel_path,
        "chars": 0,
        "hash": digest,
        "start": 0,
        "end": 0,
        "text": None,
    }


def _join_excerpt_text(excerpts: Iterable[Mapping[str, Any]]) -> str | None:
    chunks = [str(e.get("text")) for e in excerpts if e.get("text")]
    if not chunks:
        return None
    joined = "\n---\n".join(chunks)
    if len(joined) > SKILL_EXCERPT_JOIN_LIMIT:
        joined = joined[:SKILL_EXCERPT_JOIN_LIMIT]
    return joined


def none_skill_trace(reason: str) -> dict[str, Any]:
    return {
        "skill_paths": [],
        "skill_trace": "none",
        "skill_trace_reason": reason,
        "skill_excerpt": None,
        "excerpts": [],
    }


def recorded_skill_trace(paths: list[str], excerpts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "skill_paths": list(paths),
        "skill_trace": "recorded",
        "skill_trace_reason": None,
        "skill_excerpt": _join_excerpt_text(excerpts),
        "excerpts": excerpts,
    }


def merge_skill_trace(target: dict[str, Any], trace: Mapping[str, Any]) -> None:
    target["skill_paths"] = list(trace.get("skill_paths") or [])
    target["skill_trace"] = trace.get("skill_trace") or "none"
    target["skill_trace_reason"] = trace.get("skill_trace_reason")
    target["skill_excerpt"] = trace.get("skill_excerpt")
    target["excerpts"] = list(trace.get("excerpts") or [])


def record_skill_paths(
    raw_paths: Iterable[str],
    *,
    repo_root: Path,
    whitelist: SkillWhitelist | None = None,
    empty_reason: str = "fixture_no_skill",
    text_limit: int = SKILL_EXCERPT_SHORT_LIMIT,
) -> dict[str, Any]:
    wl = whitelist if whitelist is not None else load_whitelist(repo_root)
    if wl.source == "unavailable":
        return none_skill_trace("whitelist_unavailable")
    clean: list[str] = []
    seen: set[str] = set()
    for raw in raw_paths:
        safe = sanitize_export_path(str(raw), repo_root=repo_root, whitelist=wl)
        if not safe or safe in seen:
            continue
        seen.add(safe)
        clean.append(safe)
    if not clean:
        return none_skill_trace(empty_reason)
    excerpts = [build_excerpt(p, repo_root, text_limit=text_limit) for p in clean]
    return recorded_skill_trace(clean, excerpts)


def excerpt_projection(
    excerpts: Iterable[Mapping[str, Any]],
    *,
    include_text: bool = True,
) -> list[dict[str, Any]]:
    """Disk/API-safe excerpt rows: always path+chars+hash+span; optional short text."""
    out: list[dict[str, Any]] = []
    for raw in excerpts or []:
        text = raw.get("text") if include_text else None
        if isinstance(text, str) and len(text) > SKILL_EXCERPT_TEXT_LIMIT:
            text = text[:SKILL_EXCERPT_TEXT_LIMIT]
        row = {
            "path": raw.get("path"),
            "chars": raw.get("chars") if raw.get("chars") is not None else 0,
            "hash": raw.get("hash"),
            "start": raw.get("start"),
            "end": raw.get("end"),
        }
        if include_text:
            row["text"] = text
        out.append(row)
    return out


def flag_used_from_outline(outline: Mapping[str, Any] | None, source_skills: Iterable[str] | None = None) -> bool:
    skills = list(source_skills or [])
    if outline:
        skills = skills or list(outline.get("source_skills") or [])
        skills = skills or list(outline.get("skill_paths") or [])
    return bool(skills) or (outline or {}).get("skill_trace") == "recorded"


def flag_used_from_storyboard(storyboard: Mapping[str, Any] | None) -> bool:
    skill = (storyboard or {}).get("storyboard_skill")
    return skill in {"borrowed_dongman", "custom"}


def assert_skill_consistency(
    payload: Mapping[str, Any],
    *,
    flag_used: bool,
) -> None:
    """C1–C3. Raises AssertionError on contract debt."""
    paths = list(payload.get("skill_paths") or [])
    trace = payload.get("skill_trace")
    reason = payload.get("skill_trace_reason")
    if paths:
        if not flag_used:
            raise AssertionError("C1: nonempty skill_paths requires used-skill flag")
        if trace != "recorded":
            raise AssertionError("nonempty skill_paths requires skill_trace=recorded")
    if flag_used and not paths:
        if trace != "none" or not reason:
            raise AssertionError("C2/C3: used flag with empty paths requires skill_trace=none + reason")
    if trace == "none":
        if paths:
            raise AssertionError("skill_trace=none forbids nonempty skill_paths")
        if not reason:
            raise AssertionError("skill_trace=none requires skill_trace_reason")
    if trace == "recorded" and not paths:
        raise AssertionError("skill_trace=recorded requires nonempty skill_paths")


def assert_no_host_abs_in_text(text: str, *, label: str = "payload") -> None:
    if contains_host_abs(text):
        raise RuntimeError(f"unauthorized host absolute path leaked into {label}")


def assert_no_host_abs_paths(episode_dir: Path) -> None:
    if not episode_dir.is_dir():
        return
    for path in episode_dir.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_text(encoding="utf-8", errors="ignore")
        assert_no_host_abs_in_text(blob, label=str(path))
