"""Publication controls use only synthetic fixtures and temporary directories."""
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
audit=importlib.import_module('audit_repository')
configure=importlib.import_module('configure_repository')
validate=importlib.import_module('validate_repository')
builder=importlib.import_module('build_repository')

class RepositoryToolsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'repo'
  shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('.git','__pycache__','.venv'))
 def test_original_icon_is_bounded_and_rejects_malformed_or_hidden_payload(self):
  path=self.root/audit.BRAND_ICON
  original=path.read_bytes()
  self.assertTrue(audit.valid_brand_png(original))
  self.assertFalse(audit.valid_brand_png(original+b'hidden payload'))
  self.assertFalse(audit.valid_brand_png(original[:-1]))
  self.assertFalse(audit.valid_brand_png(bytes(131073)))
  path.write_bytes(original+b'hidden payload')
  self.assertIn('invalid_brand_icon',{x['kind'] for x in audit.audit(self.root)['findings']})
 def test_unapproved_binary_png_is_rejected(self):
  (self.root/'unapproved.png').write_bytes((self.root/audit.BRAND_ICON).read_bytes())
  self.assertIn('non_text_asset',{x['kind'] for x in audit.audit(self.root)['findings']})
 def test_known_secret_and_private_data_report_is_redacted(self):
  token='ghp_'+'A'*40
  email='fixture'+'@'+'private'+'.com'
  private_path='/home/'+'fixture-user/data'
  (self.root/'accidental.txt').write_text(token+'\n'+email+'\n'+private_path)
  report=audit.audit(self.root)
  kinds={f['kind'] for f in report['findings']}
  self.assertTrue({'potential_secret','non_reserved_email','private_environment_reference'}<=kinds)
  raw=json.dumps(report)
  for value in (token,email,private_path):self.assertNotIn(value,raw)
 def test_unknown_runtime_dependency_and_credential_default_fail(self):
  (self.root/'custom_components/virtavo/unsafe.py').write_text("import proprietary_driver\npassword='fixture-only'\n")
  kinds={x['kind'] for x in audit.audit(self.root)['findings']}
  self.assertIn('unapproved_runtime_dependency',kinds)
  self.assertIn('hardcoded_runtime_credential_candidate',kinds)
 def test_private_binary_and_environment_assets_fail(self):
  (self.root/'capture.pcap').write_bytes(bytes(4))
  (self.root/'.env').write_text('placeholder')
  self.assertEqual(sum(x['kind']=='forbidden_asset' for x in audit.audit(self.root)['findings']),2)
 def test_owner_binding_only_changes_local_metadata(self):
  url=configure.configure('example-owner',self.root)
  self.assertEqual(url,'https://github.com/example-owner/ha-virtavo-ip360')
  metadata=json.loads((self.root/'repository.json').read_text())
  self.assertFalse(metadata['publication_authorized'])
  manifest=json.loads((self.root/'custom_components/virtavo/manifest.json').read_text())
  self.assertEqual(manifest['codeowners'],['@example-owner'])
  report,ok=validate.validate(self.root,publication=True)
  self.assertTrue(ok,report)
 def test_invalid_owner_never_changes_files(self):
  before=(self.root/'repository.json').read_bytes()
  for owner in ('','../escape','x;command','-bad','a--b',None):
   with self.assertRaises(ValueError):configure.configure(owner,self.root)
  self.assertEqual((self.root/'repository.json').read_bytes(),before)
 def test_missing_or_wrong_codeowners_blocks_publication_check(self):
  configure.configure('example-owner',self.root)
  path=self.root/'.github/CODEOWNERS'
  path.unlink()
  report,ok=validate.validate(self.root,publication=True)
  self.assertFalse(ok);self.assertIn('codeowners_mismatch',{x['kind'] for x in report['findings']})
  path.write_text('* @different-fixture\n')
  report,ok=validate.validate(self.root,publication=True)
  self.assertFalse(ok);self.assertIn('codeowners_mismatch',{x['kind'] for x in report['findings']})
 def test_unbound_owner_blocks_publication_preparation(self):
  metadata=json.loads((self.root/'repository.json').read_text());metadata['owner']=None
  (self.root/'repository.json').write_text(json.dumps(metadata))
  report,ok=validate.validate(self.root,publication=True)
  self.assertFalse(ok);self.assertIn('github_owner_and_final_urls',report['publication_metadata_pending'])
  with self.assertRaises(ValueError):builder.build(Path(self.tmp.name)/'blocked.zip',self.root,publication=True)
 def test_archive_is_reproducible_with_no_git_or_caches(self):
  (self.root/'.git').mkdir();(self.root/'.git/config').write_text('private fixture only')
  one=Path(self.tmp.name)/'one.zip';two=Path(self.tmp.name)/'two.zip'
  builder.build(one,self.root);builder.build(two,self.root)
  self.assertEqual(one.read_bytes(),two.read_bytes())
  with zipfile.ZipFile(one) as z:
   self.assertFalse(any('.git/' in x or '__pycache__' in x for x in z.namelist()))
   self.assertIn('PACKAGE_SHA256.json',z.namelist())
 def test_missing_required_file_fails_without_contents_disclosure(self):
  (self.root/'LICENSE').unlink()
  report,ok=validate.validate(self.root)
  self.assertFalse(ok);self.assertIn('missing_required_file',{x['kind'] for x in report['findings']})
