import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import orch

HEADINGS = "\n\n".join(h + "\nsomething" for h in orch.GEMMA["dossier_headings"] if h != "## Snapshot")
DEEP = ("# a dossier\n\n_Author: planner-codex · deep dossier 2026-11-13_\n\n## Snapshot\n- **Stack:** Godot\n"
        "- **What it is:** A procedural city generator, not yet a game.\n\n" + HEADINGS)


class IssueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(orch, k, v) for k, v in {
            'STATE': root, 'DB_PATH': root / 'db.sqlite', 'JSON_PATH': root / 'state.json', 'TASTE': root / 'taste.md',
            'DESIGNS': root / 'designs', 'DOSSIERS': root / 'dossiers'}.items()]
        for p in self.patches:
            p.start()
        orch.init_db()
        with orch.db(write=True) as con:
            con.execute("INSERT INTO projects(repo_name,local_path,is_git) VALUES ('a',?,0)", (str(root),))

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def dossier(self, bottleneck):
        orch.write_dossier('a', DEEP, 'planner-codex', {'bottleneck_summary': bottleneck})

    def test_description_from_dossier(self):
        self.dossier('No tests.')
        with orch.db() as con:
            self.assertEqual(orch.get_project(con, 'a')['description'], 'A procedural city generator, not yet a game.')

    def test_one_live_issue_per_project(self):
        self.dossier('No tests.')
        self.dossier('No tests.')
        self.assertEqual(len(orch.list_issues()), 1)
        self.dossier('No geometry validation.')  # still in triage: updated in place
        issues = orch.list_issues()
        self.assertEqual([i['title'] for i in issues], ['No geometry validation.'])
        orch.write_dossier('a', DEEP, 'planner-codex', {})  # no bottleneck flag: issue untouched
        self.assertEqual(orch.list_issues()[0]['status'], 'triage')

    def test_loop_to_proposal_and_reopen_on_reject(self):
        self.dossier('No tests.')
        iid = orch.list_issues()[0]['id']
        with orch.db() as con:
            self.assertEqual(orch.issues_to_solve(con, None, orch.now()), [])  # autosolve off by default
        orch.set_issues_autosolve(True, 'producer')
        self.assertEqual([i['id'] for i in orch.queue('planner')['issues_to_solve']], [iid])
        orch.issue_claim(iid, 'planner-codex')
        self.assertEqual(orch.queue('architect')['issues_to_solve'], [])  # claimed: hidden from others
        with self.assertRaises(orch.OrchError):
            orch.issue_claim(iid, 'architect-claude')
        out = orch.issue_propose(iid, 'tech_audacity', 'Add seed geometry tests', 'Run 3 seeds, assert.', 'planner-codex')
        self.assertEqual(out['issue']['status'], 'proposed')
        self.assertEqual(out['spark']['project_name'], 'a')
        self.dossier('Different blocker now.')  # proposed: a new issue opens for the new blocker
        self.assertEqual(len(orch.list_issues()), 2)
        orch.reject(out['spark']['id'], 'Too narrow; fix the road graph instead.')
        reopened = [i for i in orch.list_issues() if i['id'] == iid][0]
        self.assertEqual(reopened['status'], 'triage')
        self.assertIn('road graph', reopened['note'])

    def test_low_priority_issues_are_parked(self):
        self.dossier('No tests.')
        orch.set_issues_autosolve(True, 'producer')
        orch.update_project('a', {'priority': 'low'}, 'producer')
        self.assertEqual(orch.queue('planner')['issues_to_solve'], [])
        orch.update_project('a', {'priority': 'medium'}, 'producer')
        self.assertEqual(len(orch.queue('planner')['issues_to_solve']), 1)

    def test_forecast_sees_issue_work(self):
        import forecast
        issue = {'id': 7, 'project_name': 'a', 'title': 'No tests.', 'status': 'triage', 'attempts': 0, 'note': None}
        q = orch.queue_from_snapshot('planner', [], [], None, orch.now(), issues=[issue])
        self.assertEqual(forecast.pick(q), ('issue', issue))
        self.assertEqual(orch.queue_from_snapshot('architect-high', [], [], None, orch.now(), issues=[issue])['issues_to_solve'], [])
        self.assertIsNone(forecast.pick(orch.queue_from_snapshot('planner', [], [], None, orch.now())))

    def test_attempt_cap_sends_to_producer(self):
        self.dossier('No tests.')
        iid = orch.list_issues()[0]['id']
        for n in range(orch.ISSUE_MAX_ATTEMPTS):
            orch.issue_claim(iid, 'planner-codex')
            out = orch.issue_release(iid, f'attempt {n} found nothing', 'planner-codex')
        self.assertEqual(out['status'], 'needs_producer')

    def test_backfill(self):
        orch.update_project('a', {'bottleneck_summary': 'Old blocker.'}, 'producer')
        (orch.DOSSIERS / 'a').mkdir(parents=True)
        (orch.DOSSIERS / 'a' / 'DOSSIER.md').write_text(DEEP, encoding='utf-8')
        self.assertEqual(orch.backfill_issues('claude-desktop'), {'issues_opened': 1, 'descriptions_set': 1})
        self.assertEqual(orch.backfill_issues('claude-desktop'), {'issues_opened': 0, 'descriptions_set': 0})


if __name__ == '__main__':
    unittest.main()
