"""Generate this project's original MIT camera icon using Python's standard library."""
from pathlib import Path
import struct
import zlib

SIZE = 256

def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))

def generate():
    rows = bytearray()
    for y in range(SIZE):
        rows.append(0)
        for x in range(SIZE):
            color = (0, 0, 0, 0)
            # Original geometric camera silhouette; no vendor artwork or fonts.
            if 28 <= x < 228 and 58 <= y < 202:
                color = (24, 103, 171, 255)
            if 62 <= x < 116 and 40 <= y < 59:
                color = (24, 103, 171, 255)
            radius = (x - 128) ** 2 + (y - 130) ** 2
            if radius <= 48 ** 2:
                color = (241, 248, 255, 255)
            if radius <= 32 ** 2:
                color = (12, 39, 68, 255)
            if (x - 117) ** 2 + (y - 119) ** 2 <= 10 ** 2:
                color = (109, 202, 244, 255)
            rows.extend(color)
    header = struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')

if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'custom_components/virtavo/brand/icon.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(generate())
