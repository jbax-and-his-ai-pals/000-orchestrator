"use strict";

const COLUMNS = [
  { key: "sparks", label: "Sparks", stages: ["spark"], awaiting: ["spark"] },
  { key: "hld", label: "HLD Review", stages: ["hld_draft", "hld_review"], awaiting: ["hld_review"] },
  { key: "lld", label: "LLD Review", stages: ["lld_draft", "lld_review"], awaiting: ["lld_review"] },
  { key: "build", label: "Building / Playtest", stages: ["building", "playtest"], awaiting: ["playtest"] },
];
const AWAITING = new Set(COLUMNS.flatMap(c => c.awaiting));
const CATEGORY_LABEL = {
  fun_gameplay: "fun / gameplay", visual_craft: "visual craft", optimization: "optimization",
  tech_audacity: "tech audacity", new_game: "new game",
};

let S = null;          // last /api/state payload
let version = "";
let openCard = null;   // {type: 'init'|'project', id}

const $ = (sel, el = document) => el.querySelector(sel);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ago = iso => {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};
const num = name => (name.match(/^(\d{3})-/) || [])[1];
const short = name => name.replace(/^\d{3}-/, "");

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Orchestrator": "1" },
  };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || data.detail || `HTTP ${r.status}`);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3200);
}

/* ---------------- data loop ---------------- */

async function refresh(force = false) {
  try {
    if (!force && S) {
      const v = await api("/api/version");
      if (v.version === version) { $("#live-dot").className = "dot on"; return; }
    }
    S = await api("/api/state");
    version = S.version;
    $("#live-dot").className = "dot on";
    render();
    if (openCard && !($("#note")?.value)) reopen();  // never clobber feedback being typed
  } catch (e) {
    $("#live-dot").className = "dot err";
  }
}

const untilText = u => (!u || u.startsWith("9999")) ? "indefinite (until ended)" : u.replace("T", " ").slice(0, 16);

function renderSpotlight() {
  const b = $("#spotlight-banner"), s = S.spotlight;
  b.hidden = !s;
  if (!s) return;
  const pending = (s.in_flight || []).filter(f => !f.handoff_done).length;
  b.innerHTML = `<span>🔦 <b>Spotlight (${esc(s.mode || "graceful")}):</b> all agents on <b>${esc(s.project)}</b> · aspect <b>${esc(s.aspect)}</b> · ${esc(untilText(s.until))}${pending ? ` · ${pending} handoff note(s) pending` : ""}${s.note ? ` · ${esc(s.note)}` : ""}</span>
    <button class="btn" id="end-spot">End spotlight</button>`;
  $("#end-spot").onclick = async () => { try { await api("/api/spotlight/end", {}); toast("Spotlight ended; agents back to the whole portfolio"); refresh(true); } catch (e) { toast(e.message, true); } };
}

function render() {
  renderSpotlight(); renderPulse(); renderBoard(); renderActivity();
  const waiting = S.initiatives.filter(i => AWAITING.has(i.stage)).length;
  $("#review-count").textContent = waiting || "";
  $("#meta").textContent = `${S.projects.length} projects · ${S.initiatives.length} initiatives · webhooks ${S.config.webhooks_enabled ? "on" : "off"}`;
}

/* ---------------- pulse ---------------- */

function meter(label, v, cls = "") {
  const ok = v !== null && v !== undefined;
  return `<span>${label}</span><div class="bar ${cls}"><i style="width:${ok ? v * 10 : 0}%"></i></div>` +
    `<span class="val ${ok ? "" : "na"}">${ok ? v + "/10" : "—"}</span>`;
}

