"""Offline device/relay serializers recovered from the supplied Android SDK.

No network access, historical sessions, SDK import or camera side effects.
Semantic values are explicit arguments; defaults from one app build must not be
mistaken for universal protocol values. See docs/PROTOCOL.md.
"""
from dataclasses import dataclass, field
from ipaddress import IPv4Address
import struct

MAGIC = bytes.fromhex('ccddeeff')
HEADER = struct.Struct('<4sIHHII')
MAX_FRAME = 65536
AUDIO_MEDIA_TYPES = frozenset((3, 5, 6))


def uint(value, bits=32):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError('Invalid unsigned protocol integer')
    return value


def fixed(value, size):
    raw = value.encode('utf-8') if isinstance(value, str) else value
    if not isinstance(raw, bytes) or b'\0' in raw or len(raw) >= size:
        raise ValueError('Invalid fixed string')
    return raw.ljust(size, b'\0')


def frame(command, body=b'', *, revision=4836, version=105):
    """20-byte transport header for the audited SDK build, not a live proof."""
    if not isinstance(body, bytes) or len(body) > MAX_FRAME - HEADER.size:
        raise ValueError('Invalid packet body')
    return HEADER.pack(MAGIC, uint(command), uint(revision, 16), uint(version, 16),
                       HEADER.size + len(body), 0) + body


def payload(packet, command):
    if not isinstance(packet, bytes) or not HEADER.size <= len(packet) <= MAX_FRAME:
        raise ValueError('Invalid response size')
    magic, cmd, revision, version, length, status = HEADER.unpack_from(packet)
    if magic != MAGIC or cmd != command or length != len(packet) or status:
        raise ValueError('Invalid or error response')
    return packet[HEADER.size:]


def session_field(session):
    if not isinstance(session, bytes) or len(session) != 128 or not any(session):
        raise ValueError('Fresh NET session must contain 128 bytes')
    return session


def device_ids_request(user_id, session, username, *, device_type, own_type,
                       offset, count, order_by, descending):
    """10048 body212: uid + SDK_DEVICE_FRESH_LIST_REQ80 + NET session128."""
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError('Page count must be between 1 and 50')
    request = (struct.pack('<IIHHHH', uint(device_type), uint(own_type), uint(offset, 16),
                           count, uint(order_by, 16), uint(descending, 16))
               + fixed(username, 64))
    return frame(10048, struct.pack('<I', uint(user_id)) + request + session_field(session))


@dataclass(frozen=True)
class DevicePage:
    total: int
    offset: int
    device_ids: tuple[int, ...]
    order_by: int
    descending: int


