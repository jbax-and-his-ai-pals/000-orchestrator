const test=require('node:test');const assert=require('node:assert/strict');
const view=require('../dashboard/static/overview.js');
const data={lanes:[],in_flight:[],pending:{queued:[],blocked:[],sparks:[],producer:[]},attention:[],suggestions:[],totals:{initiatives:0},next_update:{state:'unknown'}};
test('empty overview and unknown predictions remain explicit',()=>{const r=view.regions(data);assert.match(r.next,/Completion unknown/);assert.match(r.flight,/None/);assert.match(r.quotas,/unavailable/);assert.match(r.attention,/None/);});
test('untrusted title/status/errors escaped and all rows retained',()=>{const item={initiative_id:1,title:'<script>bad</script>',project:'x',href:'#/initiative/1',status:'<bad>',age_seconds:60};const r=view.regions({...data,in_flight:Array.from({length:240},()=>item),totals:{initiatives:240}});assert.equal((r.flight.match(/<tr>/g)||[]).length,241);assert.ok(!r.flight.includes('<script>'));assert.match(r.flight,/&lt;script&gt;/);assert.match(r.flight,/unknown/);});
test('project filter exact and counts match',()=>{const r=view.regions({...data,in_flight:[{project:'a',title:'first'},{project:'b',title:'second'}]},'a');assert.match(r.flight,/first/);assert.ok(!r.flight.includes('second'));assert.match(r.flight,/1 rows/);});
test('disabled running and stale lanes have separate text and controls',()=>{const r=view.regions({...data,lanes:[{key:'codex',label:'Codex',activity:{state:'working'},scheduler:{state:'paused'},reason:'stale',jobs:[{declaration:'orch:planner-codex',enabled:false,controllable:false,generation:3}]}]});assert.match(r.lanes,/working/);assert.match(r.lanes,/paused/);assert.match(r.lanes,/disabled/);assert.match(r.lanes,/future runs/);assert.match(r.lanes,/stale/);});
test('estimates never invent completion and preserve confidence',()=>{assert.match(view.eta({state:'over_typical'}),/Over typical/);assert.match(view.eta({completion_at:'2026-11-14T01:00Z',sample_count:3,basis:'actor_fallback_low_confidence'}),/3 samples.*lower confidence/);assert.equal(view.local('garbage'),'unknown');});
test('keyed regions do not replace focused content',()=>{const element={_html:'old',innerHTML:'draft',contains:()=>true};const container={ownerDocument:{activeElement:{}},querySelector:()=>element};view.update(container,data);assert.equal(element.innerHTML,'draft');});

test('application boots Overview with real script wiring and no runtime error',async()=>{
  const vm=require('node:vm'),fs=require('node:fs');const elements=new Map(),listeners={};
  function element(selector){if(!elements.has(selector))elements.set(selector,{hidden:selector==='#drawer',value:'',checked:false,dataset:{},style:{},classList:{toggle(){}},matches:()=>false,contains:()=>false,querySelectorAll:()=>[],querySelector:s=>element(selector+' '+s),addEventListener(){},focus(){},blur(){}});return elements.get(selector);}
  const tabs=['overview','pulse','triage','activity','utilization','taste'].map(view=>({dataset:{view},classList:{toggle(){}}}));
  const doc={body:{style:{}},activeElement:null,querySelector:element,querySelectorAll:s=>s==='.tab'?tabs:[],addEventListener:(name,fn)=>{listeners[name]=fn;}};
  for(const el of elements.values())el.ownerDocument=doc;
  const original=element;doc.querySelector=selector=>{const el=original(selector);el.ownerDocument=doc;return el;};
  const state={version:'v1',projects:[],initiatives:[],events:[],spotlight:null,config:{metrics:[],poll_seconds:4},enums:{priorities:[],complexities:[]}};
  const paths=[];const context={document:doc,location:{hash:'#/'},Navigation:require('../dashboard/static/navigation.js'),Overview:view,crypto:{randomUUID:()=> 'test-idea-token'},setInterval:()=>1,setTimeout:()=>1,clearTimeout(){},console,fetch:async path=>{paths.push(path);return {ok:true,json:async()=>path.startsWith('/api/overview')?{...data,projects:[],pages:{},project_filter:''}:state};},addEventListener(){}};
  context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../dashboard/static/app.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(paths.includes('/api/state'));assert.ok(paths.some(p=>p.startsWith('/api/overview')));assert.equal(element('#live-dot').className,'dot on');assert.equal(vm.runInContext('O.totals.initiatives',context),0);
});
