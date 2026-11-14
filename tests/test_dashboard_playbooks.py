import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import sync_playbooks
class PlaybookTests(unittest.TestCase):
    def test_isolated_export_and_install(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Path(temp)/'agents'; b=Path(temp)/'canonical'; c=Path(temp)/'installed'
            (a/'planner').mkdir(parents=True); (a/'planner'/'AGENTS.md').write_text('policy')
            self.assertEqual(sync_playbooks.main(['--source-root',str(a),'--destination-root',str(b)]),0)
            self.assertEqual(sync_playbooks.main(['--install','--source-root',str(b),'--destination-root',str(c)]),0)
            self.assertEqual((c/'planner'/'AGENTS.md').read_text(),'policy')
            (c/'planner'/'AGENTS.md').write_text('stale')
            sync_playbooks.main(['--install','--source-root',str(b),'--destination-root',str(c)])
            self.assertEqual((c/'planner'/'AGENTS.md').read_text(),'policy')
    def test_canonical_contracts(self):
        root=Path(__file__).resolve().parents[1]/'playbooks'
        scout=(root/'scout-gemma'/'AGENTS.md').read_text()
        planner=(root/'planner-codex'/'AGENTS.md').read_text()
        self.assertIn('NEVER author pitches',scout); self.assertIn('Needs frontier',scout)
        self.assertIn('quota-saving',planner); self.assertIn('Producer gates remain mandatory',planner)
if __name__=='__main__': unittest.main()
