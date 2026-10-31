import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'custom_components/virtavo/engine/net_auth.py'
spec = importlib.util.spec_from_file_location('restored_net_auth', PATH)
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)
META = dict(language=6, user_type=1, os_type=165, revision=4836)


def reply(command, payload, status=0):
    return a.HEADER.pack(a.MAGIC, command, 4836, 105, 20+len(payload), status)+payload


def login_payload():
    body = bytearray(220)
    struct.pack_into('<IIII', body, 0, 7, 0x0100007f, 19001, 29)
    body[24:152] = bytes(range(128))
    body[156:220] = b'canonical-account'.ljust(64, b'\0')
    return bytes(body)


class FakeSocket:
    def __init__(self, response, chunk=1):
        self.response = response
        self.chunk = chunk
        self.sent = []
        self.closed = False
        self.timeout = None
    def settimeout(self, timeout):
        self.timeout = timeout
    def sendall(self, data):
        if self.closed:
            raise ConnectionError('closed')
        self.sent.append(data)
    def recv(self, size):
        size = min(size, self.chunk)
        result, self.response = self.response[:size], self.response[size:]
        return result
    def close(self):
        self.closed = True


class NetAuthTests(unittest.TestCase):
    def test_request_layouts_and_hash_field(self):
        salt = b'0123456789abcdef'
        first = a.salt_request('a@example.invalid', revision=4836)
        second = a.login_request('a@example.invalid', 'secret', salt, **META)
        self.assertEqual(a.HEADER.unpack_from(first), (a.MAGIC,10030,4836,105,86,0))
        self.assertEqual(a.HEADER.unpack_from(second), (a.MAGIC,10120,4836,105,352,0))
        digest = hashlib.md5(hashlib.md5(b'secret').hexdigest().encode('ascii')+salt).hexdigest().encode('ascii')
        self.assertEqual(second[84:148], digest.ljust(64,b'\0'))
        self.assertEqual(second[148:156], struct.pack('<HHI',6,1,165))
        self.assertEqual(second[156:], bytes(196))

    def test_salt_total36_not_payload36(self):
        salt = bytes(range(16))
        self.assertEqual(a.parse_salt(a.parse_frame(reply(10030,salt))),salt)
        with self.assertRaises(a.ProtocolError):
            a.parse_salt(a.parse_frame(reply(10030,bytes(36))))

    def test_opaque_session_canonical_username_and_endpoint(self):
        session = a.parse_login(a.parse_frame(reply(10120,login_payload())))
        self.assertEqual(session.session,bytes(range(128)))
        self.assertEqual(session.canonical_username,b'canonical-account')
        self.assertEqual(session.manager_host,'127.0.0.1')
        self.assertEqual((session.user_id,session.owner_client_id,session.custom_id,session.manager_port),(7,7,29,19001))
        self.assertNotIn('canonical-account',repr(session))
        self.assertNotIn('session=',repr(session))

    def test_login_rejects_wrong_size_endpoint_or_empty_session(self):
        for size in (156,219,221):
            with self.assertRaises(a.ProtocolError):a.parse_login(a.parse_frame(reply(10120,bytes(size))))
        for change in ('uid','ip','port','session'):
            body=bytearray(login_payload())
            if change=='session':body[24:152]=bytes(128)
            else:struct.pack_into('<I',body,{'uid':0,'ip':4,'port':8}[change],0)
            with self.assertRaises(a.ProtocolError):a.parse_login(a.parse_frame(reply(10120,bytes(body))))

    def test_status_and_command_are_not_success(self):
        for command,payload,parser in ((10030,bytes(16),a.parse_salt),(10120,login_payload(),a.parse_login)):
            with self.assertRaises(a.AuthenticationError):parser(a.parse_frame(reply(command,payload,1)))
            with self.assertRaises(a.ProtocolError):parser(a.parse_frame(reply(command+1,payload)))

    def test_invalid_frames_rejected(self):
        valid=reply(10030,bytes(16))
        for packet in (valid[:19],b'bad!'+valid[4:],valid+b'x',valid[:-1],bytes(65537)):
            with self.assertRaises(a.ProtocolError):a.parse_frame(packet)

    def test_partial_reads_and_oversized_header(self):
        fake=FakeSocket(reply(10030,bytes(range(16))),chunk=1)
        self.assertEqual(a.parse_salt(a.exchange(fake,a.salt_request('a',revision=4836))),bytes(range(16)))
        fake=FakeSocket(a.HEADER.pack(a.MAGIC,10030,4836,105,65537,0),chunk=20)
        with self.assertRaises(a.ProtocolError):a.exchange(fake,a.salt_request('a',revision=4836))
        with self.assertRaises(a.ProtocolError):a.read_exact(fake,-1)

    def test_fresh_authenticate_closes_socket(self):
        fake=FakeSocket(reply(10030,b'0123456789abcdef')+reply(10120,login_payload()))
        with patch.object(a.socket,'create_connection',return_value=fake) as connect:
            session=a.authenticate('test.invalid','a','secret',**META)
        self.assertEqual(session.session,bytes(range(128)))
        self.assertTrue(fake.closed)
        self.assertEqual(len(fake.sent),2)
        connect.assert_called_once_with(('test.invalid',19000),timeout=8)

    def test_connection_retained_for_discovery_and_closed_by_context(self):
        response=reply(10048,struct.pack('<IHHHHI',1,0,1,2,0,73))
        fake=FakeSocket(reply(10030,b'0123456789abcdef')+reply(10120,login_payload())+response)
        with patch.object(a.socket,'create_connection',return_value=fake):
            with a.NetConnection.connect('test.invalid','a','secret',**META) as conn:
                self.assertFalse(fake.closed)
                self.assertEqual(conn.request(a.frame(10048,bytes(212),revision=4836),expected_command=10048),response)
                self.assertFalse(fake.closed)
            self.assertTrue(fake.closed)
            conn.close()
            with self.assertRaises(ConnectionError):conn.request(a.frame(10048,b'',revision=4836))
        self.assertEqual(len(fake.sent),3)

    def test_auth_failure_closes_socket_without_discovery(self):
        fake=FakeSocket(reply(10030,bytes(16),1))
        with patch.object(a.socket,'create_connection',return_value=fake):
            with self.assertRaises(a.AuthenticationError):a.NetConnection.connect('test.invalid','a','secret',**META)
        self.assertTrue(fake.closed)
        self.assertEqual(len(fake.sent),1)

    def test_discovery_mismatch_or_status_closes_unusable_connection(self):
        session=a.parse_login(a.parse_frame(reply(10120,login_payload())))
        for response in (reply(10049,b''),reply(10048,b'',1),reply(10048,b'')[:-1]):
            fake=FakeSocket(response)
            conn=a.NetConnection(fake,session)
            with self.assertRaises((a.ProtocolError,ConnectionError)):
                conn.request(a.frame(10048,b'',revision=4836),expected_command=10048)
            self.assertTrue(fake.closed)

    def test_local_invalid_fields_never_connect(self):
        for kwargs in ({'timeout':float('inf')},{'timeout':float('nan')},{'timeout':True},{'port':0},{'host':''},{'password':'x\0y'}):
            fields=dict(host='test.invalid',account='a',password='secret',**META);fields.update(kwargs)
            with patch.object(a.socket,'create_connection') as connect:
                with self.assertRaises(ValueError):a.NetConnection.connect(**fields)
                connect.assert_not_called()

    def test_partial_response_cannot_reset_total_deadline(self):
        fake=FakeSocket(reply(10030,bytes(16)),chunk=1)
        # The peer sends a fragment but cannot keep a request alive forever by
        # repeatedly resetting the socket timeout on each received byte.
        with patch.object(a.time,'monotonic',side_effect=[0,0,2]):
            with self.assertRaises(TimeoutError):
                a.exchange_raw(fake,a.salt_request('a',revision=4836),timeout=1)
        self.assertEqual(fake.timeout,1)

    def test_net_manager_signin_exact_and_alternate_command(self):
        session=a.parse_login(a.parse_frame(reply(10120,login_payload())))
        packet=a.manager_signin(session,access_sign_in_type=0,device_magic=0,revision=4836)
        self.assertEqual(a.HEADER.unpack_from(packet),(a.MAGIC,20200,4836,106,168,0))
        self.assertEqual(packet[20:40],struct.pack('<HHIIII',1,1,29,7,0,0))
        self.assertEqual(packet[40:],bytes(range(128)))
        alternate=a.manager_signin(session,access_sign_in_type=5,device_magic=123,revision=4836)
        self.assertEqual(a.parse_frame(alternate).command,20425)
        self.assertEqual(struct.unpack_from('<H',alternate,22)[0],0x501)

    def test_manager_rejects_short_or_empty_session(self):
        for raw in (b'x',bytes(128)):
            session=a.NetSession(1,1,2,0x0100007f,19001,raw,b'name')
            with self.assertRaises(ValueError):a.manager_signin(session,access_sign_in_type=0,device_magic=0,revision=4836)


if __name__=='__main__':unittest.main()
