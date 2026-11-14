"""Read-only dashboard projection. Clock-injected estimates never run tools or steer work."""
import datetime as dt
import json
import re
import statistics
import threading
import time
from urllib.parse import quote
import forecast
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
            overlaps=[k for k in starts if k[:3]==key[:3] and k!=key]
            for other in overlaps: starts[other]=None
            if key not in starts: starts[key]=None if overlaps else at
            elif token=='legacy': starts[key]=None
        elif status in ('done','blocked') and key in starts:
            start=starts.pop(key)
            if start and 0<(at-start).total_seconds()<=86400:
                samples.append({'actor':actor,'work_type':'build','seconds':(at-start).total_seconds()})
    return samples

def typical(samples,actor,work_type):
    return forecast.duration(samples,actor,work_type)

def estimate(samples,actor,kind,start,now):
    stats=typical(samples,actor,kind)
    if not stats or not start: return {'state':'unknown','reason':'insufficient_history' if not stats else 'no_start'}
    finish=date(start)+dt.timedelta(seconds=stats['seconds'])
    return {**stats,'state':'over_typical' if finish<now else 'estimated','completion_at':u.stamp(finish) if finish>=now else None,
            'basis_at':start}

def pace(metric,window,now):
    result={**metric,'pace':'unavailable','target_used':None,'delta_pp':None,'estimated':True}
    if result.get('reason')=='observation_stale' and (metric.get('age_seconds') or 0)<=3600:
        result.update(status='ok',reason=None)
    if (metric.get('age_seconds') or 0)>3600:
        result.update(status='stale',reason='observation_stale')
    if result['status']!='ok' or metric.get('value') is None: return result
    reset=date(metric.get('meta',{}).get('resets_at'))
    if not reset or reset<=now: return result
    duration=dt.timedelta(hours=5) if window=='5h' else dt.timedelta(days=7)
    start=reset-duration
    if not start<=now<reset: return result
    target=100*(now-start).total_seconds()/duration.total_seconds()
    actual=100-metric['value']; delta=actual-target
    result.update(pace='on pace' if abs(delta)<=5 else 'over pace' if delta>0 else 'under pace',
                  actual_used=actual,target_used=target,delta_pp=delta,
                  baseline='estimated nominal window; rolling windows approximate')
    return result

def stage_owner(stage, gates):
    if stage in gates and stage!='spark': return 'producer'
    return 'claude' if stage in ('spark','hld_draft') else 'codex'

def by_id_complexity(inits,iid):
    return next((i.get('complexity') for i in inits if i['id']==iid),None)

def empty_totals():
    return dict(open_initiatives=0,in_flight=0,waiting_on_producer=0,blocked=0,queued_subtasks=0,subtasks_done=0,subtasks_total=0,stages={})

def rollups(inits,projects,rows,gates,model):
    """Unique card/task identities: duplicate parent rows never inflate counts."""
    all_projects=[]; totals=empty_totals()
    by_project={}
    for i in inits: by_project.setdefault(i['project_name'],[]).append(i)
    blocked_ids={r['initiative_id'] for r in rows if r.get('eligibility') not in (None,'eligible','dependency wait','initiative not building')}
    for project in projects:
        name=project['repo_name']; cards=by_project.get(name,[]); result=empty_totals()
        for card in cards:
            result['open_initiatives']+=1
            result['stages'][card['stage']]=result['stages'].get(card['stage'],0)+1
            result['in_flight']+=card['stage'] in ('building','hld_draft','lld_draft')
            result['waiting_on_producer']+=card['stage'] in gates
            result['blocked']+=card['id'] in blocked_ids
            subs=json.loads(card['execution_plan_json'] or '{}').get('subtasks',[])
            result['subtasks_done']+=sum(s.get('status')=='done' for s in subs)
            result['subtasks_total']+=len(subs)
            result['queued_subtasks']+=sum(s.get('status')=='todo' for s in subs)
        for key,value in result.items():
            if key!='stages': totals[key]+=value
        for stage,count in result['stages'].items(): totals['stages'][stage]=totals['stages'].get(stage,0)+count
        all_projects.append({**result,'project':name,'estimate':model['projects'].get(name,{'state':'blocked','reason':model.get('reason','no open initiatives')}),'priority':project.get('priority')})
    return {'totals':totals,'projects':all_projects}