def parse_device_ids(packet):
    body = payload(packet, 10048)
    if len(body) < 12:
        raise ValueError('Truncated device page')
    total, offset, size, order, desc = struct.unpack_from('<IHHHH', body)
    # Reject partial or unexplained trailing records, which could otherwise
    # hide an incorrect native layout or coalesced transport data.
    if size > 50 or len(body) != 12 + size * 4 or offset > total or size > total - offset:
        raise ValueError('Invalid device page size')
    ids = struct.unpack_from('<' + 'I' * size, body, 12)
    if any(i == 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Invalid or duplicate device identifier')
    return DevicePage(total, offset, ids, order, desc)


def device_info_request(user_id, session, device_id, *, device_type, own_type):
    body = struct.pack('<IIII', uint(user_id), uint(device_id), uint(device_type), uint(own_type))
    return frame(10049, body + session_field(session))


@dataclass(frozen=True)
class DeviceInfo:
    device_id: int = field(repr=False)
    serial: bytes = field(repr=False)
    params: bytes = field(repr=False)
    name: str
    password: bytes = field(repr=False)
    manager_host: str
    login_server_code: bytes


def parse_device_info(packet):
    body = payload(packet, 10049)
    if len(body) != 272:
        raise ValueError('Invalid device metadata size')
    string = lambda a, b: body[a:b].split(b'\0', 1)[0]
    identifier = struct.unpack_from('<I', body)[0]
    if not identifier:
        raise ValueError('Missing device identifier')
    return DeviceInfo(identifier, string(4, 68), string(68, 132),
                      string(132, 196).decode('utf-8', errors='replace'), string(196, 260),
                      str(IPv4Address(body[260:264])), string(264, 272))


def des_initial_code(canonical_username, device_id):
    """Native default: first six UTF-8 bytes of canonical name + decimal ID.

    This is key input, not a key embedded in source. Do not log the result.
    The legacy MAC variant is not silently substituted for the default.
    """
    raw = canonical_username.encode('utf-8') if isinstance(canonical_username, str) else canonical_username
    if not isinstance(raw, bytes) or not raw or b'\0' in raw:
        raise ValueError('Canonical SDK username required')
    # Existing recovered Python DES key generation accepts text and re-encodes
    # UTF-8. Fail closed if truncation splits a multibyte codepoint.
    return (raw[:6] + str(uint(device_id)).encode('ascii')).decode('utf-8')


def relay_request(device_id, owner_id, *, father_id, peer_type, local_host,
                  public_host, local_port, mode, flags):
    """20301 body44; NAT/public-address fields must come from caller state."""
    body = bytearray(44)
    struct.pack_into('<HHIIII', body, 0, uint(mode, 16), 1, uint(device_id),
                     uint(father_id), uint(owner_id), uint(peer_type))
    body[20:24] = IPv4Address(public_host).packed
    struct.pack_into('>H', body, 24, uint(local_port, 16))
    struct.pack_into('<H', body, 26, uint(flags, 16))
    body[28:32] = IPv4Address(local_host).packed
    struct.pack_into('>H', body, 32, uint(local_port, 16))
    return frame(20301, bytes(body))


@dataclass(frozen=True)
class RelayInfo:
    camera_session: int = field(repr=False)
    host: str
    port: int


def parse_relay(packet):
    body = payload(packet, 20302)
    if len(body) != 44:
        raise ValueError('Invalid relay response size')
    session = struct.unpack_from('<I', body, 4)[0]
    host = IPv4Address(body[20:24])
    port = struct.unpack_from('>H', body, 24)[0]
    if not session or not port or host.is_unspecified or host.is_multicast:
        raise ValueError('Missing or invalid relay endpoint/session')
    return RelayInfo(session, str(host), port)


def udp_stun(camera_session, owner_id, *, peer_type):
    return frame(40031, struct.pack('<III', uint(camera_session), uint(owner_id), uint(peer_type)))


def udp_connect(camera_session, owner_id, *, peer_type, father_id):
    """40036 body24: owner32, peer32, father64, flags0x10001, session32."""
    return frame(40036, struct.pack('<IIQII', uint(owner_id), uint(peer_type),
                                   uint(father_id, 64), 0x10001, uint(camera_session)))


@dataclass(frozen=True)
class MediaPacket:
    media_type: int
    payload: bytes = field(repr=False)

    @property
    def is_audio(self):
        return self.media_type in AUDIO_MEDIA_TYPES


def parse_media_packet(packet):
    """Classify 40005 media only; this does not assemble video frames.

    Native real_data_return reads media type at full offset28 and data at48.
    Bytes16..27 are intentionally not interpreted as success/session/sequence
    metadata without a separately recovered layout.
    """
    if not isinstance(packet, bytes) or not 48 <= len(packet) <= MAX_FRAME:
        raise ValueError('Invalid media packet size')
    if packet[:4] != MAGIC or struct.unpack_from('<I', packet, 4)[0] != 40005:
        raise ValueError('Unexpected media packet')
    if struct.unpack_from('<I', packet, 12)[0] != len(packet):
        raise ValueError('Invalid media packet length')
    return MediaPacket(struct.unpack_from('<H', packet, 28)[0], packet[48:])


def manager_time_request(*, revision=4836):
    """Command7: native mgr_get_net_utc_time sends one zero uint32, V105."""
    return frame(7, bytes(4), revision=revision, version=105)


def device_state_request(device_id, *, revision=4836):
    """20202: native device_state copies the requested ID, not an account ID.

    Remaining native body words are exactly0,1,10. Their semantic field names
    are not inferred from these constants. No captured camera data is embedded.
    """
    return frame(20202, struct.pack('<IIII', uint(device_id), 0, 1, 10),
                 revision=revision, version=105)


def online_state_requests(device_id, *, revision=4836):
    """Native mgr_online_state sends two requests, not one/two-reply contract."""
    request = device_state_request(device_id, revision=revision)
    return request, request


def manager_device_state(device_id, *, revision=4836):
    """Named manager-control entry point for the native device-state request."""
    return device_state_request(device_id, revision=revision)
