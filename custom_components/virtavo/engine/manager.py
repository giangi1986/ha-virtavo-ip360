"""Owned asynchronous manager TCP channel with bounded response association."""
import asyncio
import contextlib
import struct
import math

from .net_auth import HEADER,MAGIC,MAX_FRAME,ProtocolError,parse_frame


class ManagerConnection:
    def __init__(self,reader,writer,*,timeout=8):
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:
            raise ValueError('Invalid manager timeout')
        self.reader=reader
        self.writer=writer
        self.timeout=timeout
        self._pending={}
        self._send_lock=asyncio.Lock()
        self._failure=None
        self._closed=False
        self._reader_task=asyncio.create_task(self._read_loop())

    @classmethod
    async def connect(cls,host,port,*,timeout=8):
        reader,writer=await asyncio.wait_for(asyncio.open_connection(host,port),timeout)
        return cls(reader,writer,timeout=timeout)

    @property
    def failed(self):return self._failure is not None

    async def _read_loop(self):
        try:
            while True:
                header=await self.reader.readexactly(HEADER.size)
                magic,command,revision,version,total,status=HEADER.unpack(header)
                if magic!=MAGIC or not HEADER.size<=total<=MAX_FRAME:
                    raise ProtocolError('Invalid manager frame header')
                # Header idle is allowed, but a partial advertised payload has
                # a finite deadline. Never allocate based on an unchecked size.
                payload=await asyncio.wait_for(self.reader.readexactly(total-HEADER.size),self.timeout)
                raw=header+payload
                pending=self._pending.get(command)
                if pending is not None:
                    future,accept=pending
                    if not future.done():
                        if status:
                            self._pending.pop(command,None)
                            future.set_exception(ProtocolError('Manager rejected request'))
                        elif accept is None or accept(raw):
                            self._pending.pop(command,None)
                            future.set_result(raw)
                # Unsolicited callbacks (notably20202) are consumed, never
                # treated as the response to a request for a different command.
        except asyncio.CancelledError:
            raise
        except Exception:
            self._failure=ProtocolError('Manager connection lost or malformed')
            for future,accept in self._pending.values():
                if not future.done():future.set_exception(self._failure)
            self._pending.clear()

    async def request(self,frame,*,expected_command,accept=None):
        return await self.request_packets((frame,),expected_command=expected_command,accept=accept)

    async def request_packets(self,frames,*,expected_command,accept=None):
        if not isinstance(frames,(tuple,list)) or not 1<=len(frames)<=8:
            raise ValueError('Bounded request sequence required')
        for frame in frames:parse_frame(frame)
        if accept is not None and not callable(accept):raise TypeError('Response predicate required')
        if type(expected_command) is not int or not 0<=expected_command<=0xffffffff:
            raise ValueError('Invalid expected manager command')
        async with self._send_lock:
            if self._closed or self.failed:
                raise ProtocolError('Manager connection unavailable')
            if expected_command in self._pending:
                raise ProtocolError('Concurrent request for same response command')
            future=asyncio.get_running_loop().create_future()
            self._pending[expected_command]=(future,accept)
            try:
                self.writer.write(b''.join(frames))
                await asyncio.wait_for(self.writer.drain(),self.timeout)
                return await asyncio.wait_for(future,self.timeout)
            except BaseException:
                # A late reply must never satisfy a later request with the
                # same command after timeout/cancellation. Abandon the channel.
                await self.close()
                raise
            finally:
                if self._pending.get(expected_command,(None,None))[0] is future:
                    self._pending.pop(expected_command,None)
                if not future.done():future.cancel()

    async def close(self):
        if self._closed:return
        self._closed=True
        self._reader_task.cancel()
        await asyncio.gather(self._reader_task,return_exceptions=True)
        for future,accept in self._pending.values():
            if not future.done():future.cancel()
        self._pending.clear()
        self.writer.close()
        with contextlib.suppress(OSError,asyncio.TimeoutError):
            await asyncio.wait_for(self.writer.wait_closed(),3)
