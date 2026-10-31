"""Owned receiver -> existing pure-Python DES -> optional A/V mux pipeline."""
import asyncio
import contextlib
import os
from pathlib import Path
import sys

from .av_mux import mux_streams
from .byte_pipe import BytePipe

DES_LAUNCHER=Path(__file__).with_name('des_launcher_isolato.py')


async def run_media_pipeline(source_factory,des_code,output_writer,*,audio=False,fps=20):
    """Run one camera session; the source receives video and optional audio sinks.

    The derived key input travels over a private inherited pipe, never argv,
    environment, log output or a temporary credential file. The DES algorithm
    itself is the recovered, unchanged Python implementation.
    """
    if not callable(source_factory):raise TypeError('Source factory required')
    if not isinstance(des_code,str) or not des_code or len(des_code.encode('utf-8'))>256:
        raise ValueError('Bounded derived DES input required')
    if type(audio) is not bool:raise ValueError('Audio setting must be boolean')
    if not DES_LAUNCHER.is_file():raise FileNotFoundError('Python DES launcher unavailable')
    process=None
    read_fd=None
    tasks=[]
    audio_pipe=BytePipe() if audio else None
    try:
        read_fd,write_fd=os.pipe()
        try:
            os.write(write_fd,des_code.encode('utf-8'))
        finally:os.close(write_fd)
        process=await asyncio.create_subprocess_exec(sys.executable,'-u',str(DES_LAUNCHER),
                    '--code-fd',str(read_fd),stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
                    pass_fds=(read_fd,))
        os.close(read_fd);read_fd=None

        async def send_video(data):
            if not isinstance(data,bytes) or len(data)>65536:raise ValueError('Bounded video chunk required')
            process.stdin.write(data)
            await process.stdin.drain()
        async def send_audio(data):
            # This sink is not supplied at all in video-only mode.
            await audio_pipe.put(data)
        async def source():
            try:await source_factory(send_video,send_audio if audio else None)
            finally:
                process.stdin.close()
                if audio_pipe is not None:await audio_pipe.feed_eof()

        source_task=asyncio.create_task(source())
        mux_task=asyncio.create_task(mux_streams(process.stdout,output_writer,audio_reader=audio_pipe,fps=fps))
        child_task=asyncio.create_task(process.wait())
        tasks=[source_task,mux_task,child_task]
        pending=set(tasks)
        while pending:
            done,pending=await asyncio.wait(pending,return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                result=task.result()
                if task is child_task:
                    if result!=0:raise RuntimeError('Python DES process failed')
                    if not source_task.done():raise RuntimeError('Python DES ended before source')
                if task is mux_task and not source_task.done():
                    raise RuntimeError('Mux ended before live source')
        return 0
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if audio_pipe is not None:await audio_pipe.feed_eof()
        if read_fd is not None:os.close(read_fd)
        if process is not None:
            process.stdin.close()
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):process.terminate()
            async def reap():
                await asyncio.gather(process.wait(),process.stdout.read(),return_exceptions=True)
            try:await asyncio.wait_for(reap(),3)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):process.kill()
                await asyncio.wait_for(reap(),3)
