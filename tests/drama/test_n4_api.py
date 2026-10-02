"""026 · HTTP assemble / validate / get / status / consumer / OpenAPI / bare n4."""

from __future__ import annotations

from pathlib import Path

from tests.drama.test_n2_api import _setup_locked
from tests.drama.test_n3_api import _setup_g2


def _attach_refs_via_store(client, pid):
    svc = client.app.state.service
    rec = svc._rec(pid, "EP01")
    data_dir = Path(svc.settings.data_dir)
    cards = rec["n3"]["cards"]
    for card in list(cards.get("characters") or []) + list(cards.get("scenes") or []):
        ident = card["id"]
        role = "face" if card.get("kind") == "character" else "plate"
        path = data_dir / "refs" / f"{ident}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"ref-{ident}".encode("utf-8"))
        card["refs"] = [{"path": str(path), "md5": "abc123", "role": role, "missing_file": False}]
        card["missing_ref"] = False
        card["weak_binding"] = False
    svc._commit(rec)


def _setup_g3_usable(client):
    pid = _setup_locked(client)
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture", "tool_profile": "seedance_2"},
    )
    assert gen.status_code == 200, gen.text
    con = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g2/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert con.status_code == 200, con.text
    mat = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    assert mat.status_code == 200, mat.text
    _attach_refs_via_store(client, pid)
    g3 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g3/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert g3.status_code == 200, g3.text
    assert g3.json()["usable_for_n4"] is True
    return pid


def test_health_lists_dn4(client):
    data = client.get("/health").json()
    assert "D-N4" in data["nodes"]
    assert data["auto_open_dn4"] is False
    assert data["docs_pass"] is False


def test_openapi_n4_copy_served(client):
    res = client.get("/openapi/drama-n4.v0.yaml")
    assert res.status_code == 200
    text = res.text
    assert "0.1.0" in text
    assert "D-N4" in text
    assert "seedance_2" in text
    assert "seedance_2_0" in text
    assert "usable_for_n4_false" in text
    assert "not_ready_for_n4" in text
    assert "force_reassemble" in text
    assert "first_shot_review" in text
    assert "EP##-prompts.jsonl" in text or "EP01-prompts.jsonl" in text
    assert "force_pass_forbidden" in text
    assert "/drama/n4" in text
    assert "usable_for_n4=false" in text


def test_http_assemble_and_consumer(client):
    pid = _setup_g3_usable(client)
    val = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/validate",
        json={"tool_profile": "seedance_2_0"},
    )
    assert val.status_code == 200, val.text
    assert val.json()["written"] is False
    assert val.json()["valid"] is True
    assert val.json()["tool_profile"] == "seedance_2"
    assert val.json()["first_shot_review"]
    asm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"tool_profile": "seedance_2_0", "actor": "yangzhou"},
    )
    assert asm.status_code == 200, asm.text
    body = asm.json()
    assert body["written"] is True
    assert body["started"] is True
    assert body["path"] == "episodes/EP01/EP01-prompts.jsonl"
    assert body["n4"]["tool_profile"] == "seedance_2"
    assert body["lines"]
    assert body["first_shot_review"]["message"]
    assert all("CHAR-" not in (row.get("prompt") or "") for row in body["lines"])
    got = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n4")
    assert got.status_code == 200
    assert got.json()["started"] is True
    st = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/status")
    assert st.status_code == 200
    assert st.json()["assemble_version"] == 1
    assert st.json()["ready_for_n4"] is True
    n4c = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n4-consumer")
    assert n4c.status_code == 200
    assert n4c.json()["started"] is True
    assert n4c.json()["jsonl"]
    assert n4c.json()["prompts_path"]


def test_http_usable_false_validate_soft_assemble_hard(client):
    pid = _setup_locked(client)
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture", "tool_profile": "seedance_2"},
    )
    assert gen.status_code == 200, gen.text
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g2/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g3/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    val = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/validate", json={})
    assert val.status_code == 200, val.text
    assert val.json()["written"] is False
    assert val.json()["valid"] is False
    assert val.json()["missing_refs"]
    asm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"actor": "yangzhou"},
    )
    assert asm.status_code == 409
    err = asm.json()["error"]
    assert err["code"] == "usable_for_n4_false"
    assert err["details"]["written"] is False
    assert err["details"]["missing_refs"]
    n4c = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n4-consumer")
    assert n4c.status_code == 200
    assert n4c.json()["started"] is False


def test_http_not_ready_for_n4(client):
    pid = _setup_g2(client)
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n3/cards/materialize",
        json={"actor": "yangzhou"},
    )
    _attach_refs_via_store(client, pid)
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g3/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    asm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"actor": "yangzhou"},
    )
    assert asm.status_code == 409
    assert asm.json()["error"]["code"] == "not_ready_for_n4"


def test_http_force_pass_forbidden(client):
    pid = _setup_g3_usable(client)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n4/assemble",
        json={"actor": "yangzhou", "force_pass": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"


def test_http_bare_n4_isolated(client):
    pid = _setup_g2(client)
    res = client.get(f"/api/v0/projects/{pid}/episodes/EP01/n4")
    assert res.status_code == 404
    msg = res.json()["error"]["message"]
    assert "D-N4 is not implemented" not in msg
    assert "/drama/n4" in msg
