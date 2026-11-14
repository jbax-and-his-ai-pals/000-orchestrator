import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import test_dashboard_steering as base
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
import app
import orch
import steering
import lane_status as lane
import utilization as u

async def request(path,method='GET',body=None,header=True):
    sent=[]; first=True
    async def receive():
        nonlocal first
        if first:
            first=False
            return {'type':'http.request','body':json.dumps(body or {}).encode(),'more_body':False}
        await asyncio.sleep(10)
        return {'type':'http.disconnect'}
    async def send(message): sent.append(message)
    headers=[(b'content-type',b'application/json')]
    if header: headers.append((b'x-orchestrator',b'1'))
    scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','headers':headers,'server':('test',80),'client':('test',1),'root_path':''}
    await app.app(scope,receive,send)
    start=next(m for m in sent if m['type']=='http.response.start')
    raw=b''.join(m.get('body',b'') for m in sent if m['type']=='http.response.body')
    return start['status'],json.loads(raw)

class DashboardAPITests(base.SteeringTests):
    def call(self,*args,**kw): return asyncio.run(request(*args,**kw))
    def test_overview_priority_conflict_and_detail(self):
        with patch.object(u,'command_output',side_effect=AssertionError('read probed')):
            status,report=self.call('/api/overview')
        self.assertEqual(status,200); self.assertEqual(report['totals']['initiatives'],3)
        status,detail=self.call('/api/initiatives/1')
        token=detail['version']
        self.assertEqual(self.call('/api/initiatives/1/priority','POST',{'priority':'high','expected_version':token})[0],200)
        self.assertEqual(self.call('/api/initiatives/1/priority','POST',{'priority':'low','expected_version':token})[0],409)
        status,sub=self.call('/api/initiatives/1/subtasks/1')
        self.assertEqual(status,200); self.assertIn('legacy',sub['diff']['basis'])
    def test_idea_idempotency_and_body_conflict(self):
        with orch.db(write=True) as con: con.execute("INSERT INTO projects(repo_name,local_path) VALUES ('000-orchestrator','test')")
        body={'title':'An idea','pitch':'Specific evidence','category':'optimization','idempotency_key':'idea-test-123'}
        first=self.call('/api/suggestions','POST',body); second=self.call('/api/suggestions','POST',body)
        self.assertEqual(first[0],200); self.assertEqual(first[1]['id'],second[1]['id']); self.assertEqual(first[1]['stage'],'spark')
        self.assertEqual(self.call('/api/suggestions','POST',{**body,'pitch':'different'})[0],409)
    def test_lane_controller_confirmed_and_unknown(self):
        jobs=[{'declaration':'orch:planner-codex','id':'test-id','enabled':True,'started_at':None,'next_run_at':None}]
        store=u.Store(orch.DB_PATH); lane.save(store,jobs)
        class Controller:
            def read(self): return [dict(j) for j in jobs]
            def set(self,jid,enabled): jobs[0]['enabled']=enabled
        result=orch.lane_control('orch:planner-codex',False,1,'producer',Controller())
        self.assertEqual(result['outcome'],'confirmed'); self.assertFalse(result['enabled'])
        with self.assertRaises(steering.Conflict): orch.lane_control('orch:planner-codex',True,1,'producer',Controller())
        class Failed(Controller):
            def set(self,jid,enabled): raise u.CollectorError('timeout')
        with self.assertRaises(u.CollectorError): orch.lane_control('orch:planner-codex',True,2,'producer',Failed())
        with store.connect() as con: self.assertFalse(lane.read(con,u.utc(store.clock()))['jobs'][0]['enabled'])
if __name__=='__main__': unittest.main()
