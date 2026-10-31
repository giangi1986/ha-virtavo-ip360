#!/usr/bin/env python3
"""Explicit read-only account diagnostic; never starts a camera or prints secrets."""
import argparse
import getpass
import importlib
import json
from pathlib import Path
import sys
import struct
import types

ROOT=Path(__file__).resolve().parents[1]
p=types.ModuleType('virtavo_diagnostic_engine')
p.__path__=[str(ROOT/'custom_components/virtavo/engine')]
sys.modules[p.__name__]=p
account=importlib.import_module(p.__name__+'.account')
net=importlib.import_module(p.__name__+'.net_auth')
discovery=importlib.import_module(p.__name__+'.discovery')
wire=importlib.import_module(p.__name__+'.device_protocol')


class _DiagnosticConnection:
    """Record only command/filter/response sizes, never payload or identities."""
    def __init__(self,connection,trace):
        self._connection=connection
        self.session=connection.session
        self.trace=trace
    def request(self,request,expected_command=None):
        item={'command':expected_command}
        if expected_command==10048:item['own_type']=struct.unpack_from('<I',request,28)[0]
        if expected_command==10049:item['own_type']=struct.unpack_from('<I',request,32)[0]
        self.trace.append(item)
        raw=self._connection.request(request,expected_command=expected_command)
        item['response_bytes']=len(raw)
        return raw


def probe(config,*,with_devices=False,on_login=None):
    result={'diagnostic_version':2,'login':'not_completed','camera_started':False,'scope':'fresh_NET_V2'}
    try:
        with account.open_account(config) as connection:
            if on_login is not None:on_login()
            session=connection.session
            result.update(login='accepted',session_bytes=len(session.session),canonical_name_available=bool(session.canonical_username))
            if with_devices:
                if not session.canonical_username:
                    result['discovery']='missing_canonical_name'
                    return result,3
                result['requests']=[]
                traced=_DiagnosticConnection(connection,result['requests'])
                found=discovery.discover_account_devices(traced,max_devices=50)
                devices=found.devices
                # This reports key-input availability, not a successful DES/video test.
                codes=sum(bool(wire.des_initial_code(session.canonical_username,d.device_id)) for d in devices)
                result.update(discovery='accepted',devices=len(devices),metadata_checked=len(devices),
                    des_code_inputs_available=codes,by_owner_type=dict(found.owner_type_counts),
                    duplicate_ids_removed=found.duplicate_ids,
                    discovery_name_normalized=found.discovery_name_changed)
    except net.AuthenticationError:
        result['login']='rejected'
        return result,2
    except (OSError,ConnectionError,TimeoutError):
        result['error']='connection_or_timeout'
        return result,4
    except net.ProtocolError:
        result['error']='unexpected_protocol_response'
        return result,3
    except ValueError:
        result['error']='configuration_or_metadata_validation'
        return result,5
    return result,0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',choices=('fr','ca','sg','sp','sh','ru'),default='fr')
    parser.add_argument('--discovery',action='store_true')
    args=parser.parse_args()
    email=input('Email IPC360 Home: ').strip()
    password=getpass.getpass('Password IPC360 Home (non visualizzata): ')
    try:
        result,status=probe(account.AccountConfig(email,password,server_code=args.region),with_devices=args.discovery,
                    on_login=lambda:print('Login corretto.',file=sys.stderr,flush=True))
    finally:
        password=None
        email=None
    print(json.dumps(result,sort_keys=True))
    return status

if __name__=='__main__':
    try:sys.exit(main())
    except (KeyboardInterrupt,EOFError):
        print(json.dumps({'login':'cancelled','camera_started':False}));sys.exit(130)
