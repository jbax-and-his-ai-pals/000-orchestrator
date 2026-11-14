import copy
import datetime as dt
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import orch
import forecast as f
import utilization as u

NOW=u.utc('2026-11-14T02:00Z')
def project(name='p',**kw):
    return dict(repo_name=name,priority='medium',complexity='standard',last_scanned_at=None,is_git=1,focus_by=None,focus_until=None,**kw)
def card(iid=1,project_name='p',stage='building',subs=None,**kw):
    return dict(id=iid,project_name=project_name,title='Card '+str(iid),stage=stage,complexity='standard',priority='medium',updated_at=str(iid),created_at=u.stamp(NOW-dt.timedelta(hours=1)),revision_note=None,worktree_path=None,execution_plan_json=json.dumps({'subtasks':subs if subs is not None else [sub(1)]}),**kw)
def sub(sid,actor='codex',status='todo',**kw):
    return dict(id=sid,title='Sub '+str(sid),assignee=actor,status=status,**kw)
def lane(actor='codex',enabled=True,**kw):
    return dict(key=actor,scheduler={'state':'enabled' if enabled else 'paused'},reason=None,quota={'state':'observed'},jobs=[dict(declaration='orch:'+actor,enabled=enabled,next_run_at=u.stamp(NOW),started_at=None)],**kw)
def run(cards=None,projects=None,lanes=None,**kw):
    return f.forecast(cards or [card()],projects or [project()],lanes if lanes is not None else [lane()],[],NOW,orch.queue_from_snapshot,**kw)

