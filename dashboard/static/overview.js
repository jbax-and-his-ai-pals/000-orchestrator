/* Pure escaped projections. No forecast control changes persisted priority. */
(function(root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={hld:'HLD',lld:'LLD',build:'build',review:'review',creation_fallback:'since creation (stage start not recorded)',stage_entry:'since entering this stage',subtask_status_entry:'since this task status began',stage_route:'routed by stage',plan:'routed by plan',claim:'claimed in chat',reset_passed:'reset has passed; refresh the reading',observation_stale:'reading is over 60 minutes old',no_observation:'no reading recorded',clock_skew:'clock differs from observation',job_absent:'scheduled job not found',legacy_exact_name:'matched by exact job name',actor_work_type:'matching actor and work type',actor_fallback_low_confidence:'actor history, lower confidence',actor_fallback:'actor history, all work types',work_type_fallback:'work-type history, all actors',default_prior:'default guess (no history)',hld_draft:'HLD drafting',lld_draft:'LLD drafting',hld_review:'HLD awaiting your review',lld_review:'LLD awaiting your review',spark:'spark',producer:'waiting on you',todo:'queued',doing:'working',blocked:'blocked',playtest:'playtest',building:'building',queued:'queued',cron:'scheduler observation'};
  const plain=v=>labels[v]||String(v??'').replaceAll('_',' ');
  const owner=v=>({codex:'planner-codex',claude:'architect-claude',gemma:'scout-gemma',producer:'you (producer)'})[v]||v||'owner unknown (no route recorded)';
  function local(iso,now=Date.now()) {
    if(!iso || !Number.isFinite(Date.parse(iso))) return 'unknown';
    const diff=Date.parse(iso)-now,minutes=Math.abs(Math.round(diff/60000));
    const span=(minutes>=60?Math.floor(minutes/60)+'h ':'')+(minutes%60)+'m';
    const relative=minutes===0?'now':diff>=0?'in '+span:span+' ago';
    return new Date(iso).toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'})+' ('+relative+')';
  }
  function until(iso,now=Date.now()) {
    const m=Math.round((Date.parse(iso)-now)/60000);
    if(!Number.isFinite(m)) return 'unknown';
    if(m<=0) return 'now';
    return 'in '+(m>=60?Math.floor(m/60)+' hr'+(m>=120?'s':'')+(m%60?' '+(m%60)+' min':''):m+' min');
  }
  function describe(e) {
    const who={'scout-gemma':'Gemma','planner-codex':'Codex','architect-claude':'Claude'}[owner(e.actor)]||owner(e.actor);
    const card=e.initiative_id?'#'+e.initiative_id+' ':'';
    if(e.work_type==='scan') return who+' refreshes the '+e.project+' dossier';
    if(e.work_type==='build') return who+' builds “'+e.title+'” ('+card+'subtask '+e.subtask_id+')';
    return who+' starts the '+plain(e.work_type)+' for '+card+e.title;
  }
  function nextUpdate(e) {
    if(!e||!e.start_at) return '<p class="next-time">'+eta(e)+'</p>';
    return '<p class="next-time">'+esc(until(e.start_at))+' <span class="hint">('+esc(local(e.start_at).replace(/ \(.*\)$/,''))+')</span></p>'
      +'<p class="next-what"><a href="'+esc(e.href)+'">'+esc(describe(e))+'</a></p>'
      +'<p class="hint">Takes '+esc(e.basis_label||'unknown')+' · done ~'+esc(local(e.completion_at))+'</p>';
  }
  function eta(e) {
    if(!e) return 'Completion unknown (no forecast supplied)';
    const basis=e.basis_label|| (e.sample_count?e.sample_count+' samples, '+plain(e.basis):'');
    if(e.state==='waiting') return 'waiting on you '+Math.floor((e.waiting_seconds||0)/60)+' min'+(e.if_approved_now?'; if approved now, ETA '+eta(e.if_approved_now):'');
    if(e.completion_at) return '~'+esc(local(e.completion_at))+(basis?' · '+esc(basis):'');
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
    return '<b>ETA now:</b> '+eta(result.eta_now)+'<br><b>If prioritized:</b> '+eta(result.if_prioritized)+'<p class="hint">Read-only: assumes top priority; active work, gates and exclusions still apply. Apply with the existing priority control.</p>'+(result.delayed?.length?'<ul>'+result.delayed.map(d=>'<li><a href="#/initiative/'+esc(d.initiative_id)+'">#'+esc(d.initiative_id)+'</a> '+(d.seconds==null?'delayed: '+esc(plain(d.reason)):'delayed ~'+Math.round(d.seconds/60)+' min; '+esc(local(d.completion_at)))+'</li>').join('')+'</ul>':'<p>No other defined work is forecast to finish later.</p>');
  }
  function rows_(items){return rows(items);}
  function rows(items,ctx) {
    if(!items.length) return '<p class="hint">None.</p>';
    items=prioritize(items,ctx);
    const age=s=>{const m=Math.floor((s||0)/60);return m<60?m+' min':Math.floor(m/60)+' hr '+(m%60)+' min';};
    return '<table class="worktable"><thead><tr><th>Work</th><th>Stage</th><th>Owner</th><th>Age</th><th>Progress</th><th>ETA</th></tr></thead><tbody>'+items.map(i=>
      '<tr><td><a href="'+esc(i.href)+'">#'+esc(i.initiative_id)+(i.subtask_id?' / '+esc(i.subtask_id):'')+' '+esc(i.title)+'</a> '+projTag(i.project)+prioTag(ctx,i.project,i.initiative_id,i.priority)+'</td><td>'+esc(STAGE[i.stage]||plain(i.stage))+'</td><td title="'+esc(plain(i.owner_basis))+'">'+esc(owner(i.owner))+'</td><td title="'+esc(plain(i.age_basis)+' · '+plain(i.eligibility))+'">'+age(i.age_seconds)+'</td><td>'+(i.progress?.total?esc(i.progress.done)+'/'+esc(i.progress.total):'—')+'</td><td class="estimate">'+eta(i.estimate)+'</td></tr>').join('')+'</tbody></table>';
  }
  function summary(t) {
    return '<div class="rollup-totals">'+[['Open initiatives','open_initiatives'],['In flight','in_flight'],['Waiting on you','waiting_on_producer'],['Blocked','blocked'],['Queued subtasks','queued_subtasks']].map(([label,key])=>'<div><strong>'+esc(t?.[key]??0)+'</strong><span>'+label+'</span></div>').join('')+'</div>';
  }
  function rollups(data,project) {
    const all=(data.rollups?.projects||[]).filter(p=>!project||p.project===project);
    const projects=prioritize(all.filter(p=>project||p.subtasks_total||Object.keys(p.stages||{}).length),data.priority_context,p=>[p.project]),idle=all.filter(p=>!projects.includes(p));
    const totals=project?projects[0]:data.rollups?.totals;
    return (project?summary(totals):'')+'<details data-key="project-rollups" open><summary>Projects</summary><div class="table-scroll"><table class="subtasks"><thead><tr><th>Project / stages</th><th>Subtasks</th><th>In flight / waiting</th><th>Rollup ETA (next checkpoints)</th></tr></thead><tbody>'+projects.map(p=>'<tr><td><a href="#/project/'+encodeURIComponent(p.project)+'">'+esc(p.project)+'</a>'+prioTag(data.priority_context,p.project)+'<p class="hint">'+Object.entries(p.stages||{}).map(([s,n])=>esc(plain(s))+': '+esc(n)).join(' · ')+'</p></td><td>'+esc(p.subtasks_done)+'/'+esc(p.subtasks_total)+'</td><td>'+esc(p.in_flight)+' in flight / '+esc(p.waiting_on_producer)+' waiting on you</td><td>'+preview('project',p.project,p.estimate)+'</td></tr>').join('')+'</tbody></table></div>'+(idle.length?'<p class="hint">No open initiatives: '+idle.map(p=>'<a href="#/project/'+encodeURIComponent(p.project)+'">'+esc(p.project)+'</a>').join(', ')+'</p>':'')+'</details>';
  }
  function timeline(data,project) {
    const events=(data.forecast?.timeline||[]).filter(e=>!project||e.project===project);
    return '<h2>Next hours</h2><p class="hint">Forecast for the next 24 hours, to the next producer checkpoint. Future plans are not invented; gates are never auto-approved.</p>'+(data.forecast?.truncated?'<p class="warning">Forecast budget reached; remaining work is explicitly outside this forecast.</p>':'')+(data.forecast?.reason?'<p class="warning">'+esc(data.forecast.reason)+'</p>':'')+(events.length?'<ol class="forecast-timeline">'+events.map(e=>'<li><time>'+esc(local(e.start_at))+'</time> <b>'+esc(owner(e.actor))+'</b> '+(e.work_type==='scan'?'picks up ':'starts #'+esc(e.initiative_id)+' '+esc(plain(e.work_type))+' ' )+'<a href="'+esc(e.href)+'">'+esc(e.title)+'</a> · '+esc(e.basis_label)+' · done ~'+esc(local(e.completion_at))+'</li>').join('')+'</ol>':'<p>No eligible start is forecast from the current schedules. See row ETAs for paused lanes, spotlight, chat ownership or producer gates.</p>');
  }

  /* ---- Priority: one ranking shared by every tab. With nothing designated (all medium, no focus,
     spotlight or chat claim) every score is equal, so each tab keeps its own order. ---- */
  const PRIO_TAG={spotlight:'🔦 spotlight',focus:'🎯 focus',claim:'💬 in chat',project_high:'▲ high-priority project',high:'▲ high priority'};
  function rank(ctx,project,iid,ipriority) {
    ctx=ctx||{};const proj=(ctx.projects||{})[project]||{},card=(ctx.initiatives||{})[iid]||{};
    project=project||card.project;const p=(ctx.projects||{})[project]||proj;
    if(ctx.spotlight&&ctx.spotlight===project) return {score:0,tag:'spotlight'};
    if(p.focus) return {score:1,tag:'focus'};
    if(iid!=null&&(ctx.claims||[]).includes(Number(iid))) return {score:2,tag:'claim'};
    if(p.priority==='high') return {score:3,tag:'project_high'};
    const ip=card.priority||ipriority;
    if(ip==='high') return {score:4,tag:'high'};
    if(p.priority==='low'||p.priority==='skip'||ip==='low') return {score:6,tag:''};
    return {score:5,tag:''};
  }
  const rowKey=r=>[r.project,r.initiative_id,r.priority];
  function prioritize(list,ctx,key=rowKey) {
    return list.map((x,i)=>[rank(ctx,...key(x)).score,i,x]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]).map(t=>t[2]);
  }
  function prioTag(ctx,project,iid,ip) {const t=rank(ctx,project,iid,ip).tag;return t?'<span class="prio-tag '+t+'">'+esc(PRIO_TAG[t])+'</span>':'';}
  const pnum=name=>(String(name||'').match(/^(\d{3})-/)||[])[1]||'';
  const pshort=name=>String(name||'').replace(/^\d{3}-/,'');
  function projTag(project) {
    if(!project) return '';
    return '<a class="proj-tag" href="#/project/'+encodeURIComponent(project)+'" title="'+esc(project)+'">'+(pnum(project)?'<span class="proj-num">'+esc(pnum(project))+'</span>':'')+'<span class="proj-name">'+esc(project==='NEW_CONCEPT'?'new concept':pshort(project))+'</span></a>';
  }
  function prioStrip(data) {
    const ctx=data.priority_context||{},open=Object.entries(ctx.initiatives||{}).filter(([,i])=>!['done','rejected'].includes(i.stage));
    const chips=[];
    if(ctx.spotlight) chips.push('<span class="prio-tag spotlight">🔦 spotlight</span>'+projTag(ctx.spotlight));
    for(const [name,p] of Object.entries(ctx.projects||{})) if(p.focus) chips.push('<span class="prio-tag focus">🎯 focus</span>'+projTag(name));
    for(const id of ctx.claims||[]){const i=(ctx.initiatives||{})[id]||{};chips.push('<span class="prio-tag claim">💬 in chat</span><a href="#/initiative/'+esc(id)+'">#'+esc(id)+' '+esc(i.title||'')+'</a>');}
    for(const [name,p] of Object.entries(ctx.projects||{})) if(p.priority==='high') chips.push('<span class="prio-tag project_high">▲ high</span>'+projTag(name));
    for(const [id,i] of open) if(i.priority==='high') chips.push('<span class="prio-tag high">▲ high</span><a href="#/initiative/'+esc(id)+'">#'+esc(id)+' '+esc(i.title)+'</a>');
    return chips.length?'<b>Prioritized</b> <span class="hint">sorted to the top of every list</span><ul>'+chips.map(c=>'<li>'+c+'</li>').join('')+'</ul>':'';
  }

  /* ---- crisp overview: numbers, status, action, milestones ---- */
  const WHO={gemma:'Gemma',codex:'Codex',claude:'Claude',gemini:'Gemini',chat:'Chat'};
  const VERB={'branch to playtest':'Playtest','HLD to review':'Review HLD','LLD + plan to review':'Review LLD + plan','pitch to approve':'Approve pitch','quota stale':'Refresh quota reading'};
  function quotaClass(v){return v==null?'':v<20?'bad':v<50?'warn':'good';}
  function kpis(data) {
    const t=data.rollups?.totals||{},q=(k,w='5h')=>(data.lanes||[]).find(l=>l.key===k)?.quota?.windows?.[w]?.value;
    const pct=v=>v==null?'—':Math.round(v)+'%';
    const tile=(n,label,cls,href,sub)=>'<'+(href?'a href="'+href+'"':'div')+' class="kpi '+(cls||'')+'"><strong>'+esc(n)+'</strong><span>'+esc(label)+'</span>'+(sub?'<em>'+sub+'</em>':'')+'</'+(href?'a':'div')+'>';
    const wk=k=>{const v=q(k,'weekly');return 'weekly <b class="'+quotaClass(v)+'-t">'+esc(pct(v))+'</b> left';};
    const g=data.gemini_free_tier||{};
    const gem=g.exhausted?['Unavailable','bad','free tier used up · resets '+until(g.resets_at)]:['Available','good',(g.runs_today?g.runs_today+' runs today':'free tier unused today')+' · resets '+until(g.resets_at)];
    return tile(t.waiting_on_producer??0,'Waiting on you',t.waiting_on_producer?'warn':'','#/tab/triage')
      +tile(t.in_flight??0,'In flight','teal','#/tab/activity')
      +tile(t.queued_subtasks??0,'Queued subtasks')
      +tile(t.blocked??0,'Blocked',t.blocked?'bad':'','#/tab/work')
      +tile(t.open_initiatives??0,'Open initiatives','','#/tab/work')
      +tile((t.subtasks_done??0)+'/'+(t.subtasks_total??0),'Subtasks done')
      +tile(pct(q('codex')),'Codex 5h left',quotaClass(q('codex')),'#/tab/utilization',wk('codex'))
      +tile(pct(q('claude')),'Claude 5h left',quotaClass(q('claude')),'#/tab/utilization',wk('claude'))
      +tile(gem[0],'Gemini',gem[1],'#/tab/utilization',esc(gem[2]));
  }
  const STAGE={spark:'pitch',hld_draft:'drafting HLD',hld_review:'HLD review',lld_draft:'drafting LLD',lld_review:'LLD review',building:'building',playtest:'playtest'};
  function ago(iso){const m=Math.round((Date.now()-Date.parse(iso))/60000);return !Number.isFinite(m)?'':m<1?'just now':m<60?m+' min ago':Math.floor(m/60)+' hr '+(m%60)+' min ago';}
  function detail(r) {
    const p=r.progress||{},bits=[STAGE[r.stage]||plain(r.stage),r.project];
    if(r.subtask_id) bits.push('subtask '+r.subtask_id+(p.total?' of '+p.total:''));
    else if(p.total) bits.push(p.done+'/'+p.total+' subtasks done');
    if(r.stage_entered_at) bits.push('in this stage since '+clock(r.stage_entered_at));
    if(r.last_activity_at) bits.push('last activity '+ago(r.last_activity_at));
    return bits.filter(Boolean).join(' · ');
  }
  function nextFor(data,actor){return (data.forecast?.timeline||[]).find(e=>e.actor===actor);}
  const clock=iso=>local(iso).replace(/ \(.*\)$/,'');
  function waitingOn(data,label) {
    const all=[...(data.in_flight||[]),...Object.values(data.pending||{}).flat()],seen=new Set(),out=[];
    for(const r of all){const why=(r.estimate?.reason||'')+' '+(r.estimate?.if_approved_now?.reason||'');
      if(why.includes('needs '+label)&&!seen.has(r.initiative_id)){seen.add(r.initiative_id);out.push(r);}}
    return out;
  }
  function now(data) {
    return '<h2>Agents now</h2><ul class="now-list">'+(data.lanes||[]).map(l=>{
      const paused=l.scheduler?.state==='paused',next=nextFor(data,l.key),name=WHO[l.key]||l.label;
      let text,cls,href='',extra='';
      if(l.key==='chat'){
        const c=l.claims||[];cls=c.length?'busy':'idle';
        text=c.length?'working with you on '+c.map(c=>'#'+c.initiative_id+' '+c.title+(c.note?' ('+c.note+')':'')).join('; '):'idle';
        href=c[0]?.href||'';
      } else if(l.activity?.task_ref){
        const row=(data.in_flight||[]).find(r=>owner(r.owner)===owner(l.key));
        text='working on '+l.activity.task_ref+(l.activity.started_at?' since '+clock(l.activity.started_at):'')+(row?' · '+detail(row):'');
        cls='busy';href=row?.href||'';
        if(paused) extra=' (scheduled runs off after this one)';
      } else if(paused){
        const waiting=waitingOn(data,name);cls='paused';
        if(l.key==='gemini') text='not scheduled: you run Gemini yourself in Antigravity';
        else if(waiting.length){text='scheduled runs off · '+waiting.length+' item(s) need '+name+': ask me in chat to run it';href=waiting[0].href;}
        else text='scheduled runs off · nothing needs it right now';
      } else if(next){text='next: '+describe(next)+', '+until(next.start_at);cls='idle';href=next.href;}
      else {text='idle';cls='idle';}
      const body=esc(text+extra);
      return '<li class="now-'+cls+'"><span class="pip"></span><b>'+esc(name)+'</b>'+(href?'<a class="now-link" href="'+esc(href)+'">'+body+'</a>':'<span>'+body+'</span>')+'</li>';
    }).join('')+'</ul><p class="hint">Scheduled runs are each agent\'s automatic timer. Claude\'s is off on purpose: I run it on demand from chat. Toggle timers on the <a href="#/tab/work">Work tab</a>.</p>';
  }
  function upcoming(data) {
    const events=(data.forecast?.timeline||[]).slice(1,5);
    return events.length?'<h3>Then</h3><ol class="upcoming">'+events.map(e=>'<li><time>'+esc(until(e.start_at))+'</time><a href="'+esc(e.href)+'">'+esc(describe(e))+'</a></li>').join('')+'</ol>':'';
  }
  function needs(data) {
    const ctx=data.priority_context||{},iid=a=>(String(a.href||'').match(/#\/initiative\/(\d+)/)||[])[1];
    const proj=a=>a.project||((ctx.initiatives||{})[iid(a)]||{}).project;
    const items=prioritize(data.attention||[],ctx,a=>[proj(a),iid(a)]);
    return '<h2>Needs you <span class="badge-n">'+items.length+'</span> <a class="hint" href="#/tab/attention">all →</a></h2>'+(items.length?'<ul class="needs">'+items.map(a=>'<li>'+projTag(proj(a))+prioTag(ctx,proj(a),iid(a))+'<a href="'+esc(a.href)+'"><b>'+esc(VERB[a.reason]||plain(a.reason))+'</b> '+esc(a.title)+'</a></li>').join('')+'</ul>':'<p class="hint">Nothing waiting on you.</p>');
  }
  function milestoneRows(data) {
    const all=[...(data.in_flight||[]),...Object.values(data.pending||{}).flat()],seen=new Map();
    for(const r of all){const prev=seen.get(r.initiative_id);if(!prev||(prev.subtask_id&&!r.subtask_id))seen.set(r.initiative_id,r);}
    const at=r=>r.estimate?.completion_at?Date.parse(r.estimate.completion_at):Infinity;
    return [...seen.values()].sort((a,b)=>at(a)-at(b)||(a.initiative_id-b.initiative_id));
  }
  function landing(r) {
    const e=r.estimate||{};
    if(e.completion_at) return {cls:'eta',text:'lands '+until(e.completion_at)+' ('+clock(e.completion_at)+')'};
    const ask={playtest:'playtest it',spark:'approve the pitch',hld_review:'review the HLD',lld_review:'review the LLD + plan'}[r.stage];
    if(e.state==='waiting'||ask) return {cls:'you',text:'waiting on you: '+(ask||plain(r.stage))};
    return {cls:'blocked',text:plain(e.reason||'not scheduled')};
  }
  function milestones(data) {
    const rows=milestoneRows(data),soon=rows.find(r=>r.estimate?.completion_at);
    const headline=soon?'<p class="headline">Next to land: <a href="'+esc(soon.href)+'">'+esc(soon.title)+'</a>, '+esc(until(soon.estimate.completion_at))+'.</p>'
      :'<p class="headline">Nothing lands without you right now: '+rows.filter(r=>landing(r).cls==='you').length+' item(s) wait on your review.</p>';
    const groups=new Map();for(const r of rows){if(!groups.has(r.project))groups.set(r.project,[]);groups.get(r.project).push(r);}
    const ctx=data.priority_context,best=g=>Math.min(...g.map(r=>rank(ctx,...rowKey(r)).score));
    for(const [k,list] of groups) groups.set(k,prioritize(list,ctx));
    const ordered=[...groups.entries()].sort((a,b)=>{const t=g=>Math.min(...g.map(r=>r.estimate?.completion_at?Date.parse(r.estimate.completion_at):Infinity));return best(a[1])-best(b[1])||t(a[1])-t(b[1])||a[0].localeCompare(b[0]);});
    return '<h2>Milestones</h2>'+headline+'<ul class="milestones">'+ordered.map(([proj,list])=>'<li class="ms-group"><a href="#/project/'+encodeURIComponent(proj)+'">'+esc(proj)+'</a>'+prioTag(ctx,proj)+'<span class="hint">'+list.length+' open</span></li>'+list.map(r=>{const l=landing(r),p=r.progress||{};
      return '<li class="ms-'+l.cls+'"><a href="'+esc(r.href)+'">#'+esc(r.initiative_id)+' '+esc(r.title)+'</a>'+prioTag(ctx,r.project,r.initiative_id,r.priority)
        +(p.total?'<span class="ms-bar" title="'+esc(p.done+'/'+p.total)+' subtasks"><i style="width:'+Math.round(100*p.done/p.total)+'%"></i></span>':'<span class="ms-bar empty"></span>')
        +'<span class="ms-when">'+esc(l.text)+'</span></li>';}).join('')).join('')+'</ul>';
  }
  function quotabar(data) {
    const rows=(data.lanes||[]).filter(l=>l.quota?.windows&&Object.keys(l.quota.windows).length).map(l=>{
      const w5=l.quota.windows['5h']||{},wk=l.quota.windows.weekly||{},v=w5.value;
      const pace=w5.delta_pp==null?'pace unknown':Math.abs(w5.delta_pp)<=5?'on pace':(w5.delta_pp>0?'over':'under')+' pace by '+Math.abs(w5.delta_pp).toFixed(0)+' pts';
      return '<div class="qrow"><b>'+esc(l.label)+'</b><div class="qbar '+quotaClass(v)+'"><i style="width:'+(v??0)+'%"></i></div><strong>'+(v==null?'—':Math.round(v)+'%')+'</strong>'
        +'<span class="hint">5h left · '+esc(pace)+' · resets '+esc(w5.meta?.resets_at?until(w5.meta.resets_at):'unknown')+(wk.value!=null?' · weekly '+Math.round(wk.value)+'% left (info only)':'')+(w5.age_seconds>3600?' · <span class="warn-t">stale reading</span>':'')+'</span></div>';
    }).join('');
    return '<h2>Quota (5h windows)</h2>'+(rows||'<p class="hint">No quota readings yet.</p>')+'<a class="hint" href="#/tab/utilization">History →</a>';
  }
  /* ---- Work tab: big rocks first ---- */
  function workActive(data) {
    const ctx=data.priority_context,rows=prioritize(data.in_flight||[],ctx),next=(data.forecast?.timeline||[])[0];
    const hero=r=>{const e=r.estimate||{},chat=r.owner_basis==='claim',when=e.completion_at?until(e.completion_at):e.state==='waiting'?'Needs review':chat?'In chat':'—';
      const sub=e.completion_at?'done ~'+clock(e.completion_at):chat?'working with you here':plain(e.reason||'no estimate');
      return '<li class="hero-row"><div class="hero-eta '+(e.completion_at?'good':'dim')+'"><strong>'+esc(when)+'</strong><span>'+esc(sub)+'</span></div><div class="hero-body"><a href="'+esc(r.href)+'">#'+esc(r.initiative_id)+(r.subtask_id?' / '+esc(r.subtask_id):'')+' '+esc(r.title)+'</a> '+projTag(r.project)+prioTag(ctx,r.project,r.initiative_id,r.priority)+'<p>'+esc(detail(r))+'</p></div><span class="hero-owner">'+esc(owner(r.owner))+'</span></li>';};
    return '<h2>Active now <span class="badge-n teal">'+rows.length+'</span></h2>'+(rows.length?'<ul class="hero">'+rows.map(hero).join('')+'</ul>':'<p class="hero-empty">Nothing is running right now.</p>')
      +(next?'<p class="hero-next">Next start: <a href="'+esc(next.href)+'">'+esc(describe(next))+'</a> <b>'+esc(until(next.start_at))+'</b></p>':'');
  }
  function bucket(iso,nowMs=Date.now()) {
    const t=Date.parse(iso),d=new Date(t),today=new Date(nowMs);today.setHours(0,0,0,0);
    const m=(t-nowMs)/60000,tomorrow=today.getTime()+86400000;
    if(m<=60) return ['a','Within the hour'];
    if(m<=180) return ['b','Next 3 hours'];
    if(t<tomorrow) return ['c','Later today'];
    if(t<tomorrow+86400000) return ['d','Tomorrow'];
    return ['e',d.toLocaleDateString([],{weekday:'long'})];
  }
  function workNext(data) {
    const events=(data.forecast?.timeline||[]).slice().sort((a,b)=>Date.parse(a.start_at)-Date.parse(b.start_at));
    if(!events.length) return '<h2>Next work</h2><p class="hint">No agent run is forecast in the next 24 hours.</p>';
    const groups=new Map();
    for(const e of events){const [k,label]=bucket(e.start_at);if(!groups.has(k))groups.set(k,{label,list:[]});groups.get(k).list.push(e);}
    const who=a=>({gemma:'Gemma',codex:'Codex',claude:'Claude'})[a]||owner(a),ctx=data.priority_context,ekey=e=>[e.project,e.initiative_id];
    for(const g of groups.values()) g.list=prioritize(g.list,ctx,ekey);
    return '<h2>Next work · by when</h2>'+[...groups.values()].map(g=>'<section class="when-group"><h3>'+esc(g.label)+' <span class="hint">'+g.list.length+'</span></h3><ol class="when-list">'+g.list.map(e=>
      '<li><div class="when-time"><strong>'+esc(until(e.start_at))+'</strong><span>'+esc(clock(e.start_at))+'</span></div>'
      +'<span class="actor-chip '+esc(e.actor)+'">'+esc(who(e.actor))+'</span>'
      +'<div class="when-what"><a href="'+esc(e.href)+'">'+esc(describe(e))+'</a>'+prioTag(ctx,e.project,e.initiative_id)+'<p>'+esc([plain(e.work_type),e.initiative_id?'#'+e.initiative_id:'',e.basis_label].filter(Boolean).join(' · '))+'</p></div>'
      +'<a class="when-proj" href="#/project/'+encodeURIComponent(e.project)+'">'+esc(e.project)+'</a>'
      +'<div class="when-done"><span>done</span><strong>'+esc(clock(e.completion_at))+'</strong></div></li>').join('')+'</ol></section>').join('');
  }
  /* ---- Attention tab: everything that needs the producer to act ---- */
  const ACT={playtest:'Playtest',spark:'Approve pitch',hld_review:'Review HLD',lld_review:'Review LLD + plan'};
  function attentionRows(data) {
    const all=[...(data.in_flight||[]),...Object.values(data.pending||{}).flat()],seen=new Set(),out=[];
    for(const r of all){if(r.subtask_id&&r.status!=='todo'&&r.owner!=='producer')continue;
      const needs=ACT[r.stage]&&!r.subtask_id||r.owner==='producer';const key=r.initiative_id+':'+(r.subtask_id||'');
      if(needs&&!seen.has(key)){seen.add(key);out.push(r);}}
    return prioritize(out.sort((a,b)=>(b.age_seconds||0)-(a.age_seconds||0)),data.priority_context);
  }
  function attentionFull(data) {
    const rows=attentionRows(data),other=(data.attention||[]).filter(a=>!String(a.key).startsWith('i:'));
    const age=s=>{const m=Math.floor((s||0)/60);return m<60?m+' min':Math.floor(m/60)+' hr '+(m%60)+' min';};
    const idx=data.initiative_index||{};
    const cut=(t,n)=>{t=String(t||'').replace(/\*\*/g,'').replace(/\s+/g,' ').trim();return t.length>n?t.slice(0,n-1).trimEnd()+'…':t;};
    const row=r=>{const e=r.estimate||{},then=e.if_approved_now,i=idx[r.initiative_id]||{},p=r.progress||{};
      const after=then?(then.completion_at?'lands '+until(then.completion_at)+' ('+clock(then.completion_at)+')':plain(then.reason||'')):'';
      const facts=[i.category&&plain(i.category),i.complexity==='high'?'high complexity':'',p.total?p.done+'/'+p.total+' subtasks':'',i.branch?'branch '+i.branch:''].filter(Boolean);
      return '<li class="att-row"><span class="att-verb">'+esc(r.subtask_id?'Hands-on check':ACT[r.stage]||'Act')+'</span><div class="att-main"><p class="att-proj">'+projTag(r.project)+prioTag(data.priority_context,r.project,r.initiative_id,r.priority)+'</p><a class="att-title" href="'+esc(r.href)+'">#'+esc(r.initiative_id)+(r.subtask_id?' / '+esc(r.subtask_id):'')+' '+esc(r.title)+'</a>'
        +'<p class="att-facts">'+facts.map(x=>'<span>'+esc(x)+'</span>').join('')+'</p>'
        +(i.pitch?'<p class="att-pitch">'+esc(cut(i.pitch,320))+'</p>':'')
        +(i.revision?'<p class="att-rev"><b>Last note</b> '+esc(cut(i.revision,240))+'</p>':'')
        +(after?'<p class="att-after"><b>After you act</b> '+esc(after)+'</p>':'')
        +'</div><div class="att-age"><strong>'+esc(age(r.age_seconds))+'</strong><span>waiting</span></div></li>';};
    return '<h2>Needs you <span class="badge-n">'+(rows.length+other.length)+'</span></h2>'+(rows.length?'<ul class="att-list">'+rows.map(row).join('')+'</ul>':'<p class="hero-empty">Nothing needs you right now.</p>')
      +(other.length?'<h3>Housekeeping</h3><ul class="att-list">'+other.map(a=>'<li class="att-row"><span class="att-verb">'+esc(VERB[a.reason]||'Check')+'</span><div><a href="'+esc(a.href)+'">'+esc(a.title)+'</a></div><span></span></li>').join('')+'</ul>':'');
  }
  function projectRoadmap(data,project) {
    const roll=(data.rollups?.projects||[]).find(p=>p.project===project)||{};
    const work=[...(data.in_flight||[]),...Object.values(data.pending||{}).flat()].filter(r=>r.project===project);
    const stages=Object.entries(roll.stages||{}).map(([s,n])=>'<span class="pill dim">'+esc(STAGE[s]||plain(s))+' '+esc(n)+'</span>').join(' ');
    return '<div class="roadmap"><p>'+stages+' <span class="pill">'+esc((roll.subtasks_done??0)+'/'+(roll.subtasks_total??0))+' subtasks</span></p>'
      +'<h3>Work breakdown</h3>'+rows(work,data.priority_context)+'<h3>Next 24 hours</h3>'+timeline(data,project).replace(/^<h2>Next hours<\/h2>/,'')+'</div>';
  }
  function regions(data,project='') {
    const filter=items=>items.filter(i=>!project||i.project===project);
    const total=(key,fallback)=>data.pages?.[key]?.total??fallback;
    const more=key=>data.pages?.[key]?.next_cursor!=null?'<button class="btn" data-more="'+esc(key)+'" data-offset="'+data.pages[key].next_cursor+'">Load more ('+data.pages[key].total+' total)</button>':'';
    const lanes=(data.lanes||[]).map(l=>{const paused=l.scheduler?.state==='paused';
      return '<article class="lane'+(paused?' paused':'')+'"><header><b>'+esc(l.label)+'</b><span class="lane-state">'+esc(plain(l.activity?.state||'unknown'))+(paused?' · scheduled runs paused':'')+'</span></header>'
      +(l.activity?.task_ref?'<p>Working on '+esc(l.activity.task_ref)+'</p>':'')
      +(l.scheduler?.next_run_at?'<p>Next run '+esc(until(l.scheduler.next_run_at))+'</p>':'')
      +(l.reason?'<p class="warning">'+esc(plain(l.reason))+'</p>':'')
      +(l.claims||[]).map(c=>'<p><a href="'+esc(c.href)+'">#'+esc(c.initiative_id)+' '+esc(c.title)+'</a></p>').join('')
      +(l.focus||[]).map(f=>'<p><a href="'+esc(f.href)+'">'+esc(f.project)+'</a> · focus</p>').join('')
      +(l.jobs||[]).map(j=>'<div class="job"><span>'+esc(j.declaration.replace(/^orch:/,''))+'</span><button class="btn sm" data-lane="'+esc(j.declaration)+'" data-enabled="'+(!j.enabled)+'" data-generation="'+esc(j.generation)+'" title="Affects future runs only" '+(!j.controllable?'disabled':'')+'>'+(j.enabled?'Turn timer off':'Turn timer on')+'</button></div>').join('')+'</article>';}).join('');
    const inFlight=filter(data.in_flight||[]);
    const pending=Object.entries(data.pending||{}).map(([name,items])=>'<details data-key="pending-'+esc(name)+'"'+(['producer','queued'].includes(name)?' open':'')+'><summary>'+esc(plain(name))+' ('+total('pending.'+name,filter(items).length)+')</summary>'+rows(filter(items),data.priority_context)+more('pending.'+name)+'</details>').join('');
    const quotas=(data.lanes||[]).map(l=>Object.entries(l.quota?.windows||{}).map(([w,m])=>'<article class="pace"><b>'+esc(l.label)+' · '+esc(w)+'</b><p>'+esc(m.value??'not recorded')+'% remaining · '+esc(plain(m.status))+'</p><p>'+esc(m.pace)+' · even-burn target used '+(m.target_used==null?'not available':m.target_used.toFixed(1)+'%')+'</p><p>Actual used '+(m.actual_used==null?'not available':m.actual_used.toFixed(1)+'%')+' · difference '+(m.delta_pp==null?'not available':m.delta_pp.toFixed(1)+'pp')+'</p><p class="hint">'+esc(plain(m.baseline||m.reason||'pace unavailable'))+' · reset '+esc(local(m.meta?.resets_at))+' · observed '+esc(local(m.observed_at))+'</p>'+(m.hint?'<p class="warning">'+esc(m.hint)+'</p>':'')+'</article>').join('')).join('');
    const attention=(data.attention||[]).map(a=>'<li><a href="'+esc(a.href)+'">'+esc(a.title)+'</a> · '+esc(plain(a.reason))+'</li>').join('')||'<li>None.</li>';
    return {workActive:workActive(data),workNext:workNext(data),attentionFull:attentionFull(data),kpis:kpis(data),now:now(data),needs:needs(data),milestones:milestones(data),quotabar:quotabar(data),stamp:'Updated '+esc(local(data.generated_at)),rollups:rollups(data,project),timeline:timeline(data,project),lanes,next:'<h2>Next expected update</h2>'+nextUpdate(data.next_update)+upcoming(data)+'<p class="hint">Next scheduled agent run: '+esc(local(data.next_update?.next_check_at))+'</p>',flight:'<h2>In flight ('+total('in_flight',inFlight.length)+' rows)</h2>'+rows(inFlight,data.priority_context)+more('in_flight'),pending,quotas:quotas||'<p>Quota pace unavailable. Gemini has no measured quota; Gemma is local.</p>',attention:'<ul>'+attention+'</ul>',suggestions:rows(filter(data.suggestions||[]),data.priority_context)+more('suggestions'),prioStrip:prioStrip(data)};
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
  const exports={rank,prioritize,prioTag,projTag,prioStrip,attentionRows,projectRoadmap,esc,plain,owner,local,eta,rows,regions,update,preview,comparison,summary,setComparison,until,describe,milestoneRows,landing,detail};
  if(typeof module!=='undefined') module.exports=exports;else root.Overview=exports;
})(typeof window!=='undefined'?window:globalThis);
