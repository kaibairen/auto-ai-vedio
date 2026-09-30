const state = { projectId: null, ep: "EP01", g2Blocked: false };

/** 018d GAP-COPY / ERR-SYNC · code → 中文横幅（与 BE catalog 同义，可长短两档） */
const COPY_BANNERS = {
  tool_profile_unset: {
    zh: "尚未选择出片工具。分镜门审仍可进行，但不能标记「可进下一出片节点」。请在需要出片前选择工具；系统会按工具允许的时长档校正各镜秒数。",
    level: "warn",
    slot: "banner",
  },
  duration_bucket_mismatch: {
    zh: "还有镜的时长对不上当前工具档（例如写成了 2–3 秒，而当前工具只允许合法档）。请改秒数或重新吸附后再试。在全部对齐前，不能标记可出片。",
    level: "error",
    slot: "banner",
  },
  ready_for_n4_requires_tool_profile: {
    zh: "请先选择出片工具。未选工具时不能进入出片准备。",
    level: "error",
    slot: "banner",
  },
  named_cast_gate: {
    zh: "还有未入表的具名角色，无法通过分镜门审。",
    level: "error",
    slot: "g2",
  },
  named_cast_missing: {
    zh: "分镜中出现未入表的具名角色，请入表或弱化具名。",
    level: "warn",
    slot: "cast-hint",
  },
  intent_unconfirmed: {
    zh: "请先完成意图确认，再生成大纲。",
    level: "error",
    slot: "banner",
  },
  intent_stale: {
    zh: "意图字段已变更，请重新确认后再生成大纲。",
    level: "error",
    slot: "banner",
  },
  intent_lane_conflict: {
    zh: "预挂与当前赛道不一致。[一键跟预挂改 lane]",
    level: "error",
    slot: "banner",
  },
  lane_required: {
    zh: "生成前必选 female|male（D3 provisional）",
    level: "error",
    slot: "banner",
  },
};

