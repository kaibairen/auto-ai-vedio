from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from aiv_drama.store import atomic_write_text
from aiv_drama_n3.library import index_payload
from aiv_drama_n3.policy import default_project_scope, project_scope_capability


def _dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def write_episode_cards(episode_dir: Path, n3: dict[str, Any] | None) -> Path | None:
    cards = (n3 or {}).get("cards")
    if not cards:
        return None
    cards_dir = episode_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "version": cards.get("version"),
        "locked": cards.get("locked"),
        "usable_for_n4": cards.get("usable_for_n4"),
        "characters": [c.get("id") for c in (cards.get("characters") or [])],
        "scenes": [s.get("id") for s in (cards.get("scenes") or [])],
        "note": "本集工作副本；库 libraries/ 为权威源",
    }
    atomic_write_text(cards_dir / "index.yaml", _dump_yaml(index))
    for card in list(cards.get("characters") or []) + list(cards.get("scenes") or []):
        ident = card.get("id")
        if not ident:
            continue
        atomic_write_text(cards_dir / f"{ident}.yaml", _dump_yaml(card))
    return cards_dir


def write_character_schema(root: Path, record: dict[str, Any], versions: list[int]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = index_payload(record, versions)
    if "project_scope" not in payload:
        payload["project_scope"] = default_project_scope()
    if "project_scope_capability" not in payload:
        payload["project_scope_capability"] = project_scope_capability()
    atomic_write_text(root / "character.yaml", _dump_yaml(payload))
    ver_dir = root / f"v{record.get('version')}"
    ver_dir.mkdir(parents=True, exist_ok=True)
    card_md = _card_md(record)
    atomic_write_text(ver_dir / "card.md", card_md)
    (ver_dir / "refs").mkdir(exist_ok=True)


def write_scene_schema(root: Path, record: dict[str, Any], versions: list[int]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = index_payload({**record, "kind": "scene"}, versions)
    payload["template_status"] = "deferred"
    payload["template_path"] = None
    atomic_write_text(root / "scene.yaml", _dump_yaml(payload))
    ver_dir = root / f"v{record.get('version')}"
    ver_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(ver_dir / "card.md", _card_md(record, scene=True))
    atomic_write_text(ver_dir / "scene.yaml", _dump_yaml(record))
    (ver_dir / "refs").mkdir(exist_ok=True)


def _card_md(record: dict[str, Any], *, scene: bool = False) -> str:
    ident = record.get("id")
    name = record.get("name")
    lines = [
        f"# {ident} {name}",
        "",
        f"- one_line: {record.get('one_line')}",
        f"- version: {record.get('version')}",
        f"- project_scope: {record.get('project_scope') or default_project_scope()} （D12 默认可覆盖假设 · chosen=null）",
        f"- origin: {record.get('source') or 'seed'}",
    ]
    if scene:
        lines.append("- template_status: deferred（F2 · 不发明 KEEP SCENE 模板路径）")
    lines.append("")
    return "\n".join(lines)
