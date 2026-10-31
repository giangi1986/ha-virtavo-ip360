"""Decifratura DES Virtavo in Python puro, senza SDK."""

from .des_keys_native import generate_subkeys
from .des_permutations_native import ip, ip_inversa, espansione, p
from .des_sbox_native import transform

SBOX = bytes.fromhex("0e040d01020f0b08030a060c05090007000f07040e020d010a060c0b0905030804010e080d06020b0f0c0907030a05000f0c080204090107050b030e0a00060d0f01080e060b03040907020d0c00050a030d04070f02080e0c00010a06090b05000e070b0a040d0105080c060903020f0d080a01030f04020b06070c00050e090a00090e06030f05010d0c070b0402080d0700090304060a0208050e0c0b0f010d060409080f03000b01020c050a0e07010a0d0006090807040f0e030b05020c070d0e030006090a010208050b0c040f0d080b05060f00030407020c010a0e090a0609000c0b070d0f01030e05020804030f00060a010d080904050b0c07020e020c0401070a0b060805030f0d000e090e0b020c04070d0105000f0a030908060402010b0a0d07080f090c050603000e0b080c07010e020d060f00090a0405030c010a0f09020608000d03040e07050b0a0f0402070c090506010d0e000b0308090e0f0502080c030700040a010d0b060403020c09050f0a0b0e01070600080d040b020e0f00080d030c0907050a06010d000b070409010a0e03050c020f080601040b0d0c03070e0a0f060800050902060b0d0801040a070905000f0e02030c0d020804060f0b010a09030e05000c07010f0d080a0307040c05060b000e0902070b0401090c0e0200060a0d0f03050802010e07040a080d0f0c09000305060b")
MASK32 = 0xffffffff

def decrypt_block(block: int, key: bytes) -> int:
    if not 0 <= block < (1 << 64):
        raise ValueError("Il blocco deve essere un intero a 64 bit")
    if len(key) != 8:
        raise ValueError("La chiave deve contenere 8 byte")

    keys = generate_subkeys(key)
    state = ip(block)

    for index in range(15, -1, -1):
        high = state >> 32
        low = state & MASK32

        expanded = espansione(high)
        substituted = transform(expanded ^ keys[index], SBOX)
        transformed = p(substituted) & MASK32

        state = ((low ^ transformed) << 32) | high

    state = ((state & MASK32) << 32) | (state >> 32)
    return ip_inversa(state)
