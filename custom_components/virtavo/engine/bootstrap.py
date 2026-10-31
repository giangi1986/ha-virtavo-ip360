"""Versioned IPC360 Home8.10.1.0 bootstrap, recovered from supplied APK.

The explicit server code avoids guessing account regions. IT's automatic mapping
was verified as fr. Other countries must select their account's region explicitly.
"""
from dataclasses import dataclass
from types import MappingProxyType

APP_CODE=165
SDK_REVISION=4836
PLATFORM_PREFIX=''
SUPPORT_2FA_FUN=False
PEER_TYPE=0
SERVER_CONFIG=MappingProxyType({'fr':'52.58.164.25','ca':'52.8.101.180','sg':'18.138.10.140','sp':'18.230.172.57','sh':'115.159.17.25','ru':'43.204.41.23'})
LANGUAGE_CODES=MappingProxyType(dict(zip(('zh','en','ja','pt','ko','es','it','ru','de','fr','zh-Hant','ar','pl','ms','th','vi','id','fil','ro','nl','sv','da','no','fi','el','hu','cs','hr','ca','sk','uk','he','tr','hi','bn'),range(35))))

@dataclass(frozen=True)
class BootstrapPlan:
    server_code:str
    dns_host:str
    fallback_ipv4:str
    @property
    def hosts(self):return self.dns_host,self.fallback_ipv4


def bootstrap_plan(country='IT',*,server_code=None):
    if server_code is None:
        if not isinstance(country,str) or country.upper()!='IT':
            raise ValueError('Select a verified server region for this account')
        server_code='fr'
    if not isinstance(server_code,str) or server_code not in SERVER_CONFIG:
        raise ValueError('Unsupported account server region')
    return BootstrapPlan(server_code,server_code+'.ipc365.com',SERVER_CONFIG[server_code])


def language_code(language):
    if not isinstance(language,str):raise TypeError('Language string required')
    return LANGUAGE_CODES.get(language,1)
