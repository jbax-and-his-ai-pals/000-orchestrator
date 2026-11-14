import asyncio
import json
import unittest
from unittest.mock import patch
import test_dashboard_steering as base
from test_dashboard_api import request
import orch
import task_policy as policy
import steering
import utilization as u
import overview
import lane_status
import datetime as dt


class ModelTaskTests(unittest.TestCase):
    setUp = base.SteeringTests.setUp
    tearDown = base.SteeringTests.tearDown

    def tasks(self, declaration='orch:planner-codex'):
        with orch.db() as con:
            return policy.read(con)[declaration]

    def change(self, changes, declaration='orch:planner-codex'):
        return orch.model_tasks(declaration, changes, policy.version(self.tasks(declaration)), 'codex-cli')

    def test_permissions_persist_conflicts_and_do_not_enable_schedules(self):
        before = policy.version(self.tasks())
        with patch.object(u, 'command_output', side_effect=AssertionError('task setting changed a schedule')):
            self.change({'coding': False})
        self.assertFalse(self.tasks()['coding'])
        with self.assertRaises(steering.Conflict):
            orch.model_tasks('orch:planner-codex', {'coding': True}, before, 'producer')
        with self.assertRaises(orch.OrchError):
            self.change({'passive': True})
        with self.assertRaises(orch.OrchError):
            orch.model_tasks('orch:planner-codex', {'coding': True}, policy.version(self.tasks()), 'planner-codex')

    def test_disabled_coding_is_filtered_and_cannot_start_but_chat_can(self):
        self.change({'coding': False})
        self.assertEqual(orch.queue('planner')['subtasks'], [])
        with self.assertRaises(orch.OrchError):
            orch.subtask_update(1, 1, 'doing', '', 'planner-codex')
        orch.subtask_update(1, 1, 'doing', '', 'codex-cli')
        # Existing work can record completion even after the permission is disabled.
        orch.subtask_update(1, 1, 'done', '', 'planner-codex')

    def test_passive_gemma_skips_code_without_starving_scans(self):
        with orch.db(write=True) as con:
            plan = {'subtasks': [{'id': 1, 'title': 'small chore', 'status': 'todo', 'assignee': 'gemma',
                    'files': ['one.txt'], 'instructions': 'Change the literal.', 'acceptance': 'Literal changed.',
                    'verify': 'true', 'mechanical': True}]}
            con.execute('UPDATE initiatives SET execution_plan_json=? WHERE id=1', (json.dumps(plan),))
        self.assertIn(orch.queue('scout')['job'], ('scan', 'facts'))
        self.assertEqual(orch.queue('scout')['project'], 'a')
        self.change({'coding': True}, 'orch:scout-gemma')
        self.assertEqual(orch.queue('scout')['job'], 'subtask')
        self.change({'coding': False, 'passive': False}, 'orch:scout-gemma')
        self.assertIsNone(orch.queue('scout')['project'])

    def test_planning_ideas_issues_and_reviews_independent(self):
        self.change({'planning': False, 'ideas': False, 'issues': False, 'review': False})
        with orch.db(write=True) as con:
            con.execute("UPDATE initiatives SET stage='lld_draft' WHERE id=1")
        self.assertEqual(orch.queue('planner')['lld_to_draft'], [])
        self.assertEqual(len(orch.queue('planner')['subtasks']), 2)
        with self.assertRaises(orch.OrchError):
            orch.attach(1, 'lld', 'design', 'planner-codex')
        with self.assertRaises(orch.OrchError):
            orch.add_spark('a', 'optimization', 'Unwanted idea', 'Evidence', 'planner-codex')
        with self.assertRaises(orch.OrchError):
            orch.issue_claim(999, 'planner-codex')
        with self.assertRaises(orch.OrchError):
            orch.review_build(2, 'pass', 'okay', 'planner-codex')

    def test_opus_planning_independent_from_sonnet(self):
        self.change({'planning': False}, 'orch:architect-claude-opus')
        with orch.db(write=True) as con:
            con.execute("UPDATE initiatives SET stage='hld_draft',complexity='high' WHERE id=1")
            con.execute("UPDATE initiatives SET stage='hld_draft',complexity='standard' WHERE id=2")
        self.assertEqual(orch.queue('architect-high')['hld_to_draft'], [])
        self.assertEqual([i['id'] for i in orch.queue('architect')['hld_to_draft']], [2])
        with self.assertRaises(orch.OrchError):
            orch.attach(1, 'hld', 'design', 'architect-claude')

    def test_api_read_only_and_strict_write_validation(self):
        with patch.object(u, 'command_output', side_effect=AssertionError('GET probed scheduler')):
            status, report = asyncio.run(request('/api/models'))
        self.assertEqual(status, 200)
        self.assertEqual(len(report['models']), 5)
        gemma = report['models'][0]
        self.assertTrue(gemma['tasks']['passive'])
        self.assertFalse(gemma['tasks']['coding'])
        path = '/api/models/orch:scout-gemma/tasks'
        body = {'expected_version': gemma['version'], 'tasks': {'coding': True}}
        self.assertEqual(asyncio.run(request(path, 'POST', body, header=False))[0], 403)
        self.assertEqual(asyncio.run(request(path, 'POST', {**body, 'tasks': {'coding': 'false'}}))[0], 422)
        self.assertEqual(asyncio.run(request(path, 'POST', body))[0], 200)
        self.assertEqual(asyncio.run(request(path, 'POST', body))[0], 409)

    def test_forecast_uses_same_permissions(self):
        now = u.utc(orch.now())
        lane_status.save(u.Store(orch.DB_PATH), [{'declaration': 'orch:planner-codex', 'id': 'codex-test',
            'enabled': True, 'started_at': None, 'next_run_at': u.stamp(now + dt.timedelta(minutes=1)),
            'schedule': {'kind': 'every', 'everyMs': 1800000}}])
        self.assertTrue(any(e['work_type'] == 'build' for e in overview.snapshot(orch)['forecast']['timeline']))
        self.change({'coding': False})
        with patch.object(u, 'command_output', side_effect=AssertionError('read probed')):
            report = overview.snapshot(orch)
        self.assertFalse(any(e['work_type'] == 'build' for e in report['forecast']['timeline']))


if __name__ == '__main__':
    unittest.main()

