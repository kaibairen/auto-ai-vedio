const state = {
  projectId: null,
  ep: "EP01",
  intent: { confirmed: false, fingerprint: null },
  check: { conflict: false, can_confirm: false, suggested_lane: null },
  sawConfirmed: false,
  seenCastVersion: 0,
  cast: null,
  storyboard: null,
  validate: null,
  episode: null,
  g1bLocked: false,
  selectedShot: null,
};

/** 018d GAP-COPY · code → 中文横幅（intent/named_cast 文案与 #12 同句，不另起） */
const COPY_BANNERS = {
  tool_profile_unset: {
    zh: "尚未选择出片工具。分镜门审仍可进行，但不能标记「可进下一出片节点」。请在需要出片前选择工具；系统会按工具允许的时长档校正各镜秒数。",
    level: "warn",
  },
  duration_bucket_mismatch: {
    zh: "还有镜的时长对不上当前工具档（例如写成了 2–3 秒，而当前工具只允许合法档）。请改秒数或重新吸附后再试。在全部对齐前，不能标记可出片。",
    level: "error",
  },
  ready_for_n4_requires_tool_profile: {
    zh: "请先选择出片工具。未选工具时不能进入出片准备。",
    level: "error",
  },
  named_cast_gate: {
    zh: "还有未入表的具名角色，无法通过分镜门审。",
    level: "error",
  },
  named_cast_missing: {
    zh: "分镜中出现未入表的具名角色，请入表或弱化具名。",
    level: "warn",
  },
  intent_unconfirmed: {
    zh: "请先完成意图确认，再生成大纲。",
    level: "error",
  },
  intent_stale: {
    zh: "意图已过期 · 请回 A2 重确认",
    level: "error",
  },
  intent_lane_conflict: {
    zh: "预挂与当前赛道不一致。[一键跟预挂改 lane]",
    level: "error",
  },
};

