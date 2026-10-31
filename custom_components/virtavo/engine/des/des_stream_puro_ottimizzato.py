#!/usr/bin/env python3
import argparse
import contextlib
import io
import os
import re
import sys
from pathlib import Path

# Motore Python indipendente


OFFSETS = (3, 5, 7, 11, 13, 17, 19, 23)
START = re.compile(b'\x00\x00\x00\x01|\x00\x00\x01')

parser = argparse.ArgumentParser()
source = parser.add_mutually_exclusive_group(required=True)
source.add_argument('--code-file')
source.add_argument('--code-fd', type=int)
args = parser.parse_args()

if args.code_fd is not None:
    if args.code_fd < 0:
        parser.error('Descrittore codice non valido')
    with os.fdopen(args.code_fd, 'rb') as code_source:
        raw_code = code_source.read(257)
    if len(raw_code) > 256:
        parser.error('Codice DES troppo lungo')
    code = raw_code.decode('utf-8').strip()
else:
    code = Path(args.code_file).read_text().strip()
if not code:
    parser.error('Codice DES vuoto')

if __package__:
    from .virtavo_keys import generate_keys
    from .des_decrypt_native import SBOX
    from .des_keys_native import generate_subkeys
    from .des_permutations_native import ip, ip_inversa, espansione, p
    from .des_sbox_native import transform
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from virtavo_keys import generate_keys
    from des_decrypt_native import SBOX
    from des_keys_native import generate_subkeys
    from des_permutations_native import ip, ip_inversa, espansione, p
    from des_sbox_native import transform

_subkeys_cache = {}

def decrypt_block_cached(block, key):
    if key not in _subkeys_cache:
        _subkeys_cache[key] = generate_subkeys(key)
    keys = _subkeys_cache[key]
    state = ip(block)
    for index in range(15, -1, -1):
        high = state >> 32
        low = state & 0xffffffff
        expanded = espansione(high)
        substituted = transform(expanded ^ keys[index], SBOX)
        transformed = p(substituted) & 0xffffffff
        state = ((low ^ transformed) << 32) | high
    state = ((state & 0xffffffff) << 32) | (state >> 32)
    return ip_inversa(state)


keys = generate_keys(code)

def decrypt(block, key):
    if len(block) != 16:
        raise ValueError("Il blocco deve contenere 16 byte")
    encrypted = int.from_bytes(block[::2], "little")
    decrypted = decrypt_block_cached(encrypted, key).to_bytes(8, "little")
    result = bytearray(block)
    result[::2] = decrypted
    return bytes(result)

contexts = keys

buffer = bytearray()
nal_count = 0
blocks = 0

def emit(nal):
    global nal_count, blocks
    matches = list(START.finditer(nal))
    if matches and matches[0].start() == 0:
        prefix = len(matches[0].group())
        if len(nal) >= prefix + 2:
            nal_type = (nal[prefix] >> 1) & 63
            if nal_type in (1, 19):
                result = bytearray(nal)
                limit = min(len(nal), 1024)
                for group in range(0, max(0, limit - 32), 512):
                    for j, offset in enumerate(OFFSETS):
                        pos = 32 + group + offset * 16
                        if pos >= limit - 48 or pos + 16 > len(nal):
                            continue
                        result[pos:pos+16] = decrypt(
                            bytes(result[pos:pos+16]), contexts[j]
                        )
                        blocks += 1
                nal = bytes(result)
    sys.stdout.buffer.write(nal)
    sys.stdout.buffer.flush()
    nal_count += 1

try:
    while chunk := sys.stdin.buffer.read1(16384):
        buffer.extend(chunk)
        if len(buffer) > 8 * 1024 * 1024:
            raise ValueError('Limite NAL DES superato')
        matches = list(START.finditer(buffer))
        if len(matches) > 1:
            cut = matches[-1].start()
            starts = [m.start() for m in matches[:-1]]
            if starts[0] > 0:
                emit(bytes(buffer[:starts[0]]))
            for j, start in enumerate(starts):
                end = starts[j+1] if j+1 < len(starts) else cut
                emit(bytes(buffer[start:end]))
            del buffer[:cut]
    if buffer:
        emit(bytes(buffer))
finally:
    print(f'NAL elaborati: {nal_count}; blocchi DES: {blocks}', file=sys.stderr)
