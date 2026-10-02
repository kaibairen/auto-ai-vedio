"""AIV-031 BE · looks tree / refs mount / has_usable_ref / no usable flip. ForcePass=never."""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.looks import (
    dest_looks_file,
    ensure_episode_looks_tree,
    looks_filename,
    looks_relpath,
)
from aiv_drama_n3.models import N3AttachRefRequest, N3MaterializeRequest
from aiv_drama_n3.refs import (
    has_must_face,
    has_usable_ref,
    is_hotlink_url,
    md5_file,
    normalize_look_ref,
    refresh_card_ref_flags,
)
from aiv_drama_n4.models import N4AssembleRequest
from aiv_drama_n4.projection import prompts_jsonl_name
from aiv_drama_n4.validate import collect_missing_refs

from tests.drama.helpers import attach_real_refs, lock_g2, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _write_fixture(path: Path, payload: bytes = b"look-fixture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_looks_tree_path_authority_and_mkdir(tmp_path):
    assert looks_relpath("EP01", "character", "CHAR-01") == "episodes/EP01/n3/looks/char/CHAR-01"
    assert looks_filename("face", "front") == "face_front.png"
    assert looks_filename("plate", "front") == "plate_front.png"
    dest, rel = dest_looks_file(tmp_path / "EP01", "EP01", "character", "CHAR-01", "face", "front")
    assert rel == "episodes/EP01/n3/looks/char/CHAR-01/face_front.png"
    assert dest.parent.is_dir()
    assert (dest.parent / "web_refs").is_dir()
    root = ensure_episode_looks_tree(
        tmp_path / "EP01",
        [{"id": "SCENE-01", "kind": "scene"}],
    )
    assert (root / "char").is_dir()
    assert (root / "scene" / "SCENE-01" / "web_refs").is_dir()


def test_has_usable_ref_face_full_not_style_or_web():
    face = {"kind": "character", "refs": [{"path": "n3/looks/char/CHAR-01/face_front.png", "md5": "abc", "role": "face"}]}
    full = {"kind": "character", "refs": [{"path": "n3/looks/char/CHAR-01/full_front.png", "md5": "abc", "role": "full"}]}
    style = {"kind": "character", "refs": [{"path": "n3/looks/char/CHAR-01/web_refs/src.png", "md5": "abc", "role": "style_ref"}]}
    web = {"kind": "character", "refs": [{"path": "n3/looks/char/CHAR-01/web_refs/src.png", "md5": "abc", "role": "web_source"}]}
    missing = {"kind": "character", "refs": [{"path": "x", "md5": "abc", "role": "face", "missing_file": True}]}
    assert has_usable_ref(face) is True
    assert has_usable_ref(full) is True
    assert has_usable_ref(style) is False
    assert has_usable_ref(web) is False
    assert has_usable_ref(missing) is False
    assert has_must_face(face) is True
    assert has_must_face(full) is False
    refresh_card_ref_flags(full)
    assert full["missing_ref"] is True
    assert full["weak_binding"] is True
    empty = {"kind": "character", "refs": []}
    refresh_card_ref_flags(empty)
    assert empty["missing_ref"] is True


def test_hotlink_rejected_and_md5_mismatch(settings, tmp_path):
    assert is_hotlink_url("https://cdn.example/face.png") is True
    assert is_hotlink_url("n3/looks/char/CHAR-01/face_front.png") is False
    exc = _err(lambda: normalize_look_ref(settings, {"path": "https://x/a.png", "md5": "aa", "role": "face"}))
    assert exc.status_code == 400
    assert exc.code == "hotlink_ref_forbidden"
    dest, rel = dest_looks_file(tmp_path, "EP01", "character", "CHAR-01", "face", "front")
    dest.write_bytes(b"bytes-a")
    digest = md5_file(dest)
    ok = normalize_look_ref(settings, {"path": str(dest), "md5": digest, "role": "face"})
    assert ok["missing_file"] is False
    drifted = normalize_look_ref(settings, {"path": str(dest), "md5": "0" * 32, "role": "face"})
    assert drifted["missing_file"] is True
    ghost = normalize_look_ref(
        settings, {"path": str(tmp_path / "nope.png"), "md5": "abc", "role": "face"}
    )
    assert ghost["missing_file"] is True


def test_attach_ref_does_not_flip_usable(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    char = rec["n3"]["cards"]["characters"][0]
    src = _write_fixture(data_dir / "fixtures" / "face.png")
    env = svc.attach_n3_look_ref(
        pid,
        "EP01",
        N3AttachRefRequest(id=char["id"], role="face", source_path=str(src), actor="yangzhou"),
        raw={"id": char["id"], "role": "face", "source_path": str(src), "actor": "yangzhou"},
    )
    assert env["usable_for_n4"] is False
    assert env["cards"]["usable_for_n4"] is False
    mounted = next(c for c in env["cards"]["characters"] if c["id"] == char["id"])
    assert mounted["refs"]
    assert mounted["refs"][0]["role"] == "face"
    assert mounted["refs"][0]["md5"]
    assert mounted["missing_ref"] is False
    assert has_usable_ref(mounted) is True
    looks = Path(svc.store.episode_dir(pid, "EP01")) / "n3" / "looks" / "char" / char["id"] / "face_front.png"
    assert looks.is_file()
    assert mounted["refs"][0]["path"] == f"episodes/EP01/n3/looks/char/{char['id']}/face_front.png"

    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    src2 = _write_fixture(data_dir / "fixtures" / "face2.png", b"look-fixture-2")
    after = svc.attach_n3_look_ref(
        pid,
        "EP01",
        N3AttachRefRequest(id=char["id"], role="face", source_path=str(src2), actor="yangzhou"),
        raw={"id": char["id"], "role": "face", "source_path": str(src2), "actor": "yangzhou"},
    )
    assert after["usable_for_n4"] is False
    assert after["cards"]["usable_for_n4"] is False
    assert svc.get_gate_g3(pid, "EP01")["usable_for_n4"] is False
    assert has_usable_ref(after["cards"]["characters"][0]) is True


def test_attach_ref_style_does_not_count_or_flip(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    char = rec["n3"]["cards"]["characters"][0]
    src = _write_fixture(data_dir / "fixtures" / "style.png")
    env = svc.attach_n3_look_ref(
        pid,
        "EP01",
        N3AttachRefRequest(id=char["id"], role="style_ref", source_path=str(src), actor="yangzhou"),
        raw={"id": char["id"], "role": "style_ref", "source_path": str(src)},
    )
    card = next(c for c in env["cards"]["characters"] if c["id"] == char["id"])
    assert has_usable_ref(card) is False
    assert card["missing_ref"] is True
    assert env["usable_for_n4"] is False


def test_attach_ref_force_and_hotlink_banned(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    ident = rec["n3"]["cards"]["characters"][0]["id"]
    src = _write_fixture(data_dir / "fixtures" / "face.png")
    for key in ("force_pass", "force", "skip_gate"):
        exc = _err(
            lambda k=key: svc.attach_n3_look_ref(
                pid,
                "EP01",
                N3AttachRefRequest(id=ident, role="face", source_path=str(src), actor="x"),
                raw={"id": ident, "role": "face", "source_path": str(src), k: True},
            )
        )
        assert exc.status_code == 400
        assert exc.code == "force_pass_forbidden"
    exc = _err(
        lambda: svc.attach_n3_look_ref(
            pid,
            "EP01",
            N3AttachRefRequest(id=ident, role="face", source_path="https://cdn.example/a.png", actor="x"),
            raw={"id": ident, "role": "face", "source_path": "https://cdn.example/a.png"},
        )
    )
    assert exc.status_code == 400
    assert exc.code == "hotlink_ref_forbidden"


def test_n4_409_after_attach_ref_still_honest(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    rec = svc._rec(pid, "EP01")
    src = _write_fixture(data_dir / "fixtures" / "face.png")
    for card in rec["n3"]["cards"]["characters"]:
        svc.attach_n3_look_ref(
            pid,
            "EP01",
            N3AttachRefRequest(id=card["id"], role="face", source_path=str(src), actor="yangzhou"),
            raw={"id": card["id"], "role": "face", "source_path": str(src)},
        )
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert svc.get_gate_g3(pid, "EP01")["usable_for_n4"] is False
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "usable_for_n4_false"
    assert exc.details.get("written") is False
    assert exc.details.get("missing_refs")
    assert not (Path(data_dir) / "projects" / pid / "episodes" / "EP01" / prompts_jsonl_name("EP01")).exists()


def test_missing_file_md5_mismatch_in_n4_list(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    attach_real_refs(svc, pid, data_dir)
    rec = svc._rec(pid, "EP01")
    ep_dir = svc.store.episode_dir(pid, "EP01")
    card = rec["n3"]["cards"]["characters"][0]
    card["refs"][0]["md5"] = "0" * 32
    refresh_card_ref_flags(card)
    svc._commit(rec)
    missing = collect_missing_refs(rec.get("n3"), svc.settings, episode_dir=ep_dir)
    reasons = {m.get("reason") for m in missing}
    assert "missing_file" in reasons
    svc.confirm_gate_g3(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.assemble_n4(pid, "EP01", N4AssembleRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.code == "usable_for_n4_false"
    assert "missing_file" in {m.get("reason") for m in (exc.details.get("missing_refs") or [])}


def test_http_attach_ref_and_force_pass(client, data_dir):
    from tests.drama.test_n3_api import _setup_g2

    svc = client.app.state.service
    pid = _setup_g2(client)
    mat = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    assert mat.status_code == 200, mat.text
    ident = mat.json()["cards"]["characters"][0]["id"]
    src = _write_fixture(data_dir / "fixtures" / "http-face.png")
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/attach-ref",
        json={"id": ident, "role": "face", "source_path": str(src), "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"
    hot = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/attach-ref",
        json={"id": ident, "role": "face", "source_path": "https://cdn.example/a.png"},
    )
    assert hot.status_code == 400
    assert hot.json()["error"]["code"] == "hotlink_ref_forbidden"
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/attach-ref",
        json={"id": ident, "role": "face", "source_path": str(src), "actor": "yangzhou"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["usable_for_n4"] is False
    assert body["cards"]["characters"][0]["refs"]
    assert svc.get_gate_g3(pid, "EP01")["usable_for_n4"] is False


def test_image_keys_isolated_from_deepseek(settings):
    assert settings.openai_api_key != "must-not-reuse"
    assert getattr(settings, "ark_api_key", None) in {None, ""}
    assert getattr(settings, "dashscope_api_key", None) in {None, ""}
    from aiv_drama.config import Settings

    isolated = Settings(
        data_dir=settings.data_dir,
        repo_root=settings.repo_root,
        default_provider="fixture",
        openai_api_key="sk-deepseek-text-only",
        openai_base_url="https://api.deepseek.com/v1",
        openai_model="deepseek-chat",
        ark_api_key=None,
        dashscope_api_key=None,
    )
    assert isolated.openai_api_key == "sk-deepseek-text-only"
    assert isolated.ark_api_key is None
    assert isolated.dashscope_api_key is None
