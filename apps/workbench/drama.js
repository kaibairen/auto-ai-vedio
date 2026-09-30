const state = {
  projectId: null,
  ep: "EP01",
  intent: { confirmed: false, fingerprint: null },
  check: { conflict: false, can_confirm: false, suggested_lane: null },
  sawConfirmed: false,
};

function $(id) { return document.getElementById(id); }
function lane0() {
  return [...document.querySelectorAll("input[name=lane0]")].find((x) => x.checked)?.value || "unset";
}
function lane1() {
  return [...document.querySelectorAll("input[name=lane1]")].find((x) => x.checked)?.value || "";
}
function lane2() {
  return [...document.querySelectorAll("input[name=lane2]")].find((x) => x.checked)?.value || "unset";
}
function setLane2(value) {
  document.querySelectorAll("input[name=lane2]").forEach((el) => {
    el.checked = el.value === value;
  });
}
function showBanner(msg, ok) {
  const el = $("banner");
  el.hidden = !msg;
  el.textContent = msg || "";
  el.style.background = ok ? "#1d3a28" : "#3a2020";
}
function showScreen(name) {
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.id !== `screen-${name}`; });
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.screen === name));
  if (name === "a2" || name === "b") {
    refreshIntent().catch(() => {});
  }
}
function isIntentConfirmed() {
  return state.intent && state.intent.confirmed === true;
}
function applyIntent(data) {
  state.intent = data.intent || { confirmed: false, fingerprint: null };
  state.check = data;
  const confirmed = isIntentConfirmed();
  if (confirmed) state.sawConfirmed = true;
  const stale = !confirmed && state.sawConfirmed;
  ["hdr-intent", "intent-badge"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.textContent = confirmed ? "intent:confirmed" : (stale ? "intent:stale · 须重确认" : "intent:draft");
    el.classList.toggle("ok", confirmed);
    el.classList.toggle("warn", stale);
    el.classList.toggle("muted", !confirmed);
  });
  const gen = $("btn-gen");
  if (gen) gen.disabled = !confirmed;
  const hint = $("gen-hint");
  if (hint) hint.hidden = confirmed;
  const bar = $("conflict-bar");
  if (bar) {
    const conflict = Boolean(data.conflict);
    bar.hidden = !conflict;
    if (conflict) {
      $("conflict-text").textContent =
        `当前赛道 ${data.current_lane || lane2()} 与预挂频向 ${(data.preattach_lanes || []).join("/") || "?"} 冲突。未对齐不可确认。`;
    }
  }
  const confirmBtn = $("btn-confirm-intent");
  if (confirmBtn) {
    const laneOk = lane2() === "female" || lane2() === "male";
    const titleOk = Boolean(($("a2-title").value || "").trim() || ($("a2-pin").value || "").trim());
    const heroOk = Boolean(($("a2-hero").value || "").trim());
    confirmBtn.disabled = !laneOk || !titleOk || !heroOk || Boolean(data.conflict);
  }
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
    if (code === "intent_unconfirmed") {
      showBanner("422 intent_unconfirmed: 请先完成意图确认，再生成大纲。", false);
      applyIntent({ intent: { confirmed: false }, conflict: state.check.conflict });
    } else if (code === "intent_stale") {
      showBanner("422 intent_stale: 意图已过期 · 请回 A2 重确认", false);
      applyIntent({ intent: { confirmed: false, fingerprint: null }, conflict: false });
    } else {
      showBanner(`${res.status} ${code}: ${data?.error?.message || ""}`, false);
    }
    throw Object.assign(new Error(code), { data, status: res.status });
  }
  showBanner("", true);
  return data;
}
function dump(id, data) { $(id).textContent = JSON.stringify(data, null, 2); }
function hdr() {
  $("hdr-meta").textContent = state.projectId ? `${state.projectId} / ${state.ep} · drama` : "未建集";
}
function parsePin(raw) {
  const text = (raw || "").trim();
  if (!text) return null;
  try { return JSON.parse(text); } catch { return { raw: text }; }
}

document.querySelectorAll(".tabs button").forEach((b) => {
  b.addEventListener("click", () => showScreen(b.dataset.screen));
});

