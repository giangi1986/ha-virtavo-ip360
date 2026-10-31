"""SBOX Virtavo ricostruita in Python puro."""

def transform(value: int, table: bytes) -> int:
    if len(table) != 512:
        raise ValueError("La tabella SBOX deve contenere 512 byte")

    result = value

    for group in range(8):
        shift = group * 6

        index = (
            (((result >> shift) & 1) << 5)
            | (((result >> (shift + 5)) & 1) << 4)
            | (((result >> (shift + 1)) & 1) << 3)
            | (((result >> (shift + 2)) & 1) << 2)
            | (((result >> (shift + 3)) & 1) << 1)
            | ((result >> (shift + 4)) & 1)
        )

        output = table[group * 64 + index]

        reversed_bits = (
            ((output & 1) << 3)
            | ((output & 2) << 1)
            | ((output & 4) >> 1)
            | ((output & 8) >> 3)
        )

        position = group * 4
        result = (result & ~(15 << position)) | (reversed_bits << position)

    return result & ((1 << 64) - 1)
