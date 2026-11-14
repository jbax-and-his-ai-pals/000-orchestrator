const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const u=require('../dashboard/static/utilization.js');
const times=['2026-11-13T20:00:00Z','2026-11-13T21:00:00Z','2026-11-13T22:00:00Z'];
const fixture={current:{},series:{gpu:{times,util_pct:[0,null,50],vram_used_mib:[1024,null,2048],vram_total_mib:[4096,4096,4096]},openai:{times,'5h':[10,null,20],weekly:[100,null,90]},anthropic:{'5h':[{ts:times[0],value:70}],weekly:[{ts:times[2],value:80}]},activity:{times,gemma:[1,2,0],codex:[1,0,1],claude:[0,1,0],gemini:[0,0,1]}}};

test('finite transforms preserve zero, gaps and singletons',()=>{
  assert.equal(u.points([0])[0][1],164);
  assert.equal(u.points([null])[0],null);
  const path=u.path([0,null,50,Infinity,NaN,100]);
  assert.equal((path.match(/M/g)||[]).length,3);
  assert.equal((path.match(/L/g)||[]).length,0);
  assert.doesNotMatch(path,/NaN|Infinity/);
  assert.equal(u.path([]),'');
});

test('exactly four bounded charts with separate axes and unconnected Claude dots',()=>{
  const html=u.charts(fixture.series);
  assert.equal((html.match(/<svg /g)||[]).length,4);
  assert.match(html,/VRAM GiB · right/);
  assert.match(html,/GPU % · left/);
  assert.match(html,/stroke-dasharray/);
  assert.match(html,/Original recorded dots only/);
  assert.match(html,/event proxy for runs/);
  const claude=html.split('<figure')[3];
  assert.equal((claude.match(/<circle/g)||[]).length,1);
  assert.equal((claude.match(/<rect/g)||[]).length,1);
  assert.equal((claude.match(/<path/g)||[]).length,1); // axes only, never a connecting data path
  assert.doesNotMatch(html,/NaN|Infinity|undefined/);
  assert.equal((u.charts({}).match(/<svg /g)||[]).length,4);
});

test('external names, reasons, resets and notes are escaped',()=>{
  const bad='<img src=x onerror="alert(1)">';
  const data={current:{ollama:{value:1,status:bad,reason:bad,observed_at:bad,meta:{models:[{name:bad,expires_at:bad}]}},openai:{'5h':{value:77,meta:{resets_at:bad}}}},notes:[bad],series:{}};
  const html=u.render(data);
  assert.doesNotMatch(html,/<img|onerror="alert/);
  assert.match(html,/&lt;img/);
  assert.equal(u.escape("<&\"'>"),'&lt;&amp;&quot;&#39;&gt;');
  assert.match(u.tiles({ollama:{value:0,meta:{models:[]}}}),/No models loaded/);
  assert.match(u.render(fixture),/Manual snapshots/);
});

test('local clock labels clamp expired resets and handle missing timestamps',()=>{
  const now=Date.parse(times[2]);
  assert.equal(u.clockText(times[0],now,true),'reset passed');
  assert.equal(u.clockText(times[0],now),'2h 0m ago');
  assert.equal(u.clockText('bad',now,true),'unknown');
});

function harness(){
  let next=1; const timers=new Map(), requests=[], data=[], statuses=[]; let ticks=0;
  const panel=u.controller({fetch:(url,opts)=>new Promise((resolve,reject)=>requests.push({url,opts,resolve,reject})),
    setInterval:(fn,ms)=>{const id=next++;timers.set(id,{fn,ms});return id;},clearInterval:id=>timers.delete(id),
    onData:d=>data.push(d),onStatus:s=>statuses.push(s),onTick:()=>ticks++});
  return {panel,timers,requests,data,statuses,get ticks(){return ticks;}};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const reply=(r,range)=>r.resolve({ok:true,json:async()=>({range,current:{},series:{}})});

test('visible-only polling prevents overlap, tears down timers and aborts leave',async()=>{
  const h=harness();h.panel.enter();h.panel.enter();
  assert.equal(h.requests.length,1);assert.equal(h.timers.size,2);
  await h.panel.load();assert.equal(h.requests.length,1);
  reply(h.requests[0],'24h');await settle();
  const before=h.data.length;
  [...h.timers.values()].find(t=>t.ms===1000).fn();
  assert.equal(h.data.length,before);assert.equal(h.ticks,2); // no chart rebuild on 1Hz tick
  [...h.timers.values()].find(t=>t.ms===60000).fn();
  assert.equal(h.requests.length,2);
  h.panel.leave();assert.equal(h.timers.size,0);assert.equal(h.requests[1].opts.signal.aborted,true);
  reply(h.requests[1],'24h');await settle();assert.equal(h.data.length,1);
});

test('range race discards late responses and fetch failure preserves last-good',async()=>{
  const h=harness();h.panel.enter();h.panel.range('7d');
  assert.equal(h.requests[0].opts.signal.aborted,true);
  reply(h.requests[1],'7d');await settle();reply(h.requests[0],'24h');await settle();
  assert.deepEqual(h.data.map(d=>d.range),['7d']);
  h.panel.range('14d');h.requests[2].reject(new Error('offline'));await settle();
  assert.match(h.statuses.at(-1),/last-good 7d data is stale/);
  assert.equal(h.data.length,1);h.panel.leave();
});

test('document visibility suspends both timers and resumes once',async()=>{
  const handlers={}, elements={};let next=0;const timers=new Map();
  for(const id of ['util-content','util-status','util-range'])elements[id]={dataset:{},querySelectorAll:()=>[],addEventListener:(name,fn)=>handlers[name]=fn};
  const document={hidden:false,getElementById:id=>elements[id],addEventListener:(name,fn)=>handlers[name]=fn};
  const window={document,fetch:async()=>({ok:true,json:async()=>fixture}),
    setInterval:(fn,ms)=>{timers.set(++next,{fn,ms});return next;},clearInterval:id=>timers.delete(id)};
  vm.runInNewContext(fs.readFileSync(require.resolve('../dashboard/static/utilization.js'),'utf8'),{window,AbortController});
  window.Utilization.enter();await settle();assert.equal(timers.size,2);
  document.hidden=true;handlers.visibilitychange();assert.equal(timers.size,0);
  document.hidden=false;handlers.visibilitychange();handlers.visibilitychange();await settle();assert.equal(timers.size,2);
  window.Utilization.leave();assert.equal(timers.size,0);
  handlers.visibilitychange();assert.equal(timers.size,0);
});
