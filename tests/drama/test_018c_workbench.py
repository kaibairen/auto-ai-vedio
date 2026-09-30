"""018c workbench HTML/JS smoke + HTTP path. ForcePass=never. docs≠PASS."""

from __future__ import annotations

from pathlib import Path

from aiv_drama_n2.named_cast import blocking_named_cast_issues

WB = Path("apps/workbench")


def test_workbench_html_has_e_f_g_and_a2():
    html = (WB / "index.html").read_text(encoding="utf-8")
    js = (WB / "drama.js").read_text(encoding="utf-8")
    assert 'id="screen-a2"' in html
    assert 'id="btn-confirm-intent"' in html
    assert "确认意图" in html
    assert 'id="screen-e"' in html
    assert 'id="screen-f"' in html
    assert 'id="screen-g"' in html
    assert 'id="e-table"' in html
    assert 'id="e-tbody"' in html
    assert ">seq<" in html
    assert "镜号" in html
    assert "bridge" in html
    assert "景别" in html
    assert "运镜" in html
    assert "人物" in html
    assert "台词" in html
    assert 'id="btn-g2-pass"' in html
    assert 'id="btn-g2-reject"' in html
    assert 'id="b-skill"' in html
    assert 'id="e-skill"' in html
    assert "本次 Skill" in html
    assert "进入 D-N2 分镜" in html
    assert "v${oldV} → v${newV}" in js or "v${oldV} → v${newV}" in js.replace(" ", "")
    assert "blockingNamedCast" in js
    assert "named_cast_auto_merged" in js
    assert "isStoryboardLocked" in js
    assert "confirmed_by" in js
    assert "force_pass" not in html.lower()
    assert "force_pass" not in js
    assert "一键开卡" not in html or "无一键开卡" in html


def test_workbench_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "screen-e" in res.text
    assert "btn-g2-pass" in res.text
    js = client.get("/workbench/static/drama.js")
    assert js.status_code == 200
    assert "blockingNamedCast" in js.text
    css = client.get("/workbench/static/drama.css")
    assert css.status_code == 200


def test_http_018c_path_episode_and_skill_and_g2_gate(client):
    proj = client.post("/api/v0/projects", json={"name": "wb018c"}).json()["project"]
    pid = proj["id"]
    client.put(
        f"/api/v0/projects/{pid}/library/characters/CHAR-01",
        json={"name": "林晚", "one_line": "重生女主", "version": 1},
    )
    client.post(
        f"/api/v0/projects/{pid}/episodes",
        json={"episode_id": "EP01", "pipeline_profile": "drama", "title": "第一集"},
    )
    client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/brief",
        json={
            "title_intent": "被流放的庶女在边关翻盘",
            "lane_preference": "female",
            "hero_one_line": "重生女主",
        },
    )
    bare = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
    )
    assert bare.status_code == 422
    assert bare.json()["error"]["code"] == "intent_unconfirmed"
    confirm = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/intent/confirm",
        json={"actor": "eng-018c"},
    )
    assert confirm.status_code == 200
    outline = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
    )
    assert outline.status_code == 200
    assert outline.json().get("skill_paths")
    g1b = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g1b/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert g1b.status_code == 200
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    )
    assert gen.status_code == 200
    body = gen.json()
    assert body["storyboard"]["locked"] is False
    assert body.get("skill_paths")
    assert "borrowed_dongman" in (body.get("storyboard_skill") or body["storyboard"]["storyboard_skill"])
    ep = client.get(f"/api/v0/projects/{pid}/episodes/EP01")
    assert ep.status_code == 200
    env = ep.json()
    assert env["intent"]["confirmed"] is True
    assert env["episode"]["pipeline_profile"] == "drama"
    assert env["lane_preference"] == "female"
    side = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/cast/sidecar-add",
        json={"name": "CODEX王子", "one_line": "弹窗反派"},
    )
    assert side.status_code == 200
    hint = (side.json().get("hints") or [{}])[0]
    assert hint.get("cast_version_old") is not None
    assert hint.get("cast_version_new") == hint["cast_version_old"] + 1
    val = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/validate", json={})
    assert val.status_code == 200
    leftover = blocking_named_cast_issues(val.json().get("issues") or [])
    if leftover:
        blocked = client.post(
            f"/api/v0/projects/{pid}/episodes/EP01/gates/g2/confirm",
            json={"decision": "pass", "actor": "yangzhou"},
        )
        assert blocked.status_code == 422
        assert blocked.json()["error"]["code"] == "named_cast_gate"
