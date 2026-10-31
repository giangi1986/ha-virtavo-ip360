import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1] / 'custom_components/virtavo/engine'
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
pipeline = load('video_pipeline')
lifecycle = load('pipeline_manager')
class LifecycleFailures(unittest.IsolatedAsyncioTestCase):
    async def test_failed_pipeline_stop_cleans_state(self):
        async def fail(): raise RuntimeError('synthetic failure')
        manager = lifecycle.PipelineManager(fail)
        await manager.acquire('a'); await asyncio.sleep(0)
        await manager.stop()
        self.assertIsNone(manager.task); self.assertFalse(manager.viewers)
    async def test_failed_pipeline_can_restart(self):
        attempts = []
        async def factory():
            attempts.append(1)
            if len(attempts) == 1: raise RuntimeError('synthetic failure')
            await asyncio.Event().wait()
        manager = lifecycle.PipelineManager(factory)
        await manager.acquire('a'); await asyncio.sleep(0)
        await manager.acquire('b'); await asyncio.sleep(0)
        self.assertEqual(len(attempts), 2); await manager.stop()
    async def test_manual_release_cancels_old_expiry(self):
        async def factory(): await asyncio.Event().wait()
        manager = lifecycle.PipelineManager(factory, idle_seconds=.01)
        await manager.refresh_viewer('a', timeout=.02)
        await manager.release('a'); await manager.acquire('a')
        await asyncio.sleep(.04)
        self.assertIn('a', manager.viewers); self.assertFalse(manager.task.done())
        await manager.stop()
    async def test_stop_joins_timers(self):
        async def factory(): await asyncio.Event().wait()
        manager = lifecycle.PipelineManager(factory)
        await manager.refresh_viewer('a', timeout=50)
        timer = manager._viewer_timers['a']; await manager.stop()
        self.assertTrue(timer.done())
class TransportFailures(unittest.IsolatedAsyncioTestCase):
    async def test_audio_is_explicitly_unavailable(self):
        with self.assertRaises(NotImplementedError): pipeline.ffmpeg_args(audio=True)
    async def test_partial_spawn_failure_terminates_started_child(self):
        class Process:
            returncode = None
            stdout = None
            terminated = False
            def terminate(self): self.terminated = True; self.returncode = -15
            async def wait(self): return self.returncode
        child = Process(); calls = []
        async def spawn(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1: return child
            raise OSError('synthetic spawn failure')
        with tempfile.NamedTemporaryFile() as code:
            with patch.object(pipeline.DES.__class__, 'is_file', return_value=True), patch.object(pipeline.asyncio, 'create_subprocess_exec', side_effect=spawn):
                with self.assertRaises(OSError):
                    await pipeline.run_pipeline(['fake'], code.name, rtsp_url='rtsp://127.0.0.1/fake')
        self.assertTrue(child.terminated)

class SyntheticProcessChain(unittest.IsolatedAsyncioTestCase):
    async def run_chain(self, writer):
        import sys
        original = asyncio.create_subprocess_exec
        processes = []
        commands = [
            "import sys;sys.stdout.buffer.write(b'x'*200000);sys.stdout.buffer.flush()",
            "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.stdout.buffer.flush()",
            "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.stdout.buffer.flush()",
        ]
        async def spawn(*args, **kwargs):
            code = commands[len(processes)]
            process = await original(sys.executable, '-c', code, **kwargs)
            processes.append(process)
            return process
        try:
            with tempfile.NamedTemporaryFile() as code:
                with patch.object(pipeline.DES.__class__, 'is_file', return_value=True), patch.object(pipeline.asyncio, 'create_subprocess_exec', side_effect=spawn):
                    return await asyncio.wait_for(pipeline.run_pipeline(['fake'], code.name, output='mpegts', output_writer=writer), 5)
        finally:
            self.assertTrue(all(p.returncode is not None for p in processes))

    async def test_normal_eof_drains_all_bytes(self):
        class Writer:
            data = bytearray()
            def write(self, chunk): self.data.extend(chunk)
            async def drain(self): pass
        writer = Writer()
        self.assertEqual(await self.run_chain(writer), 0)
        self.assertEqual(bytes(writer.data), b'x'*200000)

    async def test_consumer_failure_stops_all_children(self):
        class Writer:
            def write(self, chunk): raise RuntimeError('consumer disconnected')
            async def drain(self): pass
        with self.assertRaisesRegex(RuntimeError, 'consumer disconnected'):
            await self.run_chain(Writer())

    async def test_broken_pipe_consumer_stops_all_children(self):
        class Writer:
            def write(self, chunk): raise BrokenPipeError('consumer closed')
            async def drain(self): pass
        with self.assertRaises(BrokenPipeError):
            await self.run_chain(Writer())

    async def test_cancel_while_consumer_blocked_reaps_children(self):
        reached_consumer = asyncio.Event()
        class Writer:
            def write(self, chunk): reached_consumer.set()
            async def drain(self): await asyncio.Event().wait()
        task = asyncio.create_task(self.run_chain(Writer()))
        await asyncio.wait_for(reached_consumer.wait(), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

class InputAndLauncherTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonfinite_or_invalid_timeout_is_rejected(self):
        async def factory(): await asyncio.Event().wait()
        for value in [float('nan'), float('inf'), -1, '30']:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): lifecycle.PipelineManager(factory, idle_seconds=value)
                manager = lifecycle.PipelineManager(factory)
                with self.assertRaises(ValueError): await manager.refresh_viewer('x', timeout=value)
                self.assertIsNone(manager.task)

    async def test_real_packaged_des_launcher_starts_without_ha(self):
        import sys
        with tempfile.NamedTemporaryFile(mode='w') as code:
            code.write('SYNTHETIC-NOT-A-DEVICE-SECRET'); code.flush()
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-I', str(ROOT / 'des_launcher_isolato.py'), '--code-file', code.name,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            output, error = await asyncio.wait_for(process.communicate(b'synthetic non-video framing'), 5)
            self.assertEqual(process.returncode, 0, error.decode())
            self.assertEqual(output, b'synthetic non-video framing')
