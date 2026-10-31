"""Lifecycle tests against real HA2026.10.4; network is loopback only."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from types import MappingProxyType

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.exceptions import ConfigEntryNotReady

ROOT = Path(os.environ.get('VIRTAVO_TEST_COMPONENT_ROOT',Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(ROOT))
from custom_components.virtavo import async_setup_entry, release_status
from custom_components.virtavo.camera import DeviceStream, VirtavoCamera
from custom_components.virtavo.config_flow import VirtavoConfigFlow, VirtavoOptionsFlow, vol
from custom_components.virtavo.engine.stream_endpoint import StreamEndpoint, _EOF


def entry(options=None,data=None):
    return ConfigEntry(version=1,minor_version=1,domain='virtavo',title='Test',
                       data=data or {},options=options or {},source='user',
                       unique_id='synthetic-account',discovery_keys=MappingProxyType({}),
                       subentries_data=[])


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for field, value in [('RELEASE_READY', False), ('AUDIO_SUPPORTED', False)]:
            changed = patch.object(release_status, field, value, create=True)
            changed.start(); self.addCleanup(changed.stop)

    async def test_user_flow_never_creates_fake_account(self):
        flow=VirtavoConfigFlow()
        for value in (None,{'username':'example@invalid.test','password':'fictional'}):
            result=await flow.async_step_user(value)
            self.assertEqual(result['type'],'abort')
            self.assertEqual(result['reason'],'protocol_incomplete')
            self.assertNotIn('data',result)

    async def test_setup_rejects_unvalidated_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            hass=HomeAssistant(directory)
            with self.assertRaises(ConfigEntryNotReady):
                await async_setup_entry(hass,entry())

    async def options_flow(self,options=None,data=None):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        hass=HomeAssistant(self.directory.name)
        hass.config_entries=ConfigEntries(hass,{})
        config=entry(options,data)
        hass.config_entries._entries[config.entry_id]=config
        flow=VirtavoOptionsFlow();flow.hass=hass;flow.handler=config.entry_id
        return flow

    async def test_default_options_are_on_demand_and_audio_off(self):
        flow=await self.options_flow(data={'region':'fr'})
        result=await flow.async_step_init()
        self.assertEqual(result['data_schema']({}),{'stream_mode':'on_demand','audio_enabled':False,'region':'fr'})

    async def test_valid_options_preserve_unrelated_settings(self):
        flow=await self.options_flow(options={'retain':'setting','region':'fr'})
        result=await flow.async_step_init({'stream_mode':'continuous','audio_enabled':False,'region':'ca'})
        self.assertEqual(result['type'],'create_entry')
        self.assertEqual(result['data'],{'retain':'setting','stream_mode':'continuous','audio_enabled':False,'region':'ca'})

    async def test_unsupported_audio_and_invalid_region_are_not_saved(self):
        flow=await self.options_flow()
        result=await flow.async_step_init({'stream_mode':'bad','audio_enabled':True,'region':'bad'})
        self.assertEqual(result['type'],'form')
        self.assertEqual(result['errors'],{'stream_mode':'invalid_mode','region':'invalid_region','audio_enabled':'audio_unavailable'})

    async def test_region_is_required_when_not_previously_set(self):
        flow=await self.options_flow()
        result=await flow.async_step_init()
        with self.assertRaises(vol.Invalid):result['data_schema']({})


class CameraTests(unittest.IsolatedAsyncioTestCase):
    async def test_camera_source_lease_and_unload(self):
        started=asyncio.Event();stopped=asyncio.Event()
        async def produce(writer):
            started.set()
            try:
                writer.write(b'synthetic-camera-stream');await writer.drain()
                await asyncio.Event().wait()
            finally:stopped.set()
        camera=VirtavoCamera(DeviceStream('synthetic-device','Test',produce))
        with tempfile.TemporaryDirectory() as directory:
            camera.hass=HomeAssistant(directory)
            await camera.async_added_to_hass()
            self.assertFalse(started.is_set())
            url=await camera.stream_source()
            self.assertTrue(url.startswith('http://127.0.0.1:'))
            self.assertFalse(started.is_set())
            async with ClientSession() as client:
                response=await client.get(url)
                self.assertEqual(await response.content.readexactly(23),b'synthetic-camera-stream')
                camera.stream=AsyncMock()
                await camera.async_will_remove_from_hass()
                camera.stream.stop.assert_awaited_once()
                self.assertTrue(stopped.is_set());response.close()
            self.assertIsNone(camera._endpoint.manager.task)
            self.assertIsNone(camera._endpoint.manager._idle_task)
            self.assertFalse(camera._endpoint.manager._viewer_timers)

    async def test_continuous_is_opt_in_and_snapshot_is_inert(self):
        started=asyncio.Event()
        async def produce(writer):started.set();await asyncio.Event().wait()
        camera=VirtavoCamera(DeviceStream('synthetic-device','Test',produce,continuous=True))
        with tempfile.TemporaryDirectory() as directory:
            camera.hass=HomeAssistant(directory)
            self.assertIsNone(await camera.async_camera_image());self.assertFalse(started.is_set())
            await camera.async_added_to_hass();await asyncio.wait_for(started.wait(),1)
            await camera.async_will_remove_from_hass()
            self.assertIsNone(camera._endpoint.manager.task)


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_on_demand_bytes_and_eof(self):
        started=asyncio.Event()
        async def produce(writer):started.set();writer.write(b'ts-test');await writer.drain()
        endpoint=StreamEndpoint(produce,idle_seconds=0)
        try:
            url=await endpoint.start();self.assertFalse(started.is_set())
            async with ClientSession() as client:
                async with client.get(url) as response:
                    self.assertEqual(response.headers['Content-Type'],'video/mp2t')
                    self.assertEqual(await response.read(),b'ts-test')
            await asyncio.sleep(.02)
            self.assertFalse(endpoint.manager.viewers);self.assertIsNone(endpoint.manager.task)
        finally:await endpoint.stop()

    async def test_two_readers_share_pipeline_and_last_disconnect_stops(self):
        ready=asyncio.Event();cancelled=asyncio.Event();starts=0
        async def produce(writer):
            nonlocal starts
            starts+=1
            try:
                await ready.wait()
                while True:writer.write(b'payload');await writer.drain();await asyncio.sleep(.01)
            finally:cancelled.set()
        endpoint=StreamEndpoint(produce,idle_seconds=0)
        try:
            url=await endpoint.start()
            async with ClientSession() as client:
                first=await client.get(url);second=await client.get(url);ready.set()
                self.assertEqual(await first.content.readexactly(7),b'payload')
                self.assertEqual(await second.content.readexactly(7),b'payload');self.assertEqual(starts,1)
                first.close();await asyncio.sleep(.05);self.assertFalse(cancelled.is_set())
                second.close();await asyncio.wait_for(cancelled.wait(),2)
        finally:await endpoint.stop()

    async def test_wrong_token_never_starts_producer(self):
        started=False
        async def produce(writer):
            nonlocal started
            started=True
        endpoint=StreamEndpoint(produce)
        try:
            url=await endpoint.start()
            async with ClientSession() as client:
                async with client.get(url.rsplit('/',1)[0]+'/bad') as response:self.assertEqual(response.status,404)
            self.assertFalse(started)
        finally:await endpoint.stop()

    async def test_slow_reader_is_disconnected_with_bounded_buffer(self):
        async def produce(writer):pass
        endpoint=StreamEndpoint(produce,queue_chunks=1);queue=asyncio.Queue(1);endpoint._subscribers.add(queue)
        endpoint.write(b'first');await endpoint.drain();endpoint.write(b'overflow');await endpoint.drain()
        self.assertNotIn(queue,endpoint._subscribers);self.assertIs(await queue.get(),_EOF)

    async def test_normal_eof_does_not_discard_full_queue(self):
        async def produce(writer):writer.write(b'last-chunk');await writer.drain()
        endpoint=StreamEndpoint(produce,queue_chunks=1);queue=asyncio.Queue(1);endpoint._subscribers.add(queue)
        task=asyncio.create_task(endpoint._produce())
        await asyncio.sleep(.02)
        self.assertEqual(await queue.get(),b'last-chunk')
        self.assertIs(await queue.get(),_EOF)
        await task
