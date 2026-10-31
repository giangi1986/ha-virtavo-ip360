import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch,MagicMock

P=Path(__file__).resolve().parents[1]/'tools/check_account.py'
spec=importlib.util.spec_from_file_location('virtavo_check_test',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DiagnosticTests(unittest.TestCase):
 def test_output_excludes_account_session_and_canonical_identity(self):
  session=types.SimpleNamespace(session=b'PRIVATE_SESSION'*10,canonical_username=b'PRIVATE_CANONICAL')
  c=MagicMock();c.__enter__.return_value=c;c.session=session
  with patch.object(m.account,'open_account',return_value=c):
   result,status=m.probe(m.account.AccountConfig('PRIVATE_EMAIL','PRIVATE_PASSWORD'))
  self.assertEqual(status,0)
  self.assertFalse(result['camera_started'])
  self.assertNotIn('PRIVATE',str(result))
  c.__exit__.assert_called_once()
 def test_protocol_error_is_redacted(self):
  with patch.object(m.account,'open_account',side_effect=m.net.ProtocolError('PRIVATE_SERVER_DATA')):
   result,status=m.probe(m.account.AccountConfig('PRIVATE_EMAIL','PRIVATE_PASSWORD'))
  self.assertEqual(status,3);self.assertNotIn('PRIVATE',str(result))
 def test_rejection_is_distinct_from_connection_failure(self):
  for error,expected in ((m.net.AuthenticationError('PRIVATE'),2),(OSError('PRIVATE'),4)):
   with patch.object(m.account,'open_account',side_effect=error):
    result,status=m.probe(m.account.AccountConfig('PRIVATE_EMAIL','PRIVATE_PASSWORD'))
   self.assertEqual(status,expected);self.assertNotIn('PRIVATE',str(result))

class DiscoveryDiagnosticTests(unittest.TestCase):
 def test_both_owner_counts_are_reported_without_device_identifiers(self):
  session=types.SimpleNamespace(session=b'PRIVATE_SESSION'*10,canonical_username=b'#virtavo#PRIVATE_CANONICAL')
  c=MagicMock();c.__enter__.return_value=c;c.session=session
  device=types.SimpleNamespace(device_id=987654321,name='PRIVATE_DEVICE')
  found=types.SimpleNamespace(devices=(device,),owner_type_counts=((0,0),(1,1)),duplicate_ids=0,discovery_name_changed=True)
  with patch.object(m.account,'open_account',return_value=c),patch.object(m.discovery,'discover_account_devices',return_value=found):
   result,status=m.probe(m.account.AccountConfig('PRIVATE_EMAIL','PRIVATE_PASSWORD'),with_devices=True)
  self.assertEqual(status,0)
  self.assertEqual(result['diagnostic_version'],2)
  self.assertEqual(result['devices'],1)
  self.assertEqual(result['by_owner_type'],{0:0,1:1})
  self.assertNotIn('987654321',str(result))
  self.assertNotIn('PRIVATE',str(result))
  self.assertFalse(result['camera_started'])
 def test_metadata_error_is_not_reported_as_empty_account(self):
  session=types.SimpleNamespace(session=b'x'*128,canonical_username=b'canonical')
  c=MagicMock();c.__enter__.return_value=c;c.session=session
  with patch.object(m.account,'open_account',return_value=c),patch.object(m.discovery,'discover_account_devices',side_effect=ValueError('PRIVATE')):
   result,status=m.probe(m.account.AccountConfig('PRIVATE_EMAIL','PRIVATE_PASSWORD'),with_devices=True)
  self.assertEqual(status,5)
  self.assertEqual(result['login'],'accepted')
  self.assertNotIn('devices',result)
  self.assertNotIn('PRIVATE',str(result))

class DiagnosticTraceTests(unittest.TestCase):
 def test_trace_contains_only_command_owner_type_and_response_size(self):
  connection=MagicMock()
  connection.session=types.SimpleNamespace(canonical_username=b'PRIVATE_CANONICAL')
  connection.request.return_value=b'PRIVATE_PAYLOAD'
  trace=[]
  c=m._DiagnosticConnection(connection,trace)
  request=m.wire.device_info_request(123,b'x'*128,987654321,device_type=1,own_type=1)
  self.assertEqual(c.request(request,expected_command=10049),b'PRIVATE_PAYLOAD')
  self.assertEqual(trace,[{'command':10049,'own_type':1,'response_bytes':15}])
  self.assertNotIn('987654321',str(trace))
  self.assertNotIn('PRIVATE',str(trace))
