"""Run async code that also does synchronous database work off the server loop.

Every SQLAlchemy call in this app is synchronous. On the server's event loop
even a short wait for a pooled connection stalls every request on the
instance: on 2026-10-11 an ``async def`` plan check that queried the database
froze Cloud Run for 30-90s (see tests/test_event_loop_not_blocked.py). So an
endpoint that touches the database is a plain ``def``, which FastAPI runs in
its threadpool.

A few helpers still interleave database work with awaited network calls and
are shared with the background job passes (alert checks, Discord delivery,
the IBKR Flex sync). A sync endpoint or job runner drives such a helper with
`run_on_private_loop`: a fresh event loop in the calling worker thread, so
both the awaits and the blocking database calls between them stay in that
thread. The session is still used by one thread at a time, and the RLS
context it carries is re-applied per transaction by
database._reapply_rls_context exactly as before.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


def run_on_private_loop(coro_fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    """Run `coro_fn(*args, **kwargs)` to completion on a new loop in this thread.

    Only call this from a worker thread (a ``def`` endpoint, a job runner, or
    asyncio.to_thread). Called from code already on an event loop it raises
    RuntimeError instead of silently blocking that loop.
    """
    return asyncio.run(coro_fn(*args, **kwargs))
