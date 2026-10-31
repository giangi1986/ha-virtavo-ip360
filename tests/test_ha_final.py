"""Real HA APIs with account/runtime I/O mocked at the service boundary."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

ROOT = Path(os.environ.get('VIRTAVO_TEST_COMPONENT_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
integration = importlib.import_module('custom_components.virtavo')
flow_module = importlib.import_module('custom_components.virtavo.config_flow')
from custom_components.virtavo.camera import DeviceStream

SETTINGS = {'username':'camera@example.invalid','password':'fictional-password','region':'fr','language':'en','country':'IT'}
DEVICE = {'device_id':17,'name':'Garden','own_type':1}


def make_entry(data=None, options=None, unique_id=None):
    return ConfigEntry(version=1, minor_version=1, domain='virtavo', title='Garden',
                       data=data or {**SETTINGS, 'device':dict(DEVICE)}, options=options or {},
                       source='user', unique_id=unique_id, discovery_keys=MappingProxyType({}),
                       subentries_data=[])


class RealHAFinalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass,{})
        self.hass.config.language = 'en'
        self.hass.config.country = 'IT'
        self.ready = patch.object(flow_module.release_status,'RELEASE_READY',True)
        self.ready.start();self.addCleanup(self.ready.stop)

    async def asyncTearDown(self):
        self.directory.cleanup()

    def flow(self):
        flow=flow_module.VirtavoConfigFlow();flow.hass=self.hass;flow.handler='virtavo'
        flow.context={'source':'user'}
        return flow

    def add_entry(self, entry):
        self.hass.config_entries._entries[entry.entry_id]=entry
        return entry

    async def test_user_validation_discovery_then_explicit_device_selection(self):
        flow=self.flow()
        form=await flow.async_step_user()
        self.assertEqual(form['type'],'form');self.assertEqual(form['step_id'],'user')
        secret_record={**DEVICE,'name':'Garden@private-owner','session':b'not-for-entry','password':'device-private'}
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=[secret_record])) as validate:
            selected=await flow.async_step_user({'username':' CAMERA@EXAMPLE.INVALID ','password':'fictional-password','region':'fr'})
        self.assertEqual(selected['type'],'form');self.assertEqual(selected['step_id'],'device')
        self.assertNotIn('private-owner',repr(selected))
        self.assertEqual(validate.call_args.args[1],SETTINGS)
        result=await flow.async_step_device({'device_id':'17'})
        self.assertEqual(result['type'],'create_entry');self.assertEqual(result['title'],'Garden')
        self.assertEqual(result['data'],{**SETTINGS,'device':DEVICE})
        self.assertNotIn('result',result)
        self.assertEqual(flow.unique_id,'camera@example.invalid|fr|17')
        self.assertNotIn('device-private',repr(result));self.assertNotIn('not-for-entry',repr(result))

    async def test_wrong_password_and_connection_errors_do_not_save_credentials(self):
        for error,expected in ((flow_module.service.AuthenticationError,'invalid_auth'),
                               (flow_module.service.CannotConnect,'cannot_connect'),
                               (flow_module.service.ProtocolError,'protocol_error')):
            with self.subTest(error=error):
                flow=self.flow()
                with patch.object(flow_module.service,'async_validate_account',AsyncMock(side_effect=error('generic'))):
                    result=await flow.async_step_user(SETTINGS)
                self.assertEqual(result['type'],'form');self.assertEqual(result['errors'],{'base':expected})
                self.assertIsNone(flow._pending_data)
                self.assertNotIn('fictional-password',repr(result))

    async def test_no_devices_aborts_and_invalid_selection_does_not_create_entry(self):
        flow=self.flow()
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=[])):
            result=await flow.async_step_user(SETTINGS)
        self.assertEqual(result['reason'],'no_devices')
        flow=self.flow()
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=[DEVICE])):
            await flow.async_step_user(SETTINGS)
        result=await flow.async_step_device({'device_id':'999'})
        self.assertEqual(result['errors'],{'device_id':'invalid_device'})

    async def test_duplicate_camera_is_rejected_with_real_unique_id_check(self):
        self.add_entry(make_entry(unique_id='camera@example.invalid|fr|17'))
        flow=self.flow()
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=[DEVICE])):
            await flow.async_step_user(SETTINGS)
        with self.assertRaises(AbortFlow) as raised:
            await flow.async_step_device({'device_id':'17'})
        self.assertEqual(raised.exception.reason,'already_configured')

    async def test_release_guard_never_calls_account_service(self):
        with patch.object(flow_module.release_status,'RELEASE_READY',False),patch.object(flow_module.service,'async_validate_account',AsyncMock()) as validate:
            result=await self.flow().async_step_user(SETTINGS)
        self.assertEqual(result['reason'],'protocol_incomplete');validate.assert_not_called()

    async def test_malformed_or_duplicate_discovery_is_protocol_error(self):
        for records in ([DEVICE,DEVICE],[{'device_id':0,'name':'bad','own_type':1}],None):
            with self.subTest(records=records):
                with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=records)):
                    result=await self.flow().async_step_user(SETTINGS)
                self.assertEqual(result['errors'],{'base':'protocol_error'})

    async def test_setup_revalidates_fresh_device_and_owns_no_session_in_entry(self):
        entry=self.add_entry(make_entry(options={'region':'ca','stream_mode':'on_demand','audio_enabled':False}))
        async def pipeline(writer):
            raise AssertionError('setup must not start streaming')
        runtime=DeviceStream('17','Garden',pipeline)
        with patch.object(integration.service,'async_validate_account',AsyncMock(return_value=[DEVICE])) as validate,patch.object(integration.service,'async_create_device_runtime',AsyncMock(return_value=runtime)) as factory,patch.object(self.hass.config_entries,'async_forward_entry_setups',AsyncMock()) as forward:
            self.assertTrue(await integration.async_setup_entry(self.hass,entry))
        self.assertEqual(validate.call_args.args[1]['region'],'ca')
        self.assertEqual(factory.call_args.args[2],DEVICE)
        self.assertEqual(entry.runtime_data,(runtime,))
        forward.assert_awaited_once_with(entry,['camera'])
        self.assertEqual(len(entry.update_listeners),1)
        self.assertEqual(entry.data,{**SETTINGS,'device':DEVICE})

    async def test_setup_credential_errors_request_reauth_other_errors_retry(self):
        entry=self.add_entry(make_entry())
        for error,expected in ((integration.service.AuthenticationError,ConfigEntryAuthFailed),
                               (integration.service.CannotConnect,ConfigEntryNotReady),
                               (integration.service.ProtocolError,ConfigEntryNotReady)):
            with self.subTest(error=error):
                with patch.object(integration.service,'async_validate_account',AsyncMock(side_effect=error('generic'))),patch.object(self.hass.config_entries,'async_forward_entry_setups',AsyncMock()) as forward:
                    with self.assertRaises(expected):await integration.async_setup_entry(self.hass,entry)
                forward.assert_not_called()

    async def test_missing_selected_device_never_starts_runtime(self):
        entry=self.add_entry(make_entry())
        with patch.object(integration.service,'async_validate_account',AsyncMock(return_value=[])),patch.object(integration.service,'async_create_device_runtime',AsyncMock()) as factory:
            with self.assertRaises(ConfigEntryNotReady):await integration.async_setup_entry(self.hass,entry)
        factory.assert_not_called()

    async def test_failed_platform_forward_drops_runtime_reference(self):
        entry=self.add_entry(make_entry())
        async def pipeline(writer):pass
        runtime=DeviceStream('17','Garden',pipeline)
        with patch.object(integration.service,'async_validate_account',AsyncMock(return_value=[DEVICE])),patch.object(integration.service,'async_create_device_runtime',AsyncMock(return_value=runtime)),patch.object(self.hass.config_entries,'async_forward_entry_setups',AsyncMock(side_effect=RuntimeError('platform failed'))),patch.object(self.hass.config_entries,'async_unload_platforms',AsyncMock(return_value=True)) as rollback:
            with self.assertRaises(RuntimeError):await integration.async_setup_entry(self.hass,entry)
        self.assertIsNone(entry.runtime_data)
        rollback.assert_awaited_once_with(entry,['camera'])

    async def test_country_is_preserved_and_unsupported_paths_do_not_call_service(self):
        self.hass.config.country = 'DE'
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=[DEVICE])) as validate:
            await self.flow().async_step_user({'username':SETTINGS['username'],'password':SETTINGS['password'],'region':'fr'})
        self.assertEqual(validate.call_args.args[1]['country'],'DE')
        for country,reason in [('China','invalid_country'),('CN','unsupported_country'),('12','invalid_country')]:
            with patch.object(flow_module.service,'async_validate_account',AsyncMock()) as validate:
                result=await self.flow().async_step_user({**SETTINGS,'country':country})
            self.assertEqual(result['errors'],{'country':reason});validate.assert_not_called()

    async def test_failed_forward_preserves_original_error_if_rollback_fails(self):
        entry=self.add_entry(make_entry())
        async def pipeline(writer):pass
        runtime=DeviceStream('17','Garden',pipeline)
        with patch.object(integration.service,'async_validate_account',AsyncMock(return_value=[DEVICE])),patch.object(integration.service,'async_create_device_runtime',AsyncMock(return_value=runtime)),patch.object(self.hass.config_entries,'async_forward_entry_setups',AsyncMock(side_effect=RuntimeError('original platform error'))),patch.object(self.hass.config_entries,'async_unload_platforms',AsyncMock(side_effect=ValueError('cleanup error'))):
            with self.assertRaisesRegex(RuntimeError,'original platform error'):
                await integration.async_setup_entry(self.hass,entry)
        self.assertIsNone(entry.runtime_data)

    async def test_unload_preserves_runtime_when_platform_is_not_unloaded(self):
        entry=self.add_entry(make_entry());runtime=object();entry.runtime_data=(runtime,)
        with patch.object(self.hass.config_entries,'async_unload_platforms',AsyncMock(return_value=False)):
            self.assertFalse(await integration.async_unload_entry(self.hass,entry));self.assertEqual(entry.runtime_data,(runtime,))
        with patch.object(self.hass.config_entries,'async_unload_platforms',AsyncMock(return_value=True)):
            self.assertTrue(await integration.async_unload_entry(self.hass,entry));self.assertIsNone(entry.runtime_data)

    async def test_update_listener_schedules_entry_reload(self):
        entry=self.add_entry(make_entry())
        with patch.object(self.hass.config_entries,'async_reload',AsyncMock()) as reload:
            await integration._async_reload_entry(self.hass,entry)
        reload.assert_awaited_once_with(entry.entry_id)

    async def test_reauth_updates_only_after_fresh_auth_and_selected_discovery(self):
        entry=self.add_entry(make_entry())
        flow=self.flow();flow.context={'source':'reauth','entry_id':entry.entry_id}
        result=await flow.async_step_reauth(entry.data)
        self.assertEqual(result['step_id'],'reauth_confirm')
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(side_effect=flow_module.service.AuthenticationError('generic'))):
            rejected=await flow.async_step_reauth_confirm({'password':'rejected-new'})
        self.assertEqual(rejected['errors'],{'base':'invalid_auth'});self.assertEqual(entry.data['password'],'fictional-password')
        with patch.object(flow_module.service,'async_validate_account',AsyncMock(return_value=[DEVICE])) as validate:
            accepted=await flow.async_step_reauth_confirm({'password':'accepted-new'})
        self.assertEqual(accepted['reason'],'reauth_successful');self.assertEqual(entry.data['password'],'accepted-new')
        self.assertEqual(validate.call_args.args[1]['password'],'accepted-new')
        self.assertEqual(entry.data['username'],'camera@example.invalid')

    async def test_options_default_and_audio_gate(self):
        entry=self.add_entry(make_entry())
        flow=flow_module.VirtavoOptionsFlow();flow.hass=self.hass;flow.handler=entry.entry_id
        initial=await flow.async_step_init()
        self.assertEqual(initial['data_schema']({}),{'stream_mode':'on_demand','audio_enabled':False,'region':'fr'})
        with patch.object(flow_module.release_status,'AUDIO_SUPPORTED',False,create=True):
            rejected=await flow.async_step_init({'stream_mode':'continuous','audio_enabled':True,'region':'ca'})
        self.assertEqual(rejected['errors'],{'audio_enabled':'audio_unavailable'})
        with patch.object(flow_module.release_status,'AUDIO_SUPPORTED',True,create=True):
            accepted=await flow.async_step_init({'stream_mode':'continuous','audio_enabled':True,'region':'ca'})
        self.assertEqual(accepted['type'],'create_entry');self.assertTrue(accepted['data']['audio_enabled'])
