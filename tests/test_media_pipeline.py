import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine'
p=types.ModuleType('media_pipeline_test_engine');p.__path__=[str(BASE)];sys.modules[p.__name__]=p
spec=importlib.util.spec_from_file_location(p.__name__+'.media_pipeline',BASE/'media_pipeline.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

class MediaPipelineTests(unittest.IsolatedAsyncioTestCase):
 async def test_actual_des_worker_uses_private_fd_and_drains_nonvideo_source(self):
  out=[];audio=[];command=[]
  async def mux(video,writer,*,audio_reader,fps):
   async def drain_audio():
    while data:=await audio_reader.read():audio.append(data)
   audio_task=asyncio.create_task(drain_audio())
   while data:=await video.read(65536):out.append(data)
   await audio_task
   return 0
  async def source(video,audio_sink):
   await video(b'non-video-synthetic-bytes')
   await audio_sink(b'\xd5'*160)
  original=m.asyncio.create_subprocess_exec
  async def spawn(*args,**kwargs):
   command.extend(args)
   return await original(*args,**kwargs)
  with patch.object(m,'mux_streams',side_effect=mux),patch.object(m.asyncio,'create_subprocess_exec',side_effect=spawn):
   self.assertEqual(await m.run_media_pipeline(source,'SYNTHETIC_PRIVATE_KEY',None,audio=True),0)
  self.assertEqual(b''.join(out),b'non-video-synthetic-bytes')
  self.assertEqual(b''.join(audio),b'\xd5'*160)
  self.assertIn('--code-fd',command)
  self.assertNotIn('--code-file',command)
  self.assertNotIn('SYNTHETIC_PRIVATE_KEY',str(command))
 async def test_audio_disabled_supplies_no_audio_sink_and_stops_worker(self):
  async def mux(video,writer,*,audio_reader,fps):
   self.assertIsNone(audio_reader)
   while await video.read(65536):pass
   return 0
  async def source(video,audio_sink):
   self.assertIsNone(audio_sink);await video(b'x')
  with patch.object(m,'mux_streams',side_effect=mux):
   self.assertEqual(await m.run_media_pipeline(source,'synthetic',None),0)
 async def test_cancel_stops_source_and_actual_des_child(self):
  started=asyncio.Event();stopped=asyncio.Event();children=[]
  async def source(video,audio_sink):
   started.set()
   try:await asyncio.Event().wait()
   finally:stopped.set()
  async def mux(video,writer,**kwargs):
   while await video.read(65536):pass
  original=m.asyncio.create_subprocess_exec
  async def spawn(*args,**kwargs):
   child=await original(*args,**kwargs);children.append(child);return child
  with patch.object(m,'mux_streams',side_effect=mux),patch.object(m.asyncio,'create_subprocess_exec',side_effect=spawn):
   task=asyncio.create_task(m.run_media_pipeline(source,'synthetic',None))
   await started.wait();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(task,5)
  self.assertTrue(stopped.is_set())
  self.assertTrue(all(child.returncode is not None for child in children))
 async def test_source_failure_is_not_a_successful_stream(self):
  async def source(video,audio_sink):raise ConnectionError('synthetic source failure')
  async def mux(video,writer,**kwargs):
   while await video.read(65536):pass
  with patch.object(m,'mux_streams',side_effect=mux):
   with self.assertRaises(ConnectionError):await m.run_media_pipeline(source,'synthetic',None)