function $(id) { return document.getElementById(id); }
function lane0() {
  return [...document.querySelectorAll("input[name=lane0]")].find((x) => x.checked)?.value || "unset";
}
function lane1() {
  return [...document.querySelectorAll("input[name=lane1]")].find((x) => x.checked)?.value || "";
}
function bannerText(code, fallback) {
  const row = COPY_BANNERS[code];
  return (row && row.zh) || fallback || code;
}
function userErrorMessage(data, code) {
  return data?.error?.messages?.zh || data?.error?.message || bannerText(code, "");
}
function showBanner(msg, ok, level) {
  const el = $("banner");
  el.hidden = !msg;
  el.textContent = msg || "";
  el.classList.remove("warn", "error", "info", "ok");
  if (!msg) return;
  if (ok) el.classList.add("ok");
  else el.classList.add(level === "warn" ? "warn" : "error");
}
function showCastHint(msg) {
  const el = $("cast-hint");
  if (!el) return;
  el.hidden = !msg;
  el.textContent = msg || "";
}
function showScreen(name) {
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.id !== `screen-${name}`; });
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.screen === name));
}
async function api(method, path, body, headers) {
  const res = await fetch(`/api/v0${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(headers || {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    const code = data?.error?.code || res.status;
    const zh = userErrorMessage(data, code);
    const level = (COPY_BANNERS[code] && COPY_BANNERS[code].level) || "error";
    showBanner(`${res.status} ${code}: ${zh}`, false, level);
    if (String(code).startsWith("named_cast_")) {
      showCastHint(zh);
    }
    throw Object.assign(new Error(code), { data, status: res.status, code });
  }
  showBanner("", true);
  return data;
}
function dump(id, data) { $(id).textContent = JSON.stringify(data, null, 2); }
function hdr() {
  $("hdr-meta").textContent = state.projectId ? `${state.projectId} / ${state.ep} · drama` : "未建集";
}

function toolProfile() {
  return $("tool-profile")?.value || "";
}
function shotRows() {
  return [
    {
      shot_id: "S01",
      duration_s: Number($("shot-d1")?.value),
      camera: $("shot-cam1")?.value || "STATIC",
      tool_duration_bucket: $("shot-b1")?.value || undefined,
    },
    {
      shot_id: "S02",
      duration_s: Number($("shot-d2")?.value),
      camera: $("shot-cam2")?.value || "PUSH",
      tool_duration_bucket: $("shot-b2")?.value || undefined,
    },
  ];
}
function namedCastIssues() {
  if (!$("named-gap")?.checked) return [];
  return [{ code: "named_cast_missing", role_name: "沈衡", shot_id: "S01" }];
}
function setChip(text, kind) {
  const el = $("export-chip");
  if (!el) return;
  el.textContent = text;
  el.className = `chip ${kind || ""}`;
}
function setG2Enabled(on) {
  const btn = $("btn-g2-pass");
  if (!btn) return;
  btn.disabled = !on;
  state.g2Blocked = !on;
  const note = $("g2-gate-note");
  if (note) {
    note.hidden = on;
    note.textContent = on ? "" : COPY_BANNERS.named_cast_gate.zh;
  }
}

function applyEvaluateOk(data) {
  const warn = (data.warnings || []).find((w) => w.code === "tool_profile_unset");
  if (warn) {
    showBanner(warn.messages?.zh || warn.message || COPY_BANNERS.tool_profile_unset.zh, false, "warn");
  }
  setChip(data.chip || "出片：未选工具", !toolProfile() ? "warn" : "ok");
  const blocked = Boolean(data.g2_pass_blocked) || namedCastIssues().length > 0;
  setG2Enabled(!blocked);
  if (blocked) showCastHint(COPY_BANNERS.named_cast_missing.zh);
  else showCastHint("");
  dump("e-out", data);
}

async function evaluateCopy(extra) {
  if (!state.projectId) {
    showBanner("请先在 Hub 建集", false, "warn");
    return null;
  }
  const body = {
    tool_profile: toolProfile() || null,
    rows: shotRows(),
    named_cast_issues: namedCastIssues(),
    ...(extra || {}),
  };
  try {
    const data = await api(
      "POST",
      `/projects/${state.projectId}/episodes/${state.ep}/drama/copy-contract/evaluate`,
      body,
    );
    applyEvaluateOk(data);
    return data;
  } catch (err) {
    const code = err.code || err.data?.error?.code;
    if (code === "duration_bucket_mismatch") setChip("出片：时长未对齐", "error");
    if (code === "ready_for_n4_requires_tool_profile") setChip("出片：未选工具", "warn");
    if (code === "named_cast_gate") {
      setG2Enabled(false);
      showCastHint(userErrorMessage(err.data, code));
    }
    dump("e-out", err.data || { error: String(err) });
    return null;
  }
}

document.querySelectorAll(".tabs button").forEach((b) => {
  b.addEventListener("click", () => showScreen(b.dataset.screen));
});

$("btn-proj").onclick = async () => {
  const data = await api("POST", "/projects", { name: $("proj-name").value });
  state.projectId = data.project.id;
  hdr();
  dump("hub-out", data);
};
$("btn-ep").onclick = async () => {
  state.ep = $("ep-id").value;
  const data = await api("POST", `/projects/${state.projectId}/episodes`, {
    episode_id: state.ep,
    pipeline_profile: "drama",
    title: "第一集",
  });
  hdr();
  dump("hub-out", data);
};
$("btn-seed").onclick = async () => {
  const id = $("seed-char").value;
  const data = await api("PUT", `/projects/${state.projectId}/library/characters/${id}`, {
    version: Number($("seed-ver").value),
    name: $("seed-name").value,
    one_line: $("seed-line").value,
  });
  dump("hub-out", data);
};
$("btn-save-brief").onclick = async () => {
  let pin = null;
  const raw = $("pin").value.trim();
  if (raw) pin = JSON.parse(raw);
  const data = await api("PUT", `/projects/${state.projectId}/episodes/${state.ep}/drama/brief`, {
    title_intent: $("title-intent").value,
    pin,
    setting_notes: $("notes").value,
    lane_preference: lane0(),
    actor: "yangzhou",
  });
  dump("a-out", data);
};
$("btn-attach").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/attach`, {
    character_id: $("att-id").value,
    version: Number($("att-ver").value),
    actor: "yangzhou",
  });
  dump("a-out", data);
};
$("btn-detach").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/detach`, {
    character_id: $("att-id").value,
  });
  dump("a-out", data);
};
$("btn-gen").onclick = async () => {
  const lane = lane1();
  if (!lane) {
    showBanner(`422 lane_required: ${COPY_BANNERS.lane_required.zh}`, false, "error");
    return;
  }
  const hint = $("intent-hint");
  if (hint) hint.hidden = false;
  try {
    const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/outline`, {
      lane,
      provider: "fixture",
      actor: "yangzhou",
    });
    $("body-md").value = data.outline.body_md;
    $("shot-cap").value = data.outline.shot_cap;
    dump("cast-out", data.cast);
  } catch (err) {
    if (err.code === "intent_unconfirmed" || err.code === "intent_stale") {
      if (hint) hint.hidden = false;
    }
    dump("cast-out", err.data || { error: String(err) });
  }
};
$("btn-save-outline").onclick = async () => {
  try {
    const data = await api("PUT", `/projects/${state.projectId}/episodes/${state.ep}/drama/outline`, {
      body_md: $("body-md").value,
      shot_cap: Number($("shot-cap").value),
      unlock_edit: $("unlock").checked,
      actor: "yangzhou",
    });
    dump("cast-out", data.outline);
  } catch (err) {
    dump("cast-out", err.data || { error: String(err) });
  }
};
$("btn-reset").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/outline/reset`, {
    unlock_edit: $("unlock").checked,
  });
  $("body-md").value = data.outline.body_md;
};
async function confirm(decision) {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/gates/g1b/confirm`, {
    decision,
    actor: $("actor").value,
    note: $("note").value || undefined,
  });
  dump("c-out", data);
  dump("d-out", { locked: data.gate.locked, next_edges: data.next_edges, confirmed_by: data.outline?.confirmed_by });
}
$("btn-pass").onclick = () => confirm("pass");
$("btn-reject").onclick = () => confirm("reject");
$("btn-downstream").onclick = async () => {
  try {
    const data = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}/drama/downstream`);
    dump("dn-out", data);
  } catch (err) {
    dump("dn-out", err.data || { error: String(err) });
  }
};

if ($("btn-eval-copy")) {
  $("btn-eval-copy").onclick = () => evaluateCopy({});
  $("btn-ready-n4").onclick = () => evaluateCopy({ ready_for_n4: true });
  $("btn-g2-pass").onclick = () => evaluateCopy({ g2_pass: true });
  $("named-gap").onchange = () => {
    const blocked = namedCastIssues().length > 0;
    setG2Enabled(!blocked);
    if (blocked) {
      showCastHint("具名配角 issue 未清时，G2 pass 将被阻断。");
    } else {
      showCastHint("");
    }
  };
  $("tool-profile").onchange = () => {
    if (toolProfile()) {
      showBanner("更换出片工具后，将按新工具的允许秒数整表重算时长档。请确认后再出片。", true, "info");
      $("banner").classList.remove("ok");
      $("banner").classList.add("info");
    }
    evaluateCopy({});
  };
  setChip("出片：未选工具", "warn");
  setG2Enabled(true);
}
hdr();
