"""HA camera backed by an owned on-demand loopback source.

The guarded setup must supply real DeviceStream records from authenticated
account discovery before this platform can be enabled.
"""
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .engine.stream_endpoint import StreamEndpoint


@dataclass(frozen=True)
class DeviceStream:
    device_id: str = field(repr=False)
    name: str
    pipeline_factory: Callable[[object], Awaitable[None]] = field(repr=False)
    continuous: bool = False


async def async_setup_entry(hass, entry, async_add_entities):
    streams = entry.runtime_data
    if not isinstance(streams, tuple) or not streams or not all(isinstance(s, DeviceStream) for s in streams):
        raise ValueError('Authenticated device streams are required')
    async_add_entities([VirtavoCamera(stream) for stream in streams])


class VirtavoCamera(Camera):
    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_should_poll = False

    def __init__(self, device: DeviceStream):
        super().__init__()
        if not device.device_id or not callable(device.pipeline_factory):
            raise ValueError('Device identity and pipeline factory are required')
        self._attr_unique_id = device.device_id + '_camera'
        self._attr_name = 'Camera'
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)}, name=device.name,
            manufacturer='Virtavo / IP360 Home',
        )
        self._endpoint = StreamEndpoint(device.pipeline_factory, continuous=device.continuous)
        self._continuous = device.continuous

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._continuous:
            await self._endpoint.start()

    async def stream_source(self):
        return await self._endpoint.start()

    async def async_camera_image(self, width=None, height=None):
        return None

    async def async_will_remove_from_hass(self):
        # Close our HTTP source before joining HA's reader thread. A stalled
        # upstream can otherwise leave that thread blocked in PyAV socket I/O.
        try:
            await self._endpoint.stop()
        finally:
            try:
                if self.stream is not None:
                    await self.stream.stop()
            finally:
                await super().async_will_remove_from_hass()
