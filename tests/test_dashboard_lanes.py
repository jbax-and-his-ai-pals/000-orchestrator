import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import lane_status as lane
import utilization as u

# Sanitized installed schema, 2026-11-13; no prompts or raw configuration.
FIXTURE={'jobs':[{'id':'e9133424-6094-4b91-b79f-605052a7c74f','declarationKey':'orch:planner-codex','enabled':False,'state':{'runningAtMs':1794618000000,'nextRunAtMs':1794628800000}}],'hasMore':False,'nextOffset':None}
class LaneTests(unittest.TestCase):
    def test_sanitization_and_disabled_running(self):
        fixture=json.loads(json.dumps(FIXTURE)); fixture['jobs'][0]['payload']={'secret':'never keep'}
        jobs=lane.parse_cron(json.dumps(fixture))
        self.assertNotIn('secret',json.dumps(jobs))
        now=u.utc('2026-11-14T01:10Z')
        lanes=lane.lanes({'status':'ok','jobs':jobs,'generation':1,'observed_at':u.stamp(now)},now)
        codex=next(x for x in lanes if x['key']=='codex')
        self.assertEqual(codex['activity']['state'],'working'); self.assertEqual(codex['scheduler']['state'],'paused')
        self.assertEqual(lanes[-1]['reason'],'job_absent')
    def test_duplicate_and_incomplete(self):
        fixture=json.loads(json.dumps(FIXTURE)); fixture['jobs']*=2
        with self.assertRaises(ValueError): lane.parse_cron(json.dumps(fixture))
        with self.assertRaises(ValueError): lane.parse_cron('{"jobs":[],"hasMore":true}')
        with self.assertRaises(ValueError): lane.parse_cron('[]')
    def test_cache_failure_stale_and_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            now=u.utc('2026-11-14T01:10Z'); store=u.Store(Path(temp)/'db',lambda:now)
            store.initialize(); lane.save(store,lane.parse_cron(json.dumps(FIXTURE)))
            with store.connect() as con: self.assertEqual(lane.read(con,now)['status'],'ok')
            lane.save(store,error='timeout')
            with store.connect() as con:
                observation=lane.read(con,now)
                self.assertEqual(observation['generation'],2); self.assertEqual(len(observation['jobs']),1)
                self.assertEqual(lane.lanes(observation,now)[1]['activity']['state'],'unknown')
            lane.save(store,[])
            lane.save(store,error='timeout',observed=now-u.dt.timedelta(seconds=60))
            with store.connect() as con: self.assertEqual(lane.read(con,now)['status'],'ok')
            with store.connect() as con: self.assertEqual(lane.read(con,now+u.dt.timedelta(seconds=91))['status'],'stale')
    def test_shared_cron_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            now=[u.utc('2026-11-14T01:10Z')]; store=u.Store(Path(temp)/'db',lambda:now[0]); store.initialize()
            with store.connect() as con: con.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
            calls=[]; collectors={'cron':lambda: calls.append(1) or []}
            a=u.Sampler(store,collectors,lambda:0); b=u.Sampler(store,collectors,lambda:0)
            a.tick(); b.tick(); self.assertEqual(len(calls),1)
            now[0]+=u.dt.timedelta(seconds=121); b.next_tick=0; b.tick()
            self.assertEqual(len(calls),2); self.assertFalse(a.claim(release=True))
            b.claim(release=True); a.next_tick=0; a.tick(); self.assertEqual(len(calls),2)
if __name__=='__main__': unittest.main()
