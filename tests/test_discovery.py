import importlib.util
from pathlib import Path
import struct
import sys
import types
import unittest

BASE=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine'
PKG='discovery_test_engine'
p=types.ModuleType(PKG);p.__path__=[str(BASE)];sys.modules[PKG]=p
spec=importlib.util.spec_from_file_location(PKG+'.discovery',BASE/'discovery.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
wire=m.wire

def page(total,offset,ids):return wire.frame(10048,struct.pack('<IHHHH',total,offset,len(ids),2,0)+struct.pack('<'+'I'*len(ids),*ids))
def info(device_id):return wire.frame(10049,struct.pack('<I',device_id)+bytes(268))
class Connection:
    def __init__(self,replies):
        self.replies=iter(replies)
        self.session=types.SimpleNamespace(user_id=17,session=b'x'*128)
        self.commands=[]
    def request(self,request,expected_command=None):
        self.commands.append(expected_command)
        return next(self.replies)

class DiscoveryTests(unittest.TestCase):
    def setUp(self):self.query=m.DeviceQuery(b'canonical',1,0,2,0)
    def test_pages_and_identity_checked_metadata(self):
        ids=list(range(1,52))
        c=Connection([page(51,0,ids[:50]),page(51,50,ids[50:]),*[info(i) for i in ids]])
        self.assertEqual([d.device_id for d in m.discover_devices(c,self.query)],ids)
        self.assertEqual(c.commands[:2],[10048,10048])
        self.assertEqual(c.commands[2:],[10049]*51)
    def test_empty_account_is_valid(self):
        self.assertEqual(m.discover_devices(Connection([page(0,0,[])]),self.query),())
    def test_duplicate_or_stalled_pages_rejected(self):
        for replies in ([page(2,0,[1,1])],[page(2,0,[])],[page(2,1,[1])],[page(501,0,[1])]):
            with self.subTest(replies_count=len(replies)):
                with self.assertRaises(ValueError):m.discover_devices(Connection(replies),self.query)
    def test_changed_total_rejected(self):
        with self.assertRaises(ValueError):
            m.discover_devices(Connection([page(51,0,list(range(1,51))),page(52,50,[51])]),self.query)
    def test_wrong_device_metadata_rejected(self):
        with self.assertRaises(ValueError):
            m.discover_devices(Connection([page(1,0,[1]),info(2)]),self.query)

class AccountDiscoveryTests(unittest.TestCase):
    def connection(self,replies,canonical=b'#virtavo#MixedAlias'):
        class TraceConnection(Connection):
            def __init__(self,replies):
                super().__init__(replies)
                self.requests=[]
            def request(self,request,expected_command=None):
                self.requests.append(request)
                return super().request(request,expected_command=expected_command)
        c=TraceConnection(replies)
        c.session.canonical_username=canonical
        return c

    def test_empty_first_group_still_queries_second_and_preserves_owner(self):
        c=self.connection([page(0,0,[]),page(1,0,[42]),info(42)])
        result=m.discover_account_devices(c)
        self.assertEqual(tuple(d.device_id for d in result.devices),(42,))
        self.assertEqual(result.owner_type_counts,((0,0),(1,1)))
        self.assertEqual(result.device_owner_types,((42,1),))
        self.assertEqual(c.commands,[10048,10048,10049])
        self.assertEqual(struct.unpack_from('<I',c.requests[2],32)[0],1)
        self.assertEqual(c.requests[0][40:104].split(b'\0')[0],b'mixedalias')
        self.assertTrue(result.discovery_name_changed)
        self.assertEqual(c.session.canonical_username,b'#virtavo#MixedAlias')

    def test_both_empty_lists_remain_explicit(self):
        c=self.connection([page(0,0,[]),page(0,0,[])])
        result=m.discover_account_devices(c)
        self.assertEqual(result.devices,())
        self.assertEqual(result.owner_type_counts,((0,0),(1,0)))
        self.assertEqual(c.commands,[10048,10048])

    def test_duplicates_between_groups_return_once_and_keep_first_owner(self):
        c=self.connection([page(1,0,[1]),info(1),page(2,0,[1,2]),info(1),info(2)])
        result=m.discover_account_devices(c)
        self.assertEqual(tuple(d.device_id for d in result.devices),(1,2))
        self.assertEqual(result.duplicate_ids,1)
        self.assertEqual(result.owner_type_counts,((0,1),(1,2)))
        self.assertEqual(result.device_owner_types,((1,0),(2,1)))
        self.assertNotIn('devices=',repr(result))
        self.assertNotIn('device_owner_types=',repr(result))

    def test_combined_limit_is_enforced(self):
        c=self.connection([page(1,0,[1]),info(1),page(1,0,[2]),info(2)])
        with self.assertRaises(ValueError):m.discover_account_devices(c,max_devices=1)

    def test_name_rules_match_apk_without_altering_raw_name(self):
        for raw,expected in ((b'#virtavo#AbC',b'abc'),(b'#yuanli#ABC',b'abc'),(b'#_360eyes#AbC',b'abc'),(b'AbC',b'abc'),(b'abc#virtavo#xyz',b'abc#virtavo#xyz')):
            with self.subTest(raw=raw):
                self.assertEqual(m.account_discovery_username(raw),expected)
        self.assertEqual(m.username_no_prefix(b'#virtavo#AbC'),b'AbC')

    def test_invalid_name_rejected_before_any_request(self):
        for raw in (b'',b'bad\0name',b'#virtavo#',b'x'*64):
            c=self.connection([],canonical=raw)
            with self.assertRaises(ValueError):m.discover_account_devices(c)
            self.assertEqual(c.commands,[])
