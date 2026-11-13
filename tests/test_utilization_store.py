import contextlib
import datetime as dt
import importlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import utilization as u

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.db'
        self.now = u.utc('2026-11-13T22:00:00Z')
        self.store = u.Store(self.path, lambda: self.now)
        self.store.initialize()

    def count(self):
        with self.store.connect() as c:
            return c.execute('SELECT count(*) FROM metrics').fetchone()[0]

    def test_additive_schema_and_old_select(self):
        with patch.dict(os.environ, {'ORCH_HOME': self.tmp.name, 'ORCH_ROOT': self.tmp.name}):
            import orch
            orch = importlib.reload(orch)
        legacy = orch.SCHEMA.split('CREATE TABLE IF NOT EXISTS metrics')[0]
        with self.store.connect() as c:
            c.executescript(legacy)
            c.execute("INSERT INTO settings VALUES ('old','keep')")
            c.executescript(orch.SCHEMA)
            c.executescript(orch.SCHEMA)
            self.assertEqual(c.execute('SELECT * FROM settings').fetchone()['value'], 'keep')
            self.assertEqual(len(c.execute('SELECT id,ts,actor,kind FROM events').fetchall()), 0)
            self.assertEqual(len(c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_metrics%'").fetchall()), 2)

    def test_snapshot(self):
        result = self.store.quota_snapshot('anthropic', ['5h','weekly'], [23,40],
                                          ['2026-11-13T22:00:00-08:00']*2)
        self.assertEqual(self.count(), 2)
        self.assertEqual(result['windows']['5h']['remaining_pct'], 77)
        self.assertEqual(result['windows']['weekly']['resets_at'], '2026-11-14T06:00:00+00:00')

    def test_invalid_batch_is_atomic(self):
        for windows, used, resets in [(['5h','weekly'],[10,'NaN'],['2026-11-14T00:00Z']*2),
                                     (['5h','5h'],[1,2],['2026-11-14T00:00Z']*2),
                                     (['5h'],[1,2],['2026-11-14T00:00Z']),
                                     (['5h'],[101],['2026-11-14T00:00Z']),
                                     (['5h'],[10],['2026-11-14T00:00']),
                                     (['weekly'],[float('inf')],['bad'])]:
            with self.subTest(used=used), self.assertRaises(ValueError):
                self.store.quota_snapshot('anthropic', windows, used, resets)
            self.assertEqual(self.count(), 0)

    def test_validation_and_metadata(self):
        with self.assertRaises(ValueError):
            self.store.insert('gpu', [{'key':'util_pct','value':float('nan')}])
        self.store.insert('gpu', [{'key':'util_pct','value':None,'meta':{'raw':'secret','reason':'bad'}}])
        with self.store.connect() as c:
            row = c.execute('SELECT * FROM metrics').fetchone()
            self.assertIsNone(row['value'])
            self.assertEqual(json.loads(row['meta']), {'reason':'unavailable'})

    def test_retention_bound_and_contention(self):
        cutoff = self.now - dt.timedelta(days=14)
        self.store.insert('gpu',[{'key':'util_pct','value':1}],cutoff)
        with self.store.connect() as c:
            c.execute('CREATE TABLE unrelated (value TEXT)')
            c.execute("INSERT INTO unrelated VALUES ('keep')")
            c.executemany('INSERT INTO metrics VALUES (?,?,?,?,?)',
                          [(u.stamp(cutoff-dt.timedelta(seconds=1)), 'gpu','util_pct',1,'{}')]*5001)
        self.assertEqual(self.store.prune(), 5000)
        self.assertEqual(self.store.prune(), 1)
        self.assertEqual(self.count(), 1)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT value FROM unrelated').fetchone()[0], 'keep')
            c.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):
                self.store.insert('gpu',[{'key':'util_pct','value':1}])

    def test_cli_does_not_init_export_or_log(self):
        with patch.dict(os.environ, {'ORCH_HOME': self.tmp.name,'ORCH_ROOT':self.tmp.name}):
            import orch
            orch = importlib.reload(orch)
        with patch.object(orch,'DB_PATH', self.path), patch.object(orch,'init_all', side_effect=AssertionError), \
             patch.object(orch,'export_json', side_effect=AssertionError), patch.object(orch,'log_event', side_effect=AssertionError):
            args=['quota-snapshot','--provider','anthropic','--window','5h','--used-pct','23','--resets-at','2026-11-14T00:00Z']
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(orch.main(args),0)
            self.assertEqual(json.loads(out.getvalue())['windows']['5h']['remaining_pct'],77)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(orch.main(args+['--window','weekly']),1)
            self.assertEqual(self.count(),1)

if __name__ == '__main__':
    unittest.main()
