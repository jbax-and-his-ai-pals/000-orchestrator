import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_dashboard_steering as base
import dashboard_ops
import orch
import overview
import steering
import utilization as u

class IntegrationTests(base.SteeringTests):
    def test_large_portfolio_latency_and_complete_paging(self):
        plan=json.dumps({'subtasks':[{'id':n,'title':'task '+str(n),'assignee':'codex','status':'todo'} for n in range(1,6)]})
        with orch.db(write=True) as con:
            con.executemany("INSERT INTO initiatives(project_name,category,title,slug,stage,created_at,updated_at,execution_plan_json) VALUES ('a','optimization',?,?,'building',?,?,?)",[(str(n),str(n),orch.now(),orch.now(),plan) for n in range(1000)])
            con.executemany("INSERT INTO events(ts,actor,initiative_id,kind,message) VALUES (?,'planner-codex',?,'note','observed')",[(orch.now(),n%1000+1) for n in range(10000)])
        times=[]
        for _ in range(3):
            start=time.perf_counter(); result=overview.paged(overview.snapshot(orch)); times.append(time.perf_counter()-start)
        self.assertLess(max(times),.5, times)
        self.assertLess(len(json.dumps(result).encode()),2*1024*1024)
        self.assertEqual(result['totals']['initiatives'],1003)
        self.assertEqual(result['pages']['pending.queued']['total'],1003)
        self.assertEqual(result['pages']['pending.blocked']['total'],4003)
        self.assertEqual(len(result['pending']['blocked']),200)
        page=overview.paged(overview.snapshot(orch),collection='pending.blocked',offset=4000)
        self.assertEqual(len(page['pending']['blocked']),3)
        self.assertIsNone(page['pages']['pending.blocked']['next_cursor'])
        print('Overview scale: max %.1f ms, %d bytes initial JSON'%(max(times)*1000,len(json.dumps(result).encode())))
    def test_commit_sha_attribution_and_bounded_detail(self):
        wt=Path(self.tmp.name)/'worktrees'/'feature'; wt.mkdir(parents=True)
        def git(*args):
            return subprocess.run(['git','-C',str(wt),*args],capture_output=True,text=True,check=True).stdout.strip()
        git('init','-b','feat/test'); git('config','user.name','Test'); git('config','user.email','test@example.invalid')
        (wt/'file.txt').write_text('baseline'); git('add','.'); git('-c','core.hooksPath=/dev/null','commit','-m','base')
        (wt/'file.txt').write_text('changed')
        with orch.db(write=True) as con: con.execute("UPDATE initiatives SET worktree_path=?,branch_name='feat/test' WHERE id=1",(str(wt),))
        with patch.object(orch,'WORKTREES',wt.parent):
            sha=orch.commit(1,'subtask work','planner-codex',1)
            detail=dashboard_ops.subtask_detail(orch,1,1)
        self.assertEqual(len(sha),40); self.assertIn(sha,detail['commit_shas'])
        self.assertEqual(detail['diff']['basis'],'recorded subtask commits'); self.assertIn('+changed',detail['diff']['patch'])
    def test_reorder_keeps_verification_and_extra_metadata(self):
        with orch.db(write=True) as con:
            plan=json.loads(self.init()['execution_plan_json'])
            plan['custom']={'keep':True}; plan['subtasks'][0]['last_verify']={'ok':True,'output_tail':'proof'}
            con.execute('UPDATE initiatives SET execution_plan_json=? WHERE id=1',(json.dumps(plan),))
        before=self.init()['execution_plan_json']
        orch.reorder_subtasks(1,[2,1],steering.version(before),'producer')
        after=json.loads(self.init()['execution_plan_json'])
        self.assertEqual(after['custom'],{'keep':True}); self.assertEqual(after['subtasks'][1]['last_verify']['output_tail'],'proof')
if __name__=='__main__': unittest.main()
