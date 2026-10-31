import importlib.util
from pathlib import Path
import struct
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine'
PKG='virtavo_audio_test_engine'
pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)];sys.modules[PKG]=pkg
spec=importlib.util.spec_from_file_location(PKG+'.audio',ROOT/'audio.py')
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
from importlib import import_module
d=import_module(PKG+'.device_protocol')


def packet(data,media_type=3,declared=None):
    b=bytearray(d.frame(40005,bytes(28)+data))
    struct.pack_into('<H',b,28,media_type)
    struct.pack_into('<III',b,32,42,12345,0)
    struct.pack_into('<I',b,44,len(data) if declared is None else declared)
    return bytes(b)


class AudioTests(unittest.TestCase):
    def test_native_audio_fields(self):
        p=a.parse_audio_packet(packet(b'\xd5\x55'))
        self.assertEqual((p.frame_number,p.timestamp,p.alaw),(42,12345,b'\xd5\x55'))
        self.assertNotIn('alaw=',repr(p))
        self.assertEqual((a.CHANNELS,a.SAMPLE_RATE),(1,8000))

    def test_payload_validation_before_decoding(self):
        for b in (packet(b'x',media_type=1),packet(b''),packet(b'x',declared=2),packet(bytes(977))):
            with self.assertRaises(ValueError):a.parse_audio_packet(b)

    def test_alaw_reference_values_and_pcm_endianness(self):
        self.assertEqual([a.alaw_sample(v) for v in (0,0x55,0xD5,0x2A,0xAA)],[-5504,-8,8,-32256,32256])
        self.assertEqual(a.decode_alaw(b'\xd5\x55\xaa\x2a'),struct.pack('<hhhh',8,-8,32256,-32256))

    def test_all_codes_have_correct_sign_and_range(self):
        for v in range(128):
            self.assertEqual(a.alaw_sample(v),-a.alaw_sample(v|128))
            self.assertLess(a.alaw_sample(v),0)
            self.assertLessEqual(abs(a.alaw_sample(v)),32256)

    def test_invalid_audio_input_is_bounded(self):
        for b in (b'',bytes(977),'not bytes'):
            with self.assertRaises(ValueError):a.decode_alaw(b)
        for v in (-1,256,True,'0'):
            with self.assertRaises(ValueError):a.alaw_sample(v)

if __name__=='__main__':unittest.main()
