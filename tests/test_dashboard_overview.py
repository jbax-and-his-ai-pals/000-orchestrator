import json
import unittest
from unittest.mock import patch
from test_dashboard_steering import SteeringTests
import overview
import utilization as u

class OverviewTests(SteeringTests):
    def test_complete_inventory_no_processes(self):
        now=u.utc(orch_now())
        with patch.object(u,'command_output',side_effect=AssertionError('GET probed')):
            report=overview.snapshot(__import__('orch'),lambda:now)
        self.assertEqual(report['totals']['initiatives'],3)
        self.assertEqual(len(report['pending']['queued']),3)
        self.assertEqual(len(report['pending']['blocked']),3)
        self.assertEqual(len(report['in_flight']),3)
        self.assertTrue(all(x['age_basis']=='creation_fallback' for x in report['in_flight']))
        self.assertEqual(report['lanes'][1]['activity']['state'],'unknown')
        self.assertIsNone(report['next_update'].get('completion_at'))
    def test_unique_execution_start_correlates_running_task(self):
        import orch
        import lane_status
        orch.subtask_update(1,1,'doing','','planner-codex')
        now=u.utc(orch.now())
        jobs=[{'declaration':'orch:planner-codex','id':'job-id','enabled':False,'started_at':u.stamp(now-u.dt.timedelta(seconds=60)),'next_run_at':None}]
        lane_status.save(u.Store(orch.DB_PATH),jobs,observed=now)
        report=overview.snapshot(orch,lambda:now)
        codex=next(l for l in report['lanes'] if l['key']=='codex')
        self.assertIn('#1 sub 1',codex['activity']['task_ref'])
        self.assertEqual(codex['scheduler']['state'],'paused')
        self.assertEqual(report['confirmed_active'],[1])
        # An older doing flag cannot identify this newer cron run.
        jobs[0]['started_at']=u.stamp(now+u.dt.timedelta(seconds=1))
        lane_status.save(u.Store(orch.DB_PATH),jobs,observed=now)
        report=overview.snapshot(orch,lambda:now)
        self.assertEqual(report['confirmed_active'],[])

    def test_claims_and_waiting_producer(self):
        import orch
        orch.claim(1,'chat-a'); orch.claim(2,'chat-b')
        with orch.db(write=True) as con: con.execute("UPDATE initiatives SET stage='lld_review' WHERE id=3")
        report=overview.snapshot(orch)
        self.assertEqual(len(report['lanes'][-1]['claims']),2)
        self.assertEqual(len(report['pending']['producer']),1)
        self.assertTrue(any(x['reason']=='LLD + plan to review' for x in report['attention']))
        self.assertTrue(all(x['eligibility']!='eligible' for x in report['pending']['blocked']))

def orch_now():
    import orch
    return orch.now()
if __name__=='__main__': unittest.main()
