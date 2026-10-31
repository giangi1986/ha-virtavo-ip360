"""Full HA loader/config-entry/platform setup from a runtime-only clean copy.

Only external account/stream I/O and restricted system IP enumeration are
replaced; HA dependencies, loader, platform forward/unload remain real.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

RUNNER = r'''
import asyncio,json,pathlib,socket,sys,logging
from types import SimpleNamespace,MappingProxyType
from unittest.mock import patch
from aiohttp import ClientSession
from homeassistant import loader,auth,bootstrap
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry,ConfigEntries,ConfigEntryState
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
from custom_components.virtavo.engine import service,receiver
from custom_components.virtavo import release_status

async def main():
 hass=HomeAssistant(str(root));hass.config.country='IT';hass.config.language='en';hass.config.skip_pip=True
 loader.async_setup(hass)
 hass.config_entries=ConfigEntries(hass,{})
 await bootstrap.async_load_base_functionality(hass)
 hass.auth=await auth.auth_manager_from_config(hass,[],[])
 from homeassistant.components import http
 from unittest.mock import AsyncMock
 starts=[];ended=asyncio.Event();closed=[]
 class Account:
  def __init__(self):self.session=SimpleNamespace(canonical_username=b'PRIVATE_RECIPIENT')
  def __enter__(self):return self
  def __exit__(self,*args):closed.append(1)
 def devices(c):return SimpleNamespace(devices=(SimpleNamespace(device_id=123,name='Garden@PRIVATE_OWNER'),),device_owner_types=((123,1),))
 async def stream(data,selected,writer,*,audio=False,options=None):
  starts.append((selected,audio))
  try:
   writer.write(b'fixture-transport-bytes');await writer.drain();await asyncio.Future()
  finally:ended.set()
 entry=ConfigEntry(version=1,minor_version=1,domain='virtavo',title='Garden',data={'username':'fixture@example.invalid','password':'PRIVATE_ACCOUNT','country':'IT','language':'en','region':'fr','device':{'device_id':123,'name':'Garden','own_type':1}},options={},source='user',unique_id='fixture',discovery_keys=MappingProxyType({}),subentries_data=[])
 hass.config_entries._entries[entry.entry_id]=entry
 try:
  with patch.object(http,'async_get_source_ip',AsyncMock(return_value='127.0.0.1')),patch.object(release_status,'RELEASE_READY',True),patch.object(service,'open_account',lambda c:Account()),patch.object(service,'discover_account_devices',devices),patch.object(receiver,'run_camera_stream',stream),patch.object(socket,'create_connection',side_effect=AssertionError('External network forbidden')):
   loaded=await asyncio.wait_for(hass.config_entries.async_setup(entry.entry_id),20)
   await hass.async_block_till_done()
   print('LOADER_RESULT',loaded,entry.state.value,sorted(hass.config.components))
   assert loaded and entry.state is ConfigEntryState.LOADED
   from homeassistant.components.camera import DATA_COMPONENT
   cameras=list(hass.data[DATA_COMPONENT].entities)
   assert len(cameras)==1
   camera=cameras[0];assert camera.entity_id.startswith('camera.')
   assert not starts
   url=await camera.stream_source();assert not starts
   async with ClientSession() as client:
    response=await client.get(url)
    assert await response.content.readexactly(23)==b'fixture-transport-bytes'
    assert starts==[(123,False)]
    assert await hass.config_entries.async_unload(entry.entry_id)
    response.close()
   assert ended.is_set() and entry.state is ConfigEntryState.NOT_LOADED
   assert getattr(entry,'runtime_data',None) is None
   assert not list(hass.data[DATA_COMPONENT].entities)
   assert len(closed)==1
   for name,module in list(sys.modules.items()):
    if name.startswith('custom_components.virtavo') and getattr(module,'__file__',None):
     assert pathlib.Path(module.__file__).resolve().is_relative_to(root)
   print(json.dumps({'full_HA_config_entry_setup_unload':True,'real_loader_and_platform_forward':True,'real_HA_camera_entity_registered':True,'default_on_demand':True,'actual_HACS_download':False,'HA_decoder_tested':False,'cloud_or_camera_contacted':False,'account_contexts_closed':len(closed)}))
 finally:
  await hass.async_stop(force=True)
asyncio.run(main())
'''

class FullHALoaderTests(unittest.TestCase):
    def test_clean_runtime_manifest_loads_registers_camera_and_unloads_via_ha(self):
        with tempfile.TemporaryDirectory(prefix='virtavo-full-ha-') as directory:
            stage=Path(directory)
            shutil.copytree(ROOT/'custom_components/virtavo',stage/'custom_components/virtavo',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            runner=stage/'run_acceptance.py';runner.write_text(RUNNER)
            completed=subprocess.run([sys.executable,'-I',str(runner),str(stage)],cwd=stage,capture_output=True,text=True,timeout=40)
            self.assertEqual(completed.returncode,0,completed.stdout[-1000:]+completed.stderr[-6000:])
            result=json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertTrue(result['full_HA_config_entry_setup_unload'])
            self.assertTrue(result['real_loader_and_platform_forward'])
            self.assertTrue(result['real_HA_camera_entity_registered'])
            self.assertFalse(result['actual_HACS_download'])
            self.assertFalse(result['HA_decoder_tested'])
            print(json.dumps(result,sort_keys=True))

if __name__=='__main__':unittest.main()