const SHOT_SIZE_ZH = { ELS: "远景", LS: "全景", MS: "中景", CU: "近景", ECU: "特写" };
const CAMERA_ZH = {
  STATIC: "固定", PUSH: "推", PULL: "拉", PAN_H: "横摇", PAN_V: "垂直摇",
  TRACK: "跟", TRUCK: "移", CRANE_UP: "升", CRANE_DOWN: "降", ORBIT: "环绕",
  HANDHELD: "手持", POV: "主观", OTS: "过肩", DEEP_FOCUS: "深焦", ROLL: "旋转",
  DOLLY_ZOOM: "滑动变焦", WHIP_PUSH: "急推", WHIP_PULL: "急拉", STATIC_TO_MOVE: "静动转换",
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
  if (!msg) {
    el.style.background = "";
    return;
  }
  if (ok) {
    el.classList.add("ok");
    el.style.background = "#1d3a28";
    return;
  }
  const kind = level === "warn" ? "warn" : (level === "info" ? "info" : "error");
  el.classList.add(kind);
  el.style.background = kind === "warn" ? "#3a3418" : (kind === "info" ? "#1d2a3a" : "#3a2020");
}
function toolProfile() {
  return $("tool-profile")?.value || "";
}
function setExportChip(text, kind) {
  const el = $("export-chip");
  if (!el) return;
  el.textContent = text || "出片：未选工具";
  el.className = `chip ${kind || ""}`;
}
function paintExportChip(issues, profile) {
  const chosen = profile || toolProfile();
  if (!chosen) {
    setExportChip("出片：未选工具", "warn");
    return;
  }
  const mismatch = (issues || []).some((i) => i.code === "duration_bucket_mismatch");
  if (mismatch) setExportChip("出片：时长未对齐", "error");
  else setExportChip(`出片：时长已对齐 · ${chosen}`, "ok");
}
function applyGapCopyIssues(issues, profile) {
  const list = issues || [];
  paintExportChip(list, profile);
  const mismatch = list.find((i) => i.code === "duration_bucket_mismatch");
  if (mismatch) {
    showBanner(mismatch.messages?.zh || mismatch.message || COPY_BANNERS.duration_bucket_mismatch.zh, false, "error");
    return;
  }
  const unset = list.find((i) => i.code === "tool_profile_unset");
  if (unset) {
    showBanner(unset.messages?.zh || unset.message || COPY_BANNERS.tool_profile_unset.zh, false, "warn");
  }
}
function isStoryboardLocked(sb) {
  if (!sb) return false;
  return sb.locked === true && Boolean(sb.confirmed_by);
}
function blockingNamedCast(issues) {
  const informational = new Set(["named_cast_auto_merged", "named_cast_sidecar_added"]);
  return (issues || []).filter((i) => {
    const code = String(i.code || "");
    return code.startsWith("named_cast_") && !informational.has(code);
  });
}
function hardErrors(issues) {
  return (issues || []).filter((i) => i.severity === "error");
}
function redactSkillPath(path) {
  const text = String(path || "");
  if (!text) return "";
  if (text === "none") return "none";
  if (/^(\/home\/|\/Users\/|~\/|\\\\|[A-Za-z]:\\)/.test(text)) return "«redacted»";
  return text;
}
function hintVersions(data) {
  const hint = (data?.hints && data.hints[0]) || {};
  const oldV = hint.cast_version_old ?? data?.hints?.cast_version_old;
  const newV = hint.cast_version_new ?? hint.cast_version ?? data?.hints?.cast_version_new
    ?? data?.cast?.version;
  return { oldV, newV, hint };
}
function showCastHint(data) {
  const el = $("cast-hint");
  if (!el) return;
  const hints = Array.isArray(data?.hints) ? data.hints : [];
  const named = blockingNamedCast(data?.validate_warnings || data?.issues || []);
  const { oldV, newV } = hintVersions(data);
  const bumped = data?.cast_changed || (newV != null && state.seenCastVersion && Number(newV) > Number(state.seenCastVersion));
  if (bumped || hints.length || named.length) {
    let hintMsg = "";
    if (bumped || data?.cast_changed) {
      if (oldV != null && newV != null) {
        hintMsg = `角色表已更新（v${oldV} → v${newV}）。下拉已刷新；大纲门 G1b 仍锁定，未改大纲正文。`;
      } else {
        hintMsg = hints[0]?.message || "角色表已更新；G1b 仍锁定，大纲正文未改。";
      }
    }
    const namedMsg = named.length
      ? `具名配角 issue ${named.length} 条（${named.map((i) => i.code).join(", ")}）— G2 pass 将被阻断。`
      : "";
    el.hidden = false;
    el.textContent = [hintMsg, namedMsg].filter(Boolean).join(" ");
    el.onclick = () => {
      if (newV != null) state.seenCastVersion = Number(newV);
      el.hidden = true;
    };
  } else {
    el.hidden = true;
    el.textContent = "";
  }
}
function renderSkillStrip(detailsId, bodyId, data) {
  const box = $(detailsId);
  const body = $(bodyId);
  if (!box || !body) return;
  const flag = data?.storyboard_skill || data?.skill_flag || (data?.outline && data.skill_paths);
  const paths = (data?.skill_paths || []).filter((p) => p && p !== "none");
  const excerpt = data?.skill_excerpt;
  const excerpts = data?.excerpts || [];
  if (!flag && !paths.length && !excerpt && !excerpts.length) {
    box.hidden = true;
    body.innerHTML = "";
    return;
  }
  box.hidden = false;
  const rows = [];
  if (data?.storyboard_skill) {
    rows.push(`<div>旗标: storyboard_skill = <code>${escapeHtml(data.storyboard_skill)}</code></div>`);
  } else if (paths.length) {
    rows.push("<div>旗标: outline skill = true</div>");
  }
  if (paths.length && !flag && !data?.storyboard_skill) {
    rows.push('<div class="hint">旗标与 paths 不一致</div>');
  }
  if (paths.length) {
    rows.push("<div>paths:</div><ul>" + paths.map((p) => `<li><code>${escapeHtml(redactSkillPath(p))}</code></li>`).join("") + "</ul>");
  } else {
    rows.push("<div>本次无 Skill 摘录（none）</div>");
  }
  if (excerpts.length) {
    rows.push("<div>excerpt / hash:</div><ul>" + excerpts.map((ex) => {
      const p = redactSkillPath(ex.path || "");
      const bits = [p, ex.chars != null ? `${ex.chars} chars` : "", ex.hash ? `sha256:${ex.hash}` : ""].filter(Boolean);
      return `<li><code>${escapeHtml(bits.join(" · "))}</code></li>`;
    }).join("") + "</ul>");
  } else if (excerpt && excerpt !== "none") {
    rows.push(`<details><summary>摘录（折叠）</summary><pre class="out">${escapeHtml(String(excerpt).slice(0, 2000))}</pre></details>`);
  }
  body.innerHTML = rows.join("");
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function showScreen(name) {
  document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.id !== `screen-${name}`; });
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.screen === name));
  if (name === "a2" || name === "b") {
    refreshIntent().catch(() => {});
  }
  if (name === "hub" || name === "e" || name === "f" || name === "g" || name === "d") {
    refreshEpisodeChrome().catch(() => {});
  }
  if (name === "e") refreshScreenE().catch(() => {});
  if (name === "f") refreshScreenF().catch(() => {});
  if (name === "g") refreshScreenG().catch(() => {});
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
    } else if (code === "named_cast_gate") {
      showBanner(`422 named_cast_gate: ${data?.error?.message || "还有未入表的具名角色，无法通过分镜门审。"}`, false);
      applyG2PassGate(data?.error?.details?.issues || [{ code: "named_cast_gate" }]);
    } else if (code === "duration_bucket_mismatch") {
      showBanner(`422 duration_bucket_mismatch: ${userErrorMessage(data, code)}`, false, "error");
      setExportChip("出片：时长未对齐", "error");
    } else if (code === "ready_for_n4_requires_tool_profile") {
      showBanner(`422 ready_for_n4_requires_tool_profile: ${userErrorMessage(data, code)}`, false, "error");
      setExportChip("出片：未选工具", "warn");
    } else if (code === "upstream_unlocked") {
      showBanner("409 upstream_unlocked: 上游门 G1b 未锁，不能进 D-N2。", false);
      state.g1bLocked = false;
      applyEGate();
    } else {
      showBanner(`${res.status} ${code}: ${data?.error?.message || ""}`, false);
    }
    throw Object.assign(new Error(code), { data, status: res.status });
  }
  showBanner("", true);
  return data;
}
function dump(id, data) {
  const el = $(id);
  if (el) el.textContent = JSON.stringify(data, null, 2);
}
function hdr() {
  const ep = state.ep || "–";
  const lane = state.episode?.lane_preference || "unset";
  const profile = state.episode?.episode?.pipeline_profile || (state.projectId ? "drama" : "–");
  const castV = state.cast?.version ?? state.episode?.episode?.versions?.cast;
  $("hdr-meta").textContent = state.projectId ? `${state.projectId} / ${ep} · ${profile}` : "未建集";
  const laneEl = $("hdr-lane");
  if (laneEl) laneEl.textContent = `lane:${lane}`;
  const castEl = $("hdr-cast");
  if (castEl) castEl.textContent = castV != null ? `cast v${castV}` : "cast v–";
  const profileEl = $("hdr-profile");
  if (profileEl) {
    profileEl.textContent = `profile:${profile}`;
    if (state.projectId && profile && profile !== "drama") {
      showBanner("pipeline_profile 必须是 drama，不能进分镜表。", false);
    }
  }
  const hub = $("hub-ep");
  if (hub) {
    hub.textContent = state.projectId
      ? `${ep} · lane ${lane} · profile ${profile} · cast v${castV ?? "–"}`
      : "EP / lane / profile 将在建集后回显。";
  }
}
function parsePin(raw) {
  const text = (raw || "").trim();
  if (!text) return null;
  try { return JSON.parse(text); } catch { return { raw: text }; }
}

