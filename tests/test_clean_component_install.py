"""Isolated copy of runtime only: actual HA flow/service/factory/HTTP lifecycle.

No camera/cloud I/O or video decode; only external account and receiver I/O
boundaries are substituted. Does not claim actual HACS download certification.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

RUNNER=r'''
import asyncio,importlib,json,pathlib,socket,sys
from types import MappingProxyType,SimpleNamespace
from unittest.mock import AsyncMock,patch
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry,ConfigEntries
from custom_components import virtavo
from custom_components.virtavo import config_flow,camera,release_status
from custom_components.virtavo.engine import service,receiver

async def main():
    hass=HomeAssistant(str(root))
    hass.config_entries=ConfigEntries(hass,{})
    hass.config.language='en';hass.config.country='IT'
    closes=[];network_calls=[]
    class Account:
        def __init__(self):self.session=SimpleNamespace(canonical_username=b'PRIVATE_RECIPIENT')
        def __enter__(self):return self
        def __exit__(self,*args):closes.append(1)
    def account(config):
        network_calls.append('account')
        assert config.email=='fixture@example.invalid'
        return Account()
    def devices(connection):
        return SimpleNamespace(devices=(SimpleNamespace(device_id=123,name='Garden@PRIVATE_OWNER',password=b'PRIVATE_DEVICE'),),device_owner_types=((123,1),))
    calls=[];started=asyncio.Event();stopped=asyncio.Event();entities=[]
    async def stream(data,selected,writer,*,audio=False,options=None):
        calls.append({'selected':selected,'audio':audio,'options':dict(options or {})})
        started.set()
        try:
            writer.write(b'fixture-transport-bytes');await writer.drain()
            await asyncio.Future()
        finally:stopped.set()
    async def forward(entry,platforms):
        assert platforms==['camera']
        await camera.async_setup_entry(hass,entry,entities.extend)
        assert len(entities)==1
        entities[0].hass=hass
        await entities[0].async_added_to_hass()
    async def unload(entry,platforms):
        await entities[0].async_will_remove_from_hass()
        return True
    settings={'username':'fixture@example.invalid','password':'PRIVATE_ACCOUNT','region':'fr','country':'IT'}
    with patch.object(release_status,'RELEASE_READY',True),patch.object(release_status,'AUDIO_SUPPORTED',True),patch.object(service,'open_account',account),patch.object(service,'discover_account_devices',devices),patch.object(receiver,'run_camera_stream',stream),patch.object(hass.config_entries,'async_forward_entry_setups',AsyncMock(side_effect=forward)),patch.object(hass.config_entries,'async_unload_platforms',AsyncMock(side_effect=unload)),patch.object(socket,'create_connection',side_effect=AssertionError('No external blocking network permitted')):
        flow=config_flow.VirtavoConfigFlow();flow.hass=hass;flow.handler='virtavo';flow.context={'source':'user'}
        found=await flow.async_step_user(settings)
        assert found['step_id']=='device'
        created=await flow.async_step_device({'device_id':'123'})
        assert created['type']=='create_entry'
        assert created['data']['device']=={'device_id':123,'name':'Garden','own_type':1}
        assert 'PRIVATE_OWNER' not in repr(created)
        for options,audio_expected in (({},False),({'audio_enabled':True,'region':'ca'},True)):
            entry=ConfigEntry(version=1,minor_version=1,domain='virtavo',title='Garden',data=created['data'],options=options,source='user',unique_id='fixture-'+str(audio_expected),discovery_keys=MappingProxyType({}),subentries_data=[])
            hass.config_entries._entries[entry.entry_id]=entry
            entities.clear();calls.clear();started.clear();stopped.clear()
            assert await virtavo.async_setup_entry(hass,entry)
            runtime=entry.runtime_data[0]
            assert runtime.continuous is False
            assert not started.is_set()
            cam=entities[0]
            url=await cam.stream_source()
            assert url.startswith('http://127.0.0.1:')
            assert not started.is_set()
            async with ClientSession() as client:
                response=await client.get(url)
                assert await response.content.readexactly(23)==b'fixture-transport-bytes'
                assert started.is_set()
                assert calls==[{'selected':123,'audio':audio_expected,'options':options}]
                assert await virtavo.async_unload_entry(hass,entry)
                response.close()
            assert stopped.is_set() and entry.runtime_data is None
            assert cam._endpoint.manager.task is None
            assert cam._endpoint._runner is None
    assert len(network_calls)==3 and len(closes)==3
    for name,module in list(sys.modules.items()):
        if name.startswith('custom_components.virtavo') and getattr(module,'__file__',None):
            assert pathlib.Path(module.__file__).resolve().is_relative_to(root)
    assert not list(root.rglob('*.pcap')) and not list(root.rglob('*.so'))
    print(json.dumps({'isolated_runtime_copy':True,'real_HA_flow_service_factory_camera_endpoint':True,'default_on_demand':True,'audio_default_off_and_opt_in':True,'source_uses_only_staged_component':True,'account_connections_closed':len(closes),'camera_or_cloud_contacted':False,'actual_HACS_download_tested':False,'video_decoded':False}))
asyncio.run(main())
'''

class CleanComponentInstallTests(unittest.TestCase):
    def test_runtime_only_copy_runs_actual_ha_flow_factory_consumer_and_unload(self):
        with tempfile.TemporaryDirectory(prefix='virtavo-clean-ha-') as directory:
            stage=Path(directory)
            shutil.copytree(ROOT/'custom_components/virtavo',stage/'custom_components/virtavo',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            runner=stage/'run_acceptance.py';runner.write_text(RUNNER)
            completed=subprocess.run([sys.executable,'-I',str(runner),str(stage)],cwd=stage,capture_output=True,text=True,timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr[-5000:])
            result=json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertTrue(result['real_HA_flow_service_factory_camera_endpoint'])
            self.assertTrue(result['audio_default_off_and_opt_in'])
            self.assertFalse(result['camera_or_cloud_contacted'])
            self.assertFalse(result['actual_HACS_download_tested'])
            print(json.dumps(result,sort_keys=True))

if __name__=='__main__':unittest.main()
