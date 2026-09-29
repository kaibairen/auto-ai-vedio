const $ = (id) => document.getElementById(id);
let view = null;

function fromPath() {
  const m = location.pathname.match(/\/projects\/([^/]+)\/episodes\/([^/]+)\/n1/);
  if (m) { $("project").value = m[1]; $("ep").value = m[2]; }
}
fromPath();

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[c]));
}

function countChars(t) {
  return Array.from(String(t || "").normalize("NFC").trim()).length;
}

function api(path, opts = {}) {
  return fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  }).then(async (r) => {
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = data.error || {};
      throw Object.assign(new Error(err.message || r.statusText), { data, status: r.status });
    }
    return data;
  });
}
function base() {
  return `/api/v0/projects/${$("project").value.trim() || "default"}/episodes/${$("ep").value.trim()}`;
}
function sess() { return (view && view.session) || {}; }
function showErr(e) {
  $("err").textContent = e?.data?.error ? `${e.status} ${e.data.error.code}: ${e.data.error.message}` : (e?.message || "");
}
function badge() {
  const s = sess();
  if (s.status === "locked") return "locked";
  if (s.status === "awaiting_g1") return "awaiting_gate";
  if (s.status && s.status !== "idle") return "draft";
  return "empty";
}
function limit() {
  return sess().char_limit || (sess().path === "B" ? 500 : 400);
}
function liveDraftChars() {
  const t = $("draftTitle");
  const b = $("draftBody");
  if (t || b) return countChars(t ? t.value : "") + countChars(b ? b.value : "");
  return (sess().draft && sess().draft.chars) || 0;
}
function setLockedUi(locked) {
  document.querySelectorAll("input[name=path]").forEach((el) => { el.disabled = locked; });
  $("btnCreate").disabled = locked;
  $("btnDemo").disabled = locked;
  $("project").disabled = locked;
  $("ep").disabled = locked;
}
function renderMeta() {
  const s = sess();
  const n = liveDraftChars();
  const lim = limit();
  $("epLabel").textContent = `${$("ep").value} · N1 口播定稿`;
  $("badge").textContent = badge();
  $("lim").textContent = lim;
  $("chars").textContent = n;
  $("chars").className = n > lim ? "over" : "";
  $("fw").textContent = (s.frameworks_selected || [])[0] || (s.draft && s.draft.framework) || "—";
  $("src").textContent = s.raw_ref || "—";
  $("ver").textContent = s.version ? `v${s.version}` : "";
  setLockedUi(s.status === "locked");
}
function draftEditorHtml(d) {
  const revised = sess().path === "B"
    ? `<label><input type="checkbox" id="manualRevised" /> 标记已人工校订（框架 7/8 源缺陷；不改教材）</label>`
    : "";
  return `<div class="editor">
    <label>［标题］</label>
    <input id="draftTitle" value="${esc(d.title || "")}" />
    <label>文案内容</label>
    <textarea id="draftBody">${esc(d.body || "")}</textarea>
    ${revised}
  </div>`;
}
function bindDraftLive() {
  ["draftTitle", "draftBody"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      renderMeta();
      syncButtons();
    });
  });
}
function syncButtons() {
  const s = sess();
  const spec = s.step_spec;
  const n = liveDraftChars();
  const over = n > limit();
  const emptyDraft = n === 0 || (($("draftTitle") && !$("draftTitle").value.trim()) && ($("draftBody") && !$("draftBody").value.trim()));
  $("btnGate").hidden = s.status !== "awaiting_g1";
  $("btnGate").disabled = s.status !== "awaiting_g1" || over || emptyDraft;
  $("btnSave").hidden = !(s.status === "awaiting_g1" || (spec && spec.kind === "optimize" && s.draft));
  $("btnSave").disabled = over || emptyDraft || s.status === "locked";
  $("btnSubmit").hidden = s.status !== "active";
  $("btnCopy").hidden = s.status !== "locked";
  $("btnSubmit").disabled = !requiredOk();
}
function requiredOk() {
  const s = sess();
  const spec = s.step_spec;
  if (!spec || s.status !== "active") return false;
  if (spec.kind === "collect_raw") return !!($("raw") && $("raw").value.trim());
  if (spec.kind === "skipped_source_defect") return !!($("ack") && $("ack").checked);
  if (spec.kind === "choose_framework" || spec.kind === "reconstruct") {
    return !!document.querySelector("input[name=fw]:checked");
  }
  if (spec.kind === "generate_titles" && (s.titles || []).length) {
    return !!document.querySelector("input[name=title]:checked");
  }
  if (spec.kind === "optimize" && s.path === "A" && (s.candidates || []).length) {
    return !!document.querySelector("input[name=cand]:checked");
  }
  return true;
}
function renderStep() {
  const s = sess();
  const spec = s.step_spec;
  $("banner").innerHTML = "";
  $("fields").innerHTML = "";
  if (s.status === "locked") {
    const edges = (view.next_edges || []).map((e) => `<span class="chip">${esc(e.to)} 〔provisional〕</span>`).join("");
    $("stepTitle").textContent = "已锁定";
    $("stepHelp").textContent = "G1 已通过。next_edges 仅展示候选（D2 未拍板，不进编剧）。";
    $("fields").innerHTML = `<pre>${esc((view.artifact && view.artifact.markdown) || "")}</pre>
      <p class="muted">工件：${esc((view.artifact && view.artifact.rel_path) || "episodes/EP##/N1-口播定稿.md")}</p>
      <p>next_edges ${edges || "—"}</p>`;
    syncButtons();
    return;
  }
  if (s.status === "awaiting_g1") {
    $("stepTitle").textContent = "定稿待门 G1";
    $("stepHelp").textContent = "可改标题/正文并保存（PUT nodes/n1/draft）。打开门 G1 做创作侧 C1–C6。无 ForcePass。";
    $("fields").innerHTML = draftEditorHtml(s.draft || {});
    bindDraftLive();
    syncButtons();
    return;
  }
  if (!spec) {
    $("stepTitle").textContent = "创建会话";
    $("stepHelp").textContent = "默认路径 A〔provisional〕。一次只露一步。";
    syncButtons();
    return;
  }
  $("stepTitle").textContent = spec.step;
  $("stepHelp").textContent = spec.label;
  if (spec.kind === "skipped_source_defect") {
    $("banner").innerHTML = `<div class="banner">源缺陷 · 缺步 3。向导跳过补课，不改 .prompt/koubo-长文章.md。</div>`;
    $("fields").innerHTML = `<label><input type="checkbox" id="ack" /> 已知晓，继续</label>`;
  } else {
    if ((spec.accepts || []).includes("raw_text")) {
      $("fields").innerHTML += `<label>原料</label><textarea id="raw"></textarea>`;
    }
    if ((spec.accepts || []).includes("decision") || (spec.accepts || []).includes("notes")) {
      if (s.extract) $("fields").innerHTML += `<pre>${esc(JSON.stringify(s.extract, null, 2))}</pre>`;
      $("fields").innerHTML += `<label>notes</label><input id="notesIn" />`;
    }
    if (spec.frameworks) {
      $("fields").innerHTML += spec.frameworks.map((f) =>
        `<label><input type="radio" name="fw" value="${esc(f.name)}" /> ${esc(f.name)}${f.defective ? "（源缺陷）" : ""} — ${esc(f.summary)}</label>`
      ).join("");
    }
    if ((s.candidates || []).length && (spec.kind === "optimize" || spec.kind === "generate_candidates")) {
      $("fields").innerHTML += s.candidates.map((c) =>
        `<article><label><input type="radio" name="cand" value="${esc(c.id)}" /> <strong>${esc(c.id)} ${esc(c.title)}</strong> · ${esc(c.chars)}字</label><p>${esc(c.body)}</p></article>`
      ).join("");
    }
    if ((s.titles || []).length) {
      $("fields").innerHTML += s.titles.map((t) =>
        `<label><input type="radio" name="title" value="${esc(t.id)}" /> ${esc(t.title)}</label>`
      ).join("");
    }
    if (spec.kind === "optimize" && s.draft) {
      $("fields").innerHTML += draftEditorHtml(s.draft);
    }
  }
  $("fields").oninput = () => { renderMeta(); syncButtons(); };
  $("fields").onchange = syncButtons;
  syncButtons();
}
function payload() {
  const spec = sess().step_spec || {};
  const out = {};
  const raw = $("raw"); if (raw) out.raw_text = raw.value;
  const n = $("notesIn"); if (n && n.value) out.notes = n.value;
  const ack = $("ack"); if (ack) out.ack_defect = ack.checked;
  const fw = document.querySelector("input[name=fw]:checked");
  if (fw) { out.framework = fw.value; out.frameworks = [fw.value]; }
  const cand = document.querySelector("input[name=cand]:checked");
  if (cand) out.candidate_id = cand.value;
  const t = document.querySelector("input[name=title]:checked");
  if (t) out.title_id = t.value;
  const dt = $("draftTitle");
  const db = $("draftBody");
  if (dt || db) {
    out.edits = { title: dt ? dt.value : "", body: db ? db.value : "" };
    if (dt) out.title = dt.value;
  }
  const mr = $("manualRevised");
  if (mr && mr.checked) out.manual_revised = true;
  if ((spec.accepts || []).includes("decision") && !out.decision) out.decision = "approve";
  if (spec.kind === "generate_candidates") out.decision = "continue";
  return out;
}
async function refresh() {
  try {
    view = await api(`${base()}/nodes/n1`);
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
}
async function saveDraft() {
  const title = $("draftTitle") ? $("draftTitle").value : "";
  const body = $("draftBody") ? $("draftBody").value : "";
  const fw = (sess().frameworks_selected || [])[0] || (sess().draft && sess().draft.framework) || "";
  view = await api(`${base()}/nodes/n1/draft`, {
    method: "PUT",
    body: JSON.stringify({ title, body, framework: fw }),
  });
}
$("btnCreate").onclick = async () => {
  try {
    const path = document.querySelector("input[name=path]:checked").value;
    await api(`${base().replace(/\/episodes\/.*/, "")}/episodes`, { method: "POST", body: JSON.stringify({ ep: $("ep").value }) }).catch(() => {});
    view = await api(`${base()}/n1/sessions`, { method: "POST", body: JSON.stringify({ path, provider: "fixture" }) });
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
};
$("btnRefresh").onclick = refresh;
$("btnSubmit").onclick = async () => {
  const step = sess().current_step;
  if (!step) return;
  try {
    view = await api(`${base()}/n1/steps/${step}/submit`, { method: "POST", body: JSON.stringify(payload()) });
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
};
$("btnSave").onclick = async () => {
  try {
    await saveDraft();
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
};
$("btnBack").onclick = async () => {
  if (sess().status === "awaiting_g1" || sess().status === "locked") {
    try {
      view = await api(`${base()}/gates/g1/confirm`, { method: "POST", body: JSON.stringify({ action: "reject", actor: $("actor").value }) });
      $("err").textContent = "";
      renderMeta(); renderStep();
    } catch (e) { showErr(e); }
  }
};
$("btnGate").onclick = () => {
  const d = sess().draft || {};
  $("g1meta").textContent = `路径 ${sess().path} · 框架 ${d.framework || "—"} · ${d.chars || liveDraftChars()} 字`;
  $("g1preview").textContent = `［标题］${d.title || ""}\n文案内容：${d.body || ""}`;
  $("g1").showModal();
};
$("btnCopy").onclick = async () => {
  const text = (view.artifact && view.artifact.markdown) || "";
  try {
    await navigator.clipboard.writeText(text);
    $("err").textContent = "已复制定稿。";
  } catch {
    $("err").textContent = (view.artifact && view.artifact.rel_path) || "";
  }
};
$("btnPass").onclick = async () => {
  const boxes = [...document.querySelectorAll(".ck")];
  if (!boxes.every((b) => b.checked)) { $("err").textContent = "请勾选 C1–C6 后再通过（人过审）。"; return; }
  try {
    if ($("draftTitle") || $("draftBody")) {
      await saveDraft();
    }
    view = await api(`${base()}/gates/g1/confirm`, {
      method: "POST",
      body: JSON.stringify({ action: "pass", actor: $("actor").value, note: $("notes").value }),
    });
    $("g1").close();
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); $("g1").close(); }
};
$("btnReject").onclick = async () => {
  try {
    view = await api(`${base()}/gates/g1/confirm`, { method: "POST", body: JSON.stringify({ action: "reject", actor: $("actor").value }) });
    $("g1").close();
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
};
$("btnDemo").onclick = async () => {
  try {
    await $("btnCreate").onclick();
    const path = document.querySelector("input[name=path]:checked").value;
    const rawA = "就是那个咖啡渣别扔啊，我妈说能除臭还能当肥料。";
    const rawB = "很多人把长文章直接念完。真正能留下的口播是一个痛点、一个转折、一个行动。";
    const seq = path === "A"
      ? [["a1_raw", { raw_text: rawA }], ["a2_extract", { decision: "approve" }], ["a3_framework", { frameworks: ["惊喜揭秘型"] }], ["a4_candidates", { decision: "continue" }], ["a5_finalize", { candidate_id: "c1" }]]
      : [["b1_raw", { raw_text: rawB }], ["b2_analyze", { decision: "approve" }], ["b3_skipped", { ack_defect: true }], ["b4_titles", { title_id: "t1" }], ["b5_framework_draft", { framework: "痛点共鸣式" }], ["b6_finalize", { decision: "approve" }]];
    for (const [step, body] of seq) {
      view = await api(`${base()}/n1/steps/${step}/submit`, { method: "POST", body: JSON.stringify(body) });
    }
    view = await api(`${base()}/gates/g1/confirm`, { method: "POST", body: JSON.stringify({ action: "pass", actor: "bot:demo" }) });
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
};
document.querySelectorAll("input[name=path]").forEach((el) => {
  el.addEventListener("change", () => {
    if (sess().status === "locked") return;
    if (sess().status && sess().status !== "idle" && !confirm("清空本会话草稿？")) return;
    $("btnCreate").click();
  });
});
refresh().catch(() => {});
