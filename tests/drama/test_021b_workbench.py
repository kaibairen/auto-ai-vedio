"""021b · Screen H minimal card list. F1 warn-only. ForcePass=never."""

from __future__ import annotations

import shutil
import subprocess
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
    assert "工作台无钥" in html
    assert "btn-n3-look" in html
    assert 'id="h-cost-bar"' in html
    assert 'id="h-look-gate-hint"' in html
    assert "/look-ledger" in js
    assert "/drama/n3/look-ledger" not in js
    assert "/look_ledger" not in js
    assert "/cost" in js
    assert "/cost-ledger" not in js
    assert "LOOK_ATTEMPT_CAP" in js
    assert "needs_redraw_consent" in js
    assert "has_user_redraw_consent" in js
    assert "h-look-char" in html
    assert "h-face-ref" in html
    assert "h-look-dry" in html
    assert "generate-look" in html
    assert "generate-look" in js
    assert "cards/generate-look" in js
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
    assert "btn-n3-look" in write_fn
    assert "lookBlockedByCost" in write_fn
    assert "lookBlockedByLedger" in write_fn
    assert "lookPrerollBlocksGenerate" in write_fn
    assert "btn-g3-pass" not in write_fn
    assert "btn-g3-reject" not in write_fn


def test_workbench_look_preroll_fail_closed():
    """Cost / look-ledger null or unusable must disable look and block click POST."""
    js = (WB / "drama.js").read_text(encoding="utf-8")
    cost_fn = js.split("function lookBlockedByCost", 1)[1].split("function ", 1)[0]
    ledger_fn = js.split("function lookBlockedByLedger", 1)[1].split("function ", 1)[0]
    assert "if (!usableCostSnapshot(cost)) return true;" in cost_fn
    assert "if (!usableLookLedger(ledger)) return true;" in ledger_fn
    assert "if (!cost) return false" not in js
    assert "if (!ledger) return false" not in js
    look = js.split('if ($("btn-n3-look"))', 1)[1].split("async function confirmG3", 1)[0]
    assert look.find("lookPrerollBlocksGenerate") < look.find("refreshCostBar")
    assert look.find("lookPrerollBlocksGenerate") < look.find("cards/generate-look")
    assert look.find("return") < look.find("refreshCostBar")
    assert "cards/generate-look" in look
    node = shutil.which("node")
    assert node, "node required to execute look-gate fail-closed cases"
    harness = r"""
const fs = require("fs");
const js = fs.readFileSync("apps/workbench/drama.js", "utf8");
const start = js.indexOf("const LOOK_ATTEMPT_CAP");
const end = js.indexOf("function paintHLookGateHint");
eval(js.slice(start, end));
const okCost = { blocked: false, remaining: 60 };
const okLedger = { attempts_used: 0, needs_redraw_consent: false, has_user_redraw_consent: false };
const cases = [
  ["cost_null", lookBlockedByCost(null), true],
  ["cost_undefined", lookBlockedByCost(undefined), true],
  ["cost_empty", lookBlockedByCost({}), true],
  ["cost_ok", lookBlockedByCost(okCost), false],
  ["cost_blocked", lookBlockedByCost({ blocked: true, remaining: 1 }), true],
  ["cost_zero", lookBlockedByCost({ blocked: false, remaining: 0 }), true],
  ["ledger_null", lookBlockedByLedger(null), true],
  ["ledger_empty", lookBlockedByLedger({}), true],
  ["ledger_ok", lookBlockedByLedger(okLedger), false],
  ["ledger_cap", lookBlockedByLedger({ attempts_used: 2, needs_redraw_consent: false, has_user_redraw_consent: false }), true],
  ["ledger_needs", lookBlockedByLedger({ attempts_used: 1, needs_redraw_consent: true, has_user_redraw_consent: false }), true],
];
const failed = cases.filter(([, got, want]) => got !== want).map(([name, got, want]) => ({ name, got, want }));
if (failed.length) {
  console.error(JSON.stringify(failed));
  process.exit(1);
}
"""
    proc = subprocess.run([node, "-e", harness], cwd=".", check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_workbench_021b_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "h-char-tbody" in res.text
    assert "工作台无钥" in res.text
    assert "视觉弱绑定 · 下游一致性自负" in res.text
    assert "h-g3-badge" in res.text
    assert "usable-for-n4" in res.text
    assert "g3-weak-bind-banner" in res.text
    js = client.get("/workbench/static/drama.js")
    assert js.status_code == 200
    assert "上游门 G2 未锁，不能进 D-N3" in js.text
    assert "X-AIV-User-Grant" not in js.text
    assert "AIV_USER_GRANT_SECRET" not in js.text
    assert "not available in the workbench" in js.text
    assert "isG2Ready" in js.text
    assert "force_pass" not in js.text
    assert "look-ledger" in js.text
    assert "/drama/n3/look-ledger" not in js.text
    assert "if (!usableCostSnapshot(cost)) return true;" in js.text
    assert "if (!usableLookLedger(ledger)) return true;" in js.text
    assert "lookPrerollBlocksGenerate" in js.text
    assert "if (!cost) return false" not in js.text
    assert "user_consent" not in js.text