class ForecastTests(unittest.TestCase):
    def test_fallback_tiers(self):
        self.assertEqual(f.duration([],'codex','build')['seconds'],1200)
        self.assertIn('default guess',f.duration([],'codex','build')['basis_label'])
        samples=[dict(actor='codex',work_type='build',seconds=n) for n in [60,120,180]]
        self.assertEqual(f.duration(samples,'codex','build')['basis'],'actor_work_type')
        self.assertEqual(f.duration(samples,'codex','lld')['basis'],'actor_fallback')
        self.assertEqual(f.duration(samples,'claude','build')['basis'],'work_type_fallback')
        self.assertEqual(f.duration(samples[:2],'codex','build')['basis'],'default_prior')
    def test_defined_work_review_and_pure(self):
        cards=[card(subs=[sub(1),sub(2)])]; original=copy.deepcopy(cards)
        result=run(cards)
        self.assertEqual([x['work_type'] for x in result['timeline']],['build','build','review'])
        self.assertEqual(result['initiatives']['1']['completion_at'],u.stamp(NOW+dt.timedelta(minutes=50)))
        self.assertEqual(cards,original)
    def test_paused(self):
        result=run(lanes=[lane(enabled=False)])
        self.assertEqual(result['timeline'],[])
        self.assertIn('ask in chat to run it',result['initiatives']['1']['reason'])
    def test_spotlight_claim_and_focus(self):
        result=run(spot={'project':'other'})
        self.assertEqual(result['initiatives']['1']['reason'],'blocked by spotlight on other')
        self.assertFalse(result['timeline'])
        cards=[card(claimed_by='chat',claim_expires_at=u.stamp(NOW+dt.timedelta(hours=2)))]
        self.assertEqual(run(cards)['initiatives']['1']['reason'],'claimed in chat')
        p=project();p.update(focus_by='chat',focus_until=u.stamp(NOW+dt.timedelta(hours=2)))
        self.assertEqual(run(projects=[p])['initiatives']['1']['reason'],'project focus')
    def test_gate_is_conditional_never_executed(self):
        result=run([card(stage='lld_review')])
        self.assertFalse(result['timeline'])
        eta=result['initiatives']['1']
        self.assertEqual(eta['state'],'waiting');self.assertEqual(eta['waiting_seconds'],3600)
        self.assertEqual(eta['if_approved_now']['completion_at'],u.stamp(NOW+dt.timedelta(minutes=30)))
    def test_priority_delta_and_delays(self):
        cards=[card(1),card(2)]
        base=run(cards); bumped=run(cards,bump=('initiative','2'))
        delta=f.compare(base,bumped,'initiative','2')
        self.assertLess(delta['if_prioritized']['completion_at'],delta['eta_now']['completion_at'])
        self.assertEqual(delta['delayed'][0]['initiative_id'],1)
    def test_dependencies_and_handoff(self):
        result=run([card(subs=[sub(1,status='blocked'),sub(2)])])
        self.assertFalse(result['timeline'])
        self.assertEqual(result['items']['s:1:1']['reason'],'explicitly blocked')
        self.assertFalse(run(due={'codex':[{'initiative':1}]})['timeline'])
    def test_shared_queue_contract_and_precedence(self):
        cards=[card(1),card(2,stage='lld_draft'),card(3,subs=[sub(1,status='done')])]
        result=run(cards)
        self.assertEqual([(x['initiative_id'],x['work_type']) for x in result['timeline'][:2]],[(3,'review'),(2,'lld')])
        bad=card(subs=[sub(1,'gemma')]);bad['complexity']='high'
        self.assertFalse([x for x in run([bad],lanes=[lane('gemma')])['timeline'] if x['work_type']=='build'])
    def test_scan_and_bound(self):
        result=run([card(stage='spark')],lanes=[lane('gemma')],spot={'project':'p'})
        self.assertEqual(result['timeline'][0]['work_type'],'scan')
        result=f.simulate([card(subs=[sub(n) for n in range(10)])],[project()],[lane()],[],NOW,orch.queue_from_snapshot,max_events=2)
        self.assertTrue(result['truncated'])
    def test_active_remaining_time_and_overdue_do_not_slide(self):
        cards=[card(subs=[sub(1,status='doing')])]
        l=lane();l['jobs'][0]['enabled']=False;l['jobs'][0]['started_at']=u.stamp(NOW-dt.timedelta(minutes=5));l['scheduler']['state']='paused'
        l['activity']={'href':'#/initiative/1/subtask/1','started_at':u.stamp(NOW-dt.timedelta(minutes=5))}
        result=run(cards,lanes=[l])
        self.assertEqual(result['items']['s:1:1']['completion_at'],u.stamp(NOW+dt.timedelta(minutes=15)))
        self.assertEqual(len(result['timeline']),1)
        l['activity']['started_at']=u.stamp(NOW-dt.timedelta(minutes=30))
        result=run(cards,lanes=[l])
        self.assertEqual(result['items']['s:1:1']['state'],'over_typical')
        self.assertNotIn('completion_at',result['items']['s:1:1'])
    def test_observed_recurrence_only(self):
        self.assertIsNone(f.next_check({},NOW))
        self.assertEqual(f.next_check({'schedule':{'kind':'every','everyMs':1800000}},NOW),NOW+dt.timedelta(minutes=30))
        at=f.next_check({'schedule':{'kind':'cron','expr':'*/30 * * * *','tz':'UTC'}},NOW)
        self.assertEqual(at,NOW+dt.timedelta(minutes=30))
    def test_cross_lane_dependency_retries_after_completion(self):
        result=run([card(subs=[sub(1,'claude'),sub(2)])],lanes=[lane('codex'),lane('claude')])
        self.assertEqual([e['subtask_id'] for e in result['timeline'] if e['work_type']=='build'],[1,2])
    def test_scout_priority_and_mixed_timezone_freshness(self):
        a=project('a');b=project('b');b['priority']='high'
        result=run([card(stage='spark')],projects=[a,b],lanes=[lane('gemma')])
        self.assertEqual(result['timeline'][0]['project'],'b')
        a['last_scanned_at']='2026-11-13T17:30:00-08:00'
        result=run([card(stage='spark')],projects=[a],lanes=[lane('gemma')],spot={'project':'a'})
        self.assertFalse(result['timeline'])
    def test_gemma_falls_back_to_stale_dossier_outside_spotlight(self):
        a=project('a');b=project('b');a['last_scanned_at']='2026-11-13T17:30:00-08:00'
        result=run([card(stage='spark')],projects=[a,b],lanes=[lane('gemma')],spot={'project':'a'})
        self.assertEqual(result['timeline'][0]['project'],'b')
        a2=project('a');a2['last_scanned_at']='2026-11-13T17:30:00-08:00'
        job=orch.queue_from_snapshot('scout',[],[a2,project('b')],{'project':'a'},u.stamp(NOW))
        self.assertEqual((job['project'],job.get('fallback')),('b',True))
    def test_unknown_running_job_is_not_attributed_to_queued_work(self):
        l=lane();l['jobs'][0]['started_at']=u.stamp(NOW-dt.timedelta(minutes=1))
        result=run(lanes=[l])
        self.assertFalse(result['timeline'])
        self.assertIn('not identified',result['initiatives']['1']['reason'])
    def test_cache_returns_copies(self):
        args=([card()],[project()],[lane()],[],NOW,orch.queue_from_snapshot)
        x=f.cached(*args);x['timeline'].clear()
        self.assertTrue(f.cached(*args)['timeline'])
if __name__=='__main__': unittest.main()
