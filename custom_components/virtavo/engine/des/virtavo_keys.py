"""Generazione delle otto chiavi video in Python puro."""

import hashlib

def encrypt_code(data: str, salt: str) -> str:
    first = hashlib.md5(data.encode()).digest()
    second = hashlib.md5(
        salt.encode()[:24] + first.hex()[:16].encode()
    ).digest()

    def convert(value):
        value &= 31
        return chr(value + (48 if value < 10 else 55))

    return "".join(
        convert(a) + convert(b)
        for a, b in zip(first[:10], second[:10])
    )

def generate_keys(initial_code: str) -> list[bytes]:
    original = encrypt_code(initial_code, "default_ori")
    final = encrypt_code(original, "pro_final")
    extension = encrypt_code(final, "extention")
    combined = final + extension
    return [combined[i:i+8].encode() for i in range(0, 32, 4)]
