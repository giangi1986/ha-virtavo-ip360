"""Publication-specific synthetic A/V mux tests, not a camera/video retest."""
import asyncio
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

P=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine/av_mux.py'
spec=importlib.util.spec_from_file_location('test_av_mux_module',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Writer:
 def __init__(self):self.parts=[]
 def write(self,data):self.parts.append(data)
 async def drain(self):await asyncio.sleep(0)

class ArgsTests(unittest.TestCase):
 def test_audio_disabled_is_not_opened(self):
  args=m.ffmpeg_mux_args()
  self.assertIn('-an',args)
  self.assertNotIn('alaw',args)
 def test_audio_enabled_maps_real_alaw_track(self):
  args=m.ffmpeg_mux_args(audio_fd=42)
  self.assertIn('alaw',args);self.assertIn('8000',args);self.assertIn('pipe:42',args)
  self.assertIn('1:a:0',args);self.assertIn('aac',args);self.assertNotIn('-an',args)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg tools required')
class RealMuxTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  r=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=black:s=64x64:r=5:d=0.6','-c:v','libx265','-x265-params','pools=none:frame-threads=1:log-level=error','-f','hevc','pipe:1'],capture_output=True,timeout=20)
  if r.returncode:raise unittest.SkipTest('Synthetic HEVC encoder unavailable')
  cls.video=r.stdout
 async def test_hevc_and_g711a_are_muxed_as_video_and_audio(self):
  video=asyncio.StreamReader();video.feed_data(self.video);video.feed_eof()
  audio=asyncio.StreamReader();audio.feed_data(b'\xd5'*4800);audio.feed_eof()
  out=Writer()
  self.assertEqual(await asyncio.wait_for(m.mux_streams(video,out,audio_reader=audio,fps=5),15),0)
  with tempfile.NamedTemporaryFile(suffix='.ts') as file:
   file.write(b''.join(out.parts));file.flush()
   r=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_name,codec_type,sample_rate,channels','-of','json',file.name],capture_output=True,timeout=10)
  import json
  streams=json.loads(r.stdout)['streams']
  self.assertTrue(any(s['codec_name']=='hevc' for s in streams))
  self.assertTrue(any(s['codec_type']=='audio' and s['codec_name']=='aac' and s['sample_rate']=='8000' and s['channels']==1 for s in streams))
 async def test_video_only_has_no_audio_track(self):
  video=asyncio.StreamReader();video.feed_data(self.video);video.feed_eof();out=Writer()
  await asyncio.wait_for(m.mux_streams(video,out,fps=5),15)
  with tempfile.NamedTemporaryFile(suffix='.ts') as file:
   file.write(b''.join(out.parts));file.flush()
   r=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','csv=p=0',file.name],capture_output=True,timeout=10)
  self.assertNotIn(b'audio',r.stdout)
