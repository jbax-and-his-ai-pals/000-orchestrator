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
