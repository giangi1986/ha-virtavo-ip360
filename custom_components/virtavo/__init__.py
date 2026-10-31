"""Virtavo authenticated config-entry lifecycle."""
from collections.abc import Mapping
import contextlib

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from . import release_status
from .const import DOMAIN, CONF_REGION
from .engine import service

PLATFORMS = ['camera']


async def async_setup(hass, config):
    return True


async def _async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry):
    if not release_status.RELEASE_READY:
        raise ConfigEntryNotReady(release_status.BLOCK_REASON)
    from .camera import DeviceStream
    data = {**entry.data}
    if CONF_REGION in entry.options:
        data[CONF_REGION] = entry.options[CONF_REGION]
    try:
        selected = data['device']['device_id']
        if type(selected) is not int or selected <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ConfigEntryNotReady('A selected authenticated device is required') from None
    try:
        discovered = await service.async_validate_account(hass, data)
        if not isinstance(discovered, (list, tuple)) or not all(isinstance(record, Mapping) for record in discovered):
            raise service.ProtocolError('Invalid fresh discovery records')
        matches = [record for record in discovered if type(record.get('device_id')) is int and record['device_id'] == selected]
        if len(matches) != 1:
            raise ConfigEntryNotReady('Configured device is unavailable in fresh discovery')
        runtime = await service.async_create_device_runtime(hass, data, matches[0], dict(entry.options))
        if not isinstance(runtime, DeviceStream):
            raise service.ProtocolError('Device runtime has an invalid type')
    except service.AuthenticationError as err:
        raise ConfigEntryAuthFailed('Virtavo account credentials rejected') from err
    except service.CannotConnect as err:
        raise ConfigEntryNotReady('Virtavo account service unavailable') from err
    except service.ProtocolError as err:
        raise ConfigEntryNotReady('Virtavo account protocol response unsupported') from err
    entry.runtime_data = (runtime,)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # Forwarding may already have created a camera endpoint before a later
        # platform step failed. Ask HA to remove the partially loaded platform
        # while preserving the original exception, including cancellation.
        with contextlib.suppress(Exception):
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        entry.runtime_data = None
        raise
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data = None
    return unloaded