async function refreshEpisodeChrome() {
  if (!state.projectId) {
    hdr();
    return null;
  }
  try {
    const data = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}`);
    state.episode = data;
    if (data.episode?.versions?.cast && !state.seenCastVersion) {
      state.seenCastVersion = data.episode.versions.cast;
    }
  } catch {
    /* hub may not have episode yet */
  }
  try {
    const gate = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}/gates/g1b`);
    state.g1bLocked = Boolean(gate.gate?.locked && gate.gate?.last_decision === "pass");
  } catch {
    state.g1bLocked = false;
  }
  hdr();
  return state.episode;
}

function applyEGate() {
  const gate = $("e-gate");
  if (gate) gate.hidden = state.g1bLocked;
  const gen = $("btn-sb-gen");
  if (gen) gen.disabled = !state.g1bLocked || isStoryboardLocked(state.storyboard);
}

function charName(id) {
  if (id === "NONE") return "NONE";
  const row = (state.cast?.characters || []).find((c) => c.id === id);
  return row?.name || "?";
}

function chipLabel(id) {
  return `${id} · ${charName(id)}`;
}

function renderShots() {
  const tbody = $("e-tbody");
  if (!tbody) return;
  const rows = (state.storyboard?.rows || []).slice().sort((a, b) => (a.seq || 0) - (b.seq || 0));
  const locked = isStoryboardLocked(state.storyboard);
  const options = (state.cast?.characters || []).map((c) => c.id).concat(["NONE"]);
  tbody.innerHTML = rows.map((row) => {
    const selected = state.selectedShot === row.shot_id ? "selected" : "";
    const chips = (row.char_ids || []).map((id) => `<span class="chip">${escapeHtml(chipLabel(id))}</span>`).join("");
    const selects = locked ? "" : `<select data-shot="${escapeHtml(row.shot_id)}" class="char-pick" multiple size="2">${
      options.map((id) => `<option value="${escapeHtml(id)}" ${(row.char_ids || []).includes(id) ? "selected" : ""}>${escapeHtml(chipLabel(id))}</option>`).join("")
    }</select>`;
    return `<tr class="${selected}" data-shot="${escapeHtml(row.shot_id)}">
      <td><input type="radio" name="shot-pick" value="${escapeHtml(row.shot_id)}" ${state.selectedShot === row.shot_id ? "checked" : ""} /></td>
      <td>${row.seq ?? ""}</td>
      <td>${escapeHtml(row.shot_id || "")}</td>
      <td>${escapeHtml(row.bridge_id || "")}</td>
      <td><input type="number" min="1" class="dur-edit" data-shot="${escapeHtml(row.shot_id)}" value="${row.duration_s ?? ""}" ${locked ? "disabled" : ""} /></td>
      <td>${escapeHtml(SHOT_SIZE_ZH[row.shot_size] || "")} <code>${escapeHtml(row.shot_size || "")}</code></td>
      <td>${escapeHtml(CAMERA_ZH[row.camera] || "")} <code>${escapeHtml(row.camera || "")}</code></td>
      <td>${escapeHtml(row.action || "")}</td>
      <td class="chars">${chips}${selects}</td>
      <td>${escapeHtml(row.scene_id || "")}</td>
      <td>${escapeHtml(row.dialogue || "")}</td>
      <td>${escapeHtml(row.notes || "")}</td>
    </tr>`;
  }).join("");
  tbody.querySelectorAll("input[name=shot-pick]").forEach((el) => {
    el.addEventListener("change", () => { state.selectedShot = el.value; });
  });
  tbody.querySelectorAll("select.char-pick").forEach((el) => {
    el.addEventListener("change", () => {
      const shot = el.getAttribute("data-shot");
      const row = (state.storyboard?.rows || []).find((r) => r.shot_id === shot);
      if (row) row.char_ids = [...el.selectedOptions].map((o) => o.value);
      renderShots();
    });
  });
  tbody.querySelectorAll("input.dur-edit").forEach((el) => {
    el.addEventListener("change", () => {
      const shot = el.getAttribute("data-shot");
      const row = (state.storyboard?.rows || []).find((r) => r.shot_id === shot);
      if (row) row.duration_s = Number(el.value);
    });
  });
}

