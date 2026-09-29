const $ = (id) => document.getElementById(id);
let view = null;

function fromPath() {
  const m = location.pathname.match(/\/projects\/([^/]+)\/episodes\/([^/]+)\/n1/);
  if (m) { $("project").value = m[1]; $("ep").value = m[2]; }
}
fromPath();

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
function renderMeta() {
  const s = sess();
  $("epLabel").textContent = `${$("ep").value} · N1 口播定稿`;
  $("badge").textContent = badge();
  $("lim").textContent = s.char_limit || 400;
  const d = s.draft || {};
  $("chars").textContent = d.chars || 0;
  $("fw").textContent = (s.frameworks_selected || [])[0] || d.framework || "—";
  $("src").textContent = s.raw_ref || "—";
  $("ver").textContent = s.version ? `v${s.version}` : "";
}
function renderStep() {
  const s = sess();
  const spec = s.step_spec;
  $("banner").innerHTML = "";
  $("fields").innerHTML = "";
  $("btnGate").hidden = s.status !== "awaiting_g1";
  $("btnSubmit").hidden = s.status !== "active";
  if (s.status === "locked") {
    $("stepTitle").textContent = "已锁定";
    $("stepHelp").textContent = "G1 已通过。next_edges 仅展示候选（D2 未拍板，不进编剧）。";
    $("fields").innerHTML = `<pre>${(view.artifact && view.artifact.markdown) || ""}</pre><p class="muted">next_edges: ${(view.next_edges || []).map(e => e.to).join(", ")}</p>`;
    $("btnSubmit").hidden = true;
    return;
  }
  if (s.status === "awaiting_g1") {
    $("stepTitle").textContent = "定稿待门 G1";
    $("stepHelp").textContent = "机械校验已过。打开门 G1 做创作侧确认。无 ForcePass。";
    $("fields").innerHTML = `<pre>${(s.draft && (s.draft.title + "\n" + s.draft.body)) || ""}</pre>`;
    return;
  }
  if (!spec) {
    $("stepTitle").textContent = "创建会话";
    $("stepHelp").textContent = "默认路径 A〔provisional〕。一次只露一步。";
    return;
  }
  $("stepTitle").textContent = spec.step;
  $("stepHelp").textContent = spec.label;
  if (spec.kind === "skipped_source_defect") {
    $("banner").innerHTML = `<div class="banner">源缺陷 · 缺步 3。向导跳过补课，不改 .prompt/koubo-长文章.md。</div>`;
    $("fields").innerHTML = `<label><input type="checkbox" id="ack" /> 已知晓，继续</label>`;
    return;
  }
  if ((spec.accepts || []).includes("raw_text")) {
    $("fields").innerHTML += `<label>原料</label><textarea id="raw"></textarea>`;
  }
  if ((spec.accepts || []).includes("decision") || (spec.accepts || []).includes("notes")) {
    if (s.extract) $("fields").innerHTML += `<pre>${JSON.stringify(s.extract, null, 2)}</pre>`;
    $("fields").innerHTML += `<label>notes</label><input id="notesIn" />`;
  }
  if (spec.frameworks) {
    $("fields").innerHTML += spec.frameworks.map((f) =>
      `<label><input type="radio" name="fw" value="${f.name}" /> ${f.name}${f.defective ? "（源缺陷）" : ""} — ${f.summary}</label>`
    ).join("");
  }
  if ((s.candidates || []).length) {
    $("fields").innerHTML += s.candidates.map((c) =>
      `<article><label><input type="radio" name="cand" value="${c.id}" /> <strong>${c.id} ${c.title}</strong> · ${c.chars}字</label><p>${c.body}</p></article>`
    ).join("");
  }
  if ((s.titles || []).length) {
    $("fields").innerHTML += s.titles.map((t) =>
      `<label><input type="radio" name="title" value="${t.id}" /> ${t.title}</label>`
    ).join("");
  }
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
$("btnBack").onclick = async () => {
  if (sess().status === "awaiting_g1") {
    try {
      view = await api(`${base()}/gates/g1/confirm`, { method: "POST", body: JSON.stringify({ action: "reject", actor: $("actor").value }) });
      renderMeta(); renderStep();
    } catch (e) { showErr(e); }
  }
};
$("btnGate").onclick = () => {
  const d = sess().draft || {};
  $("g1meta").textContent = `路径 ${sess().path} · 框架 ${d.framework || "—"} · ${d.chars || 0} 字`;
  $("g1preview").textContent = `［标题］${d.title || ""}\n文案内容：${d.body || ""}`;
  $("g1").showModal();
};
$("btnPass").onclick = async () => {
  const boxes = [...document.querySelectorAll(".ck")];
  if (!boxes.every((b) => b.checked)) { $("err").textContent = "请勾选 C1–C6 后再通过（人过审）。"; return; }
  try {
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
    view = await api(`${base()}/gates/g1/confirm`, { method: "POST", body: JSON.stringify({ action: "pass", actor: "user:local" }) });
    $("err").textContent = "";
    renderMeta(); renderStep();
  } catch (e) { showErr(e); }
};
document.querySelectorAll("input[name=path]").forEach((el) => {
  el.addEventListener("change", () => {
    if (sess().status && sess().status !== "idle" && !confirm("清空本会话草稿？")) return;
    $("btnCreate").click();
  });
});
