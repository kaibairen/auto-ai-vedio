"""021b · Screen H minimal card list. F1 warn-only. ForcePass=never."""

from __future__ import annotations

from pathlib import Path

WB = Path("apps/workbench")


def test_workbench_021b_screen_h_card_list_and_badges():
    html = (WB / "index.html").read_text(encoding="utf-8")
    js = (WB / "drama.js").read_text(encoding="utf-8")
    css = (WB / "drama.css").read_text(encoding="utf-8")
    assert 'id="screen-h"' in html
    assert 'id="h-char-tbody"' in html
    assert 'id="h-scene-tbody"' in html
    assert 'id="h-char-table"' in html
    assert 'id="h-scene-table"' in html
    assert "<th>id</th>" in html
    assert "<th>name</th>" in html
    assert "<th>ref</th>" in html
    assert 'id="h-g3-badge"' in html
    assert 'id="usable-for-n4"' in html
    assert 'id="g3-weak-bind-banner"' in html
    assert 'id="h-g3-locked"' in html
    assert "usable_for_n4=false · G3 locked=" not in html
    assert "usable_for_n4=false · G3 locked=" not in js
    assert "视觉弱绑定 · 下游一致性自负" in html
    assert "视觉弱绑定 · 下游一致性自负" in js
    assert "isG3Locked" in js
    assert "attached@" in js
    assert 'text: "local"' in js
    assert 'text: "none"' in js
    assert "isG2Ready" in js
    assert "confirmed_by" in js
    assert "applyHWriteGate" in js
    assert "上游门 G2 未锁，不能进 D-N3" in js
    assert "上游门 G1b 未锁，不能进 D-N2" in js
    assert "details?.gate" in js or "details.gate" in js
    assert "btn-n3-mat" in html
    assert "btn-g3-pass" in html
    assert "btn-g3-reject" in html
    assert "force_pass" not in js
    assert "chip.attached" in css
    assert "chip.local" in css
    assert "chip.none" in css


def test_workbench_021b_does_not_disable_g3_on_weak_binding():
    js = (WB / "drama.js").read_text(encoding="utf-8")
    assert "paintHWeak" in js
    assert "btn-g3-pass" in js
    assert "btn-g3-reject" in js
    weak_fn = js.split("function paintHWeak", 1)[1].split("function ", 1)[0]
    assert "disabled" not in weak_fn
    write_fn = js.split("function applyHWriteGate", 1)[1].split("function ", 1)[0]
    assert "btn-n3-mat" in write_fn
    assert "btn-g3-pass" not in write_fn
    assert "btn-g3-reject" not in write_fn


def test_workbench_021b_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "h-char-tbody" in res.text
    assert "视觉弱绑定 · 下游一致性自负" in res.text
    assert "h-g3-badge" in res.text
    assert "usable-for-n4" in res.text
    assert "g3-weak-bind-banner" in res.text
    js = client.get("/workbench/static/drama.js")
    assert js.status_code == 200
    assert "上游门 G2 未锁，不能进 D-N3" in js.text
    assert "isG2Ready" in js.text
    assert "force_pass" not in js.text
