import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dashboard_probe_smoke as smoke
import utilization as u
class SmokeTests(unittest.TestCase):
    def test_cli_parser(self):
        self.assertEqual(smoke.parse_ollama_cli('NAME ID SIZE PROCESSOR UNTIL\n'),[])
        with self.assertRaises(ValueError): smoke.parse_ollama_cli('failed')
    def test_failures_not_success(self):
        with patch.object(u,'command_output',side_effect=u.CollectorError('missing_tool')),patch.object(u,'collect_ollama',side_effect=TimeoutError()):
            results=smoke.smoke()
        self.assertEqual(results[0]['classification'],'missing_tool')
        self.assertEqual(results[-1]['classification'],'failed')
    def test_real_output_cap(self):
        with patch.object(u.shutil,'which',return_value=sys.executable):
            with self.assertRaises(u.CollectorError) as caught:
                u.command_output('python',['-c','print("x"*1100000)'],5)
        self.assertEqual(caught.exception.reason,'oversized')
if __name__=='__main__': unittest.main()
