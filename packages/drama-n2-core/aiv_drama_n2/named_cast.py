"""O5-N named-cast scan + O1 auto-register helpers (BRIEF-AIV-017a).

Rule-first extraction: dialogue speaker prefixes and high-confidence action
proper names. Does not invent CHAR-* without writing cast. Isolated from koubo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Iterable

NAMED_CAST_PREFIX = "named_cast_"
NAMED_CAST_MISSING = "named_cast_missing"
NAMED_CAST_ROW_GAP = "named_cast_row_gap"
NAMED_CAST_UNREFERENCED = "named_cast_unreferenced"
NAMED_CAST_HEURISTIC = "named_cast_heuristic"
NAMED_CAST_AUTO_MERGED = "named_cast_auto_merged"
NAMED_CAST_GATE = "named_cast_gate"

NAMED_CAST_CHECK_MODES = ("off", "warn", "error")
DEFAULT_NAMED_CAST_CHECK = "warn"

AUTO_MERGE_ONE_LINE = "具名配角·自动挂表"
SIDECAR_ONE_LINE = "具名配角·侧车挂表"

CAST_CHANGED_HINT = {
    "code": "cast_changed",
    "message": "角色表已更新；G1b 仍锁定，大纲正文未改。请核对分镜 char_ids。",
}

G2_BLOCK_MESSAGE = "还有未入表的具名角色，无法通过分镜门审。"

SYSTEM_SPEAKERS = frozenset(
    {
        "系统音",
        "旁白",
        "广播",
        "弹窗字",
        "弹窗",
        "通缉令",
        "系统",
        "VO",
        "vo",
        "UI",
        "字幕",
        "画外音",
        "内心独白",
        "内心",
        "OS",
        "os",
    }
)

GENERIC_REFS = frozenset(
    {
        "他",
        "她",
        "它",
        "他们",
        "她们",
        "两人",
        "二人",
        "众人",
        "大家",
        "有人",
        "某人",
        "路人",
        "群演",
        "群众",
        "我",
        "你",
        "您",
        "咱",
        "我们",
        "你们",
        "自己",
        "对方",
        "此人",
        "那人",
        "这人",
    }
)

GROUP_LABELS = frozenset(
    {
        "王子们",
        "两位王子",
        "俩王子",
        "两名王子",
        "公主们",
        "两位公主",
    }
)

BARE_TITLES = frozenset(
    {
        "王子",
        "公主",
        "大人",
        "将军",
        "小姐",
        "少爷",
        "老师",
        "老板",
        "女王",
        "国王",
        "殿下",
    }
)

# Speaker prefix: "CODEX王子：" / "林晚:" (fullwidth or halfwidth colon).
SPEAKER_RE = re.compile(r"(?:^|[\n；;。！？!?])\s*([^：:\n]{1,24})[：:]")

# High-confidence titled proper names (015: CODEX王子 / OPUS5.5王子).
PROPER_NAME_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9._-]*|[\u4e00-\u9fff]{1,12})"
    r"(?:王子|公主|女王|国王|将军|大人|小姐|少爷|殿下)"
)

GROUP_RE = re.compile("|".join(sorted((re.escape(g) for g in GROUP_LABELS), key=len, reverse=True)))

NONE_ID = "NONE"


def parse_named_cast_check(value: str | None) -> str:
    mode = (value or DEFAULT_NAMED_CAST_CHECK).strip().lower()
    return mode if mode in NAMED_CAST_CHECK_MODES else DEFAULT_NAMED_CAST_CHECK


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip())
    return " ".join(text.split())


def is_system_speaker(name: str) -> bool:
    key = normalize_name(name)
    if not key:
        return True
    if key in SYSTEM_SPEAKERS:
        return True
    lowered = key.lower()
    return lowered in {s.lower() for s in SYSTEM_SPEAKERS}


def is_generic_ref(name: str) -> bool:
    return normalize_name(name) in GENERIC_REFS


def is_group_label(name: str) -> bool:
    return normalize_name(name) in GROUP_LABELS


def is_registerable_name(name: str) -> bool:
    key = normalize_name(name)
    if not key or len(key) < 2:
        return False
    if is_system_speaker(key) or is_generic_ref(key) or is_group_label(key):
        return False
    if key in BARE_TITLES:
        return False
    if key.upper() in {NONE_ID, "CHAR", "SCENE"}:
        return False
    if key.startswith("CHAR-") or key.startswith("SCENE-"):
        return False
    return True


def extract_speakers(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for match in SPEAKER_RE.finditer(text or ""):
        name = normalize_name(match.group(1))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    return hits


def extract_proper_names(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for match in PROPER_NAME_RE.finditer(text or ""):
        name = normalize_name(match.group(0))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    return hits


def extract_group_labels(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for match in GROUP_RE.finditer(text or ""):
        name = normalize_name(match.group(0))
        if name and name not in seen:
            seen.add(name)
            hits.append(name)
    return hits


def names_mentioned(text: str, pool: Iterable[str]) -> list[str]:
    """Longest-first substring hits so CODEX王子 wins over 王子."""
    body = text or ""
    if not body:
        return []
    ordered = sorted({normalize_name(n) for n in pool if normalize_name(n)}, key=len, reverse=True)
    covered: list[tuple[int, int]] = []
    hits: list[str] = []
    for name in ordered:
        start = 0
        while True:
            idx = body.find(name, start)
            if idx < 0:
                break
            end = idx + len(name)
            if any(idx >= s and end <= e for s, e in covered):
                start = idx + 1
                continue
            covered.append((idx, end))
            if name not in hits:
                hits.append(name)
            start = end
    return hits


def expand_group(label: str, individual_names: Iterable[str]) -> list[str]:
    key = normalize_name(label)
    members: list[str] = []
    if "王子" in key:
        needle = "王子"
    elif "公主" in key:
        needle = "公主"
    else:
        return []
    for name in individual_names:
        norm = normalize_name(name)
        if not is_registerable_name(norm):
            continue
        if needle in norm and not is_group_label(norm):
            if norm not in members:
                members.append(norm)
    return members


def _cast_name_index(cast: dict[str, Any] | None) -> tuple[dict[str, str], dict[str, str]]:
    """Return (norm_name→id, id→norm_name) for characters."""
    by_name: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for row in (cast or {}).get("characters") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        cid = str(row["id"])
        name = normalize_name(str(row.get("name") or ""))
        if name and name not in by_name:
            by_name[name] = cid
        by_id[cid] = name
    return by_name, by_id


def _row_prose(row: dict[str, Any]) -> tuple[str, str, str]:
    action = str(row.get("action") or "")
    dialogue = str(row.get("dialogue") or "")
    return action, dialogue, f"{action}\n{dialogue}"


def collect_named_hits(
    rows: list[dict[str, Any]],
    *,
    cast: dict[str, Any] | None = None,
    outline_body: str | None = None,
) -> list[dict[str, Any]]:
    """High-confidence A-tier named on-screen roles per shot.

    Each hit: {name, shot_id, fields, kind: speaker|action|group, registerable: bool}
    """
    by_name, _ = _cast_name_index(cast)
    pool: set[str] = set(by_name)
    outline_names = extract_proper_names(outline_body or "")
    pool.update(outline_names)

    for row in rows:
        action, dialogue, _ = _row_prose(row)
        for name in extract_speakers(dialogue) + extract_speakers(action):
            if not is_system_speaker(name) and not is_generic_ref(name):
                pool.add(name)
        pool.update(extract_proper_names(action))
        pool.update(extract_proper_names(dialogue))

    hits: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        shot_id = row.get("shot_id") or f"S{idx + 1:02d}"
        action, dialogue, combined = _row_prose(row)
        fields: set[str] = set()
        names: dict[str, str] = {}

        for name in extract_speakers(dialogue):
            if is_system_speaker(name) or is_generic_ref(name):
                continue
            names[name] = "group" if is_group_label(name) else "speaker"
            fields.add("dialogue")
        for name in extract_speakers(action):
            if is_system_speaker(name) or is_generic_ref(name):
                continue
            names.setdefault(name, "group" if is_group_label(name) else "speaker")
            fields.add("action")

        for name in names_mentioned(combined, pool):
            if is_system_speaker(name) or is_generic_ref(name):
                continue
            if name in names:
                continue
            names[name] = "group" if is_group_label(name) else "action"
            if name in action:
                fields.add("action")
            if name in dialogue:
                fields.add("dialogue")

        for name in extract_group_labels(combined):
            names.setdefault(name, "group")
            if name in action:
                fields.add("action")
            if name in dialogue:
                fields.add("dialogue")

        field_list = sorted(fields) or ["action"]
        for name, kind in names.items():
            hits.append(
                {
                    "name": name,
                    "shot_id": shot_id,
                    "fields": field_list,
                    "kind": kind,
                    "registerable": is_registerable_name(name),
                }
            )
    return hits


def resolve_hit_names(name: str, individual_pool: Iterable[str]) -> list[str]:
    if is_group_label(name):
        return expand_group(name, individual_pool)
    if is_registerable_name(name):
        return [normalize_name(name)]
    return []


def blocking_named_cast_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in issues:
        code = str(item.get("code") or "")
        if not code.startswith(NAMED_CAST_PREFIX):
            continue
        if code == NAMED_CAST_AUTO_MERGED:
            continue
        out.append(item)
    return out


def named_cast_issue_severity(mode: str) -> str:
    return "error" if mode == "error" else "warn"


def collect_named_cast_issues(
    rows: list[dict[str, Any]],
    *,
    cast: dict[str, Any] | None,
    outline_body: str | None = None,
    named_cast_check: str | None = None,
    issue_fn: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    mode = parse_named_cast_check(named_cast_check)
    if mode == "off":
        return []
    severity = named_cast_issue_severity(mode)
    by_name, _ = _cast_name_index(cast)
    hits = collect_named_hits(rows, cast=cast, outline_body=outline_body)
    individual_pool = set(by_name) | {
        h["name"] for h in hits if h.get("registerable")
    }

    issues: list[dict[str, Any]] = []
    referenced_ids: set[str] = set()
    seen_missing: set[tuple[str, str]] = set()
    seen_gap: set[tuple[str, str]] = set()
    mentioned_unresolved: dict[str, list[str]] = {}

    for row in rows:
        for cid in row.get("char_ids") or []:
            if cid and cid != NONE_ID:
                referenced_ids.add(str(cid))

    for hit in hits:
        resolved = resolve_hit_names(hit["name"], individual_pool)
        shot_id = hit["shot_id"]
        row = next((r for r in rows if r.get("shot_id") == shot_id), None)
        char_ids = [str(c) for c in ((row or {}).get("char_ids") or []) if str(c) != NONE_ID]

        if not resolved:
            key = (shot_id, hit["name"])
            if key not in seen_missing:
                seen_missing.add(key)
                issues.append(
                    issue_fn(
                        severity,
                        NAMED_CAST_MISSING,
                        "named on-screen role is not in cast",
                        shot_id=shot_id,
                        field="dialogue" if "dialogue" in hit["fields"] else "action",
                        role_name=hit["name"],
                        source_fields=hit["fields"],
                        tier="A",
                    )
                )
            continue

        for name in resolved:
            cid = by_name.get(name)
            if not cid:
                key = (shot_id, name)
                if key not in seen_missing:
                    seen_missing.add(key)
                    issues.append(
                        issue_fn(
                            severity,
                            NAMED_CAST_MISSING,
                            "named on-screen role is not in cast",
                            shot_id=shot_id,
                            field="dialogue" if "dialogue" in hit["fields"] else "action",
                            role_name=name,
                            source_fields=hit["fields"],
                            tier="A",
                        )
                    )
                mentioned_unresolved.setdefault(name, []).append(shot_id)
                continue
            if cid not in char_ids:
                key = (shot_id, cid)
                if key not in seen_gap:
                    seen_gap.add(key)
                    issues.append(
                        issue_fn(
                            severity,
                            NAMED_CAST_ROW_GAP,
                            "named on-screen role is in cast but missing from this shot char_ids",
                            shot_id=shot_id,
                            field="char_ids",
                            role_name=name,
                            matched_cast_id=cid,
                            source_fields=hit["fields"],
                            tier="A",
                        )
                    )
            mentioned_unresolved.setdefault(name, []).append(shot_id)

    seen_unref: set[str] = set()
    for name, shot_ids in mentioned_unresolved.items():
        cid = by_name.get(name)
        if not cid or cid in referenced_ids:
            continue
        if cid in seen_unref:
            continue
        seen_unref.add(cid)
        issues.append(
            issue_fn(
                severity,
                NAMED_CAST_UNREFERENCED,
                "named on-screen role is in cast but never referenced in char_ids",
                field="char_ids",
                role_name=name,
                matched_cast_id=cid,
                shot_ids=list(dict.fromkeys(shot_ids)),
                tier="A",
            )
        )
    return issues


def apply_char_id_wiring(rows: list[dict[str, Any]], name_to_id: dict[str, str]) -> list[dict[str, Any]]:
    """Add CHAR ids onto shots where the name speaks/appears. Drops NONE when named."""
    if not name_to_id:
        return rows
    pool = list(name_to_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        action, dialogue, combined = _row_prose(row)
        mentioned = set(names_mentioned(combined, pool))
        for name in extract_speakers(dialogue) + extract_speakers(action):
            if name in name_to_id:
                mentioned.add(name)
            if is_group_label(name):
                mentioned.update(expand_group(name, pool))
        for label in extract_group_labels(combined):
            mentioned.update(expand_group(label, pool))
        add_ids = [name_to_id[n] for n in mentioned if n in name_to_id]
        if not add_ids:
            out.append(updated)
            continue
        current = [str(c) for c in (updated.get("char_ids") or [])]
        current = [c for c in current if c and c != NONE_ID]
        for cid in add_ids:
            if cid not in current:
                current.append(cid)
        updated["char_ids"] = current or [NONE_ID]
        out.append(updated)
    return out


def auto_merge_named_cast(
    rec: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    alloc_char: Callable[[dict[str, Any]], str],
    one_line: str = AUTO_MERGE_ONE_LINE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """O1=A: register missing high-confidence names; wire char_ids.

    Mutates rec['cast']['characters'] and bumps cast.version when rows are added.
    Never touches outline body / G1b lock flags.
    """
    cast = rec.get("cast")
    if not isinstance(cast, dict):
        return rows, []
    outline_body = (rec.get("outline") or {}).get("body_md")
    hits = collect_named_hits(rows, cast=cast, outline_body=outline_body)
    by_name, _ = _cast_name_index(cast)
    individual_pool = set(by_name) | {h["name"] for h in hits if h.get("registerable")}

    needed: list[str] = []
    for hit in hits:
        for name in resolve_hit_names(hit["name"], individual_pool):
            if name not in by_name and name not in needed:
                needed.append(name)

    added: list[dict[str, Any]] = []
    for name in needed:
        ident = alloc_char(rec)
        row = {
            "id": ident,
            "name": name,
            "one_line": one_line,
            "library_ref": None,
        }
        cast.setdefault("characters", []).append(row)
        by_name[name] = ident
        added.append({"id": ident, "name": name})

    if added:
        cast["version"] = (cast.get("version") or 0) + 1

    wired = apply_char_id_wiring(rows, by_name)
    return wired, added
