import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import orch
import steering

class SteeringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(orch,k,v) for k,v in {'STATE':root,'DB_PATH':root/'db.sqlite','JSON_PATH':root/'state.json','DESIGNS':root/'designs'}.items()]
        for p in self.patches: p.start()
        orch.init_db(); orch.init_db()
        with orch.db(write=True) as con:
            con.execute("INSERT INTO projects(repo_name,local_path) VALUES ('a',?)",(str(root),))
            for n in range(1,4):
                plan = {'subtasks':[{'id':1,'title':'first','status':'todo','assignee':'codex'}, {'id':2,'title':'second','status':'todo','assignee':'codex'}]}
                con.execute("INSERT INTO initiatives(id,project_name,category,title,slug,stage,created_at,updated_at,execution_plan_json) VALUES (?,'a','optimization',?,?,'building',?,?,?)",(n,str(n),str(n),orch.now(),orch.now(),json.dumps(plan)))
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()
    def init(self,n=1):
        with orch.db() as con: return orch.get_initiative(con,n)
    def test_migrations_and_priority_dispatch(self):
        i=self.init(3)
        orch.set_initiative(3,'high',steering.version(i),'producer')
        self.assertEqual(orch.queue('planner')['subtasks'][0]['initiative'],3)
        with self.assertRaises(steering.Conflict): orch.set_initiative(3,'low',steering.version(i),'producer')
        self.assertEqual(self.init(3)['priority'],'high')
    def test_project_stale_and_skip(self):
        with orch.db() as con: p=orch.get_project(con,'a')
        orch.update_project('a',{'priority':'skip'},'producer',orch.project_version(p))
        self.assertEqual(orch.queue('planner')['subtasks'],[])
        with self.assertRaises(steering.Conflict): orch.update_project('a',{'priority':'high'},'producer',orch.project_version(p))
    def test_reorder_stable_and_stale(self):
        old=self.init()['execution_plan_json']
        orch.reorder_subtasks(1,[2,1],steering.version(old),'producer')
        plan=json.loads(self.init()['execution_plan_json'])
        self.assertTrue(orch.ready(plan['subtasks'][0],plan['subtasks']))
        self.assertFalse(orch.ready(plan['subtasks'][1],plan['subtasks']))
        with self.assertRaises(steering.Conflict): orch.reorder_subtasks(1,[1,2],steering.version(old),'producer')
    def test_cycles_unknown_and_frozen(self):
        for subs,order in [([{'id':1,'depends_on':[2]},{'id':2}],[1,2]),([{'id':1,'depends_on':[9]}],[1]),([{'id':1,'status':'doing'},{'id':2}],[2,1]),([{'id':1},{'id':2}],[1,1])]:
            with self.assertRaises(ValueError): steering.reordered(subs,order)
        self.assertEqual(steering.reordered([{'id':2,'depends_on':[]},{'id':1,'depends_on':[]}],[1,2])[0]['id'],1)
    def test_attempts_and_claim_guard(self):
        orch.subtask_update(1,1,'doing','','planner-codex')
        a=json.loads(self.init()['execution_plan_json'])['subtasks'][0]['run_attempt']
        orch.subtask_update(1,1,'doing','','planner-codex')
        self.assertEqual(json.loads(self.init()['execution_plan_json'])['subtasks'][0]['run_attempt'],a)
        orch.subtask_update(1,1,'done','','planner-codex')
        with orch.db() as con:
            events=orch.rows(con,"SELECT details_json FROM events WHERE kind='subtask'")
        self.assertEqual(json.loads(events[-1]['details_json'])['attempt'],a)
        orch.claim(2,'chat')
        self.assertNotIn(2,[x['initiative'] for x in orch.queue('planner')['subtasks']])
    def test_focus_spotlight_handoff_exclusions(self):
        i={'project_name':'a'}
        self.assertEqual(steering.eligibility(i,{'focus_by':'chat','focus_until':'9999'},None,'2026'),'project focus')
        self.assertEqual(steering.eligibility(i,{}, {'project':'b'},'2026'),'outside spotlight')
        self.assertIsNone(steering.eligibility(i,{}, {'project':'b'},'2026',finishing=True))
        self.assertEqual(steering.eligibility(i,{}, {'project':'a'},'2026',due=True),'handoff due')

if __name__=='__main__': unittest.main()
