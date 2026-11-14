import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import orch

HEADINGS = "\n\n".join(h + "\nsomething" for h in orch.GEMMA["dossier_headings"] if h != "## Player experience")
GEMMA_TEXT = "# a dossier\n\n_Scout: scout-gemma_\n\n## Player experience\nunknown\n\n" + HEADINGS
DEEP_TEXT = ("# a dossier\n\n_Author: planner-codex · deep dossier 2026-11-13 · ran: godot --headless_\n\n"
             "## Player experience\nYou steer a scrap robot into a furnace.\n\n" + HEADINGS)


class DossierGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(orch, k, v) for k, v in {
            'STATE': root, 'DB_PATH': root / 'db.sqlite', 'JSON_PATH': root / 'state.json',
            'DESIGNS': root / 'designs', 'DOSSIERS': root / 'dossiers'}.items()]
        for p in self.patches:
            p.start()
        orch.init_db()
        with orch.db(write=True) as con:
            con.execute("INSERT INTO projects(repo_name,local_path) VALUES ('a',?)", (str(root),))
        self.dossier = root / 'dossiers' / 'a' / 'DOSSIER.md'

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def project(self):
        with orch.db() as con:
            return orch.get_project(con, 'a')

    def test_frontier_dossier_sets_player_experience(self):
        orch.write_dossier('a', DEEP_TEXT, 'planner-codex', {'playability_score': 6})
        p = self.project()
        self.assertEqual(p['player_experience'], 'You steer a scrap robot into a furnace.')
        self.assertEqual(p['playability_score'], 6)

    def test_gemma_cannot_flatten_frontier_dossier(self):
        orch.write_dossier('a', DEEP_TEXT, 'planner-codex', {'playability_score': 6})
        out = orch.write_dossier('a', GEMMA_TEXT, 'scout-gemma', {'playability_score': 3})
        self.assertEqual(out.name, 'DOSSIER.gemma.md')
        self.assertIn('_Author: planner-codex', self.dossier.read_text(encoding='utf-8'))
        self.assertEqual(self.project()['playability_score'], 6)

    def test_gemma_still_owns_gemma_dossiers(self):
        orch.write_dossier('a', GEMMA_TEXT, 'scout-gemma')
        out = orch.write_dossier('a', GEMMA_TEXT.replace('something', 'fresh'), 'scout-gemma')
        self.assertEqual(out.name, 'DOSSIER.md')
        self.assertIn('fresh', self.dossier.read_text(encoding='utf-8'))

    def test_gemma_fallback_refreshes_facts_only_for_frontier_dossiers(self):
        self.assertEqual(orch.scout_job('a'), 'scan')
        orch.write_dossier('a', DEEP_TEXT, 'planner-codex')
        self.assertEqual(orch.scout_job('a'), 'facts')
        with orch.db(write=True) as con:
            con.execute("UPDATE projects SET last_scanned_at=NULL")
        self.assertEqual(orch.queue('scout')['job'], 'facts')


class DispatchTests(unittest.TestCase):
    def test_open_runs_only(self):
        import datetime as dt, json
        import overview
        now = dt.datetime(2026, 11, 13, 21, 0, tzinfo=dt.timezone.utc)
        ts = lambda m: (now - dt.timedelta(minutes=m)).isoformat()
        ev = lambda kind, run, m, lane='codex': {'kind': kind, 'ts': ts(m), 'project_name': 'p',
                                                 'details_json': json.dumps({'lane': lane, 'run': run, 'label': 'seed ' + run})}
        events = [ev('dispatch_end', 'a', 1), ev('dispatch_start', 'a', 5), ev('dispatch_start', 'b', 4),
                  ev('dispatch_start', 'c', 3, 'claude'), ev('dispatch_start', 'old', 60 * 13)]
        runs = overview.dispatches(events, 'codex', now)
        self.assertEqual([r['run'] for r in runs], ['b'])
        self.assertEqual(runs[0]['label'], 'seed b')


if __name__ == '__main__':
    unittest.main()
