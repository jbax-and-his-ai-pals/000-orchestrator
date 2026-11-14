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
let O = null;
let refreshBusy = false;
const detailSequence = Navigation.sequence();
let returnFocus = null;
let previousRoute = "#/";
let lastAppliedRoute = "#/";
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
  if(refreshBusy) return;
  refreshBusy=true;
  try {
    if (!force && S) {
      const v = await api("/api/version");
      if (v.version === version) { $("#live-dot").className = "dot on"; return; }
    }
    S = await api("/api/state");
    version = S.version;
    const oldOverview=O, filterValue=$("#overview-filter").value;
    O = await api("/api/overview?project="+encodeURIComponent(filterValue));
    if(oldOverview?.project_filter===filterValue) {
      for(const collection of Object.keys(O.pages)) {
        const items=(report,key)=>key.startsWith('pending.')?report.pending[key.split('.')[1]]:report[key];
        const previousCount=items(oldOverview,collection).length;
        while(items(O,collection).length<previousCount && O.pages[collection].next_cursor!=null) {
          const page=await api('/api/overview?project='+encodeURIComponent(filterValue)+'&collection='+encodeURIComponent(collection)+'&offset='+O.pages[collection].next_cursor);
          items(O,collection).push(...items(page,collection));O.pages[collection]=page.pages[collection];
        }
      }
    }
    const filter=$("#overview-filter");
    if(!filter.matches(":focus")) {
      const selected=filter.value;
      filter.innerHTML='<option value="">All projects</option>'+O.projects.map(p=>'<option value="'+esc(p.repo_name)+'">'+esc(p.repo_name)+'</option>').join("");
      filter.value=selected;
    }
    $("#live-dot").className = "dot on";
    render();
    // Detail is an explicit snapshot: polling never replaces forms or scroll.
  } catch (e) {
    $("#live-dot").className = "dot err";
  } finally { refreshBusy=false; }
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
  if(O) Overview.update($("#view-overview"),O,$("#overview-filter").value);
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
        <a class="pname" href="#/project/${encodeURIComponent(p.repo_name)}" data-project="${esc(p.repo_name)}"><span class="pnum">${num(p.repo_name)}</span>${esc(short(p.repo_name))}</a>
        <select class="prio" data-v="${p.priority}" data-prio="${esc(p.repo_name)}" aria-label="Priority">${opts}</select>
      </div>
      <div class="badges">
        ${O?.projects.find(x=>x.repo_name===p.repo_name)?.recent_activity ? '<span class="badge">recent activity (not confirmed running)</span>' : ""}
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
  return `<a href="#/initiative/${i.id}" class="card ${awaiting ? "awaiting" : O?.confirmed_active?.includes(i.id) ? "working" : ""}" data-init="${i.id}" id="card-${i.id}">
    <div class="card-sub"><span class="stage ${awaiting ? "awaiting" : ""}">${i.stage}</span>
      <span class="cat cat-${i.category}">${CATEGORY_LABEL[i.category]}</span>${i.complexity === "high" ? `<span class="cat" style="color:var(--violet)">· high</span>` : ""}</div>
    <div class="card-title">${esc(i.title)}${O?.confirmed_active?.includes(i.id) ? ' <span class="badge">confirmed working</span>' : ""}</div>
    <div class="card-sub">${esc(i.project_name === "NEW_CONCEPT" ? "✦ new concept" : short(i.project_name))} · ${ago(i.updated_at)}${prog}</div>
    ${i.revision_note ? `<div class="card-sub" style="color:var(--warn)">↺ ${esc(i.revision_note.slice(0, 90))}</div>` : ""}
    ${i.claim ? `<div class="card-sub claim">💬 in chat: ${esc(i.claim)}</div>` : ""}
  </a>`;
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

