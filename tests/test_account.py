import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch,MagicMock
BASE=Path(__file__).resolve().parents[1]/'custom_components/virtavo/engine'
PKG='account_test_engine'
p=types.ModuleType(PKG);p.__path__=[str(BASE)];sys.modules[PKG]=p
spec=importlib.util.spec_from_file_location(PKG+'.account',BASE/'account.py')
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)

class AccountTests(unittest.TestCase):
 def test_dns_metadata_and_secret_repr(self):
  config=a.AccountConfig(' TEST@EXAMPLE.INVALID ','fictional-password')
  with patch.object(a.net_auth.NetConnection,'connect',return_value='connection') as connect:
   self.assertEqual(a.open_account(config),'connection')
  self.assertEqual(connect.call_args.args,('fr.ipc365.com','test@example.invalid','fictional-password'))
  self.assertEqual(connect.call_args.kwargs,dict(language=6,user_type=1,os_type=165,revision=4836))
  self.assertNotIn('fictional-password',repr(config))
 def test_connection_errors_use_fallback(self):
  with patch.object(a.net_auth.NetConnection,'connect',side_effect=[OSError(),'fresh']) as connect:
   self.assertEqual(a.open_account(a.AccountConfig('test@example.invalid','x')),'fresh')
  self.assertEqual(connect.call_count,2)
  self.assertEqual(connect.call_args.args[0],'52.58.164.25')
 def test_rejection_is_not_retried(self):
  with patch.object(a.net_auth.NetConnection,'connect',side_effect=a.net_auth.AuthenticationError('rejected')) as connect:
   with self.assertRaises(a.net_auth.AuthenticationError):a.open_account(a.AccountConfig('test@example.invalid','x'))
  self.assertEqual(connect.call_count,1)
 def test_invalid_region_does_not_connect(self):
  with patch.object(a.net_auth.NetConnection,'connect') as connect:
   with self.assertRaises(ValueError):a.open_account(a.AccountConfig('test@example.invalid','x',country='ZZ'))
  connect.assert_not_called()
 def test_auth_only_closes_owned_connection(self):
  c=MagicMock();c.__enter__.return_value=c;c.session='fresh-session'
  with patch.object(a,'open_account',return_value=c):
   self.assertEqual(a.authenticate_account(a.AccountConfig('test@example.invalid','x')),'fresh-session')
  c.__exit__.assert_called_once()
