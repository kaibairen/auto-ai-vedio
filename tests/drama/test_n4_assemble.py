"""026 · deterministic DIR skeleton assemble, ID replace, NEG_CORE, tool alias."""

from __future__ import annotations

from aiv_drama_n4.assemble import assemble_episode_lines, assemble_shot, card_features, replace_ids
from aiv_drama_n4.camera import camera_lex, shot_size_lex
from aiv_drama_n4.skeleton import DIR_SLOT_ORDER, SLOT_REF_LEAD, join_nonempty
from aiv_drama_n4.tools import CANONICAL_SEEDANCE, Seedance2Adapter, normalize_tool_profile
from aiv_drama_n4.validate import BARE_ID_RE, NEG_CORE

from tests.drama.helpers import lock_g3_usable, seed_project_episode


def _card(ident: str, *, name: str, one_line: str, kind: str) -> dict:
    role = "face" if kind == "character" else "plate"
    return {
        "id": ident,
        "kind": kind,
        "name": name,
        "one_line": one_line,
        "origin": "local",
        "binding": "local",
        "refs": [{"path": f"/tmp/{ident}.png", "md5": "x", "role": role, "missing_file": False}],
        "library_ref": {"id": ident, "version": 3} if kind == "character" else None,
    }


def test_tool_alias_persists_seedance_2():
    persist, original = normalize_tool_profile("seedance_2_0")
    assert persist == CANONICAL_SEEDANCE
    assert original == "seedance_2_0"
    persist2, _ = normalize_tool_profile("seedance_2")
    assert persist2 == "seedance_2"


def test_unsupported_tool_rejected():
    from aiv_drama.errors import AppError

    try:
        normalize_tool_profile("kling")
    except AppError as exc:
        assert exc.status_code == 422
        assert exc.code == "unsupported_tool_profile"
    else:
        raise AssertionError("expected unsupported_tool_profile")


def test_adapter_seedance_limits():
    adapter = Seedance2Adapter()
    assert adapter.max_prompt_len == 800
    assert adapter.allowed_durations == frozenset({5, 8, 10})
    assert adapter.allowed_aspects == frozenset({"9:16", "16:9", "2.35:1"})
    assert adapter.max_ref_images == 9
    assert adapter.format_negative(NEG_CORE) == NEG_CORE


def test_skeleton_slot_order_and_camera_vocab():
    index = {
        "CHAR-01": _card("CHAR-01", name="林晚", one_line="重生女主", kind="character"),
        "SCENE-01": _card("SCENE-01", name="边关门厅", one_line="夜雨石阶", kind="scene"),
    }
    catalog = {"CHAR-01": "林晚，重生女主", "SCENE-01": "边关门厅，夜雨石阶"}
    row = {
        "shot_id": "S01",
        "seq": 1,
        "duration_s": 5,
        "shot_size": "MS",
        "camera": "PUSH",
        "action": "CHAR-01推门入室环顾",
        "char_ids": ["CHAR-01"],
        "scene_id": "SCENE-01",
        "dialogue": "你终于来了",
        "notes": "angle:low",
    }
    line = assemble_shot(
        row,
        index=index,
        catalog=catalog,
        aspect="9:16",
        tool_profile="seedance_2",
        cards_version=2,
        assemble_version=1,
    )
    prompt = line["prompt"]
    assert SLOT_REF_LEAD in prompt
    assert "林晚" in prompt
    assert "边关门厅" in prompt
    assert "中景，膝上或腰上" in prompt
    assert "镜头缓推靠近主体" in prompt
    assert "仰拍" in prompt
    assert "约5秒" in prompt
    assert "【风格】" not in prompt
    assert "【镜头】" not in prompt
    assert "平光" not in prompt
    assert "你终于来了" not in prompt
    assert prompt.index(SLOT_REF_LEAD) < prompt.index("林晚") < prompt.index("边关门厅")
    assert prompt.index("边关门厅") < prompt.index("推门入室环顾")
    assert shot_size_lex("CU") == "近景，胸以上"
    assert camera_lex("HANDHELD") == "手持跟拍，轻微晃动"
    assert line["negative"] == NEG_CORE
    assert line["negative"]
    assert line["tool_profile"] == "seedance_2"
    assert line["aspect"] == "9:16"
    assert line["fingerprint"]
    assert line["card_fingerprint"]
    assert line["card_versions"]["CHAR-01"]["version"] == 3
    assert DIR_SLOT_ORDER[0] == "slot_ref_lead"
    assert "。" in join_nonempty(["甲", "乙"])


def test_id_replaced_with_chinese_features():
    catalog = {"CHAR-01": "林晚，重生女主", "SCENE-01": "边关门厅"}
    assert "CHAR-01" not in replace_ids("CHAR-01推门", catalog)
    assert "林晚" in replace_ids("CHAR-01推门", catalog)
    card = _card("CHAR-01", name="林晚", one_line="重生女主", kind="character")
    assert "CHAR-01" not in card_features(card, kind="character")
    assert "林晚" in card_features(card, kind="character")


def test_assemble_episode_no_bare_ids(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g3_usable(svc, pid, data_dir)
    rec = svc._rec(pid, "EP01")
    lines = assemble_episode_lines(rec, tool_profile="seedance_2", aspect="9:16", assemble_version=1)
    assert lines
    for line in lines:
        assert line["negative"]
        assert NEG_CORE in line["negative"]
        assert not BARE_ID_RE.search(line["prompt"])
        assert line["tool_profile"] == "seedance_2"
        assert line["g2_fingerprint"]
        assert line["storyboard_version"]
        assert line["card_fingerprint"]
        for key in (
            "shot_id",
            "duration_s",
            "aspect",
            "tool_profile",
            "prompt",
            "negative",
            "ref_images",
            "camera",
            "char_ids",
            "scene_id",
            "fingerprint",
        ):
            assert key in line
