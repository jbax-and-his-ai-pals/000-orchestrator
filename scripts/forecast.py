"""Read-only 24-hour forecast: simulated next producer checkpoint, never gate execution.
Budgets: <=2,000 events, <=5,000 work items, 16 cached snapshots, 30s TTL.
Priors (minutes): build 20, LLD 25, HLD 30, review 10, dossier 1, spark rework 10.
Unknown future plans are not invented. All dates are aware, all inputs copied.
"""
import copy
import datetime as dt
import hashlib
import heapq
import json
import math
import statistics
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import steering
import utilization as u

PRIORS = {'build':1200, 'lld':1500, 'hld':1800, 'review':600, 'scan':60, 'spark':600}
GATES = {'spark':'hld_draft','hld_review':'lld_draft','lld_review':'building','playtest':None}
ACTOR_NAMES = {'codex':'Codex','claude':'Claude','gemma':'Gemma'}
_cache = {}
_lock = threading.Lock()

def date(value):
    try: return u.utc(value)
    except (ValueError, TypeError): return None

def duration(samples, actor, kind):
    valid=[s for s in samples if isinstance(s.get('seconds'),(int,float)) and math.isfinite(s['seconds']) and 0<s['seconds']<=86400]
    tiers=[([s['seconds'] for s in valid if s['actor']==actor and s['work_type']==kind], actor+' '+kind, 'actor_work_type'),
           ([s['seconds'] for s in valid if s['actor']==actor], actor+' tasks (all work types)', 'actor_fallback'),
           ([s['seconds'] for s in valid if s['work_type']==kind], kind+' tasks (all actors)', 'work_type_fallback')]
    for values, label, basis in tiers:
        if len(values)>=3:
            seconds=statistics.median(values)
            return {'seconds':seconds,'sample_count':len(values),'basis':basis,
                    'basis_label':f'~{max(1,round(seconds/60))} min, median of {len(values)} {label}'}
    seconds=PRIORS.get(kind,1200)
    return {'seconds':seconds,'sample_count':0,'basis':'default_prior',
            'basis_label':f'~{round(seconds/60)} min, default guess (no history; {kind} prior)'}

def pick(queue):
    if queue.get('handoffs_due') or queue.get('job')=='handoff': return None
    for key,kind in [('branches_to_review','review'),('lld_to_draft','lld'),('hld_to_draft','hld'),('sparks_needing_rework','spark'),('subtasks','build')]:
        if queue.get(key): return kind,queue[key][0]
    if queue.get('job')=='subtask': return 'build',queue
    if queue.get('job')=='scan' and queue.get('project'): return 'scan',queue
    return None

def next_check(job, after):
    """Observed recurrence only. No synthetic cadence when schedule is missing."""
    schedule=job.get('schedule') or {}
    if schedule.get('kind')=='every' and isinstance(schedule.get('everyMs'),int) and schedule['everyMs']>0:
        return after+dt.timedelta(milliseconds=max(1000,schedule['everyMs']))
    if schedule.get('kind')!='cron': return None
    fields=str(schedule.get('expr','')).split()
    if len(fields)!=5: return None
    try: zone=ZoneInfo(schedule.get('tz') or 'UTC')
    except ZoneInfoNotFoundError: return None
    def matches(expr,value):
        for part in expr.split(','):
            span,_,step=part.partition('/'); step=int(step or 1)
            if step<=0: return False
            if span=='*': low,high=0,9999
            elif '-' in span: low,high=map(int,span.split('-'))
            else: low=high=int(span)
            if low<=value<=high and (value-low)%step==0: return True
        return False
    at=after.replace(second=0,microsecond=0)+dt.timedelta(minutes=1)
    try:
        for _ in range(1440):
            local=at.astimezone(zone); weekday=(local.weekday()+1)%7
            dom=matches(fields[2],local.day); dow=matches(fields[4],weekday) or (weekday==0 and matches(fields[4],7))
            day=(dom or dow) if fields[2]!='*' and fields[4]!='*' else dom and dow
            if matches(fields[0],local.minute) and matches(fields[1],local.hour) and day and matches(fields[3],local.month): return at
            at+=dt.timedelta(minutes=1)
    except (ValueError,TypeError): return None
    return None

