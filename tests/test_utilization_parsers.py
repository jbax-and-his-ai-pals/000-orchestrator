import datetime as dt
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import utilization as u

class ParserTests(unittest.TestCase):
    def test_gpu_multi_and_unknown(self):
        rows=u.parse_gpu('10, 1024, 4096, 40, 50\n80, 2048, 8192, 60, 100')
        self.assertEqual([r['value'] for r in rows], [80,3072,12288,60,150])
        self.assertEqual(rows[0]['meta']['device_count'],2)
        rows=u.parse_gpu('0, N/A, 4096, NaN, 50')
        self.assertEqual(rows[0]['value'],0)
        self.assertIsNone(rows[1]['value'])
        self.assertIsNone(rows[3]['value'])
        for bad in ('', '1,2', 'garbage'):
            with self.assertRaises(ValueError): u.parse_gpu(bad)

    def test_ollama(self):
        self.assertEqual(u.parse_ollama('{"models":[]}')[0]['value'],0)
        row=u.parse_ollama('{"models":[{"name":"gemma","size_vram":12,"expires_at":"2026-11-13T12:00:00-08:00"}]}')[0]
        self.assertEqual(row['meta']['models'][0]['expires_at'],'2026-11-13T20:00:00+00:00')
        for bad in ('{}','{"models":null}','{"models":[1]}','bad'):
            with self.assertRaises(ValueError): u.parse_ollama(bad)

    def test_openai_usage_only_and_partial(self):
        # Source-derived fixture: installed provider-usage.format-L6iA6HgQ.mjs
        # formatUsageWindowSummary emits 'label N% left ⏱duration', joined with ·.
        # list.status-command-BDWFKp41.mjs prefixes '- provider usage: '.
        text='\x1b[32m- openai-codex usage: 5h 82% left ⏱2h 15m · Week 90% left ⏱6d 2h\x1b[0m'
        # The clock glyph may appear before resets in human-oriented status output.
        rows=u.parse_openai(text,'2026-11-13T22:00Z')
        self.assertEqual([r['value'] for r in rows],[82,90])
        self.assertEqual(rows[0]['meta']['resets_at'],'2026-11-14T00:15:00+00:00')
        self.assertEqual(rows[1]['meta']['resets_at'],'2026-11-20T00:00:00+00:00')
        expired=u.parse_openai('openai usage: 5h 1% left ⏱now','2026-11-13T22:00Z')
        self.assertEqual(expired[0]['meta']['resets_at'],'2026-11-13T22:00:00+00:00')
        partial=u.parse_openai('openai usage: Week 0% left','2026-11-13T22:00Z')
        self.assertEqual(len(partial),1)
        self.assertEqual(partial[0]['value'],0)
        for bad in ('tokens 5h 100% left','openai usage: unavailable','openai usage: 5h 101% left'):
            with self.assertRaises(ValueError): u.parse_openai(bad,'2026-11-13T22:00Z')

    def test_collectors_are_bounded_and_fixed(self):
        with patch.object(u.shutil,'which',return_value=None), patch.object(u.Path,'is_file',return_value=False):
            with self.assertRaises(u.CollectorError) as e: u.collect_gpu()
            self.assertEqual(e.exception.reason,'missing_tool')
        with patch.object(u.shutil,'which',return_value='C:/tools/nvidia-smi.exe'), patch.object(u.subprocess,'run',return_value=Mock(returncode=0,stdout='0,0,10,20,30')) as run:
            self.assertEqual(u.collect_gpu()[0]['value'],0)
            self.assertEqual(run.call_args.kwargs['timeout'],5)
            self.assertFalse(run.call_args.kwargs['shell'])
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.read.return_value=b'x'*(1024*1024+1)
        opener=Mock(); opener.open.return_value=response
        with patch.object(u.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(u.CollectorError): u.collect_ollama()
            self.assertEqual(opener.open.call_args.kwargs['timeout'],3)

if __name__=='__main__': unittest.main()
