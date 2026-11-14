import asyncio
import copy
import json
import unittest
from unittest.mock import patch
from test_dashboard_api import request
from test_dashboard_steering import SteeringTests
import orch
import overview as o
import utilization as u

class RollupTests(SteeringTests):
    def test_rollups_are_deduplicated_and_filter_before_paging(self):
        report=o.snapshot(orch)
        totals=report['rollups']['totals']
        self.assertEqual(totals['open_initiatives'],3)
        self.assertEqual(totals['subtasks_total'],6)
        self.assertEqual(totals['queued_subtasks'],6)
        self.assertEqual(totals['in_flight'],3)
        selected=report['projects'][0]['repo_name']
        page=o.paged(report,project=selected,limit=1)
        self.assertEqual(len(page['rollups']['projects']),1)
        self.assertEqual(page['rollups']['totals']['project'],selected)
        self.assertTrue(all(r['estimate'] for r in page['in_flight']))
        self.assertTrue(all(r['progress']['total']==2 for r in page['in_flight']))
    def test_owners_and_waiting(self):
        with orch.db(write=True) as con:
            con.execute("UPDATE initiatives SET stage='lld_review' WHERE id=1")
            con.execute("UPDATE initiatives SET stage='spark' WHERE id=2")
        report=o.snapshot(orch)
        waiting={r['initiative_id']:r for r in report['pending']['producer']}
        self.assertEqual(waiting[1]['owner'],'producer')
        self.assertEqual(report['pending']['sparks'][0]['owner'],'claude')
        self.assertEqual(report['rollups']['totals']['waiting_on_producer'],2)
    def test_what_if_get_never_writes(self):
        with orch.db() as con: before=[dict(r) for r in con.execute('SELECT * FROM initiatives')]; events=con.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        with patch.object(u,'command_output',side_effect=AssertionError('GET spawned tool')):
            result=o.snapshot(orch,bump=('initiative','2'))
        self.assertTrue(result['what_if']['read_only'])
        with orch.db() as con:
            self.assertEqual([dict(r) for r in con.execute('SELECT * FROM initiatives')],before)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM events').fetchone()[0],events)
    def test_pace_words_and_sixty_minute_staleness(self):
        now=u.utc('2026-11-14T02:00Z')
        metric={'status':'ok','value':90,'age_seconds':3599,'meta':{'resets_at':u.stamp(now+u.dt.timedelta(hours=2.5))}}
        self.assertEqual(o.pace(metric,'5h',now)['pace'],'under pace')
        self.assertEqual(o.pace({**metric,'value':10},'5h',now)['pace'],'over pace')
        stale=o.pace({**metric,'age_seconds':3601},'5h',now)
        self.assertEqual(stale['status'],'stale');self.assertEqual(stale['pace'],'unavailable')
    def test_real_schedule_forecast_in_snapshot(self):
        import lane_status
        now=u.utc(orch.now())
        jobs=[{'declaration':'orch:planner-codex','id':'test-id','enabled':True,'next_run_at':u.stamp(now+u.dt.timedelta(minutes=1)),'started_at':None}]
        lane_status.save(u.Store(orch.DB_PATH),jobs,observed=now)
        report=o.snapshot(orch,lambda:now)
        self.assertTrue(report['forecast']['timeline'])
        self.assertTrue(report['in_flight'][0]['estimate'].get('completion_at'))
        self.assertIn('default guess',report['in_flight'][0]['estimate']['basis_label'])
if __name__=='__main__': unittest.main()