function openDrawer() {
  const wasHidden=$("#drawer").hidden;
  if(wasHidden) returnFocus=document.activeElement;
  $("#drawer").hidden=false; document.body.style.overflow="hidden";
  if(wasHidden) $("#drawer [data-close]").focus();
}
function closeDrawer() {
  $("#drawer").hidden = true; document.body.style.overflow = ""; openCard = null;
  detailSequence.next();
  if(location.hash.includes("/initiative/") || location.hash.includes("/project/") || location.hash.startsWith("#card-")) location.hash=previousRoute;
  if(returnFocus?.isConnected) returnFocus.focus(); else $('.tab[data-view="overview"]').focus();
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

function planHtml(plan,iid,planVersion) {
  if (!plan) return "";
  const rows = (plan.subtasks || []).map(s => `<tr><td>${s.id}</td><td><b><a href="#/initiative/${iid}/subtask/${s.id}">${esc(s.title)}</a></b><div class="hint">${esc(s.instructions || "")}</div>
    ${s.files?.length ? `<div class="hint">files: ${esc(s.files.join(", "))}</div>` : ""}
    ${s.notes ? `<pre class="raw">${esc(s.notes)}</pre>` : ""}</td>
    <td><span class="who who-${s.assignee}">${s.assignee}</span></td><td class="st-${s.status}">${s.status}</td></tr>`).join("");
  const r = plan.review || {};
  const orderControls='<p class="hint">Pending order changes implicit prerequisites. Done/doing positions stay fixed.</p>'+(plan.subtasks||[]).map((s,n)=>'<div class="reorder"><span>#'+s.id+' '+esc(s.title)+'</span>'+[[-1,"Up"],[1,"Down"]].map(([delta,label])=>'<button class="btn" data-reorder="'+iid+'" data-index="'+n+'" data-delta="'+delta+'" data-version="'+esc(planVersion)+'" data-order="'+esc(JSON.stringify(plan.subtasks.map(x=>x.id)))+'" '+(["done","doing"].includes(s.status)||n+delta<0||n+delta>=plan.subtasks.length?"disabled":"")+'>'+label+' #'+s.id+'</button>').join("")+'</div>').join("");
  return `${orderControls}<table class="subtasks"><thead><tr><th>#</th><th>Subtask</th><th>Routed to</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>
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
  const seq=detailSequence.next();
  let d;
  try { d = await api(`/api/initiatives/${id}`); } catch (e) { return toast(e.message, true); }
  if(!detailSequence.valid(seq)) return;
  const i = d.initiative;
  openCard = { type: "init", id, tab: tab || openCard?.tab };
  $("#drawer-breadcrumbs").innerHTML='<a href="#/">Overview</a> / <a href="#/project/'+encodeURIComponent(i.project_name)+'">'+esc(i.project_name)+'</a> / #'+i.id;
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
  $("#drawer-controls").insertAdjacentHTML("afterbegin", `<div class="controls"><label>Initiative priority <select id="initiative-priority">${["high","medium","low"].map(p=>`<option ${p===i.priority?"selected":""}>${p}</option>`).join("")}</select></label></div>`);
  $("#initiative-priority").onchange=async e=>{const b=e.target;b.disabled=true;try{await api(`/api/initiatives/${id}/priority`,{priority:b.value,expected_version:d.version});d.version=(await api(`/api/initiatives/${id}`)).version;toast("Priority saved");await refresh(true);}catch(err){toast(err.message,true);}finally{b.disabled=false;}};
  $("#drawer-controls").onclick = e => { const b = e.target.closest("[data-act]"); if (b) act(i, b.dataset.act); };

  tabs([
    ...(d.playtest_html ? [{ key: "playtest", label: "▶ Playtest", html: `<article class="md">${d.playtest_html}</article>` }] : []),
    { key: "pitch", label: "Pitch", html: `<article class="md">${d.pitch_html || ""}</article>` },
    { key: "hld", label: "HLD", html: d.hld_html && `<article class="md">${d.hld_html}</article>` },
    { key: "lld", label: "LLD", html: d.lld_html && `<article class="md">${d.lld_html}</article>` },
    { key: "plan", label: "Execution routing", html: d.plan && planHtml(d.plan,id,d.plan_version) },
    { key: "diff", label: "Diff / tests", html: diffHtml(d.diff, i.stage === "building" || i.stage === "playtest" || i.stage === "done" ? d.plan : null) },
    { key: "handoff", label: "IDE handoff", html: d.handoff_html && `<article class="md">${d.handoff_html}</article>` },
    { key: "rev", label: "Revisions", html: d.revisions_html && `<article class="md">${d.revisions_html}</article>` },
    { key: "hnotes", label: "Handoff notes", html: d.handoff_notes_html && `<article class="md">${d.handoff_notes_html}</article>` },
    { key: "hist", label: "History", html: historyHtml(d.events) },
  ], openCard.tab);
  openDrawer();
}

let actionBusy=false;
async function act(i, action) {
  if(actionBusy)return;
  const note = ($("#note")?.value || "").trim();
  if ((action === "revise" || action === "reject") && !note) return toast("Write feedback first: it goes to the agents" + (action === "reject" ? " and the taste profile." : "."), true);
  if (action === "reject" && !confirm(`Kill "${i.title}"?${i.branch_name ? `\nThis deletes ${i.branch_name} and its worktree.` : ""}`)) return;
  actionBusy=true;
  $("#drawer-controls").querySelectorAll("[data-act]").forEach(b=>b.disabled=true);
  try {
    const r = await api(`/api/initiatives/${i.id}/${action}`, { note });
    toast(action === "claim" ? `#${i.id} claimed for chat; agents will skip it`
      : action === "release" ? `#${i.id} released to agents` : `#${i.id} → ${r.stage}`);
    await refresh(true);
    if($("#note"))$("#note").value="";
    showInitiative(i.id, null, true);
  } catch (e) { toast(e.message, true); } finally {actionBusy=false;$("#drawer-controls").querySelectorAll("[data-act]").forEach(b=>b.disabled=false);}
}

