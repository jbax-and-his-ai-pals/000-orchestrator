"""Read-only dashboard projection. Clock-injected estimates never run tools or steer work."""
import datetime as dt
import json
import re
import statistics
import threading
import time
from urllib.parse import quote
import lane_status
import steering
import utilization as u

ACTORS=u.LANES
_cache={}
_lock=threading.Lock()

def date(value):
    try: return u.utc(value)
    except (ValueError,TypeError): return None

def durations(events,now):
    """Pair exact attempt boundaries; ambiguous legacy starts invalidate their interval."""
    starts={}; samples=[]
    for event in sorted(events,key=lambda e:(date(e['ts']) or now,e.get('id',0))):
        at=date(event['ts']); actor=ACTORS.get(event['actor'])
        if not actor or not at or not now-dt.timedelta(days=90)<=at<=now: continue
        try: details=json.loads(event.get('details_json') or '{}')
        except (TypeError,ValueError): details={}
        if event['kind']!='subtask': continue
        if details.get('attempt'):
            sid=details.get('subtask_id'); status=details.get('to'); token=details['attempt']
        else:
            match=re.fullmatch(r'(\d+) -> (doing|done|blocked):.*',event.get('message') or '',re.S)
            if not match: continue
            sid=int(match[1]); status=match[2]; token='legacy'
        key=(actor,event['initiative_id'],sid,token)
        if status=='doing':
            if key not in starts: starts[key]=at
            elif token=='legacy': starts[key]=None
        elif status in ('done','blocked') and key in starts:
            start=starts.pop(key)
            if start and 0<(at-start).total_seconds()<=86400:
                samples.append({'actor':actor,'work_type':'build','seconds':(at-start).total_seconds()})
    return samples

