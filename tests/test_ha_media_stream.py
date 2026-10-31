"""Publication check: real HA HLS/HEVC/AAC path from the production mux.

Synthetic media only; account/receiver I/O substituted. No repeated camera test.
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
import asyncio,io,json,pathlib,socket,subprocess,sys,time
from types import SimpleNamespace,MappingProxyType
from unittest.mock import AsyncMock,patch
import av
from homeassistant import loader,auth,bootstrap
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry,ConfigEntries,ConfigEntryState
root=pathlib.Path(sys.argv[1]).resolve();audio=bool(int(sys.argv[2]));stall=bool(int(sys.argv[3]));sys.path.insert(0,str(root))
from custom_components.virtavo.engine import service,receiver
from custom_components.virtavo.engine.av_mux import mux_streams

async def main():
 encoded=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=black:s=64x64:r=20:d=8','-c:v','libx265','-g','20','-x265-params','pools=none:frame-threads=1:bframes=0:log-level=error','-f','hevc','pipe:1'],capture_output=True,timeout=20)
 assert encoded.returncode==0,'Synthetic HEVC encoder unavailable'
 with av.open(io.BytesIO(encoded.stdout),format='hevc') as input:
  packets=[bytes(p) for p in input.demux(video=0) if p.size]
 hass=HomeAssistant(str(root));hass.config.country='IT';hass.config.language='en';hass.config.skip_pip=True
 loader.async_setup(hass);hass.config_entries=ConfigEntries(hass,{})
 await bootstrap.async_load_base_functionality(hass)
 hass.auth=await auth.auth_manager_from_config(hass,[],[])
 from homeassistant.components import http
 starts=[];ended=asyncio.Event();closed=[];stalled=asyncio.Event()
 class Account:
  def __init__(self):self.session=SimpleNamespace(canonical_username=b'PRIVATE_RECIPIENT')
  def __enter__(self):return self
  def __exit__(self,*args):closed.append(1)
 def devices(c):return SimpleNamespace(devices=(SimpleNamespace(device_id=123,name='Garden@PRIVATE_OWNER'),),device_owner_types=((123,1),))
 async def stream(data,selected,writer,*,audio=False,options=None):
  starts.append((selected,audio));video=asyncio.StreamReader();sound=asyncio.StreamReader() if audio else None
  async def feed():
   try:
    for packet in packets:
     video.feed_data(packet)
     if sound:sound.feed_data(b'\xd5'*400)
     await asyncio.sleep(.05)
    if stall:
     stalled.set();await asyncio.Future()
   finally:
    video.feed_eof()
    if sound:sound.feed_eof()
  feeder=asyncio.create_task(feed())
  try:
   await mux_streams(video,writer,audio_reader=sound)
   await asyncio.Future()
  finally:
   feeder.cancel();await asyncio.gather(feeder,return_exceptions=True);ended.set()
 entry=ConfigEntry(version=1,minor_version=1,domain='virtavo',title='Fixture',data={'username':'fixture@example.invalid','password':'PRIVATE_ACCOUNT','country':'IT','language':'en','region':'fr','device':{'device_id':123,'name':'Garden','own_type':1}},options={'audio_enabled':audio},source='user',unique_id='fixture',discovery_keys=MappingProxyType({}),subentries_data=[])
 hass.config_entries._entries[entry.entry_id]=entry
 media=None
 try:
  with patch.object(http,'async_get_source_ip',AsyncMock(return_value='127.0.0.1')),patch.object(service,'open_account',lambda c:Account()),patch.object(service,'discover_account_devices',devices),patch.object(receiver,'run_camera_stream',stream),patch.object(socket,'create_connection',side_effect=AssertionError('External network forbidden')):
   assert await asyncio.wait_for(hass.config_entries.async_setup(entry.entry_id),20)
   await hass.async_block_till_done()
   from homeassistant.components.camera import DATA_COMPONENT
   camera=list(hass.data[DATA_COMPONENT].entities)[0]
   media=await camera.async_create_stream();assert not starts
   output=media.add_provider('hls');output.idle_timer.awake()
   started=time.monotonic();await media.start()
   async def wait_media():
    while True:
     segment=output.last_segment
     if segment is not None and segment.parts and segment.data_size_with_init>0:
      return segment
     await asyncio.sleep(.05)
   segment=await asyncio.wait_for(wait_media(),20)
   elapsed=time.monotonic()-started
   content=segment.init+b''.join(part.data for part in segment.parts)
   with av.open(io.BytesIO(content),format='mp4') as decoded:
    codecs=[s.codec_context.name for s in decoded.streams]
    counts={'video':0,'audio':0}
    for frame in decoded.decode():counts['audio' if isinstance(frame,av.AudioFrame) else 'video']+=1
   assert 'hevc' in codecs and counts['video']>0
   if audio:assert 'aac' in codecs and counts['audio']>0
   else:assert 'aac' not in codecs and counts['audio']==0
   assert starts==[(123,audio)]
   if stall:
    await asyncio.wait_for(stalled.wait(),12);await asyncio.sleep(.5)
   unload_started=time.monotonic()
   await asyncio.wait_for(hass.config_entries.async_unload(entry.entry_id),3 if stall else 12)
   unload_seconds=time.monotonic()-unload_started
   assert ended.is_set() and entry.state is ConfigEntryState.NOT_LOADED
   assert media._thread is None and getattr(entry,'runtime_data',None) is None
   assert not list(hass.data[DATA_COMPONENT].entities) and len(closed)==1
   print(json.dumps({'stalled_source':stall,'unload_seconds':round(unload_seconds,3),'synthetic_media':True,'real_HA_HLS_worker':True,'audio_enabled':audio,'codecs':codecs,'decoded_video_frames':counts['video'],'decoded_audio_frames':counts['audio'],'first_part_seconds':round(elapsed,2),'unload_closed_worker':True,'actual_HACS_download':False,'browser_playback':False,'cloud_or_camera_contacted':False}))
 finally:
  # HA stop closes any still-loaded owned integration after an assertion.
  if entry.state is ConfigEntryState.LOADED:
   await hass.config_entries.async_unload(entry.entry_id)
  await hass.async_stop(force=True)
asyncio.run(main())
'''

class HAMediaStreamTests(unittest.TestCase):
 def run_case(self,audio,stall=False):
  with tempfile.TemporaryDirectory(prefix='virtavo-ha-media-') as directory:
   stage=Path(directory)
   shutil.copytree(ROOT/'custom_components/virtavo',stage/'custom_components/virtavo',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   script=stage/'run.py';script.write_text(RUNNER)
   completed=subprocess.run([sys.executable,'-I',str(script),str(stage),str(int(audio)),str(int(stall))],cwd=stage,capture_output=True,text=True,timeout=65)
   self.assertEqual(completed.returncode,0,completed.stdout[-1000:]+completed.stderr[-5000:])
   result=json.loads(completed.stdout.strip().splitlines()[-1])
   self.assertGreater(result['decoded_video_frames'],0)
   self.assertEqual(result['audio_enabled'],audio)
   self.assertTrue(result['unload_closed_worker'])
   if stall:self.assertLess(result['unload_seconds'],3)
   print(json.dumps(result,sort_keys=True))
 def test_production_mux_to_real_HA_hls_video_only_and_audio_opt_in(self):
  for audio in (False,True):
   with self.subTest(audio=audio):self.run_case(audio)
 def test_stalled_source_unload_closes_owned_endpoint_before_reader_join(self):
  self.run_case(False,stall=True)

if __name__=='__main__':unittest.main()
