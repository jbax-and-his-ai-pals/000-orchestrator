import asyncio
import datetime as dt
import importlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import utilization as u

class SamplerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.wall=u.utc('2026-11-13T22:00Z'); self.mono=0
        self.store=u.Store(Path(self.tmp.name)/'test.db',lambda:self.wall)
        self.store.initialize()
        with self.store.connect() as c: c.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.calls=[]
        self.collectors={s:lambda s=s:self.collect(s) for s in ('gpu','ollama','openai')}

    def collect(self,source):
        self.calls.append((source,self.wall))
        # A separate immediate transaction proves no DB transaction spans collection.
        with self.store.connect() as c: c.execute('BEGIN IMMEDIATE')
        return [{'key':u.KEYS[source][0],'value':1}]

    def sampler(self): return u.Sampler(self.store,self.collectors,lambda:self.mono)
    def advance(self,seconds):
        self.wall+=dt.timedelta(seconds=seconds); self.mono+=seconds

    def test_two_owners_restart_and_takeover_frequency(self):
        a=self.sampler(); b=self.sampler()
        a.tick(); b.tick()
        self.assertEqual(len(self.calls),3)
        self.advance(121); b.tick() # expired lease, but OpenAI not due
        self.assertEqual(len([c for c in self.calls if c[0]=='openai']),1)
        b.claim(release=True)
        c=self.sampler(); c.tick()
        self.assertEqual(len([c for c in self.calls if c[0]=='openai']),1)
        self.advance(479); c.tick()
        times=[v for s,v in self.calls if s=='openai']
        self.assertEqual((times[1]-times[0]).total_seconds(),600)

    def test_failure_isolation_and_persisted_failed_attempt(self):
        def fail(): raise TimeoutError()
        self.collectors['openai']=fail
        a=self.sampler(); a.tick()
        with self.store.connect() as c:
            row=c.execute("SELECT * FROM metrics WHERE source='openai'").fetchone()
            self.assertEqual(row['key'],'error'); self.assertIn('timeout',row['meta'])
        a.claim(release=True); self.collectors['openai']=lambda:self.collect('openai')
        self.advance(60); self.sampler().tick()
        self.assertFalse(any(s=='openai' for s,t in self.calls))
        self.assertEqual(len([s for s,t in self.calls if s=='gpu']),2)

    def test_lock_contention_and_stop_thread(self):
        a=self.sampler()
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE'); a.tick()
        self.assertEqual(self.calls,[])
        self.advance(10)
        a.start(); a.stop()
        self.assertFalse(a.thread.is_alive())

    def test_lifespans_only_start_when_entered(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
        with patch.dict(os.environ,{'ORCH_HOME':self.tmp.name,'ORCH_ROOT':self.tmp.name}):
            import orch
            importlib.reload(orch)
            with patch.object(orch,'init_all',side_effect=AssertionError('import init')):
                import app
                importlib.reload(app)
        app.app.state.sampler_factory=lambda store:self.sampler()
        async def run():
            with patch.object(orch,'init_all'),patch.object(orch,'DB_PATH',Path(self.store.path)):
                async with app.lifespan(app.app):
                    async with app.lifespan(app.app):
                        pass
        asyncio.run(run())
        self.assertLessEqual(len([s for s,t in self.calls if s=='openai']),1)
        app.app.state.sampler_factory=None

if __name__=='__main__': unittest.main()