function renderPulse() {
  const q = $("#filter").value.toLowerCase();
  const showSkip = $("#show-skip").checked;
  const m = new Set(S.config.metrics);
  const order = { high: 0, medium: 1, low: 2, skip: 3 };
  const projects = S.projects
    .filter(p => showSkip || p.priority !== "skip")
    .filter(p => !q || `${p.repo_name} ${p.stack}`.toLowerCase().includes(q))
    .sort((a, b) => order[a.priority] - order[b.priority] || a.repo_name.localeCompare(b.repo_name));
  $("#pulse").innerHTML = projects.map(p => {
    const act = p.latest_activity;
    const opts = S.enums.priorities.map(o => `<option ${o === p.priority ? "selected" : ""}>${o}</option>`).join("");
    return `<div class="pcard ${p.priority === "skip" ? "skip" : ""}">
      <div class="pcard-head">
        <div class="pname" data-project="${esc(p.repo_name)}"><span class="pnum">${num(p.repo_name)}</span>${esc(short(p.repo_name))}</div>
        <select class="prio" data-v="${p.priority}" data-prio="${esc(p.repo_name)}" aria-label="Priority">${opts}</select>
      </div>
      <div class="badges">
        ${m.has("stack") && p.stack ? `<span class="badge stack">${esc(p.stack)}</span>` : ""}
        ${m.has("complexity") && p.complexity === "high" ? `<span class="badge high">high complexity</span>` : ""}
        ${!p.is_git ? `<span class="badge local">local only · no git</span>` : ""}
        ${p.has_dossier ? `<span class="badge">dossier</span>` : `<span class="badge">no dossier yet</span>`}
        ${p.has_audit ? `<span class="badge">audit notes</span>` : ""}
        ${p.focus ? `<span class="badge focus">🎯 focus: ${esc(p.focus)} · ${esc(untilText(p.focus_until))}</span>` : ""}
      </div>
      ${m.has("player_experience") ? (p.player_experience
        ? `<div class="pexp" title="${esc(p.player_experience)}">${esc(p.player_experience)}</div>`
        : `<div class="pexp na">Player experience not documented yet</div>`) : ""}
      <div class="meters">
        ${m.has("playability_score") ? meter("Playability", p.playability_score) : ""}
        ${m.has("visual_maturity") ? meter("Visual", p.visual_maturity, "vis") : ""}
      </div>
      ${p.bottleneck_summary ? `<div class="bneck">${esc(p.bottleneck_summary)}</div>` : ""}
      ${m.has("optimization_notes") && p.optimization_notes ? `<div class="bneck">${esc(p.optimization_notes)}</div>` : ""}
      <div class="activity-line">${act ? `<b>${esc(act.actor)}</b> ${esc(act.kind)} · ${esc((act.message || "").slice(0, 80))} · ${ago(act.ts)}`
        : "No agent activity yet"}${m.has("last_scanned_at") ? ` · scanned ${ago(p.last_scanned_at)}` : ""}</div>
    </div>`;
  }).join("") || `<div class="empty">No projects match.</div>`;
}

/* ---------------- board ---------------- */

function cardHtml(i) {
  const awaiting = AWAITING.has(i.stage);
  const prog = i.plan_progress ? ` · ${i.plan_progress.done}/${i.plan_progress.total} subtasks` +
    (i.plan_progress.review && i.plan_progress.review !== "pending" ? ` · review ${i.plan_progress.review}` : "") : "";
  return `<div class="card ${awaiting ? "awaiting" : "working"}" data-init="${i.id}" id="card-${i.id}">
    <div class="card-sub"><span class="stage ${awaiting ? "awaiting" : ""}">${i.stage}</span>
      <span class="cat cat-${i.category}">${CATEGORY_LABEL[i.category]}</span>${i.complexity === "high" ? `<span class="cat" style="color:var(--violet)">· high</span>` : ""}</div>
    <div class="card-title">${esc(i.title)}</div>
    <div class="card-sub">${esc(i.project_name === "NEW_CONCEPT" ? "✦ new concept" : short(i.project_name))} · ${ago(i.updated_at)}${prog}</div>
    ${i.revision_note ? `<div class="card-sub" style="color:var(--warn)">↺ ${esc(i.revision_note.slice(0, 90))}</div>` : ""}
    ${i.claim ? `<div class="card-sub claim">💬 in chat: ${esc(i.claim)}</div>` : ""}
  </div>`;
}

function renderBoard() {
  $("#board").innerHTML = COLUMNS.map(c => {
    const items = S.initiatives.filter(i => c.stages.includes(i.stage))
      .sort((a, b) => (AWAITING.has(b.stage) - AWAITING.has(a.stage)) || b.updated_at.localeCompare(a.updated_at));
    const waiting = items.filter(i => AWAITING.has(i.stage)).length;
    return `<div class="col"><div class="col-head"><span>${c.label}</span><span><b>${waiting}</b> awaiting · ${items.length}</span></div>
      <div class="col-body">${items.map(cardHtml).join("") || `<div class="empty">Nothing here.</div>`}</div></div>`;
  }).join("");
  const closed = S.initiatives.filter(i => i.stage === "done" || i.stage === "rejected");
  $("#closed-summary").textContent = `Closed (${closed.filter(i => i.stage === "done").length} done · ${closed.filter(i => i.stage === "rejected").length} rejected)`;
  $("#closed").innerHTML = closed.map(cardHtml).join("");
}

