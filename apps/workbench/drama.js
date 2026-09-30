const state = { projectId: null, ep: "EP01" };

function $(id) { return document.getElementById(id); }
function lane0() {
  return [...document.querySelectorAll("input[name=lane0]")].find((x) => x.checked)?.value || "unset";
}
function lane1() {
  return [...document.querySelectorAll("input[name=lane1]")].find((x) => x.checked)?.value || "";
}
function showBanner(msg, ok) {
  const el = $("banner");
  el.hidden = !msg;
  el.textContent = msg || "";
  el.style.background = ok ? "#1d3a28" : "#3a2020";
}
function showCastHint(data) {
  const el = $("cast-hint");
  if (!el) return;
  const hints = data?.hints || [];
  const named = (data?.validate_warnings || data?.issues || []).filter((i) =>
    String(i.code || "").startsWith("named_cast_")
  );
  if (data?.cast_changed || hints.length || named.length) {
    const hintMsg = hints[0]?.message || "角色表已更新；G1b 仍锁定，大纲正文未改。";
    const namedMsg = named.length
      ? `具名配角 issue ${named.length} 条（${named.map((i) => i.code).join(", ")}）— G2 pass 将被阻断。`
      : "";
    el.hidden = false;
    el.textContent = [data?.cast_changed ? hintMsg : "", namedMsg].filter(Boolean).join(" ");
  } else {
    el.hidden = true;
    el.textContent = "";
  }
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
    showBanner(`${res.status} ${code}: ${data?.error?.message || ""}`, false);
    throw Object.assign(new Error(code), { data, status: res.status });
  }
  showBanner("", true);
  return data;
}
function dump(id, data) { $(id).textContent = JSON.stringify(data, null, 2); }
function hdr() {
  $("hdr-meta").textContent = state.projectId ? `${state.projectId} / ${state.ep} · drama` : "未建集";
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
$("btn-sb-gen").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard/generate`, {
    provider: "fixture",
    actor: "yangzhou",
  });
  showCastHint(data);
  dump("e-out", data);
};
$("btn-sb-val").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard/validate`, {});
  showCastHint(data);
  dump("e-out", data);
};
$("btn-sidecar").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/sidecar-add`, {
    name: $("side-name").value || "CODEX王子",
    one_line: $("side-line").value || undefined,
    actor: "yangzhou",
  });
  showCastHint(data);
  dump("e-out", data);
};
async function confirmG2(decision) {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/gates/g2/confirm`, {
    decision,
    actor: $("g2-actor").value,
    note: $("g2-note").value || undefined,
  });
  showCastHint(data);
  dump("e-out", data);
}
$("btn-g2-pass").onclick = () => confirmG2("pass");
$("btn-g2-reject").onclick = () => confirmG2("reject");
hdr();