def simulate(inits, projects, lanes, samples, now, dispatch, spot=None, due=None,
             finishing_ids=(), bump=None, max_events=2000, horizon_hours=24):
    """Simulate current defined work to its next gate. Priority cannot preempt doing work.
    Producer gates use an explicit independent 'if approved now' scenario; the normal
    timeline never consumes gated work. Scheduler observations may be stale/absent.
    """
    now=u.utc(now); end=now+dt.timedelta(hours=min(24,max(1,horizon_hours)))
    cards=copy.deepcopy(inits); projs=copy.deepcopy(projects)
    original={i['id']:i for i in inits}; by_id={i['id']:i for i in cards}
    pmap={p['repo_name']:p for p in projs}
    plans={i['id']:json.loads(i.get('execution_plan_json') or '{}') for i in cards}
    if sum(len(p.get('subtasks',[])) for p in plans.values())>5000:
        return {'timeline':[],'items':{},'initiatives':{},'projects':{},'truncated':True,'reason':'forecast work-item budget exceeded'}
    if bump:
        for i in cards:
            if (bump[0]=='initiative' and str(i['id'])==str(bump[1])) or (bump[0]=='project' and i['project_name']==bump[1]):
                i['priority']='high'; i['updated_at']='0000'; pmap.get(i['project_name'],{})['priority']='high'
        # Stable front-of-equal-priority placement is a what-if only, not a persisted edit.
        projs.sort(key=lambda p:0 if bump[0]=='project' and p['repo_name']==bump[1] else 1)
    jobs=[]; lane_reasons={}; heap=[]; seq=0; timeline=[]; items={}; busy=set(); completed=set()
    for lane in lanes:
        actor=lane['key']
        if actor not in ('gemma','codex','claude'): continue
        reason=None
        if lane.get('scheduler',{}).get('state')=='paused': reason="won't run until resumed"
        elif lane.get('reason'): reason='schedule observation unavailable or stale'
        elif lane.get('quota',{}).get('state')=='exhausted': reason='quota exhausted; resume time not observed'
        lane_reasons[actor]=reason
        for job in lane.get('jobs',[]):
            if not job.get('enabled') or reason: continue
            start=date(job.get('next_run_at'))
            running=date(job.get('started_at'))
            if running and running<=now: start=now
            if not start or start<now: continue
            agent={'codex':'planner','gemma':'scout','claude':'architect-high' if job['declaration'].endswith('-opus') else 'architect'}[actor]
            jobs.append((actor,agent,job))
            heapq.heappush(heap,(start,seq,'pick',len(jobs)-1,None)); seq+=1
    def sync(iid): by_id[iid]['execution_plan_json']=json.dumps(plans[iid])
    def key_for(kind,candidate):
        if kind=='scan': return 'scan:'+candidate['project']
        iid=candidate.get('initiative',candidate.get('id'))
        return 's:'+str(iid)+':'+str(candidate['subtask']['id']) if kind=='build' else 'i:'+str(iid)+':'+kind
    steps=0
    while heap and steps<max_events:
        at,_,event,jidx,payload=heapq.heappop(heap); steps+=1
        if at>end: break
        actor,agent,job=jobs[jidx]
        if event=='done':
            kind,candidate,key,entry=payload; busy.discard(key); completed.add(key)
            entry['completion_at']=u.stamp(at)
            if kind=='scan':
                pmap[candidate['project']]['last_scanned_at']=u.stamp(at)
                projs.sort(key=lambda p:( {'high':0,'medium':1,'low':2,'skip':3}.get(p.get('priority'),1), p.get('last_scanned_at') or ''))
            else:
                iid=candidate.get('initiative',candidate.get('id')); card=by_id[iid]
                if kind=='build':
                    next(s for s in plans[iid]['subtasks'] if s['id']==candidate['subtask']['id'])['status']='done'; sync(iid)
                else:
                    card['stage']={'lld':'lld_review','hld':'hld_review','review':'playtest','spark':'spark'}[kind]
                    if kind=='review': plans[iid].setdefault('review',{})['status']='pass'; sync(iid)
            heapq.heappush(heap,(at,seq,'pick',jidx,None)); seq+=1
            continue
        q=dispatch(agent,cards,projs,spot,u.stamp(at),due or {},finishing_ids)
        choice=pick(q)
        if not choice:
            retry=next_check(job,at)
            if retry and retry<=end: heapq.heappush(heap,(retry,seq,'pick',jidx,None)); seq+=1
            continue
        kind,candidate=choice; key=key_for(kind,candidate)
        if key in busy or key in completed:
            # Other lane is executing the first eligible item; retry after it, not concurrently.
            waits=[h[0] for h in heap if h[2]=='done']
            if waits: heapq.heappush(heap,(min(waits)+dt.timedelta(seconds=1),seq,'pick',jidx,None)); seq+=1
            continue
        iid=candidate.get('initiative',candidate.get('id')); card=by_id.get(iid,{})
        if kind=='scan': title='dossier '+candidate['project']; project=candidate['project']
        else: title=candidate.get('subtask',{}).get('title') or card.get('title',''); project=card['project_name']
        stats=duration(samples,actor,kind); finish=at+dt.timedelta(seconds=stats['seconds'])
        entry={**stats,'key':key,'actor':actor,'work_type':kind,'initiative_id':iid,'project':project,
               'subtask_id':candidate.get('subtask',{}).get('id'),'title':title,'start_at':u.stamp(at),
               'completion_at':u.stamp(finish),'state':'estimated','label':'next producer checkpoint; estimate, not a deadline',
               'href':'#/initiative/'+str(iid) if iid else '#/project/'+project}
        if kind=='build': entry['href']+='/subtask/'+str(entry['subtask_id'])
        timeline.append(entry); items[key]=entry; busy.add(key)
        if finish<=end: heapq.heappush(heap,(finish,seq,'done',jidx,(kind,candidate,key,entry))); seq+=1
    truncated=bool(heap) and steps>=max_events
    # Every defined unfinished item has a forecast or a named blocker.
    init_etas={}
    for iid,card in original.items():
        subs=plans[iid].get('subtasks',[])
        hard=steering.eligibility(card,pmap.get(card['project_name'],{}),spot,u.stamp(now),False,iid in finishing_ids)
        if hard=='outside spotlight': hard='blocked by spotlight on '+spot['project']
        relevant=[e for e in timeline if e['initiative_id']==iid]
        pending=[]
        for sub in json.loads(card.get('execution_plan_json') or '{}').get('subtasks',[]):
            if sub.get('status')=='done': continue
            key='s:'+str(iid)+':'+str(sub['id'])
            if key not in items:
                reason=hard or ('waiting on you' if card['stage'] in GATES else None) or ('waiting for producer/editor work' if sub['assignee']=='ide_handoff' else None) or lane_reasons.get(sub['assignee']) or ('explicitly blocked' if sub.get('status')=='blocked' else 'outside next 24h or waiting for prerequisites / observed schedule')
                items[key]={**duration(samples,sub['assignee'],'build'),'state':'blocked','reason':reason}
            if items[key].get('state')=='blocked': pending.append(items[key]['reason'])
        if hard: eta={'state':'blocked','reason':hard}
        elif card['stage'] in GATES: eta={'state':'waiting','reason':'waiting on you','waiting_seconds':max(0,(now-(date(card.get('stage_entered_at') or card.get('created_at')) or now)).total_seconds())}
        elif pending: eta={'state':'blocked','reason':pending[0]}
        elif relevant:
            last=max(relevant,key=lambda e:e['completion_at'])
            eta={**last,'state':'estimated','label':'next producer checkpoint; estimate, not a deadline'}
            # A build without a scheduled review is not a completed rollup.
            if card['stage']=='building' and by_id[iid]['stage']=='building': eta={'state':'blocked','reason':'review outside next 24h or observed schedule','work_completion_at':last['completion_at']}
        else:
            actor='claude' if card['stage'] in ('spark','hld_draft') else 'codex'
            eta={'state':'blocked','reason':lane_reasons.get(actor) or 'outside next 24h or no observed schedule'}
        init_etas[str(iid)]=eta
    project_etas={}
    for project in pmap:
        values=[init_etas[str(i['id'])] for i in inits if i['project_name']==project]
        blocked=[v for v in values if not v.get('completion_at')]
        project_etas[project]=({'state':'blocked','reason':blocked[0].get('reason'),'partial':True} if blocked else max(values,key=lambda v:v['completion_at']) if values else {'state':'empty','reason':'no open initiatives'})
    return {'timeline':timeline,'items':items,'initiatives':init_etas,'projects':project_etas,'truncated':truncated,
            'horizon_at':u.stamp(end),'label':'Forecast to next producer checkpoint; gates are never auto-approved.'}