/* ---------------- activity + taste ---------------- */

function renderActivity() {
  $("#activity").innerHTML = S.events.map(e => `<li><span class="ts">${esc(e.ts.replace("T", " ").slice(0, 16))}</span>
    <span class="actor">${esc(e.actor)}</span>
    <span>${e.project_name ? `<b>${esc(short(e.project_name))}</b> · ` : ""}${e.initiative_id ? `<a href="#card-${e.initiative_id}" data-init="${e.initiative_id}">#${e.initiative_id}</a> · ` : ""}${esc(e.kind)} ${esc(e.message || "")}</span></li>`).join("")
    || `<li class="empty">No activity yet.</li>`;
}

async function loadTaste() {
  const t = await api("/api/taste");
  $("#taste").innerHTML = t.html || "";
}

/* ---------------- drawer ---------------- */

function openDrawer() { $("#drawer").hidden = false; document.body.style.overflow = "hidden"; }
function closeDrawer() {
  $("#drawer").hidden = true; document.body.style.overflow = ""; openCard = null;
  if (location.hash.startsWith("#card-")) history.replaceState(null, "", location.pathname);
}
function reopen() { openCard.type === "init" ? showInitiative(openCard.id, openCard.tab, true) : showProject(openCard.id, openCard.tab, true); }

function tabs(defs, active) {
  const first = active && defs.find(d => d.key === active && d.html) ? active : (defs.find(d => d.html) || defs[0]).key;
  $("#drawer-tabs").innerHTML = defs.map(d => `<button class="subtab ${d.key === first ? "active" : ""}" data-tab="${d.key}" ${d.html ? "" : "disabled"}>${d.label}</button>`).join("");
  const show = key => {
    const d = defs.find(x => x.key === key);
    $("#drawer-body").innerHTML = d.html;
    $("#drawer-tabs").querySelectorAll(".subtab").forEach(b => b.classList.toggle("active", b.dataset.tab === key));
    if (openCard) openCard.tab = key;
  };
  $("#drawer-tabs").onclick = e => { const b = e.target.closest(".subtab"); if (b && !b.disabled) show(b.dataset.tab); };
  show(first);
}

function planHtml(plan) {
  if (!plan) return "";
  const rows = (plan.subtasks || []).map(s => `<tr><td>${s.id}</td><td><b>${esc(s.title)}</b><div class="hint">${esc(s.instructions || "")}</div>
    ${s.files?.length ? `<div class="hint">files: ${esc(s.files.join(", "))}</div>` : ""}
    ${s.notes ? `<pre class="raw">${esc(s.notes)}</pre>` : ""}</td>
    <td><span class="who who-${s.assignee}">${s.assignee}</span></td><td class="st-${s.status}">${s.status}</td></tr>`).join("");
  const r = plan.review || {};
  return `<table class="subtasks"><thead><tr><th>#</th><th>Subtask</th><th>Routed to</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>
    ${plan.test_command ? `<p class="hint">Test command: <code>${esc(plan.test_command)}</code></p>` : ""}
    <p><b>Planner review:</b> <span class="st-${r.status === "pass" ? "done" : r.status === "fail" ? "blocked" : "todo"}">${esc(r.status || "pending")}</span> ${esc(r.notes || "")}</p>
    <details><summary class="hint">raw execution_plan_json</summary><pre class="raw">${esc(JSON.stringify(plan, null, 2))}</pre></details>`;
}

function testsHtml(plan) {
  if (!plan) return "";
  const subs = (plan.subtasks || []).filter(s => s.verify || s.last_verify);
  const r = plan.review || {};
  return `<h3>Tests</h3>
    <p><b>Planner review:</b> <span class="st-${r.status === "pass" ? "done" : r.status === "fail" ? "blocked" : "todo"}">${esc(r.status || "pending")}</span>
      ${r.by ? `<span class="hint">by ${esc(r.by)} ${ago(r.at)}</span>` : ""}<br>${esc(r.notes || "")}</p>
    ${plan.test_command ? `<p class="hint">Suite: <code>${esc(plan.test_command)}</code></p>` : ""}
    ${subs.map(s => {
      const v = s.last_verify;
      return `<div style="margin:10px 0"><b>#${s.id} ${esc(s.title)}</b> <span class="who who-${s.assignee}">${s.assignee}</span>
        ${v ? `<span class="${v.ok ? "st-done" : "st-blocked"}">${v.ok ? "PASS" : "FAIL"}</span> <span class="hint">${ago(v.at)}</span>` : `<span class="hint">not run</span>`}
        <div class="hint"><code>${esc(s.verify || "")}</code></div>
        ${v && v.output_tail ? `<details><summary class="hint">output</summary><pre class="raw">${esc(v.output_tail)}</pre></details>` : ""}</div>`;
    }).join("")}`;
}

function diffHtml(d, plan) {
  if (!d || !d.branch) return plan ? testsHtml(plan) : "";
  return `<p><code>${esc(d.branch)}</code> vs <code>${esc(d.base)}</code><br><span class="hint">${esc(d.worktree)}</span></p>
    <h3>Commits</h3><pre class="raw">${esc((d.commits || []).join("\n") || "(none yet)")}</pre>
    <h3>Diff stat</h3><pre class="raw">${esc(d.stat || "(no changes)")}</pre>
    ${d.uncommitted?.length ? `<h3>Uncommitted</h3><pre class="raw">${esc(d.uncommitted.join("\n"))}</pre>` : ""}
    ${testsHtml(plan)}`;
}

function historyHtml(events) {
  return `<ol class="activity">${events.map(e => `<li><span class="ts">${esc(e.ts.replace("T", " ").slice(0, 16))}</span><span class="actor">${esc(e.actor)}</span><span>${esc(e.kind)} ${esc(e.message || "")}</span></li>`).join("")}</ol>`;
}

async function showInitiative(id, tab, quiet = false) {
  let d;
  try { d = await api(`/api/initiatives/${id}`); } catch (e) { return toast(e.message, true); }
  const i = d.initiative;
  openCard = { type: "init", id, tab: tab || openCard?.tab };
  if (!quiet) history.replaceState(null, "", `#card-${id}`);
  $("#drawer-eyebrow").innerHTML = `<span class="stage ${AWAITING.has(i.stage) ? "awaiting" : ""}">${i.stage}</span>
    <span class="cat cat-${i.category}">${CATEGORY_LABEL[i.category]}</span> · ${esc(i.project_name)} · #${i.id}
    ${i.assigned_model ? ` · ${esc(i.assigned_model)}` : ""}${i.branch_name ? ` · <code>${esc(i.branch_name)}</code>` : ""}`;
  $("#drawer-title").textContent = i.title;

  const closed = i.stage === "done" || i.stage === "rejected";
  const nextLabel = d.next_stage ? `Approve → ${d.next_stage}` : "Approve";
  const warnBuild = i.stage === "building" || i.branch_name ? " Deletes the feat branch and its worktree." : "";
  $("#drawer-controls").innerHTML = closed
    ? `<div class="controls"><div class="hint">${i.stage === "rejected" ? `Rejected: ${esc(i.rejection_reason || "")}` : "Done."}</div></div>`
    : `<div class="controls">
        <textarea id="note" placeholder="Feedback (required for revise / reject; optional note on approve)"></textarea>
        <div class="row">
          <button class="btn go" data-act="advance" ${d.next_stage ? "" : "disabled"}>${nextLabel}</button>
          <button class="btn rev" data-act="revise">Request revision${d.revise_to && d.revise_to !== i.stage ? ` → ${d.revise_to}` : ""}</button>
          <button class="btn kill" data-act="reject">Reject / Kill</button>
          ${d.claim
            ? `<button class="btn" data-act="release" title="Let the scheduled agents pick this up again">Release chat claim (${esc(d.claim)})</button>`
            : `<button class="btn" data-act="claim" title="Agents skip claimed cards for 24h">Claim for chat</button>`}
        </div>
        ${d.claim ? `<div class="hint claim">💬 Claimed by <b>${esc(d.claim)}</b> until ${esc((i.claim_expires_at || "").replace("T", " ").slice(0, 16))}${i.claim_note ? ` · ${esc(i.claim_note)}` : ""}. Scheduled agents skip it.</div>` : ""}
        <div class="hint">${i.stage === "lld_review" ? "Approving creates feat/" + esc(i.slug) + " in a separate worktree; your checkout is never switched. " : ""}Reject logs your note to TASTE_PROFILE.md.${warnBuild}</div>
      </div>`;
  $("#drawer-controls").onclick = e => { const b = e.target.closest("[data-act]"); if (b) act(i, b.dataset.act); };

  tabs([
    ...(d.playtest_html ? [{ key: "playtest", label: "▶ Playtest", html: `<article class="md">${d.playtest_html}</article>` }] : []),
    { key: "pitch", label: "Pitch", html: `<article class="md">${d.pitch_html || ""}</article>` },
    { key: "hld", label: "HLD", html: d.hld_html && `<article class="md">${d.hld_html}</article>` },
    { key: "lld", label: "LLD", html: d.lld_html && `<article class="md">${d.lld_html}</article>` },
    { key: "plan", label: "Execution routing", html: d.plan && planHtml(d.plan) },
    { key: "diff", label: "Diff / tests", html: diffHtml(d.diff, i.stage === "building" || i.stage === "playtest" || i.stage === "done" ? d.plan : null) },
    { key: "handoff", label: "IDE handoff", html: d.handoff_html && `<article class="md">${d.handoff_html}</article>` },
    { key: "rev", label: "Revisions", html: d.revisions_html && `<article class="md">${d.revisions_html}</article>` },
    { key: "hnotes", label: "Handoff notes", html: d.handoff_notes_html && `<article class="md">${d.handoff_notes_html}</article>` },
    { key: "hist", label: "History", html: historyHtml(d.events) },
  ], openCard.tab);
  openDrawer();
}

async function act(i, action) {
  const note = ($("#note")?.value || "").trim();
  if ((action === "revise" || action === "reject") && !note) return toast("Write feedback first: it goes to the agents" + (action === "reject" ? " and the taste profile." : "."), true);
  if (action === "reject" && !confirm(`Kill "${i.title}"?${i.branch_name ? `\nThis deletes ${i.branch_name} and its worktree.` : ""}`)) return;
  try {
    const r = await api(`/api/initiatives/${i.id}/${action}`, { note });
    toast(action === "claim" ? `#${i.id} claimed for chat; agents will skip it`
      : action === "release" ? `#${i.id} released to agents` : `#${i.id} → ${r.stage}`);
    await refresh(true);
    showInitiative(i.id, null, true);
  } catch (e) { toast(e.message, true); }
}

async function showProject(name, tab, quiet = false) {
  let d;
  try { d = await api(`/api/projects/${encodeURIComponent(name)}`); } catch (e) { return toast(e.message, true); }
  const p = d.project;
  openCard = { type: "project", id: name, tab: tab || openCard?.tab };
  $("#drawer-eyebrow").innerHTML = `${esc(p.stack || "")} · priority ${p.priority} · ${p.complexity} complexity · scanned ${ago(p.last_scanned_at)}`;
  $("#drawer-title").textContent = p.repo_name;
  const cx = S.enums.complexities.map(o => `<option ${o === p.complexity ? "selected" : ""}>${o}</option>`).join("");
  $("#drawer-controls").innerHTML = `<div class="controls"><div class="row" style="align-items:center">
      <label class="hint">Complexity <select class="prio" id="cx">${cx}</select></label>
      <span class="hint">High routes HLDs to Opus.</span>
      ${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener" class="hint">${esc(p.url)}</a>` : `<span class="hint">no remote</span>`}
      <span class="hint">${esc(p.local_path)}</span></div>
      <div class="modebox">
        <div class="modehead">Duration (applies to both modes below)</div>
        <div class="row" style="align-items:center">
          <input type="number" id="dur-n" class="dur" min="0.25" step="0.25" value="4" aria-label="Duration">
          <select class="prio" id="dur-unit" aria-label="Duration unit"><option value="1">hours</option><option value="24">days</option></select>
          <label class="chk"><input type="checkbox" id="dur-inf"> indefinite (until I end it)</label>
        </div>
      </div>
      <div class="modebox">
        <div class="modehead">🎯 Focus session: agents stay <b>out</b>; you work this project by hand in chat</div>
        <div class="row" style="align-items:center">
        ${d.focus
          ? `<button class="btn" id="unfocus">End focus session</button><span class="hint claim">${esc(p.focus_by)} until ${esc(untilText(p.focus_until))}.</span>`
          : `<button class="btn" id="focus">Start focus session</button>`}
        </div>
      </div>
      <div class="modebox">
        <div class="modehead">🔦 Spotlight: <b>all</b> agents work only this project; other projects pause</div>
        <div class="row" style="align-items:center">
          <label class="hint">Aspect <select class="prio" id="spot-aspect">${(S.aspects || ["any"]).map(a => `<option ${a === "any" ? "selected" : ""}>${a}</option>`).join("")}</select></label>
          <label class="hint">Transition <select class="prio" id="spot-mode">
            <option value="graceful" selected>graceful: let in-flight work finish</option>
            <option value="forced">forced: pause other work now</option></select></label>
          <button class="btn" id="spot">Start spotlight</button>
        </div>
        <div class="hint">Either way, each agent must write a handoff note on the work it leaves before it may start here.</div>
      </div></div>`;
  const dur = () => $("#dur-inf").checked ? 0 : (parseFloat($("#dur-n").value) || 0) * parseFloat($("#dur-unit").value);
  $("#spot").onclick = async () => {
    const mode = $("#spot-mode").value;
    if (mode === "forced" && !confirm("Forced spotlight pauses in-progress work on every other project now. Continue?")) return;
    try { await api(`/api/projects/${encodeURIComponent(name)}/spotlight`, { aspect: $("#spot-aspect").value, hours: dur(), note: "", mode }); toast(`Spotlight on (${mode})`); refresh(true); } catch (e) { toast(e.message, true); }
  };
  const fb = $("#focus"), ub = $("#unfocus");
  if (fb) fb.onclick = async () => { try { await api(`/api/projects/${encodeURIComponent(name)}/focus`, { hours: dur(), note: "" }); toast("Focus session started; agents will skip it"); await refresh(true); showProject(name, null, true); } catch (e) { toast(e.message, true); } };
  if (ub) ub.onclick = async () => { try { await api(`/api/projects/${encodeURIComponent(name)}/unfocus`, {}); toast("Focus ended; agents resume"); await refresh(true); showProject(name, null, true); } catch (e) { toast(e.message, true); } };
  $("#cx").onchange = async e => {
    try { await api(`/api/projects/${encodeURIComponent(name)}`, { complexity: e.target.value }); toast("Saved"); refresh(true); }
    catch (err) { toast(err.message, true); }
  };
  const inits = d.initiatives.map(i => `<li><a href="#card-${i.id}" data-init="${i.id}">#${i.id} ${esc(i.title)}</a> <span class="stage">${i.stage}</span></li>`).join("");
  tabs([
    { key: "dossier", label: "Dossier", html: d.dossier_html && `<article class="md">${d.dossier_html}</article>` },
    { key: "scan", label: "Scan facts", html: d.scan && `<pre class="raw">${esc(JSON.stringify(d.scan, null, 2))}</pre>` },
    { key: "audit", label: "Audit notes", html: d.audit_html && `<article class="md">${d.audit_html}</article>` },
    { key: "inits", label: "Initiatives", html: inits && `<ul>${inits}</ul>` },
    { key: "hist", label: "History", html: d.events.length ? historyHtml(d.events) : `<p class="hint">No activity yet.</p>` },
  ], openCard.tab);
  openDrawer();
}

