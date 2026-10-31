import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock,patch
PATH=Path(__file__).resolve().parents[1]/'tools/check_stream.py'
spec=importlib.util.spec_from_file_location('stream_diag',PATH);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class StreamDiagnosticTests(unittest.IsolatedAsyncioTestCase):
 def config(self):return types.SimpleNamespace(country='IT')
 async def test_missing_dependencies_never_opens_account(self):
  with patch.object(d.shutil,'which',return_value=None),patch.object(d,'_open_owned',AsyncMock()) as opener:
   result,status=await d.probe(self.config())
  opener.assert_not_called();self.assertEqual(status,2);self.assertEqual(result['stage'],'preflight')
 async def test_private_auth_and_connection_errors_are_redacted(self):
  for error in (d.net.AuthenticationError('SECRET_EMAIL PASSWORD'),OSError('SECRET_IP SESSION')):
   with patch.object(d.shutil,'which',return_value='/fixture'),patch.object(d,'_open_owned',AsyncMock(side_effect=error)):
    result,status=await d.probe(self.config())
   self.assertNotIn('SECRET',json.dumps(result));self.assertEqual(status,4)
 async def test_invalid_country_does_not_open_network(self):
  with patch.object(d.shutil,'which',return_value='/fixture'),patch.object(d,'_open_owned',AsyncMock()) as opener:
   result,status=await d.probe(types.SimpleNamespace(country='CN'))
  opener.assert_not_called();self.assertEqual(status,4)
 async def test_late_thread_result_closed_after_cancel(self):
  import threading
  entered=threading.Event();release=threading.Event();closed=asyncio.Event();loop=asyncio.get_running_loop()
  def job(*args):entered.set();release.wait(1);return types.SimpleNamespace(close=lambda:loop.call_soon_threadsafe(closed.set))
  with patch.object(d,'_open',side_effect=job):
   task=asyncio.create_task(d._open_owned(None,0));await asyncio.to_thread(entered.wait,1);task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   release.set();await asyncio.wait_for(closed.wait(),1)
 def test_decoder_metadata_allowlist(self):
  raw=json.dumps({'streams':[{'codec_name':'hevc','codec_type':'video','nb_read_frames':'30','tags':{'title':'SECRET'}},{'codec_name':'aac','codec_type':'audio','nb_read_frames':'7'},{'codec_name':'SECRET','codec_type':'video','nb_read_frames':'9'}]})
  result=d._codec_counts(raw)
  self.assertEqual(result,{'video_frames':30,'audio_frames':7,'video_codec':'hevc','audio_codec':'aac'})
  self.assertNotIn('SECRET',json.dumps(result))
 def test_invalid_decoder_summary_is_rejected(self):
  for data in ([],{'streams':'private'},{'streams':['private']}):
   with self.assertRaises(ValueError):d._codec_counts(json.dumps(data))
 async def test_complete_probe_counts_only_allowlisted_summary_and_closes(self):
  await self.complete_probe()
 async def test_successful_decode_with_failed_cleanup_is_not_verified(self):
  await self.complete_probe(context_error=True)
 async def complete_probe(self,context_error=False):
  context=types.SimpleNamespace(device=types.SimpleNamespace(device_id=123),identity=types.SimpleNamespace(play_username=b'PRIVATE_SHARER',is_shared=True),close=lambda:None)
  close=unittest.mock.Mock(side_effect=RuntimeError('PRIVATE_CONTEXT') if context_error else None);context.close=close
  class Transport:
   def __init__(self,*args):self.stage='created';self.stats={'video_packets':1,'audio_packets':1};self.closed=0
   async def open(self):self.stage='streaming'
   async def pump(self,*args):await asyncio.Future()
   async def close(self):self.closed+=1
  transport=Transport()
  real_spawn=asyncio.create_subprocess_exec;children=[]
  async def spawn(*args,**kwargs):
   script='import sys,json;sys.stdin.buffer.read();print(json.dumps({"streams":[{"codec_name":"hevc","codec_type":"video","nb_read_frames":"3"},{"codec_name":"aac","codec_type":"audio","nb_read_frames":"2"}]}))'
   child=await real_spawn(sys.executable,'-c',script,**kwargs);children.append(child);return child
  async def pipeline(source,code,writer,**kwargs):
   self.assertEqual(code,'PRIVAT123')
   await source(AsyncMock(),AsyncMock());writer.write(b'fixture');await writer.drain()
  with patch.object(d.shutil,'which',return_value='/fixture'),patch.object(d,'_open_owned',AsyncMock(return_value=context)),patch.object(d.receiver,'RelayReceiver',return_value=transport),patch.object(d.receiver,'run_media_pipeline',pipeline),patch.object(d.asyncio,'create_subprocess_exec',spawn):
   result,status=await d.probe(self.config(),seconds=1)
  self.assertEqual(status,4 if context_error else 0);self.assertEqual(result['video_frames'],3);self.assertEqual(result['audio_frames'],2)
  self.assertEqual(result['status'],'cleanup_error' if context_error else 'verified')
  self.assertNotIn('PRIVATE',json.dumps(result));close.assert_called_once();self.assertGreaterEqual(transport.closed,1)
  self.assertTrue(all(child.returncode is not None for child in children))
 async def cleanup_failure(self,*,transport_error=False,context_error=False):
  close=unittest.mock.Mock(side_effect=RuntimeError('PRIVATE_CONTEXT') if context_error else None)
  context=types.SimpleNamespace(device=types.SimpleNamespace(device_id=123),identity=types.SimpleNamespace(play_username=b'PRIVATE_SHARER',is_shared=True),close=close)
  transport=types.SimpleNamespace(stage='created',stats={'video_packets':0},close=AsyncMock(side_effect=RuntimeError('PRIVATE_TRANSPORT') if transport_error else None))
  real_spawn=asyncio.create_subprocess_exec;children=[]
  async def spawn(*args,**kwargs):
   child=await real_spawn(sys.executable,'-c','import sys;sys.stdin.buffer.read()',**kwargs);children.append(child);return child
  with patch.object(d.shutil,'which',return_value='/fixture'),patch.object(d,'_open_owned',AsyncMock(return_value=context)),patch.object(d.receiver,'RelayReceiver',return_value=transport),patch.object(d.receiver,'run_media_pipeline',AsyncMock(side_effect=RuntimeError('PRIVATE_PIPELINE'))),patch.object(d.asyncio,'create_subprocess_exec',spawn):
   result,status=await d.probe(self.config(),seconds=1)
  self.assertEqual(status,4);self.assertEqual(result['status'],'cleanup_error')
  self.assertNotIn('PRIVATE',json.dumps(result));close.assert_called_once();transport.close.assert_awaited_once()
  self.assertTrue(children);self.assertTrue(all(child.returncode is not None for child in children))
 async def test_transport_close_failure_still_closes_account_and_decoder(self):
  await self.cleanup_failure(transport_error=True)
 async def test_account_close_failure_still_reaps_decoder(self):
  await self.cleanup_failure(context_error=True)
 async def test_reap_owned_child_on_cleanup(self):
  p=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(30)',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
  await d._reap(p);self.assertIsNotNone(p.returncode)

if __name__=='__main__':unittest.main()

class LoginFeedbackTests(unittest.TestCase):
 def test_login_feedback_precedes_discovery_and_contains_no_account_data(self):
  from unittest.mock import Mock
  context=types.SimpleNamespace(session=types.SimpleNamespace(canonical_username=b'PRIVATE'),close=Mock())
  order=[]
  def discovered(connection):
   self.assertEqual(order,['login_accepted'])
   return types.SimpleNamespace(devices=())
  with patch.object(d.account,'open_account',return_value=context),patch.object(d.discovery,'discover_account_devices',side_effect=discovered):
   with self.assertRaises(ValueError):d._open(None,0,lambda:order.append('login_accepted'))
  self.assertEqual(order,['login_accepted'])
 def test_rejected_login_never_reports_success(self):
  from unittest.mock import Mock
  notify=Mock()
  with patch.object(d.account,'open_account',side_effect=d.net.AuthenticationError('rejected')):
   with self.assertRaises(d.net.AuthenticationError):d._open(None,0,notify)
  notify.assert_not_called()
