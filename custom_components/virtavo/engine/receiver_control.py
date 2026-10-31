"""Pure receiver control recovered from the audited native SDK; no sockets.

All session and app parameters are supplied by the caller. A correlated ACK is
transport evidence, not a successful video decode or account-ownership proof.
"""
from dataclasses import dataclass, field
import struct

MAGIC=bytes.fromhex('ccddeeff')
HEADER=struct.Struct('<4sIHHII')


def uint(value,bits=32):
    if type(value) is not int or not 0<=value<1<<bits:
        raise ValueError('Invalid protocol integer')
    return value


def frame(command,body,*,revision=4836,version=105):
    return HEADER.pack(MAGIC,uint(command),uint(revision,16),uint(version,16),20+len(body),0)+body


def _body(packet,command):
    if not isinstance(packet,bytes) or not 20<=len(packet)<=65536:
        raise ValueError('Invalid control packet size')
    magic,code,revision,version,size,status=HEADER.unpack_from(packet)
    if magic!=MAGIC or code!=command or size!=len(packet) or status:
        raise ValueError('Unexpected, truncated or error control packet')
    return packet[20:]


def udp_keepalive(camera_session,owner_id,*,peer_type,revision=4836):
    """Native keep_alive64 command17: owner32, peer32, cameraSession32."""
    return frame(17,struct.pack('<III',uint(owner_id),uint(peer_type),uint(camera_session)),revision=revision)


def udp_close(camera_session,owner_id,*,peer_type,father_id,revision=4836):
    """Native close64 command40038, full48. Only close the owned route."""
    body=struct.pack('<IIQIQ',uint(owner_id),uint(peer_type),uint(father_id,64),uint(camera_session),0x10001)
    return frame(40038,body,revision=revision)


def connect_ack(packet,expected_camera_session):
    """Check52-byte40037 ACK and full40 correlation; ignore opaque tail.

    The native handler uses length52 and cameraSession at40. This additionally
    fails closed on nonzero transport status; no tail status is invented.
    """
    uint(expected_camera_session)
    _body(packet,40037)
    if len(packet)!=52:
        raise ValueError('Invalid connect ACK length')
    actual=struct.unpack_from('<I',packet,40)[0]
    if not expected_camera_session or actual!=expected_camera_session:
        raise ValueError('Connect ACK session mismatch')
    return True


@dataclass(frozen=True)
class DeviceRouteState:
    device_id:int=field(repr=False)
    father_id:int|None=field(repr=False)
    records:tuple[tuple[int,int,int],...]=field(repr=False)

    @property
    def online(self):
        return bool(self.records)


def parse_device_route_state(packet,expected_device_id):
    """Parse native20202 list response and derive dynamic fatherID.

    Full152 is a different rich/log-only response in the SDK and returnsNone.
    Other native responses carry queried deviceID at24, recordCount at28 and
    count*12 bytes from32. The SDK sets father_id from firstrecord word0.
    """
    uint(expected_device_id)
    _body(packet,20202)
    if len(packet)==152:
        return None
    if len(packet)<32:
        raise ValueError('Truncated device-state response')
    device_id,count=struct.unpack_from('<II',packet,24)
    if device_id!=expected_device_id or not expected_device_id:
        raise ValueError('Device-state response mismatch')
    if count>1024 or len(packet)!=32+count*12:
        raise ValueError('Invalid device-state record count/length')
    records=tuple(struct.unpack_from('<III',packet,32+i*12) for i in range(count))
    return DeviceRouteState(device_id,records[0][0] if records else None,records)
