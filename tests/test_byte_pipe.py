import asyncio
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine/byte_pipe.py'
spec=importlib.util.spec_from_file_location('test_bytepipe_module',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BytePipeTests(unittest.IsolatedAsyncioTestCase):
 async def test_normal_eof_preserves_every_buffered_byte(self):
  pipe=m.BytePipe();await pipe.put(b'a'*40000);await pipe.put(b'b'*40000);await pipe.feed_eof()
  self.assertEqual(await pipe.read(65536),b'a'*40000+b'b'*25536)
  self.assertEqual(await pipe.read(65536),b'b'*14464)
  self.assertEqual(await pipe.read(1),b'')
 async def test_capacity_backpressures_then_resumes_on_read(self):
  pipe=m.BytePipe(65536);await pipe.put(b'a'*65536)
  put=asyncio.create_task(pipe.put(b'b'));await asyncio.sleep(0)
  self.assertFalse(put.done())
  self.assertEqual(len(await pipe.read()),65536)
  await asyncio.wait_for(put,1)
  self.assertEqual(await pipe.read(1),b'b')
 async def test_close_releases_waiting_reader_and_blocked_producer(self):
  pipe=m.BytePipe(65536);reader=asyncio.create_task(pipe.read())
  await asyncio.sleep(0);await pipe.feed_eof();self.assertEqual(await reader,b'')
  pipe=m.BytePipe(65536);await pipe.put(b'x'*65536)
  writer=asyncio.create_task(pipe.put(b'y'));await asyncio.sleep(0);await pipe.feed_eof()
  with self.assertRaises(ConnectionError):await writer
  self.assertEqual(len(await pipe.read()),65536)
 async def test_cancelled_put_never_inserts_partial_chunk(self):
  pipe=m.BytePipe(65536);await pipe.put(b'a'*65536)
  put=asyncio.create_task(pipe.put(b'private'));await asyncio.sleep(0);put.cancel()
  await asyncio.gather(put,return_exceptions=True)
  self.assertEqual(await pipe.read(),b'a'*65536)
  await pipe.feed_eof();self.assertEqual(await pipe.read(),b'')
