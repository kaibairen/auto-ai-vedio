"""021a/021c HTTP surface. docs≠PASS. ForcePass=never."""

from __future__ import annotations

from tests.drama.helpers import sample_row
from tests.drama.test_n2_api import _setup_locked


def _setup_g2(client):
    pid = _setup_locked(client)
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    )
    assert gen.status_code == 200, gen.text
    con = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g2/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert con.status_code == 200, con.text
    return pid


def test_health_lists_dn3(client):
    data = client.get("/health").json()
    assert "D-N3" in data["nodes"]
    assert "g3" in data["gates"]
    assert data["docs_pass"] is False
    assert data["auto_open_dn3"] is False
    assert data["auto_open_dn4"] is False


def test_openapi_n3_copy_served(client):
    res = client.get("/openapi/drama-n3.v0.yaml")
    assert res.status_code == 200
    assert "0.1.0" in res.text
    assert "D-N3" in res.text
    assert "usable_for_n4" in res.text
    assert "template_paths" in res.text
    assert "force_pass_forbidden" in res.text
    assert "cards/thicken" in res.text
    assert "cards/generate-look" in res.text
    assert "cards/generate-scene" in res.text
    assert "thicken_skill_paths" in res.text
    assert "provisional_inline" in res.text
    assert "2048x1365" in res.text


def test_http_n3_upstream_unlocked(client):
    pid = _setup_locked(client)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "upstream_unlocked"


def test_http_g3_force_pass_forbidden(client):
    pid = _setup_g2(client)
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g3/confirm",
        json={"decision": "pass", "actor": "yangzhou", "force_pass": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"
    assert res.json()["error"]["details"]["gate"] == "g3"


def test_http_materialize_g3_attach_promote(client):
    pid = _setup_g2(client)
    mat = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    assert mat.status_code == 200, mat.text
    body = mat.json()
    assert body["node"] == "D-N3"
    assert body["template_paths"]
    assert body["prompt_paths"]
    assert body["usable_for_n4"] is False
    ids = {c["id"] for c in body["cards"]["characters"]}
    assert ids
    att = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/attach",
        json={"id": "CHAR-01", "version": 1, "actor": "yangzhou"},
    )
    assert att.status_code == 200, att.text
    assert att.json()["g3_skipped"] is False
    assert att.json()["gate"]["locked"] is False
    pro = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/promote",
        json={"id": "CHAR-01", "actor": "yangzhou"},
    )
    assert pro.status_code == 200, pro.text
    assert pro.json()["g3_auto_passed"] is False
    assert pro.json()["gate"]["locked"] is False
    g3 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g3/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert g3.status_code == 200, g3.text
    assert g3.json()["gate"]["locked"] is True
    assert g3.json()["usable_for_n4"] is False
    assert g3.json()["next_edges"] == ["D-N4"]
    n4 = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n4-consumer")
    assert n4.status_code == 200
    assert n4.json()["started"] is False
    locked = client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard",
        json={"rows": [sample_row()]},
    )
    assert locked.status_code == 409


def test_http_bare_n3_isolated(client):
    pid = _setup_g2(client)
    res = client.get(f"/api/v0/projects/{pid}/episodes/EP01/n3")
    assert res.status_code == 404
    assert "D-N3" in res.json()["error"]["message"] or "g3" in res.json()["error"]["message"]
