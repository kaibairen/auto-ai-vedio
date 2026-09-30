"""018d copy-contract evaluate + catalog HTTP. ForcePass=never. docs≠PASS."""

from __future__ import annotations

from aiv_drama.copy_contract import user_message
from aiv_drama.errors import AppError

from tests.drama.helpers import seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_evaluate_tool_profile_unset_warn(svc):
    pid = seed_project_episode(svc)
    env = svc.evaluate_copy_contract(
        pid,
        "EP01",
        {"tool_profile": None, "rows": [{"shot_id": "S01", "duration_s": 3, "camera": "STATIC"}]},
    )
    assert env["ok"] is True
    assert env["docs_pass"] is False
    codes = [w["code"] for w in env["warnings"]]
    assert "tool_profile_unset" in codes
    assert "尚未选择出片工具" in env["warnings"][0]["message"]
    assert env["chip"] == "出片：未选工具"
    assert env["ready_for_n4"] is False


def test_evaluate_ready_requires_tool(svc):
    pid = seed_project_episode(svc)
    exc = _err(
        lambda: svc.evaluate_copy_contract(
            pid, "EP01", {"tool_profile": "", "ready_for_n4": True, "rows": []}
        )
    )
    assert exc.status_code == 422
    assert exc.code == "ready_for_n4_requires_tool_profile"
    assert "请先选择出片工具" in exc.message


def test_evaluate_duration_mismatch(svc):
    pid = seed_project_episode(svc)
    exc = _err(
        lambda: svc.evaluate_copy_contract(
            pid,
            "EP01",
            {
                "tool_profile": "seedance_2",
                "rows": [
                    {
                        "shot_id": "S01",
                        "duration_s": 3,
                        "camera": "STATIC",
                        "tool_duration_bucket": "seedance:3",
                    }
                ],
            },
        )
    )
    assert exc.code == "duration_bucket_mismatch"
    assert "对不上" in exc.message
    envelope = exc.to_envelope()["error"]
    assert envelope["messages"]["zh"]
    assert envelope["messages"]["en"]
    assert exc.details.get("duration_s") == 3 or (exc.details.get("details") or {}).get("duration_s") == 3


def test_evaluate_named_cast_gate(svc):
    pid = seed_project_episode(svc)
    exc = _err(
        lambda: svc.evaluate_copy_contract(
            pid,
            "EP01",
            {
                "g2_pass": True,
                "named_cast_issues": [{"code": "named_cast_missing", "role_name": "沈衡"}],
            },
        )
    )
    assert exc.code == "named_cast_gate"
    assert "具名" in exc.message


def test_evaluate_named_cast_missing_error_mode(svc):
    pid = seed_project_episode(svc)
    exc = _err(
        lambda: svc.evaluate_copy_contract(
            pid,
            "EP01",
            {
                "named_cast_check": "error",
                "named_cast_issues": [{"code": "named_cast_missing"}],
            },
        )
    )
    assert exc.code == "named_cast_missing"


def test_error_catalog_http(client):
    res = client.get("/api/v0/drama/error-catalog")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == "0.1.0"
    assert body["docs_pass"] is False
    assert "intent_unconfirmed" in body["http_error_codes"]["n0n1"]
    assert "named_cast_gate" in body["http_error_codes"]["n2"]
    assert "尚未选择出片工具" in body["messages"]["tool_profile_unset"]["zh"]


def test_evaluate_http_and_openapi_n2(client):
    proj = client.post("/api/v0/projects", json={"name": "copy"}).json()["project"]
    pid = proj["id"]
    client.post(f"/api/v0/projects/{pid}/episodes", json={"episode_id": "EP01", "pipeline_profile": "drama"})
    unset = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/copy-contract/evaluate",
        json={"tool_profile": None, "rows": [{"shot_id": "S01", "duration_s": 2}]},
    )
    assert unset.status_code == 200
    assert unset.json()["warnings"][0]["code"] == "tool_profile_unset"
    mis = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/copy-contract/evaluate",
        json={"tool_profile": "seedance_2", "rows": [{"shot_id": "S01", "duration_s": 2}]},
    )
    assert mis.status_code == 422
    err = mis.json()["error"]
    assert err["code"] == "duration_bucket_mismatch"
    assert err["messages"]["zh"]
    assert err["messages"]["en"]
    spec = client.get("/openapi/drama-n2.v0.yaml")
    assert spec.status_code == 200
    assert "named_cast_gate" in spec.text
    assert "version: 0.1.0" in spec.text
    assert "version: 0.2.0" not in spec.text


def test_user_message_gap_copy_phrases():
    assert "尚未选择出片工具" in user_message("tool_profile_unset")
    assert "对不上" in user_message("duration_bucket_mismatch")