function renderIssues(el, issues) {
  if (!el) return;
  const list = issues || [];
  if (!list.length) {
    el.innerHTML = '<p class="meta">无 validate issues</p>';
    return;
  }
  el.innerHTML = "<ul>" + list.map((i) => {
    const sev = i.severity === "error" ? "hard" : "soft";
    return `<li class="${sev}"><code>${escapeHtml(i.code || "")}</code> ${escapeHtml(i.message || "")}${i.shot_id ? ` · ${escapeHtml(i.shot_id)}` : ""}</li>`;
  }).join("") + "</ul>";
}

function applyG2PassGate(issues) {
  const btn = $("btn-g2-pass");
  const block = $("f-block");
  const named = blockingNamedCast(issues);
  const errors = hardErrors(issues);
  const locked = isStoryboardLocked(state.storyboard);
  const disable = named.length > 0 || errors.length > 0 || locked || !(state.storyboard?.rows || []).length;
  if (btn) btn.disabled = disable;
  if (block) {
    block.hidden = named.length === 0;
    if (named.length) {
      block.textContent = `还有未入表的具名角色（${named.map((i) => i.code).join(", ")}），无法通过分镜门审。`;
    }
  }
}

async function refreshCast() {
  if (!state.projectId) return null;
  try {
    const data = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast`);
    state.cast = data.cast;
    if (state.cast?.version && !state.seenCastVersion) state.seenCastVersion = state.cast.version;
    hdr();
    return data;
  } catch {
    return null;
  }
}

async function refreshStoryboard() {
  if (!state.projectId) return null;
  try {
    const data = await api("GET", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard`);
    state.storyboard = data.storyboard;
    showCastHint(data);
    renderSkillStrip("e-skill", "e-skill-body", data);
    return data;
  } catch (err) {
    if (err.message === "upstream_unlocked") {
      state.storyboard = null;
    }
    return null;
  }
}

