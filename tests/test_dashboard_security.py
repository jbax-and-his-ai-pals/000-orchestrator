import asyncio
import json
import unittest
from unittest.mock import patch
import test_dashboard_api as api
import orch
import utilization as u

class SecurityTests(api.DashboardAPITests):
    def test_every_new_post_requires_header(self):
        for path in ['/api/suggestions','/api/initiatives/1/priority','/api/initiatives/1/subtasks/reorder','/api/lanes/orch:planner-codex/control']:
            self.assertEqual(self.call(path,'POST',{},header=False)[0],403,path)
        self.assertEqual(self.init()['stage'],'building')
    def test_injection_invalid_controls(self):
        for path,body in [('/api/initiatives/1/priority',{'priority':"high'; DROP TABLE events;--",'expected_version':'x'}),('/api/initiatives/1/subtasks/reorder',{'order':[1,1],'expected_plan_version':'x'}),('/api/lanes/evil/control',{'enabled':True,'expected_generation':1}),('/api/suggestions',{'title':'x','pitch':'x','category':'shell','idempotency_key':'12345678'})]:
            self.assertIn(self.call(path,'POST',body)[0],(400,409,422))
        self.assertEqual(self.init()['stage'],'building')
    def test_markdown_raw_html_is_escaped(self):
        rendered=api.app.render_md('<script>alert(1)</script>\n<img src=x onerror=alert(1)>')
        self.assertNotIn('<script>',rendered); self.assertNotIn('<img ',rendered)
    def test_metric_only_version_change(self):
        first=api.app.state_version()
        u.Store(orch.DB_PATH).insert('gpu',[{'key':'util_pct','value':10}])
        self.assertNotEqual(first,api.app.state_version())
if __name__=='__main__': unittest.main()
