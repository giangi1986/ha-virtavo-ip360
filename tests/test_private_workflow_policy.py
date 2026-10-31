"""No remote test workflow may turn private-only approval into publishing."""
from pathlib import Path
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[1]

class PrivateWorkflowPolicyTests(unittest.TestCase):
 def test_security_audit_only_runs_for_exact_private_repository(self):
  path=ROOT/'.github/workflows/private-security.yml'
  text=path.read_text();data=yaml.safe_load(text)
  self.assertEqual(data['permissions'],{'contents':'read'})
  guard=data['jobs']['audit']['if']
  self.assertIn("github.repository == 'giangi1986/ha-virtavo-ip360'",guard)
  self.assertIn('github.event.repository.private == true',guard)
  self.assertNotIn('git push',text);self.assertNotIn('--fix',text)
  self.assertNotIn('contents: write',text);self.assertNotIn('gh release',text)
 def test_hacs_validation_does_not_pretend_private_support(self):
  data=yaml.safe_load((ROOT/'.github/workflows/hacs.yml').read_text())
  self.assertEqual(data['jobs']['validate']['if'],'github.event.repository.private == false')
  self.assertEqual(data['permissions'],{'contents':'read'})

if __name__=='__main__':unittest.main()
