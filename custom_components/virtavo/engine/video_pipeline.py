"""Portable Virtavo video process pipeline; no host-specific paths or shell."""

import asyncio
import contextlib
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
DES = ENGINE / "des" / "des_stream_puro_ottimizzato.py"
DES_LAUNCHER = ENGINE / "des_launcher_isolato.py"


def ffmpeg_args(codec="hevc", *, output="mpegts", rtsp_url=None, fps=20, audio=False):
    """Build a stream-copy command. MPEG-TS stdout matches the working exec chain."""
    if audio:
        raise NotImplementedError("Audio demultiplexing is not implemented")
    if codec not in ("hevc", "h264"):
        raise ValueError("Unsupported video codec")
    if output not in ("mpegts", "rtsp"):
        raise ValueError("Unsupported output")
    if output == "rtsp" and (not isinstance(rtsp_url, str) or not rtsp_url.startswith("rtsp://")):
        raise ValueError("RTSP destination required")
    if not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError("Invalid FPS")
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-fflags", "+genpts", "-f", codec, "-r", str(fps), "-use_wallclock_as_timestamps", "1", "-i", "pipe:0",
            "-map", "0:v:0", "-c:v", "copy", "-an"]
    if output == "mpegts":
        args += ["-mpegts_flags", "+resend_headers", "-f", "mpegts", "pipe:1"]
    else:
        args += ["-f", "rtsp", "-rtsp_transport", "tcp", rtsp_url]
    return args


async def run_pipeline(bridge_command, code_file, rtsp_url=None, codec="hevc", *,
                       output="rtsp", output_writer=None, fps=20, audio=False):
    """Run bridge -> DES -> FFmpeg, shutting down every child on exit/cancel.

    output='mpegts' writes stdout to an async StreamWriter-like destination;
    output='rtsp' publishes to an externally managed RTSP server. Neither mode
    starts a go2rtc server; the caller must arrange the consumer.
    """
    if not isinstance(bridge_command, (list, tuple)) or not bridge_command or not all(
        isinstance(arg, str) and arg for arg in bridge_command
    ):
        raise ValueError("Invalid bridge command")
    if not Path(code_file).is_file():
        raise FileNotFoundError("DES code file missing")
    if not DES.is_file() or not DES_LAUNCHER.is_file():
        raise FileNotFoundError("DES engine missing")
    if output == "mpegts" and output_writer is None:
        raise ValueError("MPEG-TS output requires a writer")
    ffargs = ffmpeg_args(codec, output=output, rtsp_url=rtsp_url, fps=fps, audio=audio)
    processes, tasks = [], []

    async def spawn(*args, **kwargs):
        proc = await asyncio.create_subprocess_exec(*args, **kwargs)
        processes.append(proc)
        return proc

    async def forward(reader, writer, *, close=True):
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            if close:
                writer.close()

    try:
        bridge = await spawn(*bridge_command, stdout=asyncio.subprocess.PIPE)
        des = await spawn(sys.executable, "-u", str(DES_LAUNCHER), "--code-file", str(code_file),
                          stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        ffmpeg = await spawn(*ffargs, stdin=asyncio.subprocess.PIPE,
                             stdout=asyncio.subprocess.PIPE if output == "mpegts" else asyncio.subprocess.DEVNULL)
        tasks += [asyncio.create_task(forward(bridge.stdout, des.stdin)),
                  asyncio.create_task(forward(des.stdout, ffmpeg.stdin))]
        if output == "mpegts":
            tasks.append(asyncio.create_task(forward(ffmpeg.stdout, output_writer, close=False)))
        watchers = [asyncio.create_task(p.wait()) for p in processes]
        tasks += watchers
        # Drain the complete chain on normal EOF. Successful bridge exit must
        # not truncate data buffered in DES or FFmpeg.
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                result = task.result()
                if task in watchers and result != 0:
                    raise RuntimeError(f"Video process exited with status {result}")
        return 0
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for proc in reversed(processes):
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()

        async def reap(proc):
            # A subprocess wait can block after exit while stdout's paused
            # reader still owns a full pipe. Drain it after forwarders stop.
            drains = []
            if proc.stdout is not None:
                drains.append(proc.stdout.read())
            await asyncio.gather(proc.wait(), *drains, return_exceptions=True)

        if processes:
            try:
                await asyncio.wait_for(asyncio.gather(*(reap(p) for p in processes)), 3)
            except asyncio.TimeoutError:
                for proc in processes:
                    if proc.returncode is None:
                        with contextlib.suppress(ProcessLookupError):
                            proc.kill()
                await asyncio.wait_for(asyncio.gather(*(reap(p) for p in processes)), 3)
