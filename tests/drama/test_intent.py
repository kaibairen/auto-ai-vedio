"""018a intent confirm gate — scheme A + 422 codes."""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama.intent import compute_intent_fingerprint
from aiv_drama.models import (
    AttachRequest,
    ConfirmDramaIntentRequest,
    DramaBriefWrite,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
)
from tests.drama.helpers import persist_and_confirm_intent, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_t_i1_unconfirmed_generate_422_no_outline(svc):
    pid = seed_project_episode(svc)
    rec = svc._rec(pid, "EP01")
    assert rec.get("outline") is None
    exc = _err(
        lambda: svc.generate_outline(
            pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female"}
        )
    )
    assert exc.status_code == 422
    assert exc.code == "intent_unconfirmed"
    assert svc._rec(pid, "EP01").get("outline") is None


def test_t_i2_confirm_then_generate_ok(svc, data_dir):
    pid = seed_project_episode(svc)
    env = persist_and_confirm_intent(svc, pid)
    assert env["ok"] is True
    assert env["node"] == "D-N0"
    assert env["intent"]["confirmed"] is True
    assert env["intent"]["fingerprint"]
    assert len(env["intent"]["fingerprint"]) == 64
    gen = svc.generate_outline(
        pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female"}
    )
    assert gen["ok"] is True
    assert gen["outline"]["body_md"]
    episode = svc.get_episode(pid, "EP01")
    assert episode["intent"]["confirmed"] is True
    assert episode["episode"]["intent"]["fingerprint"] == env["intent"]["fingerprint"]
    meta = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / ".aiv" / "episode.json"
    text = meta.read_text(encoding="utf-8")
    assert '"confirmed": true' in text
    assert env["intent"]["fingerprint"] in text


def test_t_i3_must_change_clears_then_unconfirmed(svc):
    pid = seed_project_episode(svc)
    persist_and_confirm_intent(svc, pid)
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(title_intent="改了题材锚", lane_preference="female", hero_one_line="重生女主"),
    )
    rec = svc._rec(pid, "EP01")
    assert rec["intent"]["confirmed"] is False
    assert rec["intent"]["fingerprint"] is None
    exc = _err(
        lambda: svc.generate_outline(
            pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female"}
        )
    )
    assert exc.code == "intent_unconfirmed"


def test_t_i4_tamper_must_without_clear_is_stale(svc):
    pid = seed_project_episode(svc)
    persist_and_confirm_intent(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["brief"]["title_intent"] = "内部篡改MUST"
    exc = _err(
        lambda: svc.generate_outline(
            pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female"}
        )
    )
    assert exc.status_code == 422
    assert exc.code == "intent_stale"


def test_t_i5_lane_conflict_then_follow_b(svc):
    pid = seed_project_episode(svc, lane="female", hero_one_line="边关女主")
    svc.put_library_character(
        pid, "CHAR-02", LibraryCharacterWrite(name="沈策", one_line="冷面男主", version=1)
    )
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-02", version=1))
    exc = _err(lambda: svc.confirm_intent(pid, "EP01", ConfirmDramaIntentRequest(actor="eng-018a")))
    assert exc.status_code == 422
    assert exc.code == "intent_lane_conflict"
    assert exc.details.get("suggested_lane") == "male"
    assert exc.details.get("current_lane") == "female"
    preview = svc.check_intent(pid, "EP01")
    assert preview["conflict"] is True
    assert preview["can_confirm"] is False
    assert preview["suggested_lane"] == "male"
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(
            title_intent="被流放的庶女在边关翻盘",
            lane_preference="male",
            hero_one_line="边关女主",
        ),
    )
    ok = svc.confirm_intent(pid, "EP01", ConfirmDramaIntentRequest(actor="eng-018a"))
    assert ok["intent"]["confirmed"] is True


def test_t_i6_should_only_put_keeps_confirmed(svc):
    pid = seed_project_episode(svc)
    persist_and_confirm_intent(svc, pid)
    fp = svc._rec(pid, "EP01")["intent"]["fingerprint"]
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(
            title_intent="被流放的庶女在边关翻盘",
            lane_preference="female",
            hero_one_line="重生女主",
            setting_notes="只改笔记不清确认",
        ),
    )
    rec = svc._rec(pid, "EP01")
    assert rec["intent"]["confirmed"] is True
    assert rec["intent"]["fingerprint"] == fp
    gen = svc.generate_outline(
        pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female"}
    )
    assert gen["ok"] is True