async function refreshIntent() {
  if (!state.projectId) {
    applyIntent({ intent: { confirmed: false }, conflict: false, can_confirm: false });
    return null;
  }
  const data = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}/drama/intent`);
  applyIntent(data);
  dump("a2-out", data);
  $("a2-preattach").textContent = JSON.stringify({
    preattach_lanes: data.preattach_lanes,
    hero_one_line: data.hero_one_line,
    fingerprint_current: data.fingerprint_current,
  }, null, 2);
  $("preattach-empty").hidden = Boolean((data.preattach_lanes || []).length);
  return data;
}

async function saveA2Draft() {
  let pin = parsePin($("a2-pin").value);
  const data = await api("PUT", `/projects/${state.projectId}/episodes/${state.ep}/drama/brief`, {
    title_intent: $("a2-title").value,
    pin,
    setting_notes: $("notes") ? $("notes").value : undefined,
    lane_preference: lane2(),
    hero_one_line: $("a2-hero").value,
    actor: "yangzhou",
  });
  $("title-intent").value = $("a2-title").value;
  dump("a2-out", data);
  await refreshIntent();
  return data;
}

$("btn-proj").onclick = async () => {
  const data = await api("POST", "/projects", { name: $("proj-name").value });
  state.projectId = data.project.id;
  state.sawConfirmed = false;
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
  state.sawConfirmed = false;
  hdr();
  dump("hub-out", data);
  await refreshIntent();
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
    hero_one_line: $("a2-hero").value || undefined,
    actor: "yangzhou",
  });
  $("a2-title").value = $("title-intent").value;
  $("a2-pin").value = $("pin").value;
  setLane2(lane0());
  dump("a-out", data);
  await refreshIntent();
};
$("btn-goto-a2").onclick = () => {
  $("a2-title").value = $("title-intent").value;
  $("a2-pin").value = $("pin").value;
  setLane2(lane0());
  showScreen("a2");
};
$("btn-attach").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/attach`, {
    character_id: $("att-id").value,
    version: Number($("att-ver").value),
    actor: "yangzhou",
  });
  dump("a-out", data);
  await refreshIntent();
};
$("btn-detach").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/detach`, {
    character_id: $("att-id").value,
  });
  dump("a-out", data);
  await refreshIntent();
};
$("btn-a2-attach").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/attach`, {
    character_id: $("a2-att-id").value,
    version: Number($("a2-att-ver").value),
    actor: "yangzhou",
  });
  dump("a2-out", data);
  await refreshIntent();
};
$("btn-a2-detach").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/detach`, {
    character_id: $("a2-att-id").value,
  });
  dump("a2-out", data);
  await refreshIntent();
};
$("btn-save-a2").onclick = () => saveA2Draft();
$("btn-a2-back").onclick = () => showScreen("a");
$("btn-reorg").onclick = async () => {
  if (!state.projectId) return;
  const brief = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}/drama/brief`);
  $("a2-title").value = brief.brief.title_intent || "";
  $("a2-pin").value = brief.brief.pin ? JSON.stringify(brief.brief.pin) : "";
  $("a2-hero").value = brief.brief.hero_one_line || $("a2-hero").value;
  setLane2(brief.brief.lane_preference || "unset");
  dump("a2-out", { reorganize: true, outline_requested: false, brief: brief.brief });
  await refreshIntent();
};
$("btn-thin-save").onclick = async () => {
  const id = $("thin-id").value;
  await api("PUT", `/projects/${state.projectId}/library/characters/${id}`, {
    version: Number($("thin-ver").value),
    name: $("thin-name").value,
    one_line: $("thin-line").value,
  });
  $("a2-hero").value = $("thin-line").value;
  await saveA2Draft();
  await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/attach`, {
    character_id: id,
    version: Number($("thin-ver").value),
    actor: "yangzhou",
  });
  await refreshIntent();
};
$("btn-follow-b").onclick = async () => {
  const suggested = state.check.suggested_lane;
  if (!suggested) return;
  setLane2(suggested);
  document.querySelectorAll("input[name=lane0]").forEach((el) => { el.checked = el.value === suggested; });
  await saveA2Draft();
};
$("btn-confirm-intent").onclick = async () => {
  await saveA2Draft();
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/intent/confirm`, {
    actor: "yangzhou",
  });
  applyIntent(data);
  dump("a2-out", data);
  showBanner("意图已确认，可去 Outline 生成大纲。", true);
};
$("btn-gen").onclick = async () => {
  if (!isIntentConfirmed()) {
    showBanner("请先完成意图确认，再生成大纲。", false);
    return;
  }
  const lane = lane1();
  if (!lane) {
    showBanner("422 lane_required: 生成前必选 female|male（D3 provisional）", false);
    return;
  }
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/outline`, {
    lane,
    provider: "fixture",
    actor: "yangzhou",
  });
  $("body-md").value = data.outline.body_md;
  $("shot-cap").value = data.outline.shot_cap;
  dump("cast-out", data.cast);
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
document.querySelectorAll("input[name=lane2]").forEach((el) => {
  el.addEventListener("change", () => {
    const confirmBtn = $("btn-confirm-intent");
    if (confirmBtn && state.check.conflict && el.value !== state.check.suggested_lane) {
      confirmBtn.disabled = true;
    }
  });
});
applyIntent({ intent: { confirmed: false }, conflict: false });
hdr();
