/* Escaped, pure overview renderers plus draft-preserving keyed region updates. */
(function(root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const local = iso => iso && Number.isFinite(Date.parse(iso)) ? new Date(iso).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'unknown';
  function eta(e) {
    if (e?.completion_at) return 'Likely ~'+local(e.completion_at)+' · '+e.sample_count+' samples · '+e.basis+' · estimate, not a deadline';
    return e?.state === 'over_typical' ? 'Over typical duration; completion unknown' : 'Completion unknown';
  }
  function rows(items) {
    if (!items.length) return '<p class="hint">None.</p>';
    return '<div class="table-scroll"><table class="subtasks"><thead><tr><th>Work</th><th>Owner / status</th><th>Age / eligibility</th></tr></thead><tbody>'+items.map(i=>
      '<tr><td><a href="'+esc(i.href)+'">#'+esc(i.initiative_id)+(i.subtask_id?' / '+esc(i.subtask_id):'')+' '+esc(i.title)+'</a><div class="hint"><a href="#/project/'+encodeURIComponent(i.project)+'">'+esc(i.project)+'</a></div></td><td>'+esc(i.owner || 'unknown')+'<div class="hint">'+esc(i.stage)+' · '+esc(i.status)+' · '+esc(i.owner_basis)+'</div></td><td>'+Math.floor((i.age_seconds||0)/60)+' min<div class="hint">'+esc(i.age_basis)+' · '+esc(i.eligibility)+'</div></td></tr>').join('')+'</tbody></table></div>';
  }
  function regions(data,project='') {
    const filter = items => items.filter(i=>!project || i.project===project);
    const total=(key,fallback)=>data.pages?.[key]?.total??fallback;
    const more=key=>data.pages?.[key]?.next_cursor!=null?'<button class="btn" data-more="'+esc(key)+'" data-offset="'+data.pages[key].next_cursor+'">Load more ('+data.pages[key].total+' total)</button>':'';
    const lanes=(data.lanes||[]).map(l=>'<article class="lane"><h2>'+esc(l.label)+'</h2><strong>'+esc(l.activity?.state||'unknown')+'</strong><p>Quota: '+esc(l.quota?.state||'unknown')+'</p><p>'+esc(l.activity?.task_ref||l.activity?.basis||'Task unknown')+(l.activity?.started_at?' · '+Math.max(0,Math.floor((Date.now()-Date.parse(l.activity.started_at))/60000))+' min (since '+local(l.activity.started_at)+')':'')+'</p><p>Future runs: '+esc(l.scheduler?.state||'unknown')+' · next '+local(l.scheduler?.next_run_at)+'</p><p class="estimate">'+eta(l.estimate)+'</p>'+ (l.reason?'<p class="warning">'+esc(l.reason)+'</p>':'')+(l.residency?'<p>Local models: '+esc(l.residency.value??'unknown')+' resident (not proof of generation)</p>':'')+(l.claims||[]).map(c=>'<p><a href="'+esc(c.href)+'">#'+c.initiative_id+' '+esc(c.title)+'</a> · '+esc(c.owner)+'</p>').join('')+(l.focus||[]).map(f=>'<p><a href="'+esc(f.href)+'">'+esc(f.project)+'</a> · focus '+esc(f.owner)+'</p>').join('')+(l.jobs||[]).map(j=>'<div class="job"><span>'+esc(j.declaration)+'</span><p>'+eta(j.estimate)+'</p><button class="btn" data-lane="'+esc(j.declaration)+'" data-enabled="'+(!j.enabled)+'" data-generation="'+j.generation+'" '+(!j.controllable?'disabled':'')+'>'+(j.enabled?'Pause':'Resume')+' future runs</button></div>').join('')+'</article>').join('');
    const inFlight=filter(data.in_flight||[]);
    const pending=Object.entries(data.pending||{}).map(([name,items])=>'<details data-key="pending-'+esc(name)+'" open><summary>'+esc(name)+' ('+total('pending.'+name,filter(items).length)+')</summary>'+rows(filter(items))+more('pending.'+name)+'</details>').join('');
    const quotas=(data.lanes||[]).map(l=>Object.entries(l.quota?.windows||{}).map(([w,m])=>'<article class="pace"><b>'+esc(l.label)+' · '+esc(w)+'</b><p>'+esc(m.value??'unknown')+'% remaining · '+esc(m.status)+'</p><p>'+esc(m.pace)+' · even-burn target used '+(m.target_used==null?'unknown':m.target_used.toFixed(1)+'%')+'</p><p>Actual used '+(m.actual_used==null?'unknown':m.actual_used.toFixed(1)+'%')+' · Δ '+(m.delta_pp==null?'unknown':m.delta_pp.toFixed(1)+'pp')+'</p><p class="hint">'+esc(m.baseline||m.reason||'pace unavailable')+' · reset '+local(m.meta?.resets_at)+' · observed '+esc(m.observed_at||'never')+'</p></article>').join('')).join('');
    const attention=(data.attention||[]).map(a=>'<li><a href="'+esc(a.href)+'">'+esc(a.title)+'</a> · '+esc(a.reason)+'</li>').join('')||'<li>None.</li>';
    return {lanes, next:'<h2>Next expected update</h2><p class="next-time">'+eta(data.next_update)+'</p><p>Next scheduled check: '+local(data.next_update?.next_check_at)+'</p><span class="hint">Observed '+esc(data.generated_at)+' · '+data.totals.initiatives+' open initiatives (parent and subtask rows are separate)</span>', flight:'<h2>In flight ('+total('in_flight',inFlight.length)+' rows)</h2>'+rows(inFlight)+more('in_flight'), pending, quotas:quotas||'<p>Quota pace unavailable. Gemini has no measured quota; Gemma is local.</p>',attention:'<ul>'+attention+'</ul>',suggestions:rows(filter(data.suggestions||[]))+more('suggestions')};
  }
  function update(container,data,project='') {
    const result=regions(data,project);
    for (const [key,html] of Object.entries(result)) {
      const element=container.querySelector('[data-region="'+key+'"]');
      if (!element || element.contains(container.ownerDocument.activeElement) || element._html===html) continue;
      const open=new Map([...element.querySelectorAll('details[data-key]')].map(d=>[d.dataset.key,d.open]));
      element.innerHTML=html; element._html=html;
      for (const d of element.querySelectorAll('details[data-key]')) if(open.has(d.dataset.key)) d.open=open.get(d.dataset.key);
    }
  }
  const exports={esc,local,eta,rows,regions,update};
  if(typeof module!=='undefined') module.exports=exports; else root.Overview=exports;
})(typeof window!=='undefined'?window:globalThis);
