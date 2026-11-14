import asyncio
import json
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from test_dashboard_steering import SteeringTests
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
import app
import forecast
import lane_status
import orch
import overview
import utilization as u

async def get(url):
    parsed=urlsplit(url);sent=[]
    async def receive():
        return {'type':'http.request','body':b'','more_body':False}
    async def send(message):sent.append(message)
    scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1','method':'GET','scheme':'http','path':parsed.path,'raw_path':parsed.path.encode(),'query_string':parsed.query.encode(),'headers':[],'server':('test',80),'client':('test',1),'root_path':''}
    await app.app(scope,receive,send)
    return next(m['status'] for m in sent if m['type']=='http.response.start'),json.loads(b''.join(m.get('body',b'') for m in sent if m['type']=='http.response.body'))

class RevisionIntegrationTests(SteeringTests):
    def schedule(self):
        now=u.utc(orch.now())
        lane_status.save(u.Store(orch.DB_PATH),[dict(declaration='orch:planner-codex',id='test-job',enabled=True,started_at=None,next_run_at=u.stamp(now+u.dt.timedelta(minutes=1)),schedule={'kind':'every','everyMs':1800000})],observed=now)
        return now
    def test_http_forecast_filtered_overview_and_priority_preview(self):
        now=self.schedule()
        with orch.db() as con:
            cards=[dict(r) for r in con.execute('SELECT * FROM initiatives')]
            events=con.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        with patch.object(u,'command_output',side_effect=AssertionError('GET tool probe')):
            status,report=asyncio.run(get('/api/overview?project=a'))
            self.assertEqual(status,200)
            self.assertEqual([r['project'] for r in report['rollups']['projects']],['a'])
            self.assertTrue(report['forecast']['timeline'])
            self.assertTrue(all('estimate' in r for r in report['in_flight']))
            status,preview=asyncio.run(get('/api/forecast/what-if?kind=initiative&target=2'))
            self.assertEqual(status,200);self.assertTrue(preview['read_only'])
            self.assertEqual(asyncio.run(get('/api/forecast/what-if?kind=initiative&target=999'))[0],404)
            self.assertEqual(asyncio.run(get('/api/forecast/what-if?kind=invalid&target=2'))[0],422)
        with orch.db() as con:
            self.assertEqual([dict(r) for r in con.execute('SELECT * FROM initiatives')],cards)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM events').fetchone()[0],events)
    def test_paused_lane_and_conditional_gate_never_advance(self):
        self.schedule()
        with orch.db(write=True) as con:con.execute("UPDATE initiatives SET stage='lld_review' WHERE id=1")
        result=overview.snapshot(orch)
        eta=result['forecast']['initiatives']['1']
        self.assertEqual(eta['state'],'waiting')
        self.assertIn('if_approved_now',eta)
        with orch.db() as con:self.assertEqual(con.execute('SELECT stage FROM initiatives WHERE id=1').fetchone()[0],'lld_review')
    def test_project_what_if_changes_only_priority_order(self):
        self.schedule()
        with orch.db(write=True) as con:
            con.execute("INSERT INTO projects(repo_name,local_path) VALUES ('b','test')")
            con.execute("UPDATE initiatives SET project_name='b' WHERE id=3")
        report=overview.snapshot(orch,bump=('project','b'))
        self.assertTrue(report['what_if']['read_only'])
        self.assertLess(report['what_if']['if_prioritized']['completion_at'],report['what_if']['eta_now']['completion_at'])
        self.assertTrue(report['what_if']['delayed'])
    def test_repeated_reads_cache_and_keep_history(self):
        now=self.schedule()
        first=overview.snapshot(orch,lambda:now)
        second=overview.snapshot(orch,lambda:now)
        self.assertEqual(first['forecast'],second['forecast'])
        self.assertTrue(first['forecast']['timeline'])
        for row in first['in_flight']:
            self.assertIn('basis_label',row['estimate'])
            self.assertNotIn('unknown',row['estimate']['state'])
if __name__=='__main__':unittest.main()