def forecast(inits, projects, lanes, samples, now, dispatch, spot=None, due=None, finishing_ids=(), bump=None):
    result=simulate(inits,projects,lanes,samples,now,dispatch,spot,due,finishing_ids,bump)
    # Conditional model: only known next stages; no invented build plan after LLD.
    conditional=copy.deepcopy(inits)
    for card in conditional:
        if card['stage'] in GATES:
            card['stage']=GATES[card['stage']] or 'done'
    future=simulate(conditional,projects,lanes,samples,now,dispatch,spot,due,finishing_ids,bump) if any(i['stage'] in GATES for i in inits) else None
    if future:
        for card in inits:
            iid=str(card['id'])
            if card['stage'] not in GATES: continue
            eta=result['initiatives'].get(iid,{})
            if eta.get('state')=='waiting':
                eta['if_approved_now']=future['initiatives'].get(iid,{'state':'blocked','reason':'next work not defined'})
                if card['stage']=='playtest': eta['if_approved_now']={'state':'estimated','completion_at':u.stamp(now),'basis_label':'producer signoff only; no automated work remaining'}
                for sub in json.loads(card.get('execution_plan_json') or '{}').get('subtasks',[]):
                    key=f"s:{card['id']}:{sub['id']}"
                    if key in result['items'] and key in future['items']: result['items'][key]['if_approved_now']=future['items'][key]
        for project in result['projects']:
            if any(i['project_name']==project and i['stage'] in GATES for i in inits): result['projects'][project]['if_approved_now']=future['projects'].get(project)
    return result

