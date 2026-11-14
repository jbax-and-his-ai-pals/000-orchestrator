"""Narrow dashboard operations, invoked by orch entry points only."""
import datetime as dt
import json
import re
import uuid
from pathlib import Path
import lane_status as lane
import steering
import utilization as u

def lane_control(orch,declaration,enabled,expected,actor,controller=None):
    if declaration not in lane.DECLARATIONS or type(enabled) is not bool:
        raise orch.OrchError('unsupported lane control')
    controller=controller or ExternalController()
    store=u.Store(orch.DB_PATH)
    token=uuid.uuid4().hex
    with store.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        observed=lane.read(con,u.utc(store.clock()))
        steering.expect(observed['generation'],expected)
        if observed['status']!='ok': raise steering.Conflict('scheduler observation is not fresh')
        before=next((j for j in observed['jobs'] if j['declaration']==declaration),None)
        if not before: raise orch.OrchError('declaration absent')
        row=con.execute("SELECT value FROM settings WHERE key='lane_control_lease'").fetchone()
        if row and u.utc(json.loads(row[0])['until'])>u.utc(store.clock()): raise steering.Conflict('lane control in progress')
        con.execute("INSERT OR REPLACE INTO settings VALUES ('lane_control_lease',?)",(json.dumps({'token':token,'until':u.stamp(u.utc(store.clock())+dt.timedelta(seconds=90))}),))
    outcome='unknown'; after=[]
    try:
        current=controller.read()
        job=next((j for j in current if j['declaration']==declaration),None)
        if not job or job['id']!=before['id'] or job['enabled']!=before['enabled']:
            raise steering.Conflict('scheduler changed; refresh')
        write_error=None
        if job['enabled']!=enabled:
            try: controller.set(job['id'],enabled)
            except Exception as exc: write_error=exc
        after=controller.read()
        actual=next((j for j in after if j['declaration']==declaration),None)
        if not actual or actual['enabled']!=enabled:
            if write_error: raise write_error
            raise orch.OrchError('scheduler outcome not confirmed')
        outcome='confirmed'
        lane.save(store,after)
        return {'outcome':outcome,'declaration':declaration,'enabled':actual['enabled'],'affects':'future runs only'}
    finally:
        # Never pretend a timed-out external write was rolled back.
        with orch.db(write=True) as con:
            row=con.execute("SELECT value FROM settings WHERE key='lane_control_lease'").fetchone()
            if row and json.loads(row[0]).get('token')==token:
                con.execute("DELETE FROM settings WHERE key='lane_control_lease'")
            orch.log_event(con,actor,'lane_control',declaration+': '+outcome,details={'declaration':declaration,'outcome':outcome})

class ExternalController:
    def read(self): return lane.collect_cron()
    def set(self,job_id,enabled):
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,100}',job_id): raise ValueError('invalid identity')
        u.command_output('openclaw',['cron','enable' if enabled else 'disable',job_id],10)

def subtask_detail(orch,iid,sid,before=None):
    with orch.db() as con:
        init=orch.get_initiative(con,iid)
        events=orch.rows(con,'SELECT * FROM events WHERE initiative_id=? AND id<? ORDER BY id DESC LIMIT 101',iid,before or 9223372036854775807)
    sub=orch._subtask(init,sid)
    history=[]
    for e in events[:100]:
        try: d=json.loads(e.get('details_json') or '{}')
        except ValueError: d={}
        if d.get('subtask_id')==sid or not d:
            history.append({**e,'attribution':'subtask' if d else 'initiative-wide legacy'})
    result={**sub,'last_verify':{**sub.get('last_verify',{}),'output_tail':sub.get('last_verify',{}).get('output_tail','')[-2500:]},
            'history':history,'next_cursor':events[99]['id'] if len(events)>100 else None,
            'diff':{'basis':'initiative-wide legacy; subtask attribution unavailable','patch':'','truncated':False,'href':'#/initiative/'+str(iid)},
            'plan_version':steering.version(init['execution_plan_json'])}
    shas=sub.get('commit_shas',[])[:50]
    if not shas: return result
    wt=Path(init.get('worktree_path') or '')
    orch.guard(wt)
    if orch.git(wt,'rev-parse','--abbrev-ref','HEAD')!=init['branch_name']: raise orch.OrchError('worktree branch mismatch')
    patches=[]; remaining=65536; truncated=False
    for sha in shas:
        if not re.fullmatch(r'[0-9a-f]{40}',sha): raise orch.OrchError('invalid recorded SHA')
        if orch.run(['git','-C',str(wt),'merge-base','--is-ancestor',sha,'HEAD']).returncode: raise orch.OrchError('recorded commit not ancestral')
        try:
            patch=u.command_output('git',['-C',str(wt),'show','--format=short','--no-ext-diff','--no-textconv',sha,'--'],5)
        except u.CollectorError as exc:
            if exc.reason!='oversized': raise
            patch='[commit patch exceeds capture cap]'; truncated=True
        encoded=patch.encode()
        patches.append(encoded[:remaining].decode('utf-8','replace'))
        if len(encoded)>remaining: truncated=True
        remaining-=min(remaining,len(encoded))
        if not remaining: break
    result['diff']={'basis':'recorded subtask commits','commits':shas,'patch':'\n'.join(patches),'truncated':truncated}
    return result