def _next_update(model,estimates,next_checks):
    """The next expected thing: the earliest forecast event, else the earliest lane estimate."""
    check=min(next_checks,default=None)
    events=sorted(model.get('timeline') or [],key=lambda e:e['start_at'])
    if events: return {**events[0],'next_check_at':check}
    if estimates: return {**min(estimates,key=lambda e:e['completion_at']),'next_check_at':check}
    return {'state':'unknown','next_check_at':check}

def snapshot(orch,clock=None,bump=None):
    now=u.utc(clock() if clock else dt.datetime.now(u.UTC))
    with orch.db() as con:
        projects=orch.rows(con,'SELECT * FROM projects ORDER BY repo_name')
        inits=orch.rows(con,"SELECT * FROM initiatives WHERE stage NOT IN ('done','rejected')")
        events=orch.rows(con,'SELECT * FROM events ORDER BY id DESC LIMIT 10001')
        observation=lane_status.read(con,now)
        quotas={provider:{w:pace(u.current_metric(con,provider,'remaining_pct.'+w,now),w,now) for w in u.WINDOWS} for provider in ('openai','anthropic')}
        for windows in quotas.values():
            for metric in windows.values():
                if metric.get('status')=='stale' and metric.get('meta',{}).get('manual'):
                    metric['hint']='record from a Claude chat (quota-snapshot)'
        for metric in quotas['anthropic'].values():
            if metric['status'] in ('stale','missing','error'):
                metric['hint']='record from a Claude chat (quota-snapshot)'
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
    histories={}
    for event in events:
        histories.setdefault(event.get('initiative_id'),[]).append(event)
    spot=orch.get_spotlight()
    due_by_actor={actor:orch.handoffs_due(spot,actor) for actor in ("gemma","codex","claude","gemini")}
    rows=[]; pending={k:[] for k in ('sparks','queued','blocked','producer')}; attention=[]; suggestions=[]
    def add_attention(row,reason):
        attention.append({'key':str(row.get('key',row.get('initiative_id')))+':'+reason,'reason':reason,'href':row.get('href','#/'),'title':row.get('title',reason)})
    for i in inits:
        project=by_project.get(i['project_name'],{})
        history=histories.get(i['id'],[])
        stage_events=[e for e in history if e['kind']=='stage:'+i['stage']]
        entered=stage_events[0]['ts'] if stage_events else None
        claim=i.get('claimed_by') if (date(i.get('claim_expires_at')) or now)<=now else i.get('claimed_by')
        if not date(i.get('claim_expires_at')) or date(i['claim_expires_at'])<=now: claim=None
        owner=claim or stage_owner(i['stage'],orch.AWAITING_PRODUCER)
        i['stage_entered_at']=entered
        reason=steering.eligibility(i,project,spot,u.stamp(now),bool(due_by_actor.get(owner)),orch.finishing(spot,i['id']))
        base={'key':'i:'+str(i['id']),'initiative_id':i['id'],'subtask_id':None,'project':i['project_name'],
              'title':i['title'],'stage':i['stage'],'status':i['stage'],'owner':owner,'owner_basis':'claim' if claim else 'stage_route',
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
            blocked=reason or ('handoff due' if due_by_actor.get(sub.get('assignee')) and spot and i['project_name']==spot['project'] else None) or ('initiative not building' if i['stage']!='building' else None) or ('explicitly blocked' if sub.get('status')=='blocked' else None) or ('dependency wait' if not orch.ready(sub,subs) else None)
            row={**base,'key':'s:'+str(i['id'])+':'+str(sub['id']),'subtask_id':sub['id'],'title':sub['title'],
                 'status':sub.get('status','todo'),'owner':claim or sub.get('assignee'),'owner_basis':'claim' if claim else 'plan',
                 'eligibility':blocked or 'eligible','href':base['href']+'/subtask/'+str(sub['id'])}
            changes=[]
            for event in history:
                try: details=json.loads(event.get('details_json') or '{}')
                except ValueError: details={}
                if details.get('subtask_id')==sub['id'] and details.get('to')==sub.get('status') and details.get('from')!=details.get('to'):
                    changes.append(event)
            if changes:
                row.update(execution_actor=ACTORS.get(changes[0]['actor']),stage_entered_at=changes[0]['ts'],age_basis='subtask_status_entry',age_seconds=max(0,(now-(date(changes[0]['ts']) or now)).total_seconds()))
            if sub.get('status')=='doing': rows.append(row)
            else: pending['blocked' if blocked else 'queued'].append(row)
            if sub.get('status')=='blocked': add_attention(row,'explicitly blocked')
            if sub.get('last_verify',{}).get('ok') is False: add_attention(row,'verification failed')
    for actor,items in due_by_actor.items():
        for item in items:
            add_attention({'key':'handoff:'+str(item['initiative'])+':'+actor,'href':'#/initiative/'+str(item['initiative']),'title':actor+' handoff'},'handoff note due')
    for provider,windows in quotas.items():
        for window,metric in windows.items():
            if metric['status'] in ('stale','error'):
                add_attention({'key':provider+':'+window,'href':'#/tab/utilization','title':provider+' '+window},'quota '+metric['status'])
    lanes=lane_status.lanes(observation,now)
    queues={}
    # The actual dispatch interface is authoritative for first candidate and handoff precedence.
    for key,agent in [('gemma','scout'),('codex','planner'),('claude','architect'),('claude-high','architect-high')]:
        queues[key]=orch.queue(agent)
    confirmed_active=set()
    for lane in lanes:
        provider={'codex':'openai','claude':'anthropic'}.get(lane['key'])
        if provider:
            windows=quotas[provider]
            lane['quota']={'state':'exhausted' if any(m['status']=='ok' and m['value']==0 for m in windows.values()) else 'observed' if any(m['status']=='ok' for m in windows.values()) else 'unknown','windows':windows}
        if lane['key']=='gemma': lane['residency']=local
        recent=next((e for e in events if ACTORS.get(e['actor'])==lane['key'] and date(e['ts']) and 0<=(now-date(e['ts'])).total_seconds()<=600),None)
        lane['recent_activity']={'at':recent['ts'],'initiative_id':recent.get('initiative_id'),'basis':'recent event, not confirmed running'} if recent else None
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
            if start:
                # A unique explicit execution start inside this cron run can identify work;
                # old doing flags and adjacent/recent events cannot.
                active=[row for row in rows if row.get('subtask_id') is not None and row['status']=='doing'
                        and row.get('execution_actor')==lane['key'] and row['owner']==lane['key']
                        and row['age_basis']=='subtask_status_entry' and date(row['stage_entered_at'])>=date(start)]
                running_jobs=[j for j in lane['jobs'] if j.get('started_at')]
                candidate=None
                if len(active)==1 and len(running_jobs)==1:
                    row=active[0]
                    lane['activity'].update(task_ref='#'+str(row['initiative_id'])+' sub '+str(row['subtask_id'])+': '+row['title'],
                                            href=row['href'],basis='unique execution start correlated with fresh cron run',started_at=row['stage_entered_at'])
                    confirmed_active.add(row['initiative_id'])
                    candidate={'initiative':row['initiative_id'],'subtask':{'title':row['title'],'status':'doing'}}
                    kind='build'; start=row['stage_entered_at']
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
    model=forecast.cached(inits,projects,lanes,samples,now,orch.queue_from_snapshot,spot,due_by_actor,
        [i['id'] for i in inits if orch.finishing(spot,i['id'])])
    for lane in lanes:
        upcoming=[e for e in model['timeline'] if e['actor']==lane['key']]
        if upcoming: lane['estimate']=min(upcoming,key=lambda e:e['completion_at'])
        elif lane['scheduler']['state']=='paused': lane['estimate']={'state':'blocked','reason':'paused: dispatch from chat or resume its lane'}
        for job in lane['jobs']:
            choices=[e for e in upcoming if e['work_type']!='hld' or (by_id_complexity(inits,e['initiative_id'])=='high')==job['declaration'].endswith('-opus')]
            if choices: job['estimate']=choices[0]
            elif not job['enabled']: job['estimate']={'state':'blocked','reason':'paused: dispatch from chat or resume its lane'}
    all_rows=rows+[r for group in pending.values() for r in group]
    progress={i['id']:json.loads(i['execution_plan_json'] or '{}').get('subtasks',[]) for i in inits}
    for row in all_rows:
        row['estimate']=model['items'].get(row['key'],model['initiatives'].get(str(row['initiative_id']),{'state':'blocked','reason':model.get('reason','outside observed schedule')}))
        subs=progress[row['initiative_id']]
        row['progress']={'done':sum(s.get('status')=='done' for s in subs),'total':len(subs)}
    rollup=rollups(inits,projects,all_rows,orch.AWAITING_PRODUCER,model)
    comparison=None
    if bump:
        changed=forecast.cached(inits,projects,lanes,samples,now,orch.queue_from_snapshot,spot,due_by_actor,
            [i['id'] for i in inits if orch.finishing(spot,i['id'])],bump)
        comparison=forecast.compare(model,changed,bump[0],bump[1])
    claims=[{'initiative_id':i['id'],'title':i['title'],'owner':i['claimed_by'],'href':'#/initiative/'+str(i['id'])} for i in inits if i.get('claimed_by') and date(i.get('claim_expires_at')) and date(i['claim_expires_at'])>now]
    focus=[{'project':p['repo_name'],'owner':p['focus_by'],'href':'#/project/'+quote(p['repo_name'],safe='')} for p in projects if p.get('focus_by') and date(p.get('focus_until')) and date(p['focus_until'])>now]
    lanes.append({'key':'chat','label':'Chat','jobs':[],'activity':{'state':'claimed/in chat' if claims or focus else 'no claims','basis':'ownership, not process'},'claims':claims,'focus':focus,'scheduler':{'state':'none','next_run_at':None},'quota':{'state':'unknown'},'estimate':{'state':'unknown','reason':'chat has no schedule'}})
    estimates=[l['estimate'] for l in lanes if l['estimate'].get('completion_at')]
    next_checks=[l['scheduler']['next_run_at'] for l in lanes if l['scheduler'].get('next_run_at') and date(l['scheduler']['next_run_at'])>=now]
    for p in projects:
        recent=[e for e in events if e.get('project_name')==p['repo_name'] and e['actor'] not in ('init','producer') and date(e['ts']) and 0<=(now-date(e['ts'])).total_seconds()<=900]
        p['recent_activity']=bool(recent); p['version']=orch.project_version(p)
    return {'schema_version':1,'generated_at':u.stamp(now),'telemetry_generation':str(observation['generation'])+':'+str(metric_generation),
            'history_truncated':len(events)>=10000,'lanes':lanes,'next_update':_next_update(model,estimates,next_checks),
            'confirmed_active':sorted(confirmed_active),'in_flight':rows,'pending':pending,'attention':list({a['key']:a for a in attention}.values()),'suggestions':suggestions,'projects':projects,'spotlight':spot,
            'forecast':model,'rollups':rollup,'what_if':comparison,
            'totals':{'initiatives':len(inits),'in_flight_rows':len(rows),'pending_rows':sum(map(len,pending.values()))}}


def paged(report,project='',collection=None,offset=0,limit=200):
    """Explicit collection cursors keep initial JSON bounded without omitting inventory."""
    collections={'in_flight':report['in_flight'],'suggestions':report['suggestions'],
                 **{'pending.'+k:v for k,v in report['pending'].items()}}
    if collection and collection not in collections: raise ValueError('unknown overview collection')
    pages={}
    for key,items in collections.items():
        selected=[r for r in items if not project or r['project']==project]
        start=offset if collection==key else 0
        rows=selected[start:start+limit]
        pages[key]={'total':len(selected),'offset':start,'next_cursor':start+len(rows) if start+len(rows)<len(selected) else None}
        if key.startswith('pending.'): report['pending'][key.split('.')[1]]=rows
        else: report[key]=rows
    if project:
        report['rollups']['projects']=[p for p in report['rollups']['projects'] if p['project']==project]
        report['rollups']['totals']=report['rollups']['projects'][0] if report['rollups']['projects'] else empty_totals()
        report['forecast']['timeline']=[e for e in report['forecast']['timeline'] if e['project']==project]
    report['pages']=pages
    report['project_filter']=project
    return report
