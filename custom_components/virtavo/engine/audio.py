"""G.711 A-law audio processing for the native 8 kHz mono audio path.

No external codec/runtime or proprietary data table. Disabling audio means the
caller discards audio packets before invoking this module; it does not promise
that the remote camera ceases transmitting audio datagrams.
"""
from dataclasses import dataclass, field
import struct

from .device_protocol import parse_media_packet

SAMPLE_RATE = 8000
CHANNELS = 1
MAX_AUDIO_BLOCK = 976


@dataclass(frozen=True)
class AudioPacket:
    frame_number: int
    timestamp: int
    alaw: bytes = field(repr=False)


def parse_audio_packet(packet: bytes) -> AudioPacket:
    media = parse_media_packet(packet)
    if not media.is_audio:
        raise ValueError('Packet is not audio')
    size = struct.unpack_from('<I', packet, 44)[0]
    if not 0 < size <= MAX_AUDIO_BLOCK or size != len(media.payload):
        raise ValueError('Invalid native audio block size')
    frame_number, timestamp = struct.unpack_from('<II', packet, 32)
    return AudioPacket(frame_number, timestamp, media.payload)


def alaw_sample(value: int) -> int:
    """ITU G.711 A-law expansion to one signed16 sample."""
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError('A-law sample must be a byte')
    value ^= 0x55
    segment = (value >> 4) & 7
    magnitude = (value & 15) << 4
    if segment == 0:
        magnitude += 8
    elif segment == 1:
        magnitude += 0x108
    else:
        magnitude = (magnitude + 0x108) << (segment - 1)
    return magnitude if value & 0x80 else -magnitude


def decode_alaw(data: bytes) -> bytes:
    """Expand a bounded audio block to little-endian PCM signed16."""
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_AUDIO_BLOCK:
        raise ValueError('A bounded nonempty audio block is required')
    result = bytearray(len(data) * 2)
    for index, value in enumerate(data):
        struct.pack_into('<h', result, index * 2, alaw_sample(value))
    return bytes(result)
