const test=require('node:test'),assert=require('node:assert/strict');
const controls=require('../dashboard/static/models.js'),navigation=require('../dashboard/static/navigation.js');
const model={declaration:'orch:scout-gemma',label:'Gemma',model:'ollama/gemma4:12b',controllable:true,generation:1,version:'v1',job:{enabled:true},tasks:{passive:true,coding:false},capabilities:[{key:'passive',label:'Maintenance',description:'Scans'},{key:'coding',label:'Coding',description:'Small chores'}]};
test('models tab is routable and shows independent schedule and task switches',()=>{
  assert.equal(navigation.parse('#/tab/models').tab,'models');
  const html=controls.render({scheduler_status:'ok',models:[model]});
  assert.match(html,/ollama\/gemma4:12b/);assert.match(html,/data-model-power/);
  assert.match(html,/data-task="passive"[^>]*checked/);assert.doesNotMatch(html,/data-task="coding"[^>]*checked/);
  assert.equal((html.match(/role="switch"/g)||[]).length,3);
});
test('paused models retain editable permissions and unknown schedules cannot be enabled',()=>{
  const html=controls.render({scheduler_status:'stale',models:[{...model,controllable:false}]});
  assert.match(html,/Scheduler status is stale/);assert.match(html,/data-model-power[^>]*disabled/);
  assert.doesNotMatch(html,/data-model-task[^>]*disabled/);
  assert.match(controls.render({scheduler_status:'ok',models:[{...model,job:{enabled:false}}]}),/Automatic runs paused/);
});
test('model names and descriptions are escaped',()=>{
  const html=controls.render({scheduler_status:'ok',models:[{...model,label:'<script>x</script>',model:'<img src=x>'}]});
  assert.doesNotMatch(html,/<script>|<img/);assert.match(html,/&lt;script&gt;/);
});
