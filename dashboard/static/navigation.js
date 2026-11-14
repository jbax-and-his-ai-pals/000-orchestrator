(function(root) {
  'use strict';
  const tabs=new Set(['overview','pulse','attention','work','triage','activity','utilization','ideas','taste']);
  const positive=s=>/^[1-9][0-9]*$/.test(s||'');
  function parse(hash) {
    if (!hash || hash==='#' || hash==='#/') return {type:'overview'};
    if(hash.startsWith('#card-') && positive(hash.slice(6))) return {type:'initiative',id:Number(hash.slice(6)),legacy:true};
    const parts=hash.split('/');
    if(parts[0]!=='#') return {type:'not-found'};
    if(parts.length===3 && parts[1]==='project') {
      try {const name=decodeURIComponent(parts[2]);if(name && !name.includes('/') && !name.includes(String.fromCharCode(92)) && name!=='.' && name!=='..' && ![...name].some(c=>c.charCodeAt(0)<32)) return {type:'project',id:name};} catch{}
    }
    if(parts[1]==='initiative' && positive(parts[2])) {
      if(parts.length===3) return {type:'initiative',id:Number(parts[2]),sid:null};
      if(parts.length===5 && parts[3]==='subtask' && positive(parts[4])) return {type:'subtask',id:Number(parts[2]),sid:Number(parts[4])};
    }
    if(parts.length===3 && parts[1]==='tab' && tabs.has(parts[2])) return {type:'tab',tab:parts[2]};
    return {type:'not-found'};
  }
  function trap(event,panel) {
    if(event.key!=='Tab') return false;
    const elements=[...panel.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')].filter(e=>e.getClientRects().length);
    if(!elements.length) {event.preventDefault();return true;}
    const first=elements[0],last=elements.at(-1),active=panel.ownerDocument.activeElement;
    if(event.shiftKey && (active===first || !panel.contains(active))) {event.preventDefault();last.focus();return true;}
    if(!event.shiftKey && (active===last || !panel.contains(active))) {event.preventDefault();first.focus();return true;}
    return false;
  }
  function sequence() {let current=0;return {next:()=>++current,valid:n=>n===current};}
  const exports={parse,trap,sequence};
  if(typeof module!=='undefined') module.exports=exports; else root.Navigation=exports;
})(typeof window!=='undefined'?window:globalThis);