def test_t_i7_force_and_skip_intent_forbidden(svc):
    pid = seed_project_episode(svc)
    exc = _err(
        lambda: svc.confirm_intent(
            pid, "EP01", ConfirmDramaIntentRequest(actor="x"), raw={"actor": "x", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"
    exc2 = _err(
        lambda: svc.confirm_intent(
            pid, "EP01", ConfirmDramaIntentRequest(actor="x"), raw={"actor": "x", "skip_intent": True}
        )
    )
    assert exc2.status_code == 400
    assert exc2.code == "force_pass_forbidden"


def test_t_i8_photography_fields_do_not_gate_confirm(svc):
    pid = seed_project_episode(svc)
    env = svc.confirm_intent(
        pid,
        "EP01",
        ConfirmDramaIntentRequest(actor="eng-018a"),
        raw={"actor": "eng-018a", "look": "must-not-block", "九宫": True, "定妆": "nope"},
    )
    assert env["intent"]["confirmed"] is True


def test_clear_intent_then_generate_unconfirmed(svc):
    pid = seed_project_episode(svc)
    persist_and_confirm_intent(svc, pid)
    cleared = svc.clear_intent(pid, "EP01", raw={"actor": "eng-018a"})
    assert cleared["intent"]["confirmed"] is False
    assert cleared["intent"]["fingerprint"] is None
    exc = _err(
        lambda: svc.generate_outline(
            pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"lane": "female"}
        )
    )
    assert exc.code == "intent_unconfirmed"


def test_hero_one_line_draft_on_confirm_rejected(svc):
    pid = seed_project_episode(svc, hero_one_line=None)
    rec = svc._rec(pid, "EP01")
    rec["brief"]["hero_one_line"] = None
    exc = _err(
        lambda: svc.confirm_intent(
            pid,
            "EP01",
            ConfirmDramaIntentRequest(actor="eng-018a"),
            raw={"actor": "eng-018a", "hero_one_line": "只存在请求体的草稿句"},
        )
    )
    assert exc.status_code == 422
    assert exc.code == "validation"
    assert "hero_one_line" in exc.message
    missing = _err(lambda: svc.confirm_intent(pid, "EP01", ConfirmDramaIntentRequest(actor="eng-018a")))
    assert missing.status_code == 422
    assert missing.code == "validation"
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(title_intent="被流放的庶女在边关翻盘", lane_preference="female", hero_one_line="庶女·边关"),
    )
    ok = svc.confirm_intent(pid, "EP01", ConfirmDramaIntentRequest(actor="eng-018a"))
    assert ok["intent"]["confirmed"] is True


def test_fingerprint_stable_and_order_insensitive(svc):
    pid = seed_project_episode(svc)
    rec = svc._rec(pid, "EP01")
    a = compute_intent_fingerprint(rec["brief"], svc._fingerprint_cards(rec))
    shuffled = list(reversed(svc._fingerprint_cards(rec)))
    b = compute_intent_fingerprint(rec["brief"], shuffled)
    assert a == b
    assert a == compute_intent_fingerprint(rec["brief"], svc._fingerprint_cards(rec))


def test_confirm_lane_required(svc):
    pid = seed_project_episode(svc, lane="unset")
    exc = _err(lambda: svc.confirm_intent(pid, "EP01", ConfirmDramaIntentRequest(actor="eng-018a")))
    assert exc.code == "lane_required"


def test_http_intent_confirm_clear_and_openapi(client):
    proj = client.post("/api/v0/projects", json={"name": "intent"}).json()["project"]
    pid = proj["id"]
    client.post(f"/api/v0/projects/{pid}/episodes", json={"episode_id": "EP01", "pipeline_profile": "drama"})
    client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/brief",
        json={"title_intent": "一句", "lane_preference": "female", "hero_one_line": "女主谋士"},
    )
    bare = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/outline", json={"lane": "female"})
    assert bare.status_code == 422
    assert bare.json()["error"]["code"] == "intent_unconfirmed"
    con = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/intent/confirm",
        json={"actor": "eng-018a"},
    )
    assert con.status_code == 200
    assert con.json()["intent"]["confirmed"] is True
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
    )
    assert gen.status_code == 200
    cleared = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/intent/clear", json={})
    assert cleared.status_code == 200
    assert cleared.json()["intent"]["confirmed"] is False
    spec = client.get("/openapi/drama-n0n1.v0.yaml").text
    assert "0.1.0" in spec
    assert "intent_unconfirmed" in spec
    assert "intent_stale" in spec
    assert "intent_lane_conflict" in spec
    assert "confirmDramaIntent" in spec
    assert "clearDramaIntent" in spec
