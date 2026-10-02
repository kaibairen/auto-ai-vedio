"""U-033 / AIV-036 · SCENE look EXEMPT on proj_01/EP01. CHAR usable stays hard.

ForcePass=never. Does not invent card usable=true. Does not merge to main.
"""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n3.scene_look import (
    CHAR_HARD_COPY_ZH,
    EXEMPT_NOTE_ID,
    PINNED_EXEMPT_EPISODE_ID,
    SCENE_LOOK_EXEMPT,
    SCENE_LOOK_EXEMPT_COPY_ZH,
    SCENE_LOOK_EXEMPT_KEY,
    SCENE_LOOK_REQUIRED,
    resolve_scene_look_policy,
)
from aiv_drama_n3.validate import usable_for_n4
from aiv_drama_n4.assemble import assemble_shot
from aiv_drama_n4.gates import episode_usable_for_n4, require_assemble_gates
from aiv_drama_n4.models import N4AssembleRequest
from aiv_drama_n4.projection import prompts_jsonl_name
from aiv_drama_n4.validate import collect_missing_refs, collect_scene_missing_refs

from tests.drama.helpers import (
    attach_real_char_refs,
    lock_g2,
    lock_g3_char_usable,
    seed_project_episode,
)


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _char_card(*, with_ref: bool, data_dir=None) -> dict:
    refs = []
    if with_ref:
        path = (data_dir or Path("/tmp")) / "refs" / "CHAR-01.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"char-face")
        refs = [{"path": str(path), "md5": "abc123", "role": "face", "missing_file": False}]
    return {
        "id": "CHAR-01",
        "kind": "character",
        "name": "林晚",
        "one_line": "重生女主",
        "refs": refs,
        "missing_ref": not with_ref,
    }


def _scene_card(*, with_ref: bool = False, data_dir=None) -> dict:
    refs = []
    if with_ref:
        path = (data_dir or Path("/tmp")) / "refs" / "SCENE-01.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"scene-plate")
        refs = [{"path": str(path), "md5": "abc123", "role": "plate", "missing_file": False}]
    return {
        "id": "SCENE-01",
        "kind": "scene",
        "name": "边关门厅",
        "one_line": "夜雨石阶",
        "appearance": "青石门洞，雨湿灯笼",
        "light_anchor": "冷青夜雨侧光",
        "refs": refs,
        "missing_ref": not with_ref,
        "usable_for_n4": False,
    }


def _rec(*, project_id: str, episode_id: str, n3: dict, scene_look: str | None = None) -> dict:
    episode = {
        "project_id": project_id,
        "episode_id": episode_id,
        "pipeline_profile": "drama",
    }
    if scene_look is not None:
        episode["scene_look"] = scene_look
    return {
        "episode": episode,
        "gate_g2": {"locked": True, "last_decision": "pass"},
        "gate_g3": {"locked": True, "last_decision": "pass"},
        "storyboard": {
            "locked": True,
            "ready_for_n4": True,
            "tool_profile": "seedance_2",
            "rows": [{"shot_id": "S01", "camera": "PUSH", "shot_size": "MS", "notes": ""}],
        },
        "n3": n3,
    }


def test_policy_pin_is_proj_01_ep01_not_global():
    pinned = resolve_scene_look_policy(project_id="proj_01", episode_id="EP01")
    assert pinned.mode == SCENE_LOOK_EXEMPT
    assert pinned.source == "pin"
    assert pinned.exempt_machine_value == PINNED_EXEMPT_EPISODE_ID
    assert resolve_scene_look_policy(project_id="proj_01", episode_id="EP02").mode == SCENE_LOOK_REQUIRED
    assert resolve_scene_look_policy(project_id="proj_02", episode_id="EP01").mode == SCENE_LOOK_REQUIRED
    rolled = resolve_scene_look_policy(
        {"episode": {"project_id": "proj_01", "episode_id": "EP01", "scene_look": "required"}}
    )
    assert rolled.mode == SCENE_LOOK_REQUIRED
    assert rolled.source == "episode_flag"
    flagged = resolve_scene_look_policy(
        {"episode": {"project_id": "proj_02", "episode_id": "EP02", "scene_look_exempt": True}}
    )
    assert flagged.mode == SCENE_LOOK_EXEMPT
    assert flagged.source == "episode_flag"


def test_char_only_usable_true_on_exempt_false_off_scope(tmp_path):
    n3 = {"cards": {"characters": [_char_card(with_ref=True, data_dir=tmp_path)], "scenes": [_scene_card()]}}
    rec_ok = _rec(project_id="proj_01", episode_id="EP01", n3=n3)
    rec_ep02 = _rec(project_id="proj_01", episode_id="EP02", n3=n3)
    rec_proj02 = _rec(project_id="proj_02", episode_id="EP01", n3=n3)
    assert usable_for_n4(n3, g3_locked=True, rec=rec_ok) is True
    assert collect_missing_refs(n3, rec=rec_ok) == []
    assert collect_scene_missing_refs(n3)
    usable, missing = episode_usable_for_n4(rec_ok)
    assert usable is True
    assert missing == []
    require_assemble_gates(rec_ok)
    assert usable_for_n4(n3, g3_locked=True, rec=rec_ep02) is False
    assert any(item.get("kind") == "scene" for item in collect_missing_refs(n3, rec=rec_ep02))
    exc = _err(lambda: require_assemble_gates(rec_ep02))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    assert any(item.get("kind") == "scene" for item in (exc.details.get("missing_refs") or []))
    exc2 = _err(lambda: require_assemble_gates(rec_proj02))
    assert exc2.status_code == 409
    assert exc2.code == "usable_for_n4_false"


