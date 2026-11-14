import datetime as dt
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import overview as o
import utilization as u
class EstimateTests(unittest.TestCase):
    def setUp(self): self.now=u.utc('2026-11-14T01:00Z')
    def test_pairing_legacy_sparse_and_overdue(self):
        events=[]
        for n in range(3):
            for status,minutes in [('doing',20+n*20),('done',10+n*20)]:
                events.append({'id':len(events),'ts':u.stamp(self.now-dt.timedelta(minutes=minutes)),'actor':'planner-codex','initiative_id':n,'kind':'subtask','message':'1 -> '+status+': ok'})
        samples=o.durations(events,self.now)
        self.assertEqual(len(samples),3)
        self.assertEqual(o.typical(samples,'codex','build')['seconds'],600)
        result=o.estimate(samples,'codex','build',u.stamp(self.now-dt.timedelta(minutes=11)),self.now)
        self.assertEqual(result['state'],'over_typical'); self.assertIsNone(result['completion_at'])
        self.assertEqual(o.estimate(samples[:2],'codex','build',u.stamp(self.now),self.now)['basis'],'default_prior')
    def test_gates_and_ambiguity_not_runtime(self):
        events=[{'id':n,'ts':u.stamp(self.now-dt.timedelta(minutes=10-n)),'actor':'planner-codex','initiative_id':1,'kind':'subtask','message':'1 -> '+status+': '} for n,status in enumerate(['doing','doing','done'])]
        self.assertEqual(o.durations(events,self.now),[])
        for e in events: e['kind']='stage:lld_review'
        self.assertEqual(o.durations(events,self.now),[])
    def test_attempt_pairing_actor_and_invalid_interval(self):
        events=[]
        for actor,status,offset,attempt in [('planner-codex','doing',20,'a'),('architect-claude','done',10,'a'),('planner-codex','done',5,'b'),('planner-codex','done',0,'a')]:
            events.append({'id':len(events),'ts':u.stamp(self.now-dt.timedelta(minutes=offset)),'actor':actor,'initiative_id':1,'kind':'subtask','details_json':json.dumps({'subtask_id':1,'to':status,'attempt':attempt})})
        self.assertEqual(len(o.durations(events,self.now)),1)
    def test_quota_pace_resets_and_manual_snapshots(self):
        metric={'status':'ok','value':50,'meta':{'resets_at':u.stamp(self.now+dt.timedelta(hours=2.5)),'manual':True}}
        pace=o.pace(metric,'5h',self.now)
        self.assertEqual(pace['target_used'],50); self.assertEqual(pace['pace'],'on pace'); self.assertTrue(pace['estimated'])
        self.assertEqual(o.pace({**metric,'status':'stale'},'5h',self.now)['pace'],'unavailable')
        self.assertEqual(o.pace(metric,'5h',self.now+dt.timedelta(hours=3))['pace'],'unavailable')
if __name__=='__main__': unittest.main()