async function showProject(name, tab, quiet = false) {
  const seq=detailSequence.next();
  let d;
  try { d = await api(`/api/projects/${encodeURIComponent(name)}`); } catch (e) { return toast(e.message, true); }
  if(!detailSequence.valid(seq)) return;
  const p = d.project;
  $("#drawer-breadcrumbs").innerHTML='<a href="#/">Overview</a> / '+esc(name);
  openCard = { type: "project", id: name, tab: tab || openCard?.tab };
  $("#drawer-eyebrow").innerHTML = `${esc(p.stack || "")} · priority ${p.priority} · ${p.complexity} complexity · scanned ${ago(p.last_scanned_at)}`;
  $("#drawer-title").textContent = p.repo_name;
  const cx = S.enums.complexities.map(o => `<option ${o === p.complexity ? "selected" : ""}>${o}</option>`).join("");
  $("#drawer-controls").innerHTML = `<div class="controls"><div class="row" style="align-items:center">
      <label>Project priority <select id="project-priority">${["high","medium","low","skip"].map(pr=>`<option ${pr===p.priority?"selected":""}>${pr}</option>`).join("")}</select></label>
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
  $("#project-priority").onchange=async e=>{const b=e.target;b.disabled=true;try{await api(`/api/projects/${encodeURIComponent(name)}`,{priority:b.value,expected_version:d.project_version});d.project_version=(await api(`/api/projects/${encodeURIComponent(name)}`)).project_version;toast("Priority saved");await refresh(true);}catch(err){toast(err.message,true);}finally{b.disabled=false;}};
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
    try { await api(`/api/projects/${encodeURIComponent(name)}`, { complexity: e.target.value, expected_version:d.project_version }); toast("Saved"); refresh(true); }
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
    const targetHash=tab.dataset.view==="overview"?"#/":"#/tab/"+tab.dataset.view;
    if(location.hash!==targetHash) location.hash=targetHash;
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
  if (card) { e.preventDefault(); previousRoute=Navigation.parse(location.hash).type==="project"?location.hash:"#/"; location.hash="#/initiative/"+card.dataset.init; return; }
  const pn = e.target.closest("[data-project]");
  if (pn) {e.preventDefault();previousRoute="#/";location.hash="#/project/"+encodeURIComponent(pn.dataset.project);return;}
});

document.addEventListener("change", async e => {
  const sel = e.target.closest("[data-prio]");
  if (!sel) return;
  sel.dataset.v = sel.value;
  try { await api(`/api/projects/${encodeURIComponent(sel.dataset.prio)}`, { priority: sel.value, expected_version:O?.projects.find(p=>p.repo_name===sel.dataset.prio)?.version }); toast(`${short(sel.dataset.prio)} → ${sel.value}`); refresh(true); }
  catch (err) { toast(err.message, true); }
});

document.addEventListener("keydown", e => { if(!$("#drawer").hidden) {if(e.key==="Escape") closeDrawer();else Navigation.trap(e,$(".drawer-panel"));} });
$("#filter").addEventListener("input", () => S && renderPulse());
$("#show-skip").addEventListener("change", () => S && renderPulse());

(async () => {
  await refresh(true);
  applyRoute();
  setInterval(refresh, (S?.config.poll_seconds || 4) * 1000);
})();


$("#overview-filter").onchange=()=>refresh(true);
let ideaToken=crypto.randomUUID();
$("#idea-form").onsubmit=async e=>{
  e.preventDefault();const form=e.currentTarget,b=form.querySelector('button');if(b.disabled)return;b.disabled=true;
  const values=Object.fromEntries(new FormData(form));
  try {const result=await api('/api/suggestions',{...values,idempotency_key:ideaToken});form.reset();ideaToken=crypto.randomUUID();$("#idea-status").textContent='Created spark #'+result.id;await refresh(true);}
  catch(err){$("#idea-status").textContent=err.message;}finally{b.disabled=false;}
};
document.addEventListener('click',async e=>{
  const lane=e.target.closest('[data-lane]'),order=e.target.closest('[data-reorder]');
  const button=lane||order;if(!button||button.disabled)return;
  if(lane && !confirm((lane.dataset.enabled==='true'?'Resume':'Pause')+' '+lane.dataset.lane+'? Affects future runs only; current work is not cancelled.'))return;
  if(order && !confirm('Change pending order? This changes implicit prerequisites; completed and doing entries stay fixed.'))return;
  button.disabled=true;
  try {
    if(lane)await api('/api/lanes/'+encodeURIComponent(lane.dataset.lane)+'/control',{enabled:lane.dataset.enabled==='true',expected_generation:+lane.dataset.generation});
    else {const ids=JSON.parse(order.dataset.order),n=+order.dataset.index,m=n+(+order.dataset.delta);[ids[n],ids[m]]=[ids[m],ids[n]];await api('/api/initiatives/'+order.dataset.reorder+'/subtasks/reorder',{order:ids,expected_plan_version:order.dataset.version});}
    toast('Saved');await refresh(true);if(order)showInitiative(+order.dataset.reorder,'plan',true);
  }catch(err){toast(err.message,true);await refresh(true);}finally{button.disabled=false;}
});
async function showSubtask(iid,sid) {
  const seq=detailSequence.next();
  try {
    const d=await api('/api/initiatives/'+iid+'/subtasks/'+sid);if(!detailSequence.valid(seq))return;
    openCard={type:'subtask',id:iid,sid};
    $('#drawer-breadcrumbs').innerHTML='<a href="#/">Overview</a> / <a href="#/initiative/'+iid+'">Initiative #'+iid+'</a> / Subtask '+sid;
    $('#drawer-title').textContent=d.title;$('#drawer-eyebrow').textContent=(d.assignee||'unknown')+' · '+d.status;
    $('#drawer-controls').innerHTML='';$('#drawer-tabs').innerHTML='';
    $('#drawer-body').innerHTML='<h3>Instructions</h3><pre class="raw">'+esc(d.instructions)+'</pre><h3>Acceptance</h3><p>'+esc(d.acceptance)+'</p><h3>Verify</h3><code>'+esc(d.verify)+'</code><pre class="raw">'+esc(d.last_verify?.output_tail||'Not run')+'</pre><h3>Diff · '+esc(d.diff.basis)+'</h3><pre class="raw">'+esc(d.diff.patch||'See initiative Diff / tests for legacy changes.')+'</pre>'+(d.diff.href?'<p><a href="'+esc(d.diff.href)+'">View initiative-wide diff / tests</a></p>':'')+(d.diff.truncated?'<p>Patch truncated.</p>':'')+'<h3>History</h3>'+historyHtml(d.history)+(d.next_cursor?'<button class="btn" id="more-history">More history</button>':'');
    const more=$('#more-history');let cursor=d.next_cursor;if(more)more.onclick=async()=>{more.disabled=true;try{const page=await api('/api/initiatives/'+iid+'/subtasks/'+sid+'?before='+cursor);if(detailSequence.valid(seq)){more.insertAdjacentHTML('beforebegin',historyHtml(page.history));cursor=page.next_cursor;if(!cursor)more.remove();else more.disabled=false;}}catch(err){toast(err.message,true);more.disabled=false;}};
    openDrawer();
  }catch(err){if(detailSequence.valid(seq))toast(err.message,true);}
}
function applyRoute() {
  const route=Navigation.parse(location.hash);
  if(location.hash!==lastAppliedRoute && ["initiative","project","subtask"].includes(route.type)) previousRoute=lastAppliedRoute;
  lastAppliedRoute=location.hash||"#/";
  if(route.type==='initiative')return showInitiative(route.id);
  if(route.type==='subtask')return showSubtask(route.id,route.sid);
  if(route.type==='project')return showProject(route.id);
  if(!$('#drawer').hidden)closeDrawer();
  const tab=route.type==='tab'?route.tab:'overview';
  if(route.type==='not-found')toast('Route not found',true);
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===tab));
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+tab));
  if(tab==='taste')loadTaste();
  if(window.Utilization)tab==='utilization'?Utilization.enter():Utilization.leave();
}
window.addEventListener('hashchange',applyRoute);

// Fetch further inventory pages only on demand; every count includes unloaded rows.
document.addEventListener('click',async e=>{
  const button=e.target.closest('[data-more]');if(!button||button.disabled)return;button.disabled=true;
  const project=$('#overview-filter').value,collection=button.dataset.more;
  try {
    const page=await api('/api/overview?project='+encodeURIComponent(project)+'&collection='+encodeURIComponent(collection)+'&offset='+button.dataset.offset);
    if(project!==$('#overview-filter').value)return;
    if(collection.startsWith('pending.'))O.pending[collection.split('.')[1]].push(...page.pending[collection.split('.')[1]]);
    else O[collection].push(...page[collection]);
    O.pages[collection]=page.pages[collection];
    button.blur();Overview.update($('#view-overview'),O,project);
  }catch(err){toast(err.message,true);button.disabled=false;}
});
