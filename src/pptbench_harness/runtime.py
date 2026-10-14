"""Shared limits inherited by all tasks in a batch, never serialized into config."""
import asyncio
from contextvars import ContextVar
from contextlib import asynccontextmanager
AGENT_LIMIT=ContextVar('agent_limit',default=None)
RENDER_LIMIT=ContextVar('render_limit',default=None)

def configure(config):
    AGENT_LIMIT.set(asyncio.Semaphore(config['execution']['agent_concurrency']))
    RENDER_LIMIT.set(asyncio.Semaphore(config['execution']['render_concurrency']))

@asynccontextmanager
async def slot(kind):
    sem=(AGENT_LIMIT if kind=='agent' else RENDER_LIMIT).get()
    if sem is None:yield
    else:
        async with sem:yield
