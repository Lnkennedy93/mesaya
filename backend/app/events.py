"""Pub/sub en memoria para tiempo real (SSE). Un canal por restaurante y por mesa."""
import asyncio
import json
from collections import defaultdict

_subs: dict[str, set] = defaultdict(set)
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop):
    global _loop
    _loop = loop


def publish(channel: str, event: str, data: dict | None = None):
    msg = {"event": event, "data": data or {}}
    if _loop is None:
        return
    for q in list(_subs.get(channel, ())):
        _loop.call_soon_threadsafe(_put, q, msg)


def _put(q, msg):
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        pass


async def stream(channel: str, request):
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subs[channel].add(q)
    try:
        yield "retry: 3000\n\n"
        yield "event: hello\ndata: {}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(q.get(), timeout=20)
                yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        _subs[channel].discard(q)
        if not _subs[channel]:
            _subs.pop(channel, None)
