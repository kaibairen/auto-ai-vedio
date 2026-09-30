from __future__ import annotations


def _setup(client):
    proj = client.post("/api/v0/projects", json={"name": "api"}).json()["project"]
    pid = proj["id"]
    client.put(
        f"/api/v0/projects/{pid}/library/characters/CHAR-01",
        json={"name": "林晚", "one_line": "重生女主", "version": 1},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes",
        json={"episode_id": "EP01", "pipeline_profile": "drama"},
    )
    client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/brief",
        json={
            "title_intent": "被流放的庶女在边关翻盘",
            "lane_preference": "female",
            "hero_one_line": "重生女主",
        },
    )
    return pid


def _confirm(client, pid):
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/intent/confirm",
        json={"actor": "eng-018a"},
    )
    assert res.status_code == 200, res.text
    return res


def test_health(client):
    data = client.get("/health").json()
    assert data["ok"] is True
    assert data["nodes"] == ["D-N0", "D-N1", "D-N2"]
    assert data["gate"] == "g1b"
    assert data["gates"] == ["g1b", "g2"]
    assert data["koubo_n1"] is False
    assert data["docs_pass"] is False


def test_openapi_copy_served(client):
    res = client.get("/openapi/drama-n0n1.v0.yaml")
    assert res.status_code == 200
    assert "0.1.0" in res.text
    assert "D-N0" in res.text
    n2 = client.get("/openapi/drama-n2.v0.yaml")
    assert n2.status_code == 200
    assert "named_cast_gate" in n2.text
    assert "duration_bucket_mismatch" in n2.text
    assert "ready_for_n4_requires_tool_profile" in n2.text


def test_force_pass_on_http_confirm(client):
    pid = _setup(client)
    _confirm(client, pid)
    client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/outline", json={"lane": "female", "provider": "fixture"})
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g1b/confirm",
        json={"decision": "pass", "actor": "yangzhou", "force_pass": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"


def test_skip_gate_on_generate(client):
    pid = _setup(client)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "skip_gate": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"


def test_dual_skill_preview_rejected(client):
    pid = _setup(client)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "dual_skill_preview": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "validation"


def test_lane_required_http(client):
    proj = client.post("/api/v0/projects", json={"name": "x"}).json()["project"]
    pid = proj["id"]
    client.post(f"/api/v0/projects/{pid}/episodes", json={"episode_id": "EP01", "pipeline_profile": "drama"})
    client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/brief",
        json={"title_intent": "一句", "lane_preference": "unset"},
    )
    res = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/outline", json={})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "intent_unconfirmed"


def test_http_happy_pass_and_downstream(client):
    pid = _setup(client)
    _confirm(client, pid)
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
    )
    assert gen.status_code == 200
    down = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/downstream")
    assert down.status_code == 409
    assert down.json()["error"]["code"] == "upstream_unlocked"
    con = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g1b/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert con.status_code == 200
    body = con.json()
    assert body["next_edges"] == ["D-N2"]
    assert body["gate"]["locked"] is True
    locked_put = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"body_md": body["outline"]["body_md"] + "x"},
    )
    assert locked_put.status_code == 409
    assert locked_put.json()["error"]["code"] == "locked"
    ok = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/downstream")
    assert ok.status_code == 200
    assert ok.json()["started"] is False


def test_if_match_http(client):
    pid = _setup(client)
    res = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/brief",
        json={"title_intent": "改", "lane_preference": "female"},
        headers={"If-Match": "99"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "version_conflict"


def test_koubo_paths_404(client):
    pid = _setup(client)
    for path in (
        f"/api/v0/projects/{pid}/episodes/EP01/n1",
        f"/api/v0/projects/{pid}/episodes/EP01/nodes/n1/draft",
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g1/confirm",
    ):
        res = client.get(path)
        assert res.status_code == 404
        assert "koubo-N1" in res.json()["error"]["message"]


def test_shot_cap_exceeded_http(client):
    pid = _setup(client)
    _confirm(client, pid)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "shot_cap": 13},
    )
    assert res.status_code == 422
    code = res.json()["error"]["code"]
    assert code in {"shot_cap_exceeded", "validation"}


def test_idempotency_key_generate_http(client):
    pid = _setup(client)
    _confirm(client, pid)
    headers = {"Idempotency-Key": "abc"}
    a = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
        headers=headers,
    )
    b = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
        headers=headers,
    )
    assert a.status_code == b.status_code == 200
    assert a.json()["outline"]["version"] == b.json()["outline"]["version"]