/* ---------------- wiring ---------------- */

document.addEventListener("click", e => {
  const tab = e.target.closest(".tab");
  if (tab) {
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === `view-${tab.dataset.view}`));
    if (tab.dataset.view === "taste") loadTaste();
    if (window.Utilization) {
      if (tab.dataset.view === "utilization") window.Utilization.enter();
      else window.Utilization.leave();
    }
    return;
  }
  if (e.target.closest("[data-close]")) return closeDrawer();
  const card = e.target.closest("[data-init]");
  if (card) { e.preventDefault(); return showInitiative(+card.dataset.init); }
  const pn = e.target.closest("[data-project]");
  if (pn) return showProject(pn.dataset.project);
});

document.addEventListener("change", async e => {
  const sel = e.target.closest("[data-prio]");
  if (!sel) return;
  sel.dataset.v = sel.value;
  try { await api(`/api/projects/${encodeURIComponent(sel.dataset.prio)}`, { priority: sel.value }); toast(`${short(sel.dataset.prio)} → ${sel.value}`); refresh(true); }
  catch (err) { toast(err.message, true); }
});

document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#drawer").hidden) closeDrawer(); });
$("#filter").addEventListener("input", () => S && renderPulse());
$("#show-skip").addEventListener("change", () => S && renderPulse());

(async () => {
  await refresh(true);
  const m = location.hash.match(/^#card-(\d+)/);
  if (m) {
    document.querySelector('.tab[data-view="triage"]').click();
    showInitiative(+m[1]);
  }
  setInterval(refresh, (S?.config.poll_seconds || 4) * 1000);
})();
