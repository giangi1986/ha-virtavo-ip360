"""HA-facing account validation and fresh device runtime construction.

Only minimal display/selector records are persisted. Sessions, camera passwords,
manager addresses and sharing account names stay in owned runtime memory.
"""
import asyncio
from dataclasses import dataclass,field
from functools import partial

from .account import AccountConfig,open_account
from .discovery import discover_account_devices
from .net_auth import AuthenticationError,ProtocolError
from .ownership import parse_device_identity


class CannotConnect(ConnectionError):
    """An account or transport endpoint is unavailable."""


def account_settings(data,options=None):
    settings={**data,**(options or {})}
    return AccountConfig(settings['username'],settings['password'],
          country=settings.get('country','IT'),language=settings.get('language','en'),
          server_code=settings.get('region','fr'))


def _inspect_account(data):
    try:
        with open_account(account_settings(data)) as connection:
            inventory=discover_account_devices(connection)
            groups=dict(inventory.device_owner_types)
            result=[]
            for device in inventory.devices:
                group=groups[device.device_id]
                identity=parse_device_identity(device.name,connection.session.canonical_username,group)
                result.append({'device_id':device.device_id,
                               'name':identity.display_name or 'Camera',
                               'own_type':group})
            return result
    except AuthenticationError:raise
    except (OSError,ConnectionError,TimeoutError):
        raise CannotConnect('Account endpoint unavailable') from None
    except ValueError:
        raise ProtocolError('Account device discovery could not be validated') from None


async def async_validate_account(hass,data):
    job=partial(_inspect_account,dict(data))
    if hass is None:return await asyncio.to_thread(job)
    return await hass.async_add_executor_job(job)


@dataclass
class SessionContext:
    connection:object=field(repr=False)
    device:object=field(repr=False)
    own_type:int
    identity:object=field(repr=False)
    def close(self):self.connection.close()


def _open_device(data,device_id,options):
    connection=None
    try:
        connection=open_account(account_settings(data,options))
        inventory=discover_account_devices(connection)
        groups=dict(inventory.device_owner_types)
        device=next((d for d in inventory.devices if d.device_id==device_id),None)
        if device is None:raise ProtocolError('Selected device is no longer visible')
        identity=parse_device_identity(device.name,connection.session.canonical_username,groups[device_id])
        # Shared playback must use the metadata sharing identity, never silently
        # substitute the current account if that field is missing.
        identity.play_username
        return SessionContext(connection,device,groups[device_id],identity)
    except BaseException:
        if connection is not None:connection.close()
        raise


async def async_open_device(data,device_id,options=None):
    task=asyncio.create_task(asyncio.to_thread(_open_device,dict(data),device_id,dict(options or {})))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Executor work cannot be force-cancelled. Close its result when it
        # arrives, so an unload during login never leaks the newly owned socket.
        def close_late(future):
            if not future.cancelled():
                try:context=future.result()
                except BaseException:return
                context.close()
        task.add_done_callback(close_late)
        raise


async def async_create_device_runtime(hass,data,device,options):
    from ..camera import DeviceStream
    from .receiver import run_camera_stream
    if type(device.get('device_id')) is not int or device['device_id']<=0:
        raise ProtocolError('Validated device identity required')
    audio=options.get('audio_enabled',data.get('audio_enabled',False))
    mode=options.get('stream_mode',data.get('stream_mode','on_demand'))
    if type(audio) is not bool or mode not in ('on_demand','continuous'):
        raise ValueError('Invalid stream options')
    snapshot=dict(data)
    selected=dict(device)
    runtime_options=dict(options)
    async def pipeline(output_writer):
        await run_camera_stream(snapshot,selected['device_id'],output_writer,
                                audio=audio,options=runtime_options)
    return DeviceStream(str(device['device_id']),device['name'],pipeline,
                        continuous=mode=='continuous')
