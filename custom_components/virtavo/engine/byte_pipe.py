"""Bounded async byte pipe shared by receiver and media subprocesses."""
import asyncio
from collections import deque


class BytePipe:
    def __init__(self,capacity=1024*1024):
        if type(capacity) is not int or capacity<65536:
            raise ValueError('Pipe capacity must allow one bounded media chunk')
        self.capacity=capacity
        self._chunks=deque()
        self._size=0
        self._eof=False
        self._condition=asyncio.Condition()

    async def put(self,data):
        if not isinstance(data,bytes) or len(data)>65536:
            raise ValueError('Bounded byte chunk required')
        if not data:return
        async with self._condition:
            await self._condition.wait_for(lambda:self._eof or self._size+len(data)<=self.capacity)
            if self._eof:raise ConnectionError('Byte pipe is closed')
            self._chunks.append(data)
            self._size+=len(data)
            self._condition.notify_all()

    async def read(self,size=65536):
        if type(size) is not int or not 1<=size<=65536:
            raise ValueError('Bounded read size required')
        async with self._condition:
            await self._condition.wait_for(lambda:self._chunks or self._eof)
            if not self._chunks:return b''
            result=bytearray()
            while self._chunks and len(result)<size:
                chunk=self._chunks.popleft()
                take=min(len(chunk),size-len(result))
                result.extend(chunk[:take])
                if take<len(chunk):self._chunks.appendleft(chunk[take:])
            self._size-=len(result)
            self._condition.notify_all()
            return bytes(result)

    async def feed_eof(self):
        # EOF retains buffered bytes. Closing also releases blocked producers.
        async with self._condition:
            self._eof=True
            self._condition.notify_all()
