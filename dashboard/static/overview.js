/* Pure escaped projections. No forecast control changes persisted priority. */
(function(root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={creation_fallback:'since creation (stage start not recorded)',stage_entry:'since entering this stage',subtask_status_entry:'since this task status began',stage_route:'routed by stage',plan:'routed by plan',claim:'claimed in chat',reset_passed:'reset has passed; refresh the reading',observation_stale:'reading is over 60 minutes old',no_observation:'no reading recorded',clock_skew:'clock differs from observation',job_absent:'scheduled job not found',legacy_exact_name:'matched by exact job name',actor_work_type:'matching actor and work type',actor_fallback_low_confidence:'actor history, lower confidence',actor_fallback:'actor history, all work types',work_type_fallback:'work-type history, all actors',default_prior:'default guess (no history)',hld_draft:'HLD drafting',lld_draft:'LLD drafting',hld_review:'HLD awaiting your review',lld_review:'LLD awaiting your review',spark:'spark',producer:'waiting on you',todo:'queued',doing:'working',blocked:'blocked',playtest:'playtest',building:'building',queued:'queued',cron:'scheduler observation'};
  const plain=v=>labels[v]||String(v??'').replaceAll('_',' ');
  const owner=v=>({codex:'planner-codex',claude:'architect-claude',gemma:'scout-gemma',producer:'you (producer)'})[v]||v||'owner unknown (no route recorded)';
  function local(iso,now=Date.now()) {
    if(!iso || !Number.isFinite(Date.parse(iso))) return 'unknown';
    const diff=Date.parse(iso)-now,minutes=Math.abs(Math.round(diff/60000));
    const span=(minutes>=60?Math.floor(minutes/60)+'h ':'')+(minutes%60)+'m';
    const relative=minutes===0?'now':diff>=0?'in '+span:span+' ago';
    return new Date(iso).toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'})+' ('+relative+')';
  }
  function eta(e) {
    if(!e) return 'Completion unknown (no forecast supplied)';
    const basis=e.basis_label|| (e.sample_count?e.sample_count+' samples, '+plain(e.basis):'');
    if(e.state==='waiting') return 'waiting on you '+Math.floor((e.waiting_seconds||0)/60)+' min'+(e.if_approved_now?'; if approved now, ETA '+eta(e.if_approved_now):'');
    if(e.completion_at) return '~'+esc(local(e.completion_at))+(basis?' · '+esc(basis):'')+' · estimate, not a deadline';
    if(e.state==='over_typical') return 'Over typical duration; waiting for an updated completion estimate'+(basis?' · '+esc(basis):'');
    return esc(plain(e.reason||'Completion unknown'))+(basis?' · '+esc(basis):'')+(e.if_approved_now?'; if approved now, ETA '+eta(e.if_approved_now):'');
  }
  const comparisons=new Map();
  function setComparison(kind,target,result) {comparisons.set(kind+":"+target,{at:Date.now(),result});}
  function preview(kind,target,estimate) {
    const cached=comparisons.get(kind+":"+target);
    const html=cached&&Date.now()-cached.at<30000?comparison(cached.result):"";
    return '<div class="forecast-preview"><span>ETA now: '+eta(estimate)+'</span> <button class="btn" data-forecast-kind="'+esc(kind)+'" data-forecast-target="'+esc(target)+'">If prioritized?</button><div class="forecast-result" role="status">'+html+'</div></div>';
  }
  function comparison(result) {
    return '<b>ETA now:</b> '+eta(result.eta_now)+'<br><b>If prioritized:</b> '+eta(result.if_prioritized)+'<p class="hint">Read-only: assumes top priority; active work, gates and exclusions still apply. Apply with the existing priority control.</p>'+(result.delayed?.length?'<ul>'+result.delayed.map(d=>'<li><a href="#/initiative/'+esc(d.initiative_id)+'">#'+esc(d.initiative_id)+'</a> delayed ~'+Math.round(d.seconds/60)+' min; '+esc(local(d.completion_at))+'</li>').join('')+'</ul>':'<p>No other defined work is forecast to finish later.</p>');
  }
  function rows(items) {
    if(!items.length) return '<p class="hint">None.</p>';
    return '<div class="table-scroll"><table class="subtasks"><thead><tr><th>Work</th><th>Owner / status</th><th>Age / eligibility</th><th>Progress / ETA</th></tr></thead><tbody>'+items.map(i=>
      '<tr><td><a href="'+esc(i.href)+'">#'+esc(i.initiative_id)+(i.subtask_id?' / '+esc(i.subtask_id):'')+' '+esc(i.title)+'</a><div class="hint"><a href="#/project/'+encodeURIComponent(i.project)+'">'+esc(i.project)+'</a></div></td><td>'+esc(owner(i.owner))+'<div class="hint">'+[...new Set([i.stage,i.status].filter(Boolean))].map(v=>esc(plain(v))).join(' · ')+' · '+esc(plain(i.owner_basis))+'</div></td><td>'+Math.floor((i.age_seconds||0)/60)+' min<div class="hint">'+esc(plain(i.age_basis))+' · '+esc(plain(i.eligibility))+'</div></td><td>'+esc(i.progress?.done??0)+'/'+esc(i.progress?.total??0)+' subtasks<div class="estimate">'+eta(i.estimate)+'</div></td></tr>').join('')+'</tbody></table></div>';
  }
  function summary(t) {
    return '<div class="rollup-totals">'+[['Open initiatives','open_initiatives'],['In flight','in_flight'],['Waiting on you','waiting_on_producer'],['Blocked','blocked'],['Queued subtasks','queued_subtasks']].map(([label,key])=>'<div><strong>'+esc(t?.[key]??0)+'</strong><span>'+label+'</span></div>').join('')+'</div>';
  }
  function rollups(data,project) {
    const projects=(data.rollups?.projects||[]).filter(p=>!project||p.project===project);
    const totals=project?projects[0]:data.rollups?.totals;
    return summary(totals)+'<details data-key="project-rollups" open><summary>Project rollups</summary><div class="table-scroll"><table class="subtasks"><thead><tr><th>Project / stages</th><th>Subtasks</th><th>In flight / waiting</th><th>Rollup ETA (next checkpoints)</th></tr></thead><tbody>'+projects.map(p=>'<tr><td><a href="#/project/'+encodeURIComponent(p.project)+'">'+esc(p.project)+'</a><p class="hint">'+Object.entries(p.stages||{}).map(([s,n])=>esc(plain(s))+': '+esc(n)).join(' · ')+'</p></td><td>'+esc(p.subtasks_done)+'/'+esc(p.subtasks_total)+'</td><td>'+esc(p.in_flight)+' in flight / '+esc(p.waiting_on_producer)+' waiting on you</td><td>'+preview('project',p.project,p.estimate)+'</td></tr>').join('')+'</tbody></table></div></details>';
  }
  function timeline(data,project) {
    const events=(data.forecast?.timeline||[]).filter(e=>!project||e.project===project);
    return '<h2>Next hours</h2><p class="hint">Forecast for the next 24 hours, to the next producer checkpoint. Future plans are not invented; gates are never auto-approved.</p>'+(data.forecast?.truncated?'<p class="warning">Forecast budget reached; remaining work is explicitly outside this forecast.</p>':'')+(data.forecast?.reason?'<p class="warning">'+esc(data.forecast.reason)+'</p>':'')+(events.length?'<ol class="forecast-timeline">'+events.map(e=>'<li><time>'+esc(local(e.start_at))+'</time> <b>'+esc(owner(e.actor))+'</b> '+(e.work_type==='scan'?'picks up ':'starts #'+esc(e.initiative_id)+' '+esc(plain(e.work_type))+' ' )+'<a href="'+esc(e.href)+'">'+esc(e.title)+'</a> · '+esc(e.basis_label)+' · done ~'+esc(local(e.completion_at))+'</li>').join('')+'</ol>':'<p>No eligible start is forecast from the current schedules. See row ETAs for paused lanes, spotlight, chat ownership or producer gates.</p>');
  }
  function regions(data,project='') {
    const filter=items=>items.filter(i=>!project||i.project===project);
    const total=(key,fallback)=>data.pages?.[key]?.total??fallback;
    const more=key=>data.pages?.[key]?.next_cursor!=null?'<button class="btn" data-more="'+esc(key)+'" data-offset="'+data.pages[key].next_cursor+'">Load more ('+data.pages[key].total+' total)</button>':'';
    const lanes=(data.lanes||[]).map(l=>'<article class="lane"><h2>'+esc(l.label)+'</h2><strong>'+esc(plain(l.activity?.state||'unknown'))+'</strong><p>Quota: '+esc(plain(l.quota?.state||'unknown'))+'</p><p>'+esc(l.activity?.task_ref||plain(l.activity?.basis)||'Task not identified')+(l.activity?.started_at?' · since '+esc(local(l.activity.started_at)):'')+'</p><p>Future runs: '+esc(plain(l.scheduler?.state||'unknown'))+' · next '+esc(local(l.scheduler?.next_run_at))+'</p><p class="estimate">'+eta(l.estimate)+'</p>'+(l.reason?'<p class="warning">'+esc(plain(l.reason))+'</p>':'')+(l.residency?'<p>Local models: '+esc(l.residency.value??'unknown')+' resident (not proof of generation)</p>':'')+(l.claims||[]).map(c=>'<p><a href="'+esc(c.href)+'">#'+esc(c.initiative_id)+' '+esc(c.title)+'</a> · '+esc(c.owner)+'</p>').join('')+(l.focus||[]).map(f=>'<p><a href="'+esc(f.href)+'">'+esc(f.project)+'</a> · focus '+esc(f.owner)+'</p>').join('')+(l.jobs||[]).map(j=>'<div class="job"><span>'+esc(j.declaration)+'</span><p>'+eta(j.estimate)+'</p><button class="btn" data-lane="'+esc(j.declaration)+'" data-enabled="'+(!j.enabled)+'" data-generation="'+esc(j.generation)+'" '+(!j.controllable?'disabled':'')+'>'+(j.enabled?'Pause':'Resume')+' future runs</button></div>').join('')+'</article>').join('');
    const inFlight=filter(data.in_flight||[]);
    const pending=Object.entries(data.pending||{}).map(([name,items])=>'<details data-key="pending-'+esc(name)+'" open><summary>'+esc(plain(name))+' ('+total('pending.'+name,filter(items).length)+')</summary>'+rows(filter(items))+more('pending.'+name)+'</details>').join('');
    const quotas=(data.lanes||[]).map(l=>Object.entries(l.quota?.windows||{}).map(([w,m])=>'<article class="pace"><b>'+esc(l.label)+' · '+esc(w)+'</b><p>'+esc(m.value??'not recorded')+'% remaining · '+esc(plain(m.status))+'</p><p>'+esc(m.pace)+' · even-burn target used '+(m.target_used==null?'not available':m.target_used.toFixed(1)+'%')+'</p><p>Actual used '+(m.actual_used==null?'not available':m.actual_used.toFixed(1)+'%')+' · difference '+(m.delta_pp==null?'not available':m.delta_pp.toFixed(1)+'pp')+'</p><p class="hint">'+esc(plain(m.baseline||m.reason||'pace unavailable'))+' · reset '+esc(local(m.meta?.resets_at))+' · observed '+esc(local(m.observed_at))+'</p>'+(m.hint?'<p class="warning">'+esc(m.hint)+'</p>':'')+'</article>').join('')).join('');
    const attention=(data.attention||[]).map(a=>'<li><a href="'+esc(a.href)+'">'+esc(a.title)+'</a> · '+esc(plain(a.reason))+'</li>').join('')||'<li>None.</li>';
    return {rollups:rollups(data,project),timeline:timeline(data,project),lanes,next:'<h2>Next expected update</h2><p class="next-time">'+eta(data.next_update)+'</p><p>Next scheduled check: '+esc(local(data.next_update?.next_check_at))+'</p><span class="hint">Observed '+esc(local(data.generated_at))+' · '+data.totals.initiatives+' open initiatives (parent and subtask rows are separate)</span>',flight:'<h2>In flight ('+total('in_flight',inFlight.length)+' rows)</h2>'+rows(inFlight)+more('in_flight'),pending,quotas:quotas||'<p>Quota pace unavailable. Gemini has no measured quota; Gemma is local.</p>',attention:'<ul>'+attention+'</ul>',suggestions:rows(filter(data.suggestions||[]))+more('suggestions')};
  }
  function update(container,data,project='') {
    for(const [key,html] of Object.entries(regions(data,project))) {
      const element=container.querySelector('[data-region="'+key+'"]');
      if(!element||element.contains(container.ownerDocument.activeElement)||element._html===html) continue;
      const open=new Map([...element.querySelectorAll('details[data-key]')].map(d=>[d.dataset.key,d.open]));
      element.innerHTML=html;element._html=html;
      for(const d of element.querySelectorAll('details[data-key]')) if(open.has(d.dataset.key)) d.open=open.get(d.dataset.key);
    }
  }
  const exports={esc,plain,owner,local,eta,rows,regions,update,preview,comparison,summary,setComparison};
  if(typeof module!=='undefined') module.exports=exports;else root.Overview=exports;
})(typeof window!=='undefined'?window:globalThis);
