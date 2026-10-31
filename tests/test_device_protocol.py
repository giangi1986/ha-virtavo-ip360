import importlib.util
from pathlib import Path
import struct
import sys
import unittest

P = Path(__file__).resolve().parents[1] / 'custom_components/virtavo/engine/device_protocol.py'
spec = importlib.util.spec_from_file_location('device_protocol_tested', P)
d = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = d
spec.loader.exec_module(d)
SESSION = bytes(range(128))


class DiscoveryTests(unittest.TestCase):
    def test_request_lengths_and_preserve_raw_session(self):
        packet = d.device_ids_request(7, SESSION, b'canonical', device_type=1, own_type=0,
                                      offset=50, count=50, order_by=2, descending=0)
        self.assertEqual(len(packet), 232)
        self.assertEqual(d.HEADER.unpack_from(packet), (d.MAGIC,10048,4836,105,232,0))
        body = d.payload(packet,10048)
        self.assertEqual(struct.unpack_from('<IIIHHHH',body),(7,1,0,50,50,2,0))
        self.assertEqual(body[20:29],b'canonical')
        self.assertEqual(body[-128:],SESSION)
        info = d.device_info_request(7,SESSION,99,device_type=1,own_type=0)
        self.assertEqual(len(info),164)
        self.assertEqual(d.payload(info,10049),struct.pack('<IIII',7,99,1,0)+SESSION)

    def test_page_offsets_and_ids(self):
        body=struct.pack('<IHHHHII',100,50,2,2,0,99,100)
        page=d.parse_device_ids(d.frame(10048,body))
        self.assertEqual((page.total,page.offset,page.device_ids),(100,50,(99,100)))

    def test_empty_page(self):
        page=d.parse_device_ids(d.frame(10048,struct.pack('<IHHHH',0,0,0,2,0)))
        self.assertEqual(page.device_ids,())

    def test_invalid_page_boundaries_and_duplicates(self):
        bodies=[struct.pack('<IHHHH',5,0,51,2,0),
                struct.pack('<IHHHH',5,6,0,2,0),
                struct.pack('<IHHHHII',5,0,2,2,0,9,9),
                struct.pack('<IHHHHI',5,0,1,2,0,0),
                struct.pack('<IHHHHI',5,0,2,2,0,9),
                struct.pack('<IHHHHI',5,0,0,2,0,9)]
        for body in bodies:
            with self.subTest(size=len(body)):
                with self.assertRaises(ValueError):d.parse_device_ids(d.frame(10048,body))

    def test_metadata_exact_native_offsets(self):
        body=bytearray(272)
        struct.pack_into('<I',body,0,99)
        body[4:7]=b'ABC';body[68:71]=b'PAR';body[132:138]=b'Camera'
        body[196:202]=b'secret';body[260:264]=bytes((127,0,0,1));body[264:266]=b'fr'
        info=d.parse_device_info(d.frame(10049,bytes(body)))
        self.assertEqual((info.device_id,info.serial,info.params,info.name),(99,b'ABC',b'PAR','Camera'))
        self.assertEqual((info.password,info.manager_host,info.login_server_code),(b'secret','127.0.0.1',b'fr'))
        self.assertNotIn('secret',repr(info))

    def test_metadata_rejects_wrong_size_id_and_status(self):
        for body in (bytes(271),bytes(273),bytes(272)):
            with self.assertRaises(ValueError):d.parse_device_info(d.frame(10049,body))
        packet=bytearray(d.frame(10048,struct.pack('<IHHHH',0,0,0,2,0)))
        struct.pack_into('<I',packet,16,1)
        with self.assertRaises(ValueError):d.parse_device_ids(bytes(packet))

    def test_no_empty_or_truncated_sessions(self):
        for value in (bytes(128),b'x'*127,b'x'*129,'not bytes'):
            with self.assertRaises(ValueError):d.session_field(value)
        self.assertEqual(d.session_field(SESSION),SESSION)

    def test_page_input_bounds_and_missing_explicit_values(self):
        kwargs=dict(device_type=1,own_type=0,offset=0,count=50,order_by=2,descending=0)
        for count in (0,51,True):
            with self.assertRaises(ValueError):d.device_ids_request(1,SESSION,b'name',**(kwargs|{'count':count}))
        with self.assertRaises(TypeError):d.device_ids_request(1,SESSION,b'name')
        with self.assertRaises(ValueError):d.device_ids_request(1,SESSION,b'\0name',**kwargs)


class KeyInputTests(unittest.TestCase):
    def test_native_default_key_input_uses_canonical_bytes(self):
        self.assertEqual(d.des_initial_code(b'CANONICAL',99),'CANONI99')
        self.assertEqual(d.des_initial_code('abcdef',4294967295),'abcdef4294967295')
        self.assertEqual(d.des_initial_code(b'abc',99),'abc99')

    def test_invalid_key_input_fails_closed(self):
        for value in (b'',b'ab\0cd',None):
            with self.assertRaises(ValueError):d.des_initial_code(value,99)
        with self.assertRaises(UnicodeDecodeError):d.des_initial_code('aaaaaé',99)
        with self.assertRaises(ValueError):d.des_initial_code('abcdef',True)


