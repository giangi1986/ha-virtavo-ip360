"""Isolated installer rejects corrupt/unsafe archives before touching outputs."""
from pathlib import Path
import importlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
builder=importlib.import_module('build_repository')
installer=importlib.import_module('stage_install')

class StageInstallTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.base=Path(self.tmp.name);self.parent=self.base/'parent';self.parent.mkdir()
  self.archive=self.base/'source.zip';builder.build(self.archive,ROOT)
 def rewrite(self,transform,extra=None):
  destination=self.base/'changed.zip'
  with zipfile.ZipFile(self.archive) as source,zipfile.ZipFile(destination,'w') as out:
   for name in source.namelist():out.writestr(name,transform(name,source.read(name)))
   if extra:out.writestr(*extra)
  return destination
 def assert_rejected_without_outputs(self,path):
  with self.assertRaises((ValueError,KeyError)):installer.stage_install(path,self.parent)
  self.assertEqual(list(self.parent.iterdir()),[])
 def test_installs_only_complete_runtime_into_fresh_directory(self):
  before=self.parent/'sentinel.txt';before.write_text('untouched')
  stage=installer.stage_install(self.archive,self.parent)
  self.assertEqual(before.read_text(),'untouched')
  self.assertEqual([p.name for p in stage.iterdir()],['custom_components'])
  self.assertEqual((stage/'custom_components/virtavo/camera.py').read_bytes(),(ROOT/'custom_components/virtavo/camera.py').read_bytes())
  self.assertFalse((stage/'README.md').exists())
 def test_corrupted_runtime_is_rejected_before_output_creation(self):
  changed=self.rewrite(lambda n,d:d+b'\n# changed' if n.endswith('/camera.py') else d)
  self.assert_rejected_without_outputs(changed)
 def test_traversal_and_absolute_paths_are_rejected(self):
  for name in ('../escape','/absolute','custom_components/virtavo/../../escape','custom_components\\virtavo\\escape'):
   with self.subTest(name=name):self.assert_rejected_without_outputs(self.rewrite(lambda n,d:d,(name,b'fixture')))
 def test_symlinks_are_rejected(self):
  entry=zipfile.ZipInfo('custom_components/virtavo/link.py');entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
  self.assert_rejected_without_outputs(self.rewrite(lambda n,d:d,(entry,b'outside')))
 def test_duplicate_entries_are_rejected(self):
  import warnings
  with warnings.catch_warnings():
   warnings.simplefilter('ignore',UserWarning)
   path=self.rewrite(lambda n,d:d,('custom_components/virtavo/camera.py',b'duplicate'))
  self.assert_rejected_without_outputs(path)
 def test_actual_HA_loader_works_from_staged_archive(self):
  # Reuse the full loader contract with this installer as its only source.
  from test_full_ha_loader import RUNNER
  stage=installer.stage_install(self.archive,self.parent)
  runner=self.base/'run.py';runner.write_text(RUNNER)
  r=subprocess.run([sys.executable,'-I',str(runner),str(stage)],cwd=stage,capture_output=True,text=True,timeout=40)
  self.assertEqual(r.returncode,0,r.stdout[-1000:]+r.stderr[-4000:])
  result=json.loads(r.stdout.strip().splitlines()[-1])
  self.assertTrue(result['full_HA_config_entry_setup_unload'])
  self.assertFalse(result['actual_HACS_download'])

if __name__=='__main__':unittest.main()
