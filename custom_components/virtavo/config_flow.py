"""Validated account/device setup and reauthentication for Virtavo."""
from collections.abc import Mapping

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from . import release_status
from .engine import service
from .const import (
    CONF_AUDIO_ENABLED, CONF_REGION, CONF_STREAM_MODE, DEFAULT_AUDIO_ENABLED,
    DEFAULT_STREAM_MODE, DOMAIN, SERVER_REGIONS, STREAM_MODE_CONTINUOUS,
    STREAM_MODE_ON_DEMAND,
)


def _device_id(record):
    value = record.get('device_id') if isinstance(record, Mapping) else None
    if type(value) is not int or value <= 0:
        raise service.ProtocolError('Invalid discovered device identity')
    return value


def _selectable(records):
    if not isinstance(records, (list, tuple)):
        raise service.ProtocolError('Invalid discovered device list')
    selected = {}
    for item in records:
        identity = _device_id(item)
        if str(identity) in selected:
            raise service.ProtocolError('Duplicate discovered device identity')
        name = item.get('name')
        owner_type = item.get('own_type')
        if not isinstance(name, str) or type(owner_type) is not int or owner_type < 0:
            raise service.ProtocolError('Invalid discovered device metadata')
        # Persist no sessions, manager endpoints or device passwords.
        selected[str(identity)] = {'device_id': identity, 'name': name.split('@', 1)[0] or f'Camera {identity}', 'own_type': owner_type}
    return selected


class VirtavoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._pending_data = None
        self._devices = {}
        self._reauth_entry = None

    async def async_step_user(self, user_input=None):
        if not release_status.RELEASE_READY:
            return self.async_abort(reason='protocol_incomplete')
        errors = {}
        if user_input is not None:
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            region = user_input.get(CONF_REGION)
            country = user_input.get('country', self.hass.config.country or 'IT')
            country = country.upper() if isinstance(country, str) else ''
            if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password or region not in SERVER_REGIONS:
                errors['base'] = 'invalid_input'
            elif len(country) != 2 or not country.isascii() or not country.isalpha():
                errors['country'] = 'invalid_country'
            elif country == 'CN':
                errors['country'] = 'unsupported_country'
            else:
                locale = (self.hass.config.language or 'en').replace('_', '-')
                if locale != 'zh-Hant':
                    locale = locale.split('-', 1)[0]
                candidate = {CONF_USERNAME: username.strip().lower(), CONF_PASSWORD: password,
                             CONF_REGION: region, 'language': locale, 'country': country}
                try:
                    records = await service.async_validate_account(self.hass, candidate)
                    devices = _selectable(records)
                except service.AuthenticationError:
                    errors['base'] = 'invalid_auth'
                except service.CannotConnect:
                    errors['base'] = 'cannot_connect'
                except service.ProtocolError:
                    errors['base'] = 'protocol_error'
                else:
                    if not devices:
                        return self.async_abort(reason='no_devices')
                    self._pending_data = candidate
                    self._devices = devices
                    return await self.async_step_device()
        return self.async_show_form(step_id='user', data_schema=vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_REGION): vol.In(SERVER_REGIONS),
            vol.Required('country', default=self.hass.config.country or 'IT'): str,
        }), errors=errors)

    async def async_step_device(self, user_input=None):
        if not release_status.RELEASE_READY:
            return self.async_abort(reason='protocol_incomplete')
        if self._pending_data is None or not self._devices:
            return await self.async_step_user()
        errors = {}
        if user_input is not None:
            key = user_input.get('device_id')
            if key not in self._devices:
                errors['device_id'] = 'invalid_device'
            else:
                device = self._devices[key]
                data = {**self._pending_data, 'device': device}
                identity = f"{data[CONF_USERNAME]}|{data[CONF_REGION]}|{device['device_id']}"
                await self.async_set_unique_id(identity)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=device['name'], data=data)
        choices = {key: record['name'] for key, record in self._devices.items()}
        return self.async_show_form(step_id='device', data_schema=vol.Schema({
            vol.Required('device_id'): vol.In(choices),
        }), errors=errors)

    async def async_step_reauth(self, entry_data):
        if not release_status.RELEASE_READY:
            return self.async_abort(reason='protocol_incomplete')
        self._reauth_entry = self.hass.config_entries.async_get_known_entry(self.context['entry_id'])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if not release_status.RELEASE_READY:
            return self.async_abort(reason='protocol_incomplete')
        if self._reauth_entry is None:
            return self.async_abort(reason='reauth_entry_missing')
        errors = {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD)
            if not isinstance(password, str) or not password:
                errors['base'] = 'invalid_input'
            else:
                candidate = {**self._reauth_entry.data, **{CONF_REGION: self._reauth_entry.options.get(CONF_REGION, self._reauth_entry.data[CONF_REGION])}, CONF_PASSWORD: password}
                try:
                    records = _selectable(await service.async_validate_account(self.hass, candidate))
                    selected_id = str(self._reauth_entry.data['device']['device_id'])
                    if selected_id not in records:
                        raise service.ProtocolError('Configured device no longer discovered')
                except service.AuthenticationError:
                    errors['base'] = 'invalid_auth'
                except service.CannotConnect:
                    errors['base'] = 'cannot_connect'
                except service.ProtocolError:
                    errors['base'] = 'protocol_error'
                else:
                    # The config-entry update listener owns reload scheduling;
                    # avoid scheduling a duplicate reload via the flow helper.
                    self.hass.config_entries.async_update_entry(self._reauth_entry, data={
                        **self._reauth_entry.data, CONF_PASSWORD: password,
                        'device': records[selected_id],
                    })
                    return self.async_abort(reason='reauth_successful')
        return self.async_show_form(step_id='reauth_confirm', data_schema=vol.Schema({
            vol.Required(CONF_PASSWORD): str,
        }), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return VirtavoOptionsFlow()


class VirtavoOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            mode = user_input.get(CONF_STREAM_MODE)
            region = user_input.get(CONF_REGION)
            audio = user_input.get(CONF_AUDIO_ENABLED)
            if mode not in (STREAM_MODE_ON_DEMAND, STREAM_MODE_CONTINUOUS):
                errors[CONF_STREAM_MODE] = 'invalid_mode'
            if region not in SERVER_REGIONS:
                errors[CONF_REGION] = 'invalid_region'
            if type(audio) is not bool:
                errors[CONF_AUDIO_ENABLED] = 'invalid_audio'
            elif audio and not getattr(release_status, 'AUDIO_SUPPORTED', False):
                errors[CONF_AUDIO_ENABLED] = 'audio_unavailable'
            if not errors:
                return self.async_create_entry(title='', data={
                    **self.config_entry.options, CONF_STREAM_MODE: mode,
                    CONF_REGION: region, CONF_AUDIO_ENABLED: audio,
                })
        existing = {**self.config_entry.data, **self.config_entry.options}
        region_key = vol.Required(CONF_REGION, default=existing[CONF_REGION]) if CONF_REGION in existing else vol.Required(CONF_REGION)
        return self.async_show_form(step_id='init', data_schema=vol.Schema({
            vol.Required(CONF_STREAM_MODE, default=existing.get(CONF_STREAM_MODE, DEFAULT_STREAM_MODE)): vol.In((STREAM_MODE_ON_DEMAND, STREAM_MODE_CONTINUOUS)),
            vol.Required(CONF_AUDIO_ENABLED, default=existing.get(CONF_AUDIO_ENABLED, DEFAULT_AUDIO_ENABLED)): bool,
            region_key: vol.In(SERVER_REGIONS),
        }), errors=errors)
