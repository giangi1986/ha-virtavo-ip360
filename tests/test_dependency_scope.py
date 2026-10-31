"""Bound the Pillow finding to actual Virtavo HA paths, without exploit inputs.

Reuse the proven media fixture. The new publication requirement is that real
HLS output and unsupported-image requests do not invoke Pillow image APIs.
This is not a claim about every Home Assistant integration or every execution.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_ha_media_stream import RUNNER as MEDIA_RUNNER

ROOT = Path(__file__).resolve().parents[1]
MARKER = "   media=await camera.async_create_stream();assert not starts"
GUARD = r'''
   from contextlib import ExitStack
   from PIL import Image as PillowImage
   from aiohttp import web
   from aiohttp.test_utils import make_mocked_request
   from homeassistant.components.camera import CameraImageView, DATA_COMPONENT
   from homeassistant.components.http import KEY_AUTHENTICATED
   pillow_calls=[]
   def forbidden_pillow(*args,**kwargs):
    pillow_calls.append(True)
    raise AssertionError('Pillow image processing entered the Virtavo path')
   # Decoder/encoder entry points and related transform operations appearing
   # in the advisory report; no malicious image, PoC or native exploit runs.
   guards=ExitStack()
   for name in ('open','new','frombytes','frombuffer','fromarray','merge'):
    guards.enter_context(patch.object(PillowImage,name,forbidden_pillow))
   for name in ('save','convert','filter','transform','quantize','getexif'):
    guards.enter_context(patch.object(PillowImage.Image,name,forbidden_pillow))
   assert not camera.use_stream_for_stills
   assert await camera.async_camera_image() is None
   view=CameraImageView(hass.data[DATA_COMPONENT])
   for query in ('','?width=128&height=72'):
    request=make_mocked_request('GET','/api/camera_proxy/'+camera.entity_id+query)
    request[KEY_AUTHENTICATED]=True
    try:
     await view.get(request,camera.entity_id)
    except web.HTTPInternalServerError:
     pass
    else:
     raise AssertionError('Unsupported still image unexpectedly returned data')
   request=make_mocked_request('GET','/api/camera_proxy/'+camera.entity_id)
   request[KEY_AUTHENTICATED]=False
   try:
    await view.get(request,camera.entity_id)
   except (web.HTTPForbidden,web.HTTPUnauthorized):
    pass
   else:
    raise AssertionError('Unauthenticated image access was accepted')
   assert not starts, 'Unsupported images must not wake the camera'
'''


class DependencyScopeTests(unittest.TestCase):
    def test_actual_HA_stream_and_image_requests_do_not_enter_Pillow_image_APIs(self):
        self.assertEqual(MEDIA_RUNNER.count(MARKER), 1)
        runner = MEDIA_RUNNER.replace(MARKER, GUARD + "\n" + MARKER)
        end = "   print(json.dumps({'stalled_source':stall,"
        self.assertEqual(runner.count(end), 1)
        runner = runner.replace(
            end,
            "   assert not pillow_calls\n"
            "   guards.close()\n"
            "   print(json.dumps({'Pillow_image_API_calls':len(pillow_calls),"
            "'unsupported_image_requests':2,'unsupported_images_woke_camera':False,"
            "'unauthenticated_image_access_rejected':True,"
            "'scope':'actual_HA_HLS_audio_and_unsupported_stills_only',"
            "'host_vulnerabilities_fixed':False,'stalled_source':stall,",
        )
        with tempfile.TemporaryDirectory(prefix='virtavo-dependency-scope-') as directory:
            stage = Path(directory)
            shutil.copytree(
                ROOT / 'custom_components/virtavo', stage / 'custom_components/virtavo',
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'),
            )
            script = stage / 'check_scope.py'
            script.write_text(runner)
            completed = subprocess.run(
                [sys.executable, '-I', str(script), str(stage), '1', '0'],
                cwd=stage, capture_output=True, text=True, timeout=65,
            )
            self.assertEqual(
                completed.returncode, 0,
                completed.stdout[-1000:] + completed.stderr[-5000:],
            )
            result = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(result['Pillow_image_API_calls'], 0)
            self.assertEqual(result['unsupported_image_requests'], 2)
            self.assertFalse(result['unsupported_images_woke_camera'])
            self.assertTrue(result['unauthenticated_image_access_rejected'])
            self.assertGreater(result['decoded_video_frames'], 0)
            self.assertGreater(result['decoded_audio_frames'], 0)
            self.assertTrue(result['unload_closed_worker'])
            print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