def cached(inits,projects,lanes,samples,now,dispatch,spot=None,due=None,finishing_ids=(),bump=None):
    # Include clock minute and all observed schedule/portfolio facts; never cache by mutable identity.
    key=hashlib.sha256(json.dumps([inits,projects,lanes,samples,u.stamp(now.replace(second=0,microsecond=0)),spot,due,list(finishing_ids),bump],sort_keys=True,default=str).encode()).hexdigest()
    with _lock:
        hit=_cache.get(key)
        if hit and time.monotonic()-hit[0]<30: return copy.deepcopy(hit[1])
    result=forecast(inits,projects,lanes,samples,now,dispatch,spot,due,finishing_ids,bump)
    with _lock:
        if len(_cache)>=16: _cache.pop(next(iter(_cache)))
        _cache[key]=(time.monotonic(),result)
    return copy.deepcopy(result)

def compare(base, changed, kind, target):
    collection='initiatives' if kind=='initiative' else 'projects'
    before=base[collection].get(str(target),{}); after=changed[collection].get(str(target),{})
    delayed=[]
    for iid,eta in base['initiatives'].items():
        other=changed['initiatives'].get(iid,{})
        if date(eta.get('completion_at')) and date(other.get('completion_at')) and date(other['completion_at'])>date(eta['completion_at']):
            delayed.append({'initiative_id':int(iid),'seconds':(date(other['completion_at'])-date(eta['completion_at'])).total_seconds(),'completion_at':other['completion_at']})
    return {'eta_now':before,'if_prioritized':after,'delayed':delayed,'read_only':True}
