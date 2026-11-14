const test=require('node:test');const assert=require('node:assert/strict');
const view=require('../dashboard/static/overview.js');
const row=(id,project,extra={})=>({initiative_id:id,project,title:'card '+id,href:'#/initiative/'+id,stage:'hld_review',priority:'medium',age_seconds:1000-id,...extra});
const base={lanes:[],in_flight:[],pending:{producer:[row(1,'001-a'),row(2,'002-b'),row(3,'003-c')]},attention:[],suggestions:[],totals:{},next_update:{state:'unknown'}};
const ctx=(o={})=>({spotlight:null,claims:[],projects:{'001-a':{priority:'medium'},'002-b':{priority:'medium'},'003-c':{priority:'medium'}},initiatives:{1:{project:'001-a',priority:'medium',stage:'hld_review',title:'card 1'},2:{project:'002-b',priority:'medium',stage:'hld_review',title:'card 2'},3:{project:'003-c',priority:'medium',stage:'hld_review',title:'card 3'}},...o});
const ids=html=>[...html.matchAll(/#\/initiative\/(\d+)"/g)].map(m=>+m[1]);

test('nothing designated keeps each tab order and shows no strip',()=>{
  const d={...base,priority_context:ctx()};
  assert.deepEqual(view.attentionRows(d).map(r=>r.initiative_id),[1,2,3]);
  assert.equal(view.prioStrip(d),'');
  assert.ok(!view.regions(d).attentionFull.includes('prio-tag'));
});
test('designations sort to the top: spotlight > focus > claim > project high > card high',()=>{
  const c=ctx({spotlight:'003-c'});c.projects['002-b'].focus=true;
  assert.deepEqual(view.attentionRows({...base,priority_context:c}).map(r=>r.initiative_id),[3,2,1]);
  const c2=ctx({claims:[3]});c2.initiatives[2].priority='high';
  assert.deepEqual(view.attentionRows({...base,priority_context:c2}).map(r=>r.initiative_id),[3,2,1]);
  const c3=ctx();c3.projects['001-a'].priority='low';c3.projects['003-c'].priority='high';
  assert.deepEqual(view.attentionRows({...base,priority_context:c3}).map(r=>r.initiative_id),[3,2,1]);
});
test('attention rows lead with the project and mark why they are prioritized',()=>{
  const d={...base,priority_context:ctx({spotlight:'002-b'})};const html=view.regions(d).attentionFull;
  assert.match(html,/class="att-proj"><a class="proj-tag" href="#\/project\/002-b"[^>]*><span class="proj-num">002<\/span><span class="proj-name">b<\/span>/);
  assert.match(html,/spotlight/);assert.deepEqual(ids(html),[2,1,3]);
  assert.match(view.prioStrip(d),/Prioritized/);
});
test('work tables and overview needs follow the same ranking',()=>{
  const c=ctx();c.initiatives[3].priority='high';
  const d={...base,in_flight:[row(1,'001-a'),row(3,'003-c')],attention:[{key:'i:1:x',href:'#/initiative/1',title:'one',reason:'HLD to review'},{key:'i:3:x',href:'#/initiative/3',title:'three',reason:'HLD to review'}],priority_context:c};
  const r=view.regions(d);assert.deepEqual(ids(r.flight),[3,1]);assert.deepEqual(ids(r.needs),[3,1]);assert.match(r.needs,/proj-tag/);
});
