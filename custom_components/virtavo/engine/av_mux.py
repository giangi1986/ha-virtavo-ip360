"""Mux decrypted HEVC and optional raw G.711 A-law into MPEG-TS.

The caller owns camera/session reception and DES. This stage uses no SDK,
PCAP or external RTSP server. Audio timing comes from its 8000 Hz sample count;
video uses the FFmpeg reader's arrival clock. The unverified native timestamp
is deliberately not converted to media PTS. Exact A/V sync is not certified.
"""
import asyncio
import contextlib
import os


class _PipeWriter:
    def __init__(self,fd):
        self.fd=fd
        self.pending=b''
        os.set_blocking(fd,False)
    def write(self,data):
        if self.pending or not isinstance(data,bytes) or len(data)>65536:
            raise ValueError('Bounded writes must be drained')
        self.pending=data
    async def drain(self):
        while self.pending:
            try:
                sent=os.write(self.fd,self.pending)
                self.pending=self.pending[sent:]
            except BlockingIOError:
                loop=asyncio.get_running_loop()
                future=loop.create_future()
                def ready():
                    if not future.done():future.set_result(None)
                loop.add_writer(self.fd,ready)
                try:await future
                finally:loop.remove_writer(self.fd)
    def close(self):
        if self.fd is not None:
            fd,self.fd=self.fd,None
            os.close(fd)


def ffmpeg_mux_args(*,audio_fd=None,fps=20):
    if type(fps) is not int or not 1<=fps<=120:raise ValueError('Invalid FPS')
    args=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-fflags','+genpts',
          '-f','hevc','-r',str(fps),'-use_wallclock_as_timestamps','1','-i','pipe:0']
    if audio_fd is not None:
        if type(audio_fd) is not int or audio_fd<0:raise ValueError('Invalid audio descriptor')
        args+=['-f','alaw','-ar','8000','-ac','1','-i',f'pipe:{audio_fd}']
    args+=['-map','0:v:0','-c:v','copy']
    args+=['-map','1:a:0','-c:a','aac','-b:a','32k'] if audio_fd is not None else ['-an']
    return args+['-mpegts_flags','+resend_headers','-f','mpegts','pipe:1']


async def mux_streams(video_reader,output_writer,*,audio_reader=None,fps=20):
    """Drain both bounded sources; cancellation/error terminates the child."""
    process=None
    audio_write=None
    read_fd=None
    tasks=[]
    try:
        if audio_reader is not None:
            if os.name!='posix':raise NotImplementedError('Audio pipe requires POSIX')
            read_fd,write_fd=os.pipe()
            audio_write=_PipeWriter(write_fd)
        args=ffmpeg_mux_args(audio_fd=read_fd,fps=fps)
        extra={'pass_fds':(read_fd,)} if read_fd is not None else {}
        process=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,**extra)
        if read_fd is not None:
            os.close(read_fd);read_fd=None
        async def forward(reader,writer,close):
            try:
                while data:=await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            finally:
                if close:writer.close()
        tasks=[asyncio.create_task(forward(video_reader,process.stdin,True)),
               asyncio.create_task(forward(process.stdout,output_writer,False))]
        if audio_reader is not None:
            tasks.append(asyncio.create_task(forward(audio_reader,audio_write,True)))
        wait=asyncio.create_task(process.wait());tasks.append(wait)
        pending=set(tasks)
        while pending:
            done,pending=await asyncio.wait(pending,return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                value=task.result()
                if task is wait:
                    if value!=0:raise RuntimeError('Media mux process failed')
                    await tasks[1]  # Drain already-buffered MPEG-TS output.
                    return 0
        return 0
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if audio_write is not None:audio_write.close()
        if read_fd is not None:os.close(read_fd)
        if process is not None:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):process.terminate()
            async def reap():
                await asyncio.gather(process.wait(),process.stdout.read(),return_exceptions=True)
            try:await asyncio.wait_for(reap(),3)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):process.kill()
                await asyncio.wait_for(reap(),3)