def test_scene_missing_plus_char_missing_face_still_409(tmp_path):
    n3 = {"cards": {"characters": [_char_card(with_ref=False)], "scenes": [_scene_card()]}}
    rec = _rec(project_id="proj_01", episode_id="EP01", n3=n3)
    assert usable_for_n4(n3, g3_locked=True, rec=rec) is False
    missing = collect_missing_refs(n3, rec=rec)
    assert missing
    assert all(item.get("kind") != "scene" for item in missing)
    assert any(item.get("id") == "CHAR-01" for item in missing)
    exc = _err(lambda: require_assemble_gates(rec))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    assert exc.details.get(SCENE_LOOK_EXEMPT_KEY) == "EP01"
    assert exc.details.get("scene_look") == SCENE_LOOK_EXEMPT
    assert all(item.get("kind") != "scene" for item in (exc.details.get("missing_refs") or []))
    assert "人物缺合格脸图" in exc.message


def test_assemble_expands_thick_scene_text_without_plate():
    char = {
        "id": "CHAR-01",
        "kind": "character",
        "name": "林晚",
        "one_line": "重生女主",
        "refs": [{"path": "/tmp/CHAR-01.png", "md5": "x", "role": "face", "missing_file": False}],
    }
    scene = _scene_card()
    line = assemble_shot(
        {
            "shot_id": "S01",
            "duration_s": 5,
            "shot_size": "MS",
            "camera": "PUSH",
            "action": "推门入室环顾",
            "char_ids": ["CHAR-01"],
            "scene_id": "SCENE-01",
            "notes": "",
        },
        index={"CHAR-01": char, "SCENE-01": scene},
        catalog={"CHAR-01": "林晚，重生女主", "SCENE-01": "边关门厅，夜雨石阶，青石门洞，雨湿灯笼"},
        aspect="9:16",
        tool_profile="seedance_2",
        cards_version=1,
        assemble_version=1,
    )
    prompt = line["prompt"]
    assert "边关门厅" in prompt
    assert "青石门洞" in prompt
    assert "冷青夜雨侧光" in prompt
    assert "SCENE-01" not in prompt
    assert "/tmp/CHAR-01.png" in line["ref_images"]
    assert all("SCENE-01" not in path for path in line["ref_images"])
    assert scene.get("usable_for_n4") is not True


def test_char_only_assemble_writes_jsonl_on_ep01(svc, data_dir):
    pid = seed_project_episode(svc)
    assert pid == "proj_01"
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    for scene in rec["n3"]["cards"]["scenes"]:
        scene["appearance"] = scene.get("appearance") or f"{scene.get('name') or scene['id']}青石空间"
        scene["light_anchor"] = scene.get("light_anchor") or "冷青侧光"
        assert not scene.get("refs")
        scene["usable_for_n4"] = False
    svc._commit(rec)
    attach_real_char_refs(svc, pid, data_dir)
    passed = svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert passed["usable_for_n4"] is True
    assert passed[SCENE_LOOK_EXEMPT_KEY] == "EP01"
    assert passed["scene_look"] == SCENE_LOOK_EXEMPT
    assert passed["scene_look_note"] == EXEMPT_NOTE_ID
    assert SCENE_LOOK_EXEMPT_COPY_ZH in (passed.get("scene_look_copy") or "")
    assert CHAR_HARD_COPY_ZH in (passed.get("char_look_copy") or "")
    rec = svc._rec(pid, "EP01")
    for scene in rec["n3"]["cards"]["scenes"]:
        assert scene.get("usable_for_n4") is not True
        assert not scene.get("refs")
    env = svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    assert env["written"] is True
    assert env["usable_for_n4"] is True
    assert env[SCENE_LOOK_EXEMPT_KEY] == "EP01"
    assert env["scene_look"] == SCENE_LOOK_EXEMPT
    assert env.get("missing_refs") == []
    path = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.strip()
    prompts = "".join(line.get("prompt") or "" for line in env["lines"])
    assert "SCENE-" not in prompts
    scene_names = [s.get("name") for s in rec["n3"]["cards"]["scenes"] if s.get("name")]
    assert scene_names
    assert any(name in prompts for name in scene_names)
    assert any("冷青侧光" in (line.get("prompt") or "") for line in env["lines"])


def test_char_missing_face_still_409_on_exempt_assemble(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    missing = exc.details.get("missing_refs") or []
    assert missing
    assert any(item.get("id", "").startswith("CHAR-") for item in missing)
    assert all(item.get("kind") != "scene" for item in missing)
    assert exc.details.get(SCENE_LOOK_EXEMPT_KEY) == "EP01"
    assert not (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")).exists()


def test_force_pass_still_400_on_exempt_path(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g3_char_usable(svc, pid, data_dir)
    for key in ("force_pass", "force", "skip_gate"):
        exc = _err(
            lambda k=key: svc.assemble_n4(
                pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou", k: True}
            )
        )
        assert exc.status_code == 400
        assert exc.code == "force_pass_forbidden"
        assert not (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")).exists()
