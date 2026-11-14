(function(root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(data) {
    if(!data) return '<p>Loading model controls…</p>';
    return (data.scheduler_status !== 'ok' ? '<p class="warning" role="status">Scheduler status is '+esc(data.scheduler_status)+'. Enable controls will return when status is fresh. Task permissions can still be saved.</p>' : '')
      + '<div class="model-grid">'+data.models.map(m => {
        const known = m.controllable, enabled = m.job?.enabled, tasks = Object.values(m.tasks).filter(Boolean).length;
        return '<article class="model-card" data-model-card="'+esc(m.declaration)+'"><header><div><h2>'+esc(m.label)+'</h2><p class="model-id">'+esc(m.model)+'</p></div>'
          +'<button type="button" class="model-power '+(known&&enabled?'on':'')+'" role="switch" aria-checked="'+(known&&enabled?'true':'false')+'" aria-label="Enable scheduled '+esc(m.label)+'" data-model-power="'+esc(m.declaration)+'" data-enabled="'+(!enabled)+'" data-generation="'+esc(m.generation)+'" '+(!known?'disabled':'')+'>'+(known?(enabled?'Enabled':'Disabled'):'Unavailable')+'</button></header>'
          +'<p class="model-status">'+(m.job?.started_at?'A run is in progress. ': '')+(known?(enabled?(tasks?'Automatic runs enabled':'No task types selected; runs have no eligible work'):'Automatic runs paused. Available for your chat sessions.'):'Scheduler status unavailable.')+'</p>'
          +'<fieldset><legend>Allowed tasks</legend>'+m.capabilities.map(t => '<label class="model-task"><span><b>'+esc(t.label)+'</b><small>'+esc(t.description)+'</small></span><input type="checkbox" role="switch" aria-label="'+esc(m.label+': '+t.label)+'" data-model-task="'+esc(m.declaration)+'" data-task="'+esc(t.key)+'" data-version="'+esc(m.version)+'" '+(m.tasks[t.key]?'checked':'')+'></label>').join('')+'</fieldset>'
          +'<p class="hint">'+(known&&enabled?(m.job.next_run_at?'Next scheduled run: '+esc(new Date(m.job.next_run_at).toLocaleString()):'Next scheduled run has not been observed yet.'):'Task choices are saved while this model is off.')+'</p></article>';
      }).join('')+'</div>';
  }
  function update(container, data, force=false) {
    if(!container || (!force && container.contains(container.ownerDocument.activeElement))) return;
    const html=render(data);
    if(container._html===html) return;
    container.innerHTML=html;container._html=html;
  }
  const api={render,update};
  if(typeof module!=='undefined') module.exports=api;else root.ModelControls=api;
})(typeof window!=='undefined'?window:globalThis);
