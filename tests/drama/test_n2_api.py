from __future__ import annotations

from tests.drama.helpers import sample_row


def _setup_locked(client):
    proj = client.post("/api/v0/projects", json={"name": "n2"}).json()["project"]
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
        json={"title_intent": "被流放的庶女在边关翻盘", "lane_preference": "female"},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g1b/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    return pid


def test_health_lists_dn2(client):
    data = client.get("/health").json()
    assert "D-N2" in data["nodes"]
    assert "g2" in data["gates"]
    assert data["docs_pass"] is False
    assert data["auto_open_dn3"] is False


def test_openapi_n2_copy_served(client):
    res = client.get("/openapi/drama-n2.v0.yaml")
    assert res.status_code == 200
    assert "0.1.0" in res.text
    assert "D-N2" in res.text
    assert "g2" in res.text


def test_http_upstream_unlocked(client):
    proj = client.post("/api/v0/projects", json={"name": "u"}).json()["project"]
    pid = proj["id"]
    client.post(f"/api/v0/projects/{pid}/episodes", json={"episode_id": "EP01", "pipeline_profile": "drama"})
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "upstream_unlocked"


def test_http_force_pass_g2(client):
    pid = _setup_locked(client)
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    )
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g2/confirm",
        json={"decision": "pass", "actor": "yangzhou", "force_pass": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"
    assert res.json()["error"]["details"]["gate"] == "g2"


def test_http_happy_generate_validate_g2(client):
    pid = _setup_locked(client)
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    )
    assert gen.status_code == 200
    body = gen.json()
    assert body["node"] == "D-N2"
    assert body["storyboard"]["storyboard_skill"] == "borrowed_dongman"
    val = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/validate", json={})
    assert val.status_code == 200
    assert val.json()["valid"] is True
    assert val.json()["ready_for_n4"] is False
    con = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g2/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert con.status_code == 200
    assert con.json()["next_edges"] == ["D-N3"]
    assert con.json()["gate"]["locked"] is True
    locked = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": [sample_row()]},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "locked"


def test_http_cast_id_unknown_and_prompt(client):
    pid = _setup_locked(client)
    bad_char = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": [sample_row(char_ids=["CHAR-99"])]},
    )
    assert bad_char.status_code == 422
    assert bad_char.json()["error"]["code"] == "cast_id_unknown"
    leak = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": [sample_row(action="宫格指令 [Image1] Seedance 时间轴")]},
    )
    assert leak.status_code == 422
    assert leak.json()["error"]["code"] == "prompt_forbidden"


def test_http_reorder_and_reset(client):
    pid = _setup_locked(client)
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    ).json()
    ids = [r["shot_id"] for r in gen["storyboard"]["rows"]]
    flipped = list(reversed(ids))
    reo = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/reorder",
        json={"shot_ids": flipped, "actor": "yangzhou"},
    )
    assert reo.status_code == 200
    assert [r["shot_id"] for r in reo.json()["storyboard"]["rows"]] == flipped
    rst = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/reset",
        json={},
    )
    assert rst.status_code == 200
    assert rst.json()["storyboard"]["rows"] == []


def test_http_bare_n2_404(client):
    pid = _setup_locked(client)
    for path in (
        f"/api/v0/projects/{pid}/episodes/EP01/n2",
        f"/api/v0/projects/{pid}/episodes/EP01/nodes/n2/draft",
    ):
        res = client.get(path)
        assert res.status_code == 404
        assert "D-N2" in res.json()["error"]["message"]


def test_http_put_select_profile_adsorbs_short_shots(client):
    pid = _setup_locked(client)
    short = [sample_row(duration_s=2, camera="WHIP_PUSH", tool_duration_bucket=None, grid_strict=True)]
    first = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": short},
    )
    assert first.status_code == 200
    val = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/validate", json={})
    assert val.status_code == 200
    assert val.json()["valid"] is True
    assert val.json()["ready_for_n4"] is False
    assert any(i["code"] == "tool_profile_unset" for i in val.json()["issues"])
    adsorbed = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": short, "tool_profile": "seedance_2"},
    )
    assert adsorbed.status_code == 200, adsorbed.text
    row = adsorbed.json()["storyboard"]["rows"][0]
    assert row["duration_s"] == 8
    assert row["tool_duration_bucket"] == "seedance:8"
    after = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/validate", json={})
    assert after.status_code == 200
    assert after.json()["valid"] is True
    assert after.json()["ready_for_n4"] is True


def test_http_selected_profile_short_shot_422(client):
    pid = _setup_locked(client)
    legal = [sample_row(duration_s=5, camera="STATIC", tool_duration_bucket="seedance:5")]
    ok = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": legal, "tool_profile": "seedance_2"},
    )
    assert ok.status_code == 200
    short = [sample_row(duration_s=2, camera="STATIC", tool_duration_bucket=None)]
    bad = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": short, "tool_profile": "seedance_2"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "duration_bucket_mismatch"


def test_http_idempotency_generate(client):
    pid = _setup_locked(client)
    headers = {"Idempotency-Key": "sb-http"}
    a = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
        headers=headers,
    )
    b = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
        headers=headers,
    )
    assert a.status_code == b.status_code == 200
    assert a.json()["storyboard"]["version"] == b.json()["storyboard"]["version"]