class RelayTests(unittest.TestCase):
    def test_request_exact_offsets_with_explicit_semantics(self):
        packet=d.relay_request(99,7,father_id=41,peer_type=1,local_host='127.0.0.1',
                               public_host='0.0.0.0',local_port=30000,mode=0,flags=0)
        self.assertEqual(len(packet),64)
        body=d.payload(packet,20301)
        self.assertEqual(struct.unpack_from('<HHIIII',body),(0,1,99,41,7,1))
        self.assertEqual(body[20:24],bytes(4))
        self.assertEqual(body[24:26],struct.pack('>H',30000))
        self.assertEqual(body[28:32],b'\x7f\0\0\1')
        self.assertEqual(body[32:34],struct.pack('>H',30000))

    def test_no_invented_relay_defaults(self):
        with self.assertRaises(TypeError):d.relay_request(99,7)
        with self.assertRaises(TypeError):d.udp_connect(9,7)
        with self.assertRaises(TypeError):d.udp_stun(9,7)

    def test_relay_response(self):
        body=bytearray(44);struct.pack_into('<I',body,4,9)
        body[20:24]=bytes((127,0,0,1));struct.pack_into('>H',body,24,1234)
        relay=d.parse_relay(d.frame(20302,bytes(body)))
        self.assertEqual((relay.camera_session,relay.host,relay.port),(9,'127.0.0.1',1234))
        self.assertNotIn('camera_session',repr(relay))
        for invalid in (bytes(44),bytes(43),bytes(45)):
            with self.assertRaises(ValueError):d.parse_relay(d.frame(20302,invalid))

    def test_udp_native_fields(self):
        stun=d.udp_stun(9,7,peer_type=1)
        self.assertEqual(len(stun),32)
        self.assertEqual(d.payload(stun,40031),struct.pack('<III',9,7,1))
        connect=d.udp_connect(9,7,peer_type=1,father_id=41)
        self.assertEqual(len(connect),44)
        self.assertEqual(d.payload(connect,40036),struct.pack('<IIQII',7,1,41,0x10001,9))

    def test_shared_frame_guards(self):
        packet=d.frame(20302,bytes(44))
        for bad in (packet[:19],b'BAD!'+packet[4:],packet+b'x',packet[:-1]):
            with self.assertRaises(ValueError):d.payload(bad,20302)
        with self.assertRaises(ValueError):d.payload(packet,20301)
        for value in (True,-1,2**32,'1'):
            with self.assertRaises(ValueError):d.uint(value)


class MediaClassificationTests(unittest.TestCase):
    @staticmethod
    def packet(media_type,payload=b'media'):
        result=bytearray(d.frame(40005,bytes(28)+payload))
        struct.pack_into('<H',result,28,media_type)
        return bytes(result)

    def test_audio_types_are_classified_before_des(self):
        for media_type in (3,5,6):
            result=d.parse_media_packet(self.packet(media_type))
            self.assertTrue(result.is_audio)
            self.assertEqual(result.payload,b'media')
        self.assertFalse(d.parse_media_packet(self.packet(1)).is_audio)

    def test_classification_does_not_assume_status_or_sequence_metadata(self):
        packet=bytearray(self.packet(1));struct.pack_into('<I',packet,16,0xffffffff)
        self.assertEqual(d.parse_media_packet(bytes(packet)).payload,b'media')

    def test_bad_datagrams_rejected(self):
        good=self.packet(1)
        for bad in (good[:47],good+b'x',good[:-1],b'BAD!'+good[4:],d.frame(40036,bytes(28))):
            with self.assertRaises(ValueError):d.parse_media_packet(bad)



class ManagerControlTests(unittest.TestCase):
    def test_time_request_zero_word(self):
        packet=d.manager_time_request()
        self.assertEqual(packet,d.HEADER.pack(d.MAGIC,7,4836,105,24,0)+bytes(4))

    def test_state_uses_fresh_device_identifier(self):
        for identifier in (1,99,0xffffffff):
            packet=d.device_state_request(identifier)
            self.assertEqual(len(packet),36)
            self.assertEqual(d.HEADER.unpack_from(packet),(d.MAGIC,20202,4836,105,36,0))
            self.assertEqual(packet[20:],struct.pack('<IIII',identifier,0,1,10))
        self.assertNotEqual(d.device_state_request(1),d.device_state_request(99))

    def test_online_state_is_two_requests_without_reply_assumption(self):
        requests=d.online_state_requests(99)
        self.assertEqual(requests,(d.device_state_request(99),)*2)

    def test_manager_control_argument_validation(self):
        for identifier in (-1,2**32,True,'99'):
            with self.assertRaises(ValueError):d.device_state_request(identifier)
        with self.assertRaises(ValueError):d.manager_time_request(revision=65536)

if __name__=='__main__':unittest.main()
