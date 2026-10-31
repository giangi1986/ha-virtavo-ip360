import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
BASE=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine'
p=types.ModuleType('manager_test_engine');p.__path__=[str(BASE)];sys.modules[p.__name__]=p
spec=importlib.util.spec_from_file_location(p.__name__+'.manager',BASE/'manager.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
from importlib import import_module
net=import_module(p.__name__+'.net_auth')

class ManagerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):self.servers=[];self.writers=[]
 async def asyncTearDown(self):
  for w in self.writers:w.close()
  await asyncio.gather(*(w.wait_closed() for w in self.writers),return_exceptions=True)
  for s in self.servers:s.close();await s.wait_closed()
 async def connect(self,handler,timeout=.2):
  async def server(r,w):
   self.writers.append(w)
   try:await handler(r,w)
   except (ConnectionError,asyncio.IncompleteReadError):pass
   finally:w.close()
  s=await asyncio.start_server(server,'127.0.0.1',0);self.servers.append(s)
  return await m.ManagerConnection.connect('127.0.0.1',s.sockets[0].getsockname()[1],timeout=timeout)
 async def read_request(self,r):
  h=await r.readexactly(20);total=net.HEADER.unpack(h)[4]
  return net.parse_frame(h+await r.readexactly(total-20))
 async def test_unsolicited_callback_does_not_satisfy_wrong_pending_command(self):
  async def handler(r,w):
   request=await self.read_request(r);self.assertEqual(request.command,20301)
   w.write(net.frame(20202,b'callback',revision=4836)+net.frame(20302,b'relay',revision=4836));await w.drain()
   await r.read()
  c=await self.connect(handler)
  try:
   raw=await c.request(net.frame(20301,b'',revision=4836),expected_command=20302)
   self.assertEqual(net.parse_frame(raw).payload,b'relay')
  finally:await c.close()
 async def test_fragmented_and_coalesced_frames_are_read_exactly(self):
  async def handler(r,w):
   await self.read_request(r)
   response=net.frame(7,b'time',revision=4836)
   for piece in [response[:3],response[3:18],response[18:]]:
    w.write(piece);await w.drain();await asyncio.sleep(.001)
   await r.read()
  c=await self.connect(handler)
  try:self.assertEqual(net.parse_frame(await c.request(net.frame(7,b'\0'*4,revision=4836),expected_command=7)).payload,b'time')
  finally:await c.close()
 async def test_timeout_abandons_channel_before_any_retry(self):
  async def handler(r,w):await self.read_request(r);await r.read()
  c=await self.connect(handler,timeout=.02)
  with self.assertRaises(asyncio.TimeoutError):
   await c.request(net.frame(7,b'',revision=4836),expected_command=7)
  self.assertTrue(c._closed)
  with self.assertRaises(net.ProtocolError):await c.request(net.frame(7,b'',revision=4836),expected_command=7)
 async def test_oversize_response_releases_waiter_and_closes(self):
  async def handler(r,w):
   await self.read_request(r);w.write(net.HEADER.pack(net.MAGIC,7,4836,105,65537,0));await w.drain();await r.read()
  c=await self.connect(handler)
  with self.assertRaises(net.ProtocolError):await c.request(net.frame(7,b'',revision=4836),expected_command=7)
  self.assertTrue(c._closed)
 async def test_cancellation_reaps_reader_and_closes_writer(self):
  async def handler(r,w):await self.read_request(r);await r.read()
  c=await self.connect(handler,timeout=1)
  task=asyncio.create_task(c.request(net.frame(7,b'',revision=4836),expected_command=7))
  await asyncio.sleep(.01);task.cancel()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertTrue(c._reader_task.done());self.assertTrue(c.writer.is_closing())

 async def test_two_native_requests_can_wait_for_one_correlated_record_response(self):
  async def handler(r,w):
   first=await self.read_request(r);second=await self.read_request(r)
   self.assertEqual(first.command,20202);self.assertEqual(second.command,20202)
   w.write(net.frame(20202,b'rich',revision=4836)+net.frame(20202,b'record',revision=4836))
   await w.drain();await r.read()
  c=await self.connect(handler)
  try:
   request=net.frame(20202,b'query',revision=4836)
   response=await c.request_packets((request,request),expected_command=20202,
                                  accept=lambda raw:net.parse_frame(raw).payload==b'record')
   self.assertEqual(net.parse_frame(response).payload,b'record')
  finally:await c.close()
