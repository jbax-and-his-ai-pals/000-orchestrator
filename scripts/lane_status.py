"""Cached sanitized scheduler observations; never probe from a GET."""
import datetime as dt
import json
import re
import utilization as u

REGISTRY = {'gemma':['orch:scout-gemma'], 'codex':['orch:planner-codex'],
            'claude':['orch:architect-claude','orch:architect-claude-opus'],
            'gemini':['orch:reviewer-gemini']}
DECLARATIONS = {d for jobs in REGISTRY.values() for d in jobs}
SCHEMA = """CREATE TABLE IF NOT EXISTS lane_observations(
 source TEXT PRIMARY KEY, observed_at TEXT, attempted_at TEXT, status TEXT,
 payload_json TEXT, generation INTEGER NOT NULL DEFAULT 0);"""

def milliseconds(value):
    if value is None: return None
    if isinstance(value,bool) or not isinstance(value,(float,int)) or value < 0: raise ValueError('invalid timestamp')
    return u.stamp(dt.datetime.fromtimestamp(value/1000,u.UTC))

def parse_cron(text):
    data = json.loads(text)
    if not isinstance(data,dict) or not isinstance(data.get('jobs'),list) or data.get('hasMore'):
        raise ValueError('unsupported or incomplete cron schema')
    result = []
    seen = set()
    for job in data['jobs']:
        if not isinstance(job,dict): raise ValueError('invalid job')
        declaration = job.get('declarationKey')
        basis = 'declarationKey'
        if not declaration:
            # Exact legacy names only, never substring matching.
            declaration = next((d for d in DECLARATIONS if job.get('name') in (d,d.replace(':','-',1))),None)
            basis = 'legacy_exact_name'
        if declaration not in DECLARATIONS: continue
        if declaration in seen: raise ValueError('duplicate declaration')
        seen.add(declaration)
        if type(job.get('enabled')) is not bool or not re.fullmatch(r'[a-zA-Z0-9-]{1,100}',str(job.get('id',''))):
            raise ValueError('invalid job identity/state')
        state = job.get('state',{})
        if not isinstance(state,dict): raise ValueError('invalid state')
        result.append({'declaration':declaration,'id':job['id'],'enabled':job['enabled'],'basis':basis,
                       'next_run_at':milliseconds(state.get('nextRunAtMs')),
                       'started_at':milliseconds(state.get('runningAtMs')),
                       'last_run_at':milliseconds(state.get('lastRunAtMs')),
                       'schedule':{k:v for k,v in job.get('schedule',{}).items() if k in ('kind','everyMs','expr','tz') and isinstance(v,(str,int))},
                       'last_status':state.get('lastRunStatus') if state.get('lastRunStatus') in ('ok','error','skipped') else None})
    return result

def collect_cron():
    return parse_cron(u.command_output('openclaw',['cron','list','--all','--json'],10))

def save(store,payload=None,error=None,observed=None):
    timestamp=u.stamp(observed or store.clock())
    with store.connect() as con:
        con.executescript(SCHEMA)
        con.execute("INSERT INTO lane_observations(source,observed_at,attempted_at,status,payload_json,generation) VALUES ('cron',?,?,?,?,1) ON CONFLICT(source) DO UPDATE SET observed_at=CASE WHEN excluded.status='ok' THEN excluded.observed_at ELSE observed_at END, attempted_at=excluded.attempted_at,status=excluded.status,payload_json=CASE WHEN excluded.status='ok' THEN excluded.payload_json ELSE payload_json END,generation=generation+1 WHERE excluded.attempted_at>=lane_observations.attempted_at",
                    (timestamp if not error else None,timestamp,error or 'ok',json.dumps(payload) if not error else None))

def read(con,now):
    row=con.execute("SELECT * FROM lane_observations WHERE source='cron'").fetchone()
    if not row: return {'status':'missing','jobs':[],'generation':0,'observed_at':None}
    row=dict(row)
    age=(now-u.utc(row['observed_at'])).total_seconds() if row['observed_at'] else None
    status=row['status']
    if status=='ok' and (age is None or age<0 or age>90): status='stale'
    return {'status':status,'jobs':json.loads(row['payload_json'] or '[]'),'generation':row['generation'],
            'observed_at':row['observed_at'],'attempted_at':row['attempted_at'],'age_seconds':age}

def lanes(observation,now):
    result=[]
    fresh=observation['status']=='ok'
    for key,declarations in REGISTRY.items():
        jobs=[]
        for declaration in declarations:
            job=next((j for j in observation['jobs'] if j['declaration']==declaration),None)
            if job: jobs.append({**job,'generation':observation['generation'],'controllable':fresh})
        future=any(j['started_at'] and u.utc(j['started_at'])>now for j in jobs)
        running=[j for j in jobs if j['started_at'] and u.utc(j['started_at'])<=now]
        enabled=[j for j in jobs if j['enabled']]
        result.append({'key':key,'label':key.title(),'jobs':jobs,'observed_at':observation['observed_at'],
                       'reason':observation['status'] if not fresh else 'clock_skew' if future else ('job_absent' if len(jobs)!=len(declarations) else None),
                       'activity':{'state':'working' if fresh and running and not future else 'idle' if fresh and jobs and not running and not future else 'unknown',
                                   'started_at':min(j['started_at'] for j in running) if fresh and running else None,'task_ref':None,'basis':'cron' if fresh else 'unknown'},
                       'scheduler':{'state':'unknown' if not fresh or not jobs else 'enabled' if len(enabled)==len(jobs) else 'paused' if not enabled else 'mixed',
                                    'next_run_at':min((j['next_run_at'] for j in enabled if j['next_run_at']),default=None) if fresh else None},
                       'quota':{'state':'local' if key=='gemma' else 'unknown'}})
    return result