function paintEStatus(extra) {
  const sb = state.storyboard;
  const locked = isStoryboardLocked(sb);
  const status = $("e-status");
  const cap = sb?.shot_cap ?? 12;
  const n = sb?.shot_count ?? (sb?.rows || []).length;
  if (status) {
    status.textContent = `${state.ep || "EP"} · 短剧 · D-N2 · ${locked ? "locked" : "draft"} · cast v${state.cast?.version ?? "–"} · ${state.g1bLocked ? "G1b✓" : "G1b未锁"}`;
  }
  const count = $("e-shot-count");
  if (count) count.textContent = `镜数 ${n}/${cap}`;
  const badge = $("e-skill-badge");
  if (badge) badge.textContent = `skill:${sb?.storyboard_skill || extra?.storyboard_skill || "–"}`;
  const up = $("e-upstream");
  if (up) {
    up.textContent = sb
      ? `lane ${sb.lane || "–"} · shot_cap ${cap} · upstream outline v${sb.upstream_outline_version ?? "–"} / cast v${sb.upstream_cast_version ?? "–"}`
      : "上游只读摘要将在刷新后出现。";
  }
  const ready = $("e-ready");
  if (ready) {
    const edges = extra?.next_edges || state.episode?.next_edges || [];
    const pretend = !locked && edges.includes("D-N2");
    ready.textContent = pretend
      ? "next_edges 含 D-N2 且 locked=false — 不是已可下游出片，也不是 D-N3 开工。"
      : `ready_for_n4=${sb?.ready_for_n4 ? "true" : "false"}（灰态）· locked=${locked}`;
  }
  const sel = $("tool-profile");
  if (sel && document.activeElement !== sel) {
    sel.value = sb?.tool_profile || "";
  }
  paintExportChip(extra?.issues || extra?.validate_warnings || state.validate?.issues, sb?.tool_profile);
  applyEGate();
}

async function refreshScreenE() {
  await refreshEpisodeChrome();
  applyEGate();
  if (!state.g1bLocked) {
    paintEStatus();
    renderShots();
    return;
  }
  await refreshCast();
  const sb = await refreshStoryboard();
  paintEStatus(sb);
  renderShots();
  if (sb?.validate_warnings) {
    renderIssues($("e-issues"), sb.validate_warnings);
    applyGapCopyIssues(sb.validate_warnings, sb?.storyboard?.tool_profile || state.storyboard?.tool_profile);
  }
}

