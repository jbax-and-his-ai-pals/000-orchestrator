import asyncio
import datetime as dt
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import utilization as u

async def request(app,path,query=b''):
    sent=[]
    first=True
    async def receive():
        nonlocal first
        if first:
            first=False
            return {'type':'http.request','body':b'','more_body':False}
        await asyncio.sleep(10)
        return {'type':'http.disconnect'}
    async def send(message): sent.append(message)
    scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'}, 'http_version':'1.1',
           'method':'GET','scheme':'http','path':path,'raw_path':path.encode(),
           'query_string':query,'headers':[],'server':('test',80),'client':('test',1),'root_path':''}
    await app(scope,receive,send)
    start=next(m for m in sent if m['type']=='http.response.start')
    body=b''.join(m.get('body',b'') for m in sent if m['type']=='http.response.body')
    return start,body

class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.now=u.utc('2026-11-13T22:04:00Z')
        self.store=u.Store(Path(self.tmp.name)/'test.db',lambda:self.now)
        self.store.initialize()
        with self.store.connect() as c:
            c.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, kind TEXT, message TEXT)')

    def test_empty_ranges_and_invalid(self):
        for selected in u.RANGES:
            report=u.utilization_report(self.store,selected)
            self.assertEqual(report['current']['gpu']['status'],'missing')
            self.assertEqual(report['current']['gemini']['status'],'parked')
            self.assertLessEqual(len(report['series']['gpu']['times']),336)
            self.assertTrue(all(v is None for v in report['series']['gpu']['util_pct']))
        with self.assertRaises(ValueError): u.utilization_report(self.store,'all')

    def test_last_good_failure_stale_and_windows(self):
        old=self.now-dt.timedelta(days=2)
        self.store.insert('gpu',[{'key':'util_pct','value':44}],old)
        report=u.utilization_report(self.store)
        self.assertEqual(report['current']['gpu']['status'],'stale')
        self.assertEqual(report['current']['gpu']['value'],44)
        self.assertFalse(any(v is not None for v in report['series']['gpu']['util_pct']))
        self.store.insert('gpu',[{'key':'error','value':1,'meta':{'reason':'missing_tool'}}])
        current=u.utilization_report(self.store)['current']['gpu']
        self.assertEqual(current['status'],'error'); self.assertEqual(current['value'],44)
        self.assertEqual(current['observed_at'],u.stamp(old))
        self.store.quota_snapshot('anthropic',['5h'],[23],[u.stamp(self.now-dt.timedelta(seconds=1))])
        current=u.utilization_report(self.store)['current']['anthropic']
        self.assertEqual(current['5h']['reason'],'reset_passed')
        self.assertEqual(current['weekly']['status'],'missing')

    def test_bucket_means_last_and_event_offsets(self):
        for n in (10,30):
            self.store.insert('gpu',[{'key':'util_pct','value':n}],self.now-dt.timedelta(seconds=n))
            self.store.insert('openai',[{'key':'remaining_pct.5h','value':n}],self.now-dt.timedelta(seconds=n))
        report=u.utilization_report(self.store)
        self.assertEqual(report['series']['gpu']['util_pct'][-1],20)
        self.assertEqual(report['series']['openai']['5h'][-1],10)
        with self.store.connect() as c:
            for actor,message in [('reviewer-gemini','HTTP 429 503'),('planner','429'),('other','503')]:
                c.execute('INSERT INTO events(ts,actor,kind,message) VALUES (?,?,?,?)',('2026-11-13T14:00:00-08:00',actor,'note',message))
        report=u.utilization_report(self.store)
        self.assertEqual(sum(report['series']['activity']['codex']),1)
        self.assertEqual(report['current']['gemini']['logged_actions'],1)
        self.assertEqual(report['current']['gemini']['logged_errors'],{'429':1,'503':1})

    def test_fixture_budgets_and_dot_bounds(self):
        start=self.now-dt.timedelta(days=14)
        with self.store.connect() as c:
            def fixture():
                for minute in range(14*24*60):
                    ts=u.stamp(start+dt.timedelta(minutes=minute))
                    for source,key in [('gpu',k) for k in u.KEYS['gpu']]+[('ollama','loaded_count')]:
                        yield ts,source,key,50,'{}'
            c.executemany('INSERT INTO metrics VALUES (?,?,?,?,?)',fixture())
            c.executemany('INSERT INTO metrics VALUES (?,?,?,?,?)',
                [(u.stamp(self.now-dt.timedelta(seconds=i)),'anthropic','remaining_pct.5h',80,'{}') for i in range(3000)])
        before=time.perf_counter(); report=u.utilization_report(self.store,'14d'); elapsed=time.perf_counter()-before
        size=len(json.dumps(report).encode())
        print('14-day fixture: %d bytes response, %.1f ms query, %d bytes DB' % (size,elapsed*1000,Path(self.store.path).stat().st_size))
        self.assertLess(size,500*1024)
        self.assertLess(Path(self.store.path).stat().st_size,100*1024*1024)
        self.assertEqual(len(report['series']['anthropic']['5h']),1000)
        self.assertTrue(report['notes'])
        self.assertEqual(len(report['series']['gpu']['times']),336)

    def test_asgi_validation_csp_and_no_collectors(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
        with patch.dict(os.environ,{'ORCH_HOME':self.tmp.name,'ORCH_ROOT':self.tmp.name}):
            import orch
            importlib.reload(orch)
            with patch.object(orch,'init_all',side_effect=AssertionError):
                import app
                importlib.reload(app)
        with patch.object(orch,'DB_PATH',Path(self.store.path)), \
             patch.object(u,'collect_gpu',side_effect=AssertionError), \
             patch.object(u,'command_output',side_effect=AssertionError):
            start,body=asyncio.run(request(app.app,'/api/utilization',b'range=7d'))
            self.assertEqual(start['status'],200)
            self.assertEqual(json.loads(body)['range'],'7d')
            headers=dict(start['headers'])
            self.assertIn(b"script-src 'self'",headers[b'content-security-policy'])
            start,body=asyncio.run(request(app.app,'/api/utilization',b'range=all'))
            self.assertEqual(start['status'],422)

if __name__=='__main__': unittest.main()
