from __future__ import annotations


def test_create_session_and_http_step_gating(client, project, ep):
    r = client.post(f"/api/v0/projects/{project}/episodes", json={"ep": ep})
    assert r.status_code == 200
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions",
        json={"path": "A", "provider": "fixture"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["allowed_steps"] == [1]
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/3/submit",
        json={"confirm": True},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "step_not_allowed"


def test_http_downstream_409_and_g1_confirm(client, project, ep):
    client.post(f"/api/v0/projects/{project}/episodes", json={"ep": ep})
    client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions",
        json={"path": "A", "provider": "fixture"},
    )
    r = client.put(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/draft",
        json={"title": "钩子", "body": "三秒内把痛点说完，结尾只留一个行动。评论区扣1。"},
    )
    assert r.status_code == 200
    r = client.get(f"/api/v0/projects/{project}/episodes/{ep}/n1/final")
    assert r.status_code == 409
    assert r.json()["error"] == "n1_not_locked"
    r = client.get(f"/api/v0/projects/{project}/episodes/{ep}/n1?consumer=downstream")
    assert r.status_code == 409
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/gates/g1/confirm",
        json={"decision": "pass", "actor": "bot:http"},
    )
    assert r.status_code == 200
    assert r.json()["locked"] is True
    assert r.json()["auto_advanced"] is False
    r = client.get(f"/api/v0/projects/{project}/episodes/{ep}/n1/final")
    assert r.status_code == 200
    fm = r.json()["artifact"]["frontmatter"]
    assert fm["locked"] is True
    assert fm["confirmed_by"] == "bot:http"
    assert fm["node"] == "N1"


def test_http_force_pass_and_n1_lock_absent(client, project, ep):
    client.post(f"/api/v0/projects/{project}/episodes", json={"ep": ep})
    client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions",
        json={"path": "A", "provider": "fixture"},
    )
    client.put(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/draft",
        json={"title": "t", "body": "有钩子的短口播。评论区见。"},
    )
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/gates/g1/confirm",
        json={"decision": "pass", "actor": "admin", "force_pass": True},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "force_pass_forbidden"
    r = client.post(f"/api/v0/projects/{project}/episodes/{ep}/n1/lock", json={})
    assert r.status_code == 404
    assert r.json()["error"] == "lock_path_removed"


def test_http_path_b_skip_step_3(client, project, ep):
    client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions",
        json={"path": "B", "provider": "fixture"},
    )
    client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/1/submit",
        json={"text": "长文：一个痛点加一个行动。"},
    )
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/2/submit",
        json={"confirm": True},
    )
    assert r.json()["allowed_steps"] == [4]
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/3/submit",
        json={"confirm": True},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "source_defect_skip"
