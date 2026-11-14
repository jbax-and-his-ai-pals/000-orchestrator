/* Independent same-origin utilization panel. No dependencies or inline handlers. */
(function (root) {
  "use strict";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const format = (value, unit = "") => finite(value) ? Number(value.toFixed(1)) + unit : "Unknown";
  const colors = {gemma:"var(--good)",codex:"var(--accent)",claude:"var(--violet)",gemini:"var(--warn)"};
  const lanes = Object.keys(colors);
  const clockText = (iso, now, reset = false) => {
    const seconds = (Date.parse(iso) - now) / 1000;
    if (!Number.isFinite(seconds)) return "unknown";
    if (reset && seconds <= 0) return "reset passed";
    const amount = Math.max(0, reset ? seconds : -seconds);
    const text = amount >= 86400 ? Math.floor(amount/86400) + "d " + Math.floor(amount%86400/3600) + "h" :
      amount >= 3600 ? Math.floor(amount/3600) + "h " + Math.floor(amount%3600/60) + "m" : Math.floor(amount/60) + "m " + Math.floor(amount%60) + "s";
    return reset ? "in " + text : text + " ago";
  };
  function age(item) {
    return item?.observed_at ? '<span data-util-age="' + escape(item.observed_at) + '"></span>' : "never recorded";
  }
  function state(item) {
    return '<span class="util-badge">' + escape(item?.status || "missing") + '</span> ' + escape(item?.reason || "");
  }
  function card(title, body, item) {
    return '<article class="util-card"><h2>' + title + '</h2><p class="util-source">' + state(item) + '</p>' + body + '<p class="util-age">Last recorded: ' + age(item) + '</p></article>';
  }
  function quota(title, windows, manual) {
    return '<article class="util-card"><h2>' + title + '</h2><p class="util-source">' + (manual ? 'Manual snapshots · not live usage' : 'Status output · estimated resets') + '</p>' + ["5h","weekly"].map(w => {
      const item = windows?.[w];
      const reset = item?.meta?.resets_at;
      return '<div class="util-window"><b>' + w + '</b><strong>' + format(item?.value, "% remaining") + '</strong><small>' + state(item) + '</small><small>Recorded ' + age(item) + '</small><small>Reset ' + (reset ? '<span data-util-reset="' + escape(reset) + '"></span> · ' + escape(reset) : 'unknown') + '</small></div>';
    }).join("") + '</article>';
  }
  function tiles(current) {
    const gpu = current.gpu || {}, v = gpu.values || {}, models = current.ollama?.meta?.models || [];
    const total = v.vram_total_mib, used = v.vram_used_mib;
    const pct = finite(total) && total > 0 && finite(used) ? clamp(used/total*100,0,100) : 0;
    return '<div class="util-tiles">' + card('GPU', '<strong class="util-value">' + format(v.util_pct,'%') + '</strong><p>VRAM ' + format(finite(used) ? used/1024 : null,' GiB') + ' / ' + format(finite(total) ? total/1024 : null,' GiB') + '</p><div class="util-meter" aria-label="VRAM used"><i style="width:' + pct + '%"></i></div><p>' + format(v.temperature_c,' °C') + ' · ' + format(v.power_w,' W') + '</p><small>' + (gpu.meta?.device_count > 1 ? escape(gpu.meta.device_count) + ' GPUs: max utilization / temperature; summed memory / power' : 'Local NVIDIA telemetry') + '</small>',gpu) +
      card('Ollama', '<strong>' + format(current.ollama?.value,' loaded') + '</strong><ul>' + models.map(m => '<li>' + escape(m.name) + ' · ' + format(finite(m.size_vram) ? m.size_vram/(1024**3) : null,' GiB') + '<small>Expires ' + (m.expires_at ? '<span data-util-reset="' + escape(m.expires_at) + '"></span>' : 'unknown') + '</small></li>').join('') + '</ul>' + (current.ollama?.value === 0 ? '<p>No models loaded</p>' : ''),current.ollama) +
      quota('OpenAI',current.openai,false) + quota('Claude',current.anthropic,true) +
      card('Gemini', '<strong>' + format(current.gemini?.logged_actions,' logged actions') + '</strong><p>Logged errors: 429 ' + format(current.gemini?.logged_errors?.['429']) + ' · 503 ' + format(current.gemini?.logged_errors?.['503']) + '</p><small>Selected range. Actions are a calls proxy, not measured calls or API quota. Only reviewer-gemini events.</small>',current.gemini) + '</div>';
  }
  function points(values, max = 100) {
    const denominator = Math.max(1, values.length-1);
    return values.map((value,index) => finite(value) ? [48+index/denominator*544, 164-clamp(value/Math.max(1,max),0,1)*132] : null);
  }
  function path(values, max = 100) {
    let connected = false;
    return points(values,max).map(p => {
      if (!p) { connected=false; return ''; }
      const out=(connected?'L':'M') + p[0].toFixed(2) + ',' + p[1].toFixed(2);
      connected=true; return out;
    }).join(' ');
  }
  function line(values,color,max,dashed=false) {
    const ps=points(values,max);
    return '<path d="' + path(values,max) + '" fill="none" stroke="' + color + '" stroke-width="2"' + (dashed ? ' stroke-dasharray="5 4"' : '') + '/>' +
      ps.filter(Boolean).map(p => '<circle cx="' + p[0].toFixed(2) + '" cy="' + p[1].toFixed(2) + '" r="1.4" fill="' + color + '"/>').join('');
  }
  function dateLabel(iso) { return iso ? String(iso).slice(5,16).replace('T',' ') + ' UTC' : ''; }
  function chart(title,body,legend,times,max=100,right=null,summary="") {
    return '<figure class="util-chart"><figcaption>' + escape(title) + '</figcaption><svg viewBox="0 0 640 210" role="img" aria-label="' + escape(title + '. ' + summary) + '"><title>' + escape(title) + '</title><desc>' + escape(summary || 'Gaps indicate no observations; no interpolation across empty buckets.') + '</desc>' +
      '<path d="M48 32V164H592" fill="none" stroke="var(--line)"/>' + [0,.5,1].map(f => '<line x1="48" x2="592" y1="' + (164-f*132) + '" y2="' + (164-f*132) + '" stroke="var(--line)"/><text x="43" y="' + (168-f*132) + '" text-anchor="end">' + format(f*max) + '</text>' + (right !== null ? '<text x="598" y="' + (168-f*132) + '">' + format(f*right) + '</text>' : '')).join('') +
      body + '<text x="48" y="190">' + escape(dateLabel(times?.[0])) + '</text><text x="592" y="190" text-anchor="end">' + escape(dateLabel(times?.at(-1))) + '</text></svg><div class="util-legend">' + legend + '</div><p class="util-summary">' + escape(summary) + '</p></figure>';
  }
  function legend(label,color,dashed=false) {
    return '<span><i style="background:' + color + '"' + (dashed ? ' class="dashed"' : '') + '></i>' + escape(label) + '</span>';
  }
  function charts(series) {
    const gpu=series.gpu || {}, ai=series.openai || {}, claude=series.anthropic || {}, activity=series.activity || {};
    const memory=(gpu.vram_used_mib || []).map(n => finite(n) ? n/1024 : null);
    const memoryMax=Math.max(1,...(gpu.vram_total_mib || []).filter(finite).map(n=>n/1024),...memory.filter(finite));
    const charts=[];
    charts.push(chart('GPU / VRAM',line(gpu.util_pct || [],'var(--teal)',100)+line(memory,'var(--muted)',memoryMax,true),legend('GPU % · left','var(--teal)')+legend('VRAM GiB · right','var(--muted)',true),gpu.times,100,memoryMax,'Left axis: utilization %. Right axis: VRAM GiB. Bucket means; gaps are unknown.'));
    charts.push(chart('OpenAI remaining',line(ai['5h'] || [],'var(--accent)',100)+line(ai.weekly || [],'var(--violet)',100,true),legend('5h %','var(--accent)')+legend('Weekly %','var(--violet)',true),ai.times,100,null,'Percent remaining. Last observation in each bucket; gaps are unknown.'));
    const start=Date.parse(gpu.times?.[0]), end=Date.parse(gpu.times?.at(-1));
    let dots='';
    for (const w of ['5h','weekly']) for (const dot of (claude[w] || []).slice(0,1000)) {
      const ms=Date.parse(dot.ts);
      if (!finite(dot.value) || !finite(ms) || !finite(start) || !finite(end)) continue;
      const x=48+clamp((ms-start)/Math.max(1,end-start),0,1)*544, y=164-clamp(dot.value/100,0,1)*132;
      const color=w==='5h'?'var(--violet)':'var(--warn)';
      dots+=w==='5h' ? '<circle cx="'+x.toFixed(2)+'" cy="'+y.toFixed(2)+'" r="3" fill="'+color+'"/>' : '<rect x="'+(x-3).toFixed(2)+'" y="'+(y-3).toFixed(2)+'" width="6" height="6" fill="'+color+'"/>';
    }
    charts.push(chart('Claude manual snapshots',dots,legend('● 5h %','var(--violet)')+legend('■ Weekly %','var(--warn)'),gpu.times,100,null,'Original recorded dots only, never connected. Percent remaining; manual readings may be stale.'));
    const length=activity.times?.length || 0, step=544/Math.max(1,length);
    const totals=Array.from({length},(_,i)=>lanes.reduce((sum,lane)=>sum+(finite(activity[lane]?.[i]) ? Math.max(0,activity[lane][i]) : 0),0));
    const max=Math.max(1,...totals); let bars='';
    for (let i=0;i<length;i++) {
      let bottom=164;
      for (const lane of lanes) {
        const height=clamp((finite(activity[lane]?.[i]) ? activity[lane][i] : 0)/max,0,1)*132;
        bottom-=height;
        bars+='<rect x="'+(48+i*step).toFixed(2)+'" y="'+bottom.toFixed(2)+'" width="'+Math.max(.2,step*.8).toFixed(2)+'" height="'+height.toFixed(2)+'" fill="'+colors[lane]+'"/>';
      }
    }
    charts.push(chart('Agent activity / hour (event proxy for runs)',bars,lanes.map(l=>legend(l,colors[l])).join(''),activity.times,max,null,'Hourly logged actions by lane, not measured model calls or exact runs.'));
    return '<div class="util-charts">'+charts.join('')+'</div>';
  }
  function render(data) {
    return tiles(data.current || {}) + charts(data.series || {}) + '<p class="util-source">' + (data.notes || []).map(escape).join(' · ') + '</p>';
  }

  /* Injected callbacks/timers make range races and lifecycle deterministic in Node tests. */
  function controller(options) {
    const {fetch:fetcher, setInterval:setTimer, clearInterval:clearTimer, onData, onStatus, onTick} = options;
    let active=false, selected='24h', generation=0, pending=null, poll=null, clock=null, last=null;
    async function load() {
      if (!active || pending) return;
      const ticket=++generation, abort=new AbortController();
      pending=abort;
      onStatus(last ? 'Refreshing · last recorded '+last.range : 'Loading utilization…');
      try {
        const response=await fetcher('/api/utilization?range='+selected,{signal:abort.signal});
        if (!response.ok) throw new Error('HTTP '+response.status);
        const data=await response.json();
        if (!active || ticket!==generation) return;
        last=data; onData(data); onTick();
        onStatus('Recorded data · '+data.range+' · refresh every 60s');
      } catch (error) {
        if (active && ticket===generation && error.name!=='AbortError')
          onStatus(last ? 'Fetch failed · last-good '+last.range+' data is stale' : 'Utilization unavailable · retrying every 60s');
      } finally { if (ticket===generation) pending=null; }
    }
    function leave() {
      active=false; generation++; pending?.abort(); pending=null;
      if (poll!==null) clearTimer(poll);
      if (clock!==null) clearTimer(clock);
      poll=clock=null;
    }
    function enter() {
      if (active) return;
      active=true; load(); poll=setTimer(load,60000); clock=setTimer(onTick,1000);
    }
    function range(value) {
      if (!['24h','7d','14d'].includes(value)) return;
      selected=value; generation++; pending?.abort(); pending=null; load();
    }
    return {enter,leave,range,load};
  }
  const exported={escape,finite,clockText,points,path,charts,tiles,render,controller};
  if (typeof module!=='undefined' && module.exports) module.exports=exported;
  if (!root.document) return;
  const content=root.document.getElementById('util-content'), status=root.document.getElementById('util-status');
  function tick() {
    const now=Date.now();
    content.querySelectorAll('[data-util-age]').forEach(el=>el.textContent=clockText(el.dataset.utilAge,now));
    content.querySelectorAll('[data-util-reset]').forEach(el=>el.textContent=clockText(el.dataset.utilReset,now,true));
  }
  const panel=controller({fetch:root.fetch.bind(root),setInterval:root.setInterval.bind(root),clearInterval:root.clearInterval.bind(root),
    onData:data=>{content.innerHTML=render(data);},onStatus:text=>{status.textContent=text;},onTick:tick});
  let wanted=false;
  root.Utilization={enter(){wanted=true;if(!root.document.hidden)panel.enter();},leave(){wanted=false;panel.leave();}};
  root.document.getElementById('util-range').addEventListener('change',e=>panel.range(e.target.value));
  root.document.addEventListener('visibilitychange',()=>{if(root.document.hidden)panel.leave();else if(wanted)panel.enter();});
})(typeof window!=='undefined' ? window : globalThis);
