"""On-demand lifecycle for one Virtavo pipeline and multiple viewers."""
import asyncio
import contextlib
import math


class PipelineManager:
    def __init__(self, pipeline_factory, continuous=False, idle_seconds=5):
        if not isinstance(idle_seconds, (int, float)) or not math.isfinite(idle_seconds) or idle_seconds < 0:
            raise ValueError('idle_seconds must be nonnegative')
        self.pipeline_factory = pipeline_factory
        self.continuous = continuous
        self.idle_seconds = idle_seconds
        self.task = None
        self.viewers = set()
        self._idle_task = None
        self._viewer_timers = {}
        self._lock = asyncio.Lock()

    def _cancel_idle(self):
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None

    async def _start_locked(self):
        if self.task is not None and not self.task.done():
            return
        if self.task is not None:
            # Observe a previous failure before replacing the task.
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self.task
        self.task = asyncio.create_task(self.pipeline_factory())

    async def acquire(self, viewer):
        async with self._lock:
            self._cancel_idle()
            await self._start_locked()
            self.viewers.add(viewer)

    def _release_locked(self, viewer):
        self.viewers.discard(viewer)
        timer = self._viewer_timers.pop(viewer, None)
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        if not self.viewers and not self.continuous:
            self._cancel_idle()
            self._idle_task = asyncio.create_task(self._stop_when_idle())

    async def release(self, viewer):
        async with self._lock:
            self._release_locked(viewer)

    async def _stop_when_idle(self):
        current = asyncio.current_task()
        try:
            await asyncio.sleep(self.idle_seconds)
            async with self._lock:
                if not self.viewers and not self.continuous:
                    await self._stop_locked()
        except asyncio.CancelledError:
            pass
        finally:
            if self._idle_task is current:
                self._idle_task = None

    async def _stop_locked(self):
        task, self.task = self.task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await task

    async def refresh_viewer(self, viewer, timeout=30):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be positive')
        # Timer replacement, acquire and expiry share the same lock: an old
        # expiry cannot discard a viewer after a newer refresh has acquired it.
        async with self._lock:
            previous = self._viewer_timers.pop(viewer, None)
            if previous:
                previous.cancel()
            self._cancel_idle()
            await self._start_locked()
            self.viewers.add(viewer)

            async def expire():
                current = asyncio.current_task()
                try:
                    await asyncio.sleep(timeout)
                    async with self._lock:
                        if self._viewer_timers.get(viewer) is current:
                            self._release_locked(viewer)
                except asyncio.CancelledError:
                    pass
            self._viewer_timers[viewer] = asyncio.create_task(expire())

    async def start_continuous(self):
        async with self._lock:
            self.continuous = True
            self._cancel_idle()
            await self._start_locked()

    async def stop(self):
        async with self._lock:
            self.continuous = False
            pending = list(self._viewer_timers.values())
            if self._idle_task:
                pending.append(self._idle_task)
            self._cancel_idle()
            for timer in self._viewer_timers.values():
                timer.cancel()
            self._viewer_timers.clear()
            self.viewers.clear()
            await self._stop_locked()
        # Join cancelled housekeeping tasks after releasing the lock.
        await asyncio.gather(*pending, return_exceptions=True)
