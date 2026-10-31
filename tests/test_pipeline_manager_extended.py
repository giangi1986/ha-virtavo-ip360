import asyncio, importlib.util, pathlib, unittest
P = pathlib.Path(__file__).resolve().parents[1] / 'custom_components/virtavo/engine/pipeline_manager.py'
spec = importlib.util.spec_from_file_location('virtavo_manager', P)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.starts=0; self.stops=0
        async def factory():
            self.starts+=1
            try: await asyncio.Event().wait()
            finally: self.stops+=1
        self.manager=m.PipelineManager(factory,idle_seconds=.01)
    async def asyncTearDown(self): await self.manager.stop()
    async def test_acquire_and_idle_stop(self):
        await self.manager.acquire('a'); await asyncio.sleep(0)
        self.assertEqual(self.starts,1)
        await self.manager.release('a'); await asyncio.sleep(.03)
        self.assertEqual(self.stops,1)
    async def test_multiple_viewers(self):
        await self.manager.acquire('a'); await self.manager.acquire('b'); await asyncio.sleep(0)
        await self.manager.release('a'); await asyncio.sleep(.03)
        self.assertEqual(self.stops,0)
        await self.manager.release('b'); await asyncio.sleep(.03)
        self.assertEqual(self.stops,1)
    async def test_reacquire_cancels_idle(self):
        await self.manager.acquire('a'); await asyncio.sleep(0)
        await self.manager.release('a'); await self.manager.acquire('b'); await asyncio.sleep(.03)
        self.assertEqual(self.starts,1); self.assertEqual(self.stops,0)
    async def test_continuous_keeps_stream(self):
        await self.manager.start_continuous(); await asyncio.sleep(0)
        await self.manager.acquire('a'); await self.manager.release('a'); await asyncio.sleep(.03)
        self.assertEqual(self.stops,0)
    async def test_refresh_timeout(self):
        await self.manager.refresh_viewer('a',timeout=.01); await asyncio.sleep(.04)
        self.assertEqual(self.stops,1)
    async def test_refresh_resets_timeout(self):
        await self.manager.refresh_viewer('a',timeout=.03); await asyncio.sleep(.02)
        await self.manager.refresh_viewer('a',timeout=.03); await asyncio.sleep(.02)
        self.assertEqual(self.stops,0)
        await asyncio.sleep(.04); self.assertEqual(self.stops,1)
