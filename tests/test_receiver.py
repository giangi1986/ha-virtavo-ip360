"""Fresh transport contract using only synthetic localhost TCP/UDP peers."""
import asyncio
import importlib
from pathlib import Path
import socket
import struct
import sys
import types
import unittest
from unittest.mock import AsyncMock,patch
BASE=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine'
p=types.ModuleType('receiver_test_engine');p.__path__=[str(BASE)];sys.modules[p.__name__]=p
r=importlib.import_module(p.__name__+'.receiver')
w=r.wire
n=importlib.import_module(p.__name__+'.net_auth')

class ReceiverTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.udp.setblocking(False);self.udp.bind(('127.0.0.1',0))
  self.writers=[];self.frames=[];self.selected=123;self.offline=False;self.wrong_relay=False
  self.server=await asyncio.start_server(self.manager,'127.0.0.1',0)
  s=n.NetSession(7,7,9,struct.unpack('<I',socket.inet_aton('127.0.0.1'))[0],self.server.sockets[0].getsockname()[1],b'S'*128,b'RECIPIENT')
  self.closed=0
  def close():self.closed+=1
  self.context=types.SimpleNamespace(connection=types.SimpleNamespace(session=s),identity=types.SimpleNamespace(play_username=b'SHARER'),close=close)
  self.receiver=r.RelayReceiver(self.context,self.selected,'IT',timeout=.15,idle_timeout=.08)
 async def asyncTearDown(self):
  await self.receiver.close()
  self.udp.close()
  for x in self.writers:x.close()
  await asyncio.gather(*(x.wait_closed() for x in self.writers),return_exceptions=True)
  self.server.close();await self.server.wait_closed()
 async def manager(self,reader,writer):
  self.writers.append(writer)
  try:
   while True:
    header=await reader.readexactly(20);command=w.HEADER.unpack(header)[1];size=w.HEADER.unpack(header)[4]
    raw=header+await reader.readexactly(size-20);self.frames.append(raw)
    if command==20200:response=w.frame(20200,struct.pack('<I',2)+bytes(128))
    elif command==7:response=w.frame(7,bytes(8))
    elif command==20202:
     # Two requests native; a rich callback must not satisfy correlation.
     body=struct.pack('<III',0,self.selected,0 if self.offline else 1)
     if not self.offline:body+=struct.pack('<III',456,0,0)
     response=w.frame(20202,bytes(132))+w.frame(20202,body)
    elif command==20301:
     body=bytearray(44);struct.pack_into('<I',body,4,999 if self.wrong_relay else self.selected)
     body[20:24]=socket.inet_aton('127.0.0.1');struct.pack_into('>H',body,24,self.udp.getsockname()[1]);response=w.frame(20302,bytes(body))
    else:raise AssertionError(command)
    writer.write(response);await writer.drain()
  except (asyncio.IncompleteReadError,ConnectionError):pass
  finally:writer.close()
 async def handshake(self):
  task=asyncio.create_task(self.receiver.open());loop=asyncio.get_running_loop()
  a,source=await asyncio.wait_for(loop.sock_recvfrom(self.udp,65536),1)
  b,source2=await asyncio.wait_for(loop.sock_recvfrom(self.udp,65536),1)
  self.assertEqual(source,source2);self.assertEqual([w.HEADER.unpack_from(x)[1] for x in (a,b)],[40031,40036])
  ack=bytearray(w.frame(40037,bytes(32)));struct.pack_into('<I',ack,40,self.selected)
  await loop.sock_sendto(self.udp,bytes(ack),source);await task
  return source
 def media(self,kind,data,*,device=123):
  body=bytearray(28);struct.pack_into('<I',body,0,device);struct.pack_into('<H',body,8,kind);struct.pack_into('<I',body,24,len(data))
  return w.frame(40005,bytes(body)+data)
 async def assert_local_timeout(self,coro,*,limit=.25):
  # Distinguish the receiver's own deadline from a test-harness timeout.
  task=asyncio.create_task(coro)
  try:
   done,_=await asyncio.wait({task},timeout=limit)
   self.assertIn(task,done,'Receiver did not enforce its own finite deadline')
   with self.assertRaises(TimeoutError):await task
  finally:
   task.cancel();await asyncio.gather(task,return_exceptions=True)
 async def test_fresh_route_country_owned_port_and_cleanup(self):
  source=await self.handshake()
  raw=next(x for x in self.frames if w.HEADER.unpack_from(x)[1]==20301)
  self.assertEqual(struct.unpack_from('<H',raw,20)[0],0x4954)
  self.assertEqual(struct.unpack_from('<III',raw,28),(456,7,0))
  self.assertEqual(raw[40:44],bytes(4));self.assertEqual(struct.unpack_from('>H',raw,44)[0],source[1])
  self.assertEqual(struct.unpack_from('<H',raw,46)[0],0)
  await self.receiver.close()
  packet,_=await asyncio.wait_for(asyncio.get_running_loop().sock_recvfrom(self.udp,65536),1)
  self.assertEqual(w.HEADER.unpack_from(packet)[1],40038)
  self.assertIsNone(self.receiver.sock);self.assertIsNone(self.receiver.manager)
 async def test_wrong_selected_device_in_relay_fails_closed(self):
  self.wrong_relay=True
  with self.assertRaises(r.ProtocolError):await self.receiver.open()
  self.assertNotEqual(self.receiver.stage,'streaming')
 async def test_offline_has_no_static_father_fallback(self):
  self.offline=True
  with self.assertRaises(r.ProtocolError):await self.receiver.open()
  self.assertIsNone(self.receiver.sock)
 async def test_media_correlation_audio_off_and_idle(self):
  source=await self.handshake();video=[]
  async def sink(data):video.append(data)
  task=asyncio.create_task(self.receiver.pump(sink,None));loop=asyncio.get_running_loop()
  for packet in [self.media(0,b'FOREIGN',device=999),self.media(3,b'AUDIO'),self.media(0,b'VIDEO')]:await loop.sock_sendto(self.udp,packet,source)
  with self.assertRaises(TimeoutError):await task
  self.assertEqual(video,[b'VIDEO']);self.assertEqual(self.receiver.stats['audio_discarded'],1)
 async def test_audio_on_routes_only_valid_bounded_alaw(self):
  source=await self.handshake();audio=[]
  async def sink(data):audio.append(data)
  task=asyncio.create_task(self.receiver.pump(AsyncMock(),sink));loop=asyncio.get_running_loop()
  await loop.sock_sendto(self.udp,self.media(3,b'\xd5'*160),source)
  with self.assertRaises(TimeoutError):await task
  self.assertEqual(audio,[b'\xd5'*160]);self.assertEqual(self.receiver.stats['audio_packets'],1)
 async def test_cancel_closes_receiver_and_account(self):
  entered=asyncio.Event()
  async def pipeline(source,code,writer,**kwargs):
   self.assertEqual(code,'SHARER123');entered.set();await asyncio.Future()
  with patch.object(r,'async_open_device',AsyncMock(return_value=self.context)),patch.object(r,'run_media_pipeline',pipeline):
   task=asyncio.create_task(r.run_camera_stream({'country':'IT'},123,None));await entered.wait();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
  self.assertEqual(self.closed,1)
 async def test_invalid_country_opens_no_account(self):
  with patch.object(r,'async_open_device',AsyncMock()) as opener:
   for country in ('CN','ITA','',None):
    with self.assertRaises(ValueError):await r.run_camera_stream({'country':country},123,None)
   opener.assert_not_called()
 async def test_receiver_constructor_error_closes_open_account(self):
  with patch.object(r,'async_open_device',AsyncMock(return_value=self.context)),patch.object(r,'RelayReceiver',side_effect=ValueError('invalid')):
   with self.assertRaises(ValueError):await r.run_camera_stream({'country':'IT'},123,None)
  self.assertEqual(self.closed,1)
 async def test_cleanup_failure_still_closes_account(self):
  fake=types.SimpleNamespace(close=AsyncMock(side_effect=OSError('closed')))
  with patch.object(r,'async_open_device',AsyncMock(return_value=self.context)),patch.object(r,'RelayReceiver',return_value=fake),patch.object(r,'run_media_pipeline',AsyncMock()):
   with self.assertRaises(OSError):await r.run_camera_stream({'country':'IT'},123,None)
  self.assertEqual(self.closed,1)
 async def test_invalid_device_opens_no_account(self):
  with patch.object(r,'async_open_device',AsyncMock()) as opener:
   for device in (0,-1,True,'123'):
    with self.assertRaises(ValueError):await r.run_camera_stream({'country':'IT'},device,None)
   opener.assert_not_called()
 def test_timeouts_are_finite_positive_numbers(self):
  for value in (float('nan'),float('inf'),float('-inf'),0,-1,True,'8'):
   for name in ('timeout','idle_timeout'):
    with self.assertRaises(ValueError):r.RelayReceiver(self.context,123,'IT',**{name:value})
 async def test_audio_only_does_not_extend_required_video_deadline(self):
  source=await self.handshake();loop=asyncio.get_running_loop()
  async def flood():
   while True:
    await loop.sock_sendto(self.udp,self.media(3,b'\xd5'*160),source)
    await asyncio.sleep(.005)
  traffic=asyncio.create_task(flood())
  try:
   await self.assert_local_timeout(self.receiver.pump(AsyncMock(),AsyncMock()))
   self.assertGreater(self.receiver.stats['audio_packets'],0)
  finally:
   traffic.cancel();await asyncio.gather(traffic,return_exceptions=True)
 async def test_invalid_media_traffic_does_not_starve_absolute_deadline(self):
  source=await self.handshake();loop=asyncio.get_running_loop()
  async def flood():
   while True:
    await loop.sock_sendto(self.udp,b'invalid',source)
    await asyncio.sleep(0)
  traffic=asyncio.create_task(flood())
  try:
   await self.assert_local_timeout(self.receiver.pump(AsyncMock(),None))
   self.assertGreater(self.receiver.stats['invalid_packets'],0)
  finally:
   traffic.cancel();await asyncio.gather(traffic,return_exceptions=True)
 async def test_video_length_mismatch_rejected_before_des_sink(self):
  source=await self.handshake();loop=asyncio.get_running_loop()
  packet=bytearray(self.media(0,b'VIDEO'));struct.pack_into('<I',packet,44,999)
  await loop.sock_sendto(self.udp,bytes(packet),source);sink=AsyncMock()
  with self.assertRaises(TimeoutError):await self.receiver.pump(sink,None)
  sink.assert_not_called();self.assertEqual(self.receiver.stats['invalid_packets'],1)
 async def test_stalled_sink_has_finite_deadline(self):
  source=await self.handshake();loop=asyncio.get_running_loop()
  await loop.sock_sendto(self.udp,self.media(0,b'VIDEO'),source)
  async def stalled(data):await asyncio.Future()
  await self.assert_local_timeout(self.receiver.pump(stalled,None))
 async def test_invalid_handshake_traffic_does_not_starve_absolute_deadline(self):
  loop=asyncio.get_running_loop();task=asyncio.create_task(self.receiver.open())
  _,source=await asyncio.wait_for(loop.sock_recvfrom(self.udp,65536),1)
  await asyncio.wait_for(loop.sock_recvfrom(self.udp,65536),1)
  async def flood():
   while True:
    await loop.sock_sendto(self.udp,b'invalid',source)
    await asyncio.sleep(0)
  traffic=asyncio.create_task(flood())
  try:
   done,_=await asyncio.wait({task},timeout=.4)
   self.assertIn(task,done,'Handshake deadline was starved by invalid packets')
   with self.assertRaises(TimeoutError):await task
   self.assertGreater(self.receiver.stats['invalid_packets'],0)
  finally:
   task.cancel();traffic.cancel();await asyncio.gather(task,traffic,return_exceptions=True)
 def test_strict_signin_shape(self):
  for body in (bytes(132),struct.pack('<I',2),struct.pack('<I',3)+bytes(128)):
   with self.assertRaises((ValueError,r.ProtocolError)):r.signin_ack(w.frame(20200,body))
  r.signin_ack(w.frame(20200,struct.pack('<I',2)+bytes(128)))

if __name__=='__main__':unittest.main()
