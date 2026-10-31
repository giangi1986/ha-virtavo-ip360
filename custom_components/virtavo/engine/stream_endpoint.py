"""Owned loopback MPEG-TS source for HA; no external RTSP server required."""
import asyncio
import contextlib
import secrets

from aiohttp import web

from .pipeline_manager import PipelineManager

_EOF = object()


class StreamEndpoint:
    """One producer, bounded per-viewer buffers, and leases tied to HTTP readers."""

    def __init__(self, pipeline_factory, *, continuous=False, idle_seconds=5, queue_chunks=32):
        if type(queue_chunks) is not int or queue_chunks < 1:
            raise ValueError('queue_chunks must be a positive integer')
        self._factory = pipeline_factory
        self._queue_chunks = queue_chunks
        self._subscribers = set()
        self._runner = None
        self._source = None
        self._closing = False
        self._pending = b''
        self._lock = asyncio.Lock()
        self.manager = PipelineManager(self._produce, continuous=continuous, idle_seconds=idle_seconds)

    def write(self, data):
        if not isinstance(data, bytes) or len(data) > 65536:
            raise ValueError('expected bounded byte chunk')
        if self._pending:
            raise RuntimeError('writer drain required')
        self._pending = data

    async def drain(self):
        data, self._pending = self._pending, b''
        if not data:
            return
        for queue in tuple(self._subscribers):
            if queue.full():
                self._subscribers.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(_EOF)
            else:
                queue.put_nowait(data)
        await asyncio.sleep(0)

    async def _produce(self):
        try:
            await self._factory(self)
        finally:
            self._pending = b''
            for queue in tuple(self._subscribers):
                try:
                    # Keep normal EOF lossless. Only a reader stalled for a
                    # bounded interval is disconnected and has its queue dropped.
                    await asyncio.wait_for(queue.put(_EOF), timeout=1)
                except asyncio.TimeoutError:
                    self._subscribers.discard(queue)
                    while not queue.empty():
                        queue.get_nowait()
                    queue.put_nowait(_EOF)

    async def start(self):
        async with self._lock:
            if self._closing:
                raise RuntimeError('endpoint is closed')
            if self._runner is not None:
                return self._source
            token = secrets.token_urlsafe(32)
            app = web.Application()
            app.router.add_get('/' + token, self._handle)
            runner = web.AppRunner(app, access_log=None, shutdown_timeout=3)
            try:
                await runner.setup()
                site = web.TCPSite(runner, '127.0.0.1', 0)
                await site.start()
                self._source = f'http://127.0.0.1:{runner.addresses[0][1]}/{token}'
                self._runner = runner
                if self.manager.continuous:
                    await self.manager.start_continuous()
                return self._source
            except BaseException:
                await runner.cleanup()
                self._runner = None
                self._source = None
                raise

    async def _handle(self, request):
        if self._closing:
            raise web.HTTPServiceUnavailable()
        queue = asyncio.Queue(self._queue_chunks)
        viewer = object()
        self._subscribers.add(queue)
        response = web.StreamResponse(headers={
            'Content-Type': 'video/mp2t', 'Cache-Control': 'no-store',
        })
        try:
            await response.prepare(request)
            await self.manager.acquire(viewer)
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if request.transport is None or request.transport.is_closing():
                        break
                    continue
                if chunk is _EOF:
                    break
                await response.write(chunk)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._subscribers.discard(queue)
            if self._closing:
                # stop() already revoked every lease. Do not schedule a new
                # idle timer while runner.cleanup() is joining HTTP handlers.
                self.manager.viewers.discard(viewer)
            else:
                await self.manager.release(viewer)
            with contextlib.suppress(ConnectionError, RuntimeError):
                await response.write_eof()
        return response

    async def stop(self):
        async with self._lock:
            self._closing = True
            await self.manager.stop()
            for queue in tuple(self._subscribers):
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(_EOF)
            if self._runner is not None:
                await self._runner.cleanup()
                self._runner = None
            self._subscribers.clear()
            self._source = None