async function refreshScreenF() {
  await refreshEpisodeChrome();
  await refreshCast();
  const sb = await refreshStoryboard();
  let issues = [];
  try {
    const val = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard/validate`, {});
    state.validate = val;
    issues = val.issues || [];
    renderIssues($("f-issues"), issues);
    showCastHint(val);
    applyGapCopyIssues(issues, state.storyboard?.tool_profile);
    dump("f-out", val);
  } catch (err) {
    dump("f-out", err.data || { error: String(err) });
  }
  const named = blockingNamedCast(issues);
  const errors = hardErrors(issues);
  const sbv = state.storyboard;
  const sum = $("f-summary");
  if (sum) {
    sum.textContent = `镜数 ${sbv?.shot_count ?? 0} · Σdur ${(sbv?.rows || []).reduce((a, r) => a + (Number(r.duration_s) || 0), 0)}s · 硬错 ${errors.length} · named_cast 阻断 ${named.length} · locked=${isStoryboardLocked(sbv)}`;
  }
  applyG2PassGate(issues);
}

async function refreshScreenG() {
  await refreshEpisodeChrome();
  const sb = await refreshStoryboard();
  const locked = isStoryboardLocked(state.storyboard);
  const edges = sb?.next_edges || state.episode?.next_edges || [];
  const sum = $("g-summary");
  if (sum) {
    sum.textContent = locked
      ? `locked=true · confirmed_by=${state.storyboard.confirmed_by} · storyboard v${state.storyboard.version}`
      : "尚未 G2 pass（看 locked/confirmed_by，不单靠 next_edges）。";
  }
  const next = $("g-next");
  if (next) {
    next.textContent = `next_edges: ${JSON.stringify(edges)} — D-N3 只是候选文案，不自动开卡。`;
  }
  dump("g-out", { storyboard: state.storyboard, episode: state.episode, next_edges: edges });
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
  state.seenCastVersion = 0;
  hdr();
  dump("hub-out", data);
  await refreshIntent();
  await refreshEpisodeChrome();
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
  await refreshEpisodeChrome();
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
  renderSkillStrip("b-skill", "b-skill-body", data);
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
  state.g1bLocked = Boolean(data.gate?.locked && data.gate?.last_decision === "pass");
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
$("btn-goto-e").onclick = () => showScreen("e");
document.querySelectorAll("input[name=lane2]").forEach((el) => {
  el.addEventListener("change", () => {
    const confirmBtn = $("btn-confirm-intent");
    if (confirmBtn && state.check.conflict && el.value !== state.check.suggested_lane) {
      confirmBtn.disabled = true;
    }
  });
});
applyIntent({ intent: { confirmed: false }, conflict: false });

$("btn-sb-gen").onclick = async () => {
  if (!state.g1bLocked) {
    showBanner("上游门 G1b 未锁，不能生成空表。", false);
    applyEGate();
    return;
  }
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard/generate`, {
    provider: "fixture",
    tool_profile: toolProfile() || null,
    actor: "yangzhou",
  });
  state.storyboard = data.storyboard;
  showCastHint(data);
  renderSkillStrip("e-skill", "e-skill-body", data);
  dump("e-out", data);
  await refreshCast();
  if (data.cast_changed) {
    const { newV } = hintVersions(data);
    if (newV != null) state.cast = { ...(state.cast || {}), version: Number(newV) };
  }
  paintEStatus(data);
  renderShots();
  if (data.validate_warnings) {
    renderIssues($("e-issues"), data.validate_warnings);
    applyGapCopyIssues(data.validate_warnings, data.storyboard?.tool_profile);
  }
};
$("btn-sb-val").onclick = async () => {
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard/validate`, {});
  state.validate = data;
  showCastHint(data);
  dump("e-out", data);
  renderIssues($("e-issues"), data.issues || []);
  applyG2PassGate(data.issues || []);
  applyGapCopyIssues(data.issues || [], data.storyboard?.tool_profile || state.storyboard?.tool_profile);
};
$("btn-sidecar").onclick = async () => {
  const before = state.cast?.version ?? state.seenCastVersion;
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/drama/cast/sidecar-add`, {
    name: $("side-name").value || "CODEX王子",
    one_line: $("side-line").value || undefined,
    actor: "yangzhou",
  });
  showCastHint({
    ...data,
    hints: (data.hints || []).map((h) => ({
      ...h,
      cast_version_old: h.cast_version_old ?? before,
      cast_version_new: h.cast_version_new ?? data.cast?.version,
    })),
  });
  dump("e-out", data);
  await refreshCast();
  await refreshStoryboard();
  paintEStatus(data);
  renderShots();
};
$("btn-sb-save").onclick = async () => {
  if (!state.storyboard?.rows?.length) {
    showBanner("没有可保存的分镜行。", false);
    return;
  }
  const data = await api("PUT", `/projects/${state.projectId}/episodes/${state.ep}/drama/storyboard`, {
    rows: state.storyboard.rows,
    tool_profile: toolProfile() || null,
    actor: "yangzhou",
    unlock_edit: isStoryboardLocked(state.storyboard),
  });
  state.storyboard = data.storyboard;
  dump("e-out", data);
  paintEStatus(data);
  renderShots();
};
$("btn-sb-up").onclick = () => moveSelected(-1);
$("btn-sb-down").onclick = () => moveSelected(1);
$("btn-open-g2").onclick = () => showScreen("f");
$("btn-g2-back").onclick = () => showScreen("e");

