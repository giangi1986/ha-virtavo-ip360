"""Fresh NET account -> manager -> owned relay UDP -> Python DES/mux.

No captured session, SDK, fixed camera address or background domestic service.
UDP payload order is preserved as received; loss recovery is not implemented.
"""
import asyncio
import contextlib
import math
import socket
import struct

from . import device_protocol as wire
from .audio import parse_audio_packet
from .manager import ManagerConnection
from .media_pipeline import run_media_pipeline
from .net_auth import ProtocolError, manager_signin
from .receiver_control import connect_ack, parse_device_route_state, udp_close, udp_keepalive
from .service import async_open_device


def country_mode(country):
    """Audited non-CN getPlayNetType: two upper-case country bytes."""
    if not isinstance(country,str) or len(country)!=2 or not country.isascii() or not country.isalpha():
        raise ValueError('Two-letter country required')
    country=country.upper()
    if country=='CN':
        raise ValueError('CN carrier routing is not supported by this beta')
    return int.from_bytes(country.encode('ascii'),'big')


def signin_ack(packet):
    body=wire.payload(packet,20200)
    if len(body)!=132 or struct.unpack_from('<I',body)[0]!=2:
        raise ProtocolError('Unexpected manager sign-in response')


class RelayReceiver:
    """One selected device and one owned transport; bounded startup/idle."""
    def __init__(self,context,device_id,country,*,timeout=8,idle_timeout=15):
        self.context=context
        self.device_id=wire.uint(device_id)
        if not self.device_id:raise ValueError('Selected device required')
        self.mode=country_mode(country)
        for value in (timeout,idle_timeout):
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Finite positive timeout required')
        self.timeout=timeout
        self.idle_timeout=idle_timeout
        self.manager=None
        self.sock=None
        self.relay=None
        self.father_id=None
        self.stage='created'
        self.stats={'video_packets':0,'audio_packets':0,'audio_discarded':0,'invalid_packets':0}

    async def open(self):
        session=self.context.connection.session
        self.stage='manager_connect'
        self.manager=await ManagerConnection.connect(session.manager_host,session.manager_port,timeout=self.timeout)
        self.stage='manager_signin'
        signin_ack(await self.manager.request(manager_signin(session,access_sign_in_type=0,
                   device_magic=0,revision=4836),expected_command=20200))
        self.stage='manager_time'
        await self.manager.request(wire.manager_time_request(),expected_command=7)
        self.stage='device_state'
        def accept_state(packet):
            # Rich log-only callbacks and other selected devices are not replies
            # to this query. Malformed matching records fail closed.
            if len(packet)==152:return False
            if len(packet)>=28 and struct.unpack_from('<I',packet,24)[0]!=self.device_id:return False
            return parse_device_route_state(packet,self.device_id) is not None
        raw=await self.manager.request_packets(wire.online_state_requests(self.device_id),
                                              expected_command=20202,accept=accept_state)
        state=parse_device_route_state(raw,self.device_id)
        if not state.online or not state.father_id:raise ProtocolError('Selected device has no online route')
        self.father_id=state.father_id
        local_host=self.manager.writer.get_extra_info('sockname')[0]
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((local_host,0))
        local_port=self.sock.getsockname()[1]
        self.stage='relay_route'
        raw=await self.manager.request(wire.relay_request(self.device_id,session.owner_client_id,
                 father_id=self.father_id,peer_type=0,local_host=local_host,public_host='0.0.0.0',
                 local_port=local_port,mode=self.mode,flags=0),expected_command=20302)
        relay=wire.parse_relay(raw)
        if relay.camera_session!=self.device_id:raise ProtocolError('Relay selected-device mismatch')
        self.relay=(relay.host,relay.port)
        self.stage='udp_connect'
        loop=asyncio.get_running_loop()
        await loop.sock_sendto(self.sock,wire.udp_stun(self.device_id,session.owner_client_id,peer_type=0),self.relay)
        await loop.sock_sendto(self.sock,wire.udp_connect(self.device_id,session.owner_client_id,
                             peer_type=0,father_id=self.father_id),self.relay)
        deadline=loop.time()+self.timeout
        while True:
            if loop.time()>=deadline:raise TimeoutError('Relay handshake timed out')
            packet,source=await asyncio.wait_for(loop.sock_recvfrom(self.sock,65536),max(.001,deadline-loop.time()))
            if source!=self.relay:continue
            try:connect_ack(packet,self.device_id)
            except ValueError:
                self.stats['invalid_packets']+=1
                continue
            self.stage='streaming'
            return

    async def pump(self,send_video,send_audio):
        loop=asyncio.get_running_loop()
        session=self.context.connection.session
        async def keepalive():
            while True:
                await loop.sock_sendto(self.sock,udp_keepalive(self.device_id,session.owner_client_id,peer_type=0),self.relay)
                await asyncio.sleep(3)
        heartbeat=asyncio.create_task(keepalive())
        deadline=loop.time()+self.idle_timeout
        try:
            while True:
                if heartbeat.done():heartbeat.result()
                if loop.time()>=deadline:raise TimeoutError('Relay media timed out')
                packet,source=await asyncio.wait_for(loop.sock_recvfrom(self.sock,65536),max(.001,deadline-loop.time()))
                if source!=self.relay:continue
                try:
                    media=wire.parse_media_packet(packet)
                    if struct.unpack_from('<I',packet,20)[0]!=self.device_id:continue
                    if not media.payload or struct.unpack_from('<I',packet,44)[0]!=len(media.payload):
                        raise ValueError('Invalid native media payload length')
                    if media.is_audio:
                        if send_audio is None:
                            self.stats['audio_discarded']+=1
                            continue
                        block=parse_audio_packet(packet).alaw
                    elif media.media_type not in (0,1):continue
                except ValueError:
                    self.stats['invalid_packets']+=1
                    continue
                if media.is_audio:
                    await asyncio.wait_for(send_audio(block),self.idle_timeout)
                    self.stats['audio_packets']+=1
                else:
                    await asyncio.wait_for(send_video(media.payload),self.idle_timeout)
                    self.stats['video_packets']+=1
                    # H.265 is required. Audio-only traffic must not keep a
                    # failed video session alive indefinitely.
                    deadline=loop.time()+self.idle_timeout
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat,return_exceptions=True)

    async def close(self):
        if self.sock is not None:
            if self.relay is not None and self.father_id is not None:
                packet=udp_close(self.device_id,self.context.connection.session.owner_client_id,
                                 peer_type=0,father_id=self.father_id)
                for _ in range(3):
                    with contextlib.suppress(OSError,asyncio.TimeoutError):
                        await asyncio.wait_for(asyncio.get_running_loop().sock_sendto(self.sock,packet,self.relay),.2)
            self.sock.close()
            self.sock=None
        if self.manager is not None:
            await self.manager.close()
            self.manager=None


async def run_camera_stream(data,device_id,output_writer,*,audio=False,options=None):
    options=dict(options or {})
    # Validate before opening any network connection.
    country=options.get('country',data.get('country','IT'))
    country_mode(country)
    if not wire.uint(device_id):raise ValueError('Selected device required')
    context=await async_open_device(data,device_id,options)
    receiver=None
    try:
        receiver=RelayReceiver(context,device_id,country)
        code=wire.des_initial_code(context.identity.play_username,device_id)
        async def source(video_sink,audio_sink):
            try:
                await receiver.open()
                await receiver.pump(video_sink,audio_sink)
            finally:await receiver.close()
        await run_media_pipeline(source,code,output_writer,audio=audio)
    finally:
        try:
            if receiver is not None:await receiver.close()
        finally:context.close()
