"""Generazione indipendente delle sottochiavi DES Virtavo."""

PC1 = (56, 48, 40, 32, 24, 16, 8, 0, 57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 60, 52, 44, 36, 28, 20, 12, 4, 27, 19, 11, 3)
PC2 = (13, 16, 10, 23, 0, 4, 2, 27, 14, 5, 20, 9, 22, 18, 11, 3, 25, 7, 15, 6, 26, 19, 12, 1, 40, 51, 30, 36, 46, 54, 29, 39, 50, 44, 32, 46, 43, 48, 38, 55, 33, 52, 45, 41, 49, 35, 28, 31)
ROTATIONS = (1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1)

def permute(value, table):
    return sum(((value >> bit) & 1) << i for i, bit in enumerate(table))

def ror28(value, shift):
    mask = (1 << 28) - 1
    return ((value >> shift) | (value << (28-shift))) & mask

def generate_subkeys(key):
    if len(key) != 8:
        raise ValueError("La chiave deve contenere 8 byte")

    value = permute(int.from_bytes(key, "little"), PC1)
    result = []

    for shift in ROTATIONS:
        c = ror28(value & ((1 << 28)-1), shift)
        d = ror28(value >> 28, shift)
        value = c | (d << 28)
        result.append(permute(value, PC2))

    return result