function moveSelected(delta) {
  const rows = state.storyboard?.rows;
  if (!rows || !state.selectedShot) return;
  const idx = rows.findIndex((r) => r.shot_id === state.selectedShot);
  const next = idx + delta;
  if (idx < 0 || next < 0 || next >= rows.length) return;
  const tmp = rows[idx];
  rows[idx] = rows[next];
  rows[next] = tmp;
  rows.forEach((r, i) => { r.seq = i + 1; });
  renderShots();
}

async function confirmG2(decision) {
  if (decision === "pass") {
    const issues = state.validate?.issues || [];
    if (blockingNamedCast(issues).length) {
      showBanner("客户端已禁用 G2 pass：存在阻断 named_cast_*。", false);
      applyG2PassGate(issues);
      return;
    }
  }
  const data = await api("POST", `/projects/${state.projectId}/episodes/${state.ep}/gates/g2/confirm`, {
    decision,
    actor: $("g2-actor").value,
    note: $("g2-note").value || undefined,
  });
  showCastHint(data);
  dump("f-out", data);
  dump("e-out", data);
  state.storyboard = data.storyboard;
  if (decision === "pass") {
    showScreen("g");
  } else {
    showScreen("e");
  }
}
$("btn-g2-pass").onclick = () => confirmG2("pass");
$("btn-g2-reject").onclick = () => confirmG2("reject");

async function evaluateCopy(extra) {
  if (!state.projectId) {
    showBanner("请先在 Hub 建集", false, "warn");
    return null;
  }
  const body = {
    tool_profile: toolProfile() || null,
    rows: state.storyboard?.rows || [],
    ...(extra || {}),
  };
  try {
    const data = await api(
      "POST",
      `/projects/${state.projectId}/episodes/${state.ep}/drama/copy-contract/evaluate`,
      body,
    );
    applyGapCopyIssues(data.issues || data.warnings || [], toolProfile());
    if (data.chip) {
      const kind = !toolProfile() ? "warn" : (data.chip.includes("未对齐") ? "error" : "ok");
      setExportChip(data.chip, kind);
    }
    dump("e-out", data);
    return data;
  } catch (err) {
    dump("e-out", err.data || { error: String(err) });
    return null;
  }
}
if ($("btn-eval-copy")) {
  $("btn-eval-copy").onclick = () => evaluateCopy({});
}
if ($("btn-ready-n4")) {
  $("btn-ready-n4").onclick = () => evaluateCopy({ ready_for_n4: true });
}
if ($("tool-profile")) {
  $("tool-profile").addEventListener("change", () => {
    if (toolProfile()) {
      showBanner("更换出片工具后，将按新工具的允许秒数整表重算时长档。请确认后再出片。", true, "info");
      const el = $("banner");
      if (el) {
        el.classList.remove("ok");
        el.classList.add("info");
        el.style.background = "#1d2a3a";
      }
    }
    evaluateCopy({}).catch(() => {});
  });
}
hdr();
