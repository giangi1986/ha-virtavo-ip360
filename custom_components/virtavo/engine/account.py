"""Fresh account bootstrap and discovery, without historical session material."""
from dataclasses import dataclass,field
from .bootstrap import APP_CODE,SDK_REVISION,bootstrap_plan,language_code
from . import net_auth

@dataclass(frozen=True)
class AccountConfig:
    email:str=field(repr=False)
    password:str=field(repr=False)
    country:str='IT'
    language:str='it'
    server_code:str|None=None


def open_account(config):
    if not isinstance(config,AccountConfig):raise TypeError('AccountConfig required')
    if not isinstance(config.email,str) or not config.email.strip():raise ValueError('Email required')
    plan=bootstrap_plan(config.country,server_code=config.server_code)
    for index,host in enumerate(plan.hosts):
        try:
            return net_auth.NetConnection.connect(host,config.email.strip().lower(),config.password,
                       language=language_code(config.language),user_type=1,os_type=APP_CODE,revision=SDK_REVISION)
        except (OSError,ConnectionError,TimeoutError):
            if index==len(plan.hosts)-1:raise ConnectionError('Regional endpoint unavailable') from None
    raise AssertionError('Bootstrap requires endpoints')


def authenticate_account(config):
    with open_account(config) as connection:return connection.session