def typical(samples,actor,work_type):
    exact=[s['seconds'] for s in samples if s['actor']==actor and s['work_type']==work_type]
    basis='actor_work_type'
    if len(exact)<3:
        exact=[s['seconds'] for s in samples if s['actor']==actor]; basis='actor_fallback_low_confidence'
    if len(exact)<3: return None
    exact.sort()
    return {'seconds':statistics.median(exact),'sample_count':len(exact),'basis':basis,
            'p25':exact[(len(exact)-1)//4],'p75':exact[3*(len(exact)-1)//4]}

def estimate(samples,actor,kind,start,now):
    stats=typical(samples,actor,kind)
    if not stats or not start: return {'state':'unknown','reason':'insufficient_history' if not stats else 'no_start'}
    finish=date(start)+dt.timedelta(seconds=stats['seconds'])
    return {**stats,'state':'over_typical' if finish<now else 'estimated','completion_at':u.stamp(finish) if finish>=now else None,
            'basis_at':start,'label':'estimate, not a deadline'}

def pace(metric,window,now):
    result={**metric,'pace':'unavailable','target_used':None,'delta_pp':None,'estimated':True}
    if metric['status']!='ok' or metric.get('value') is None: return result
    reset=date(metric.get('meta',{}).get('resets_at'))
    if not reset or reset<=now: return result
    duration=dt.timedelta(hours=5) if window=='5h' else dt.timedelta(days=7)
    start=reset-duration
    if not start<=now<reset: return result
    target=100*(now-start).total_seconds()/duration.total_seconds()
    actual=100-metric['value']; delta=actual-target
    result.update(pace='on pace' if abs(delta)<=5 else 'ahead (faster spending)' if delta>0 else 'behind',
                  actual_used=actual,target_used=target,delta_pp=delta,
                  baseline='estimated nominal window; rolling windows approximate')
    return result

def snapshot(orch,clock=None):
    now=u.utc(clock() if clock else dt.datetime.now(u.UTC))
    with orch.db() as con:
        projects=orch.rows(con,'SELECT * FROM projects ORDER BY repo_name')
        inits=orch.rows(con,"SELECT * FROM initiatives WHERE stage NOT IN ('done','rejected')")
        events=orch.rows(con,'SELECT * FROM events ORDER BY id DESC LIMIT 10001')
        observation=lane_status.read(con,now)
        quotas={provider:{w:pace(u.current_metric(con,provider,'remaining_pct.'+w,now),w,now) for w in u.WINDOWS} for provider in ('openai','anthropic')}
        local=u.current_metric(con,'ollama','loaded_count',now)
        metric_generation=con.execute('SELECT COALESCE(MAX(rowid),0) FROM metrics').fetchone()[0]
    events=events[:10000]
    highwater=events[0]['id'] if events else 0
    cache_key=(str(orch.DB_PATH),highwater)
    with _lock:
        cached=_cache.get(cache_key)
        if not cached or time.monotonic()-cached[0]>30:
            cached=(time.monotonic(),durations(events,now)); _cache.clear(); _cache[cache_key]=cached
    samples=cached[1]
    by_project={p['repo_name']:p for p in projects}
    spot=orch.get_spotlight()
    rows=[]; pending={k:[] for k in ('sparks','queued','blocked','producer')}; attention=[]; suggestions=[]
    def add_attention(row,reason):
        attention.append({'key':str(row.get('key',row.get('initiative_id')))+':'+reason,'reason':reason,'href':row.get('href','#/'),'title':row.get('title',reason)})
    for i in inits:
        project=by_project.get(i['project_name'],{})
        history=[e for e in events if e.get('initiative_id')==i['id']]
        stage_events=[e for e in history if e['kind']=='stage:'+i['stage']]
        entered=stage_events[0]['ts'] if stage_events else None
        claim=i.get('claimed_by') if (date(i.get('claim_expires_at')) or now)<=now else i.get('claimed_by')
        if not date(i.get('claim_expires_at')) or date(i['claim_expires_at'])<=now: claim=None
        owner=claim or {'hld_draft':'claude','lld_draft':'codex'}.get(i['stage'])
        reason=steering.eligibility(i,project,spot,orch.now(),False,orch.finishing(spot,i['id']))
        base={'key':'i:'+str(i['id']),'initiative_id':i['id'],'subtask_id':None,'project':i['project_name'],
              'title':i['title'],'stage':i['stage'],'status':i['stage'],'owner':owner,'owner_basis':'claim' if claim else 'stage_route' if owner else 'unknown',
              'created_at':i['created_at'],'stage_entered_at':entered,'age_basis':'stage_entry' if entered else 'creation_fallback',
              'age_seconds':max(0,(now-(date(entered or i['created_at']) or now)).total_seconds()),
              'last_activity_at':history[0]['ts'] if history else None,'eligibility':reason or 'eligible',
              'href':'#/initiative/'+str(i['id']),'priority':i.get('priority','medium'),'version':steering.version(i)}
        if i["stage"] not in orch.AWAITING_PRODUCER: rows.append(base)
        if i['stage']=='spark':
            pending['sparks'].append(base)
            if i['project_name']=='000-orchestrator': suggestions.append(base)
        elif i['stage'] in orch.AWAITING_PRODUCER:
            pending['producer'].append(base); add_attention(base,orch.AWAITING_PRODUCER[i['stage']])
        plan=json.loads(i['execution_plan_json'] or '{}'); subs=plan.get('subtasks',[])
        if plan.get('review',{}).get('status')=='fail': add_attention(base,'review failed')
        for sub in subs:
            if sub.get('status')=='done': continue
            blocked=reason or ('initiative not building' if i['stage']!='building' else None) or ('explicitly blocked' if sub.get('status')=='blocked' else None) or ('dependency wait' if not orch.ready(sub,subs) else None)
            row={**base,'key':'s:'+str(i['id'])+':'+str(sub['id']),'subtask_id':sub['id'],'title':sub['title'],
                 'status':sub.get('status','todo'),'owner':claim or sub.get('assignee'),'owner_basis':'claim' if claim else 'plan',
                 'eligibility':blocked or 'eligible','href':base['href']+'/subtask/'+str(sub['id'])}
            if sub.get('status')=='doing': rows.append(row)
            else: pending['blocked' if blocked else 'queued'].append(row)
            if sub.get('status')=='blocked': add_attention(row,'explicitly blocked')
            if sub.get('last_verify',{}).get('ok') is False: add_attention(row,'verification failed')
    lanes=lane_status.lanes(observation,now)
    queues={}
    # The actual dispatch interface is authoritative for first candidate and handoff precedence.
    for key,agent in [('gemma','scout'),('codex','planner'),('claude','architect'),('claude-high','architect-high')]:
        queues[key]=orch.queue(agent)
    for lane in lanes:
        provider={'codex':'openai','claude':'anthropic'}.get(lane['key'])
        if provider:
            windows=quotas[provider]
            lane['quota']={'state':'exhausted' if any(m['status']=='ok' and m['value']==0 for m in windows.values()) else 'observed' if any(m['status']=='ok' for m in windows.values()) else 'unknown','windows':windows}
        if lane['key']=='gemma': lane['residency']=local
        for job in lane['jobs']:
            candidate=None; queue=queues.get('claude-high' if job['declaration'].endswith('-opus') else lane['key'],{})
            if queue.get('handoffs_due') or queue.get('job')=='handoff':
                job['estimate']={'state':'unknown','reason':'handoff due'}; continue
            kind=None
            if queue.get('branches_to_review'): candidate=queue['branches_to_review'][0]; kind='review'
            elif queue.get('lld_to_draft'): candidate=queue['lld_to_draft'][0]; kind='lld'
            elif queue.get('hld_to_draft'): candidate=queue['hld_to_draft'][0]; kind='hld'
            elif queue.get('subtasks'):
                candidate=queue['subtasks'][0]; kind='build'
            elif queue.get('job')=='subtask': candidate=queue; kind='build'
            fresh=observation['status']=='ok'
            start=job.get('started_at') if fresh else None
            if start and candidate and candidate.get('subtask',{}).get('status') != 'doing':
                candidate=None  # a running cron alone does not identify a task
            if not start and fresh and job['enabled']: start=job.get('next_run_at')
            if start and date(start)<now and not job.get('started_at'): start=None
            if lane['quota']['state']=='exhausted': start=None
            job['estimate']=estimate(samples,lane['key'],kind,start,now) if candidate and start else {'state':'unknown','reason':'no eligible work or schedule'}
            if candidate:
                iid=candidate.get('initiative',candidate.get('id'))
                job['estimate']['href']='#/initiative/'+str(iid)
                job['estimate']['title']=candidate.get('title') or candidate.get('subtask',{}).get('title')
            # Never attach the queued candidate to a confirmed running job as task identity.
        valid=[j['estimate'] for j in lane['jobs'] if j.get('estimate',{}).get('completion_at')]
        lane['estimate']=min(valid,key=lambda x:x['completion_at']) if valid else {'state':'unknown','reason':'completion unknown'}
        if lane['reason']: add_attention({'key':lane['key'],'href':'#/','title':lane['label']},'scheduler '+lane['reason'])
        if lane['quota']['state']=='exhausted': add_attention({'key':lane['key'],'title':lane['label']},'quota exhausted')
    claims=[{'initiative_id':i['id'],'title':i['title'],'owner':i['claimed_by'],'href':'#/initiative/'+str(i['id'])} for i in inits if i.get('claimed_by') and date(i.get('claim_expires_at')) and date(i['claim_expires_at'])>now]
    focus=[{'project':p['repo_name'],'owner':p['focus_by'],'href':'#/project/'+quote(p['repo_name'],safe='')} for p in projects if p.get('focus_by') and date(p.get('focus_until')) and date(p['focus_until'])>now]
    lanes.append({'key':'chat','label':'Chat','jobs':[],'activity':{'state':'claimed/in chat' if claims or focus else 'no claims','basis':'ownership, not process'},'claims':claims,'focus':focus,'scheduler':{'state':'none','next_run_at':None},'quota':{'state':'unknown'},'estimate':{'state':'unknown','reason':'chat has no schedule'}})
    estimates=[l['estimate'] for l in lanes if l['estimate'].get('completion_at')]
    next_checks=[l['scheduler']['next_run_at'] for l in lanes if l['scheduler'].get('next_run_at') and date(l['scheduler']['next_run_at'])>=now]
    for p in projects:
        recent=[e for e in events if e.get('project_name')==p['repo_name'] and e['actor'] not in ('init','producer') and date(e['ts']) and 0<=(now-date(e['ts'])).total_seconds()<=900]
        p['recent_activity']=bool(recent); p['version']=orch.project_version(p)
    return {'schema_version':1,'generated_at':u.stamp(now),'telemetry_generation':str(observation['generation'])+':'+str(metric_generation),
            'history_truncated':len(events)>=10000,'lanes':lanes,'next_update':min(estimates,key=lambda e:e['completion_at']) if estimates else {'state':'unknown','next_check_at':min(next_checks,default=None)},
            'in_flight':rows,'pending':pending,'attention':list({a['key']:a for a in attention}.values()),'suggestions':suggestions,'projects':projects,'spotlight':spot,
            'totals':{'initiatives':len(inits),'in_flight_rows':len(rows),'pending_rows':sum(map(len,pending.values()))}}
