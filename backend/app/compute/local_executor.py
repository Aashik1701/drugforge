"""
LocalExecutor — runs LOCAL/LOCAL_SMALL tools in-process, exactly as they run
today (this is a thin wrapper, not new execution logic). The only addition
over calling tool.fn directly is a concurrency gate matching
MAX_LOCAL_CONCURRENT_TOOLS: cheap/fast tools may briefly queue behind the
semaphore rather than being rejected outright — unlike heavy jobs, a few ms
of queuing for a sub-100ms prediction is invisible.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from tools.registry import Tool


class LocalExecutor:
    def __init__(self, max_concurrent: int = 2) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, tool: Tool, *args: Any, **kwargs: Any) -> Any:
        async with self._semaphore:
            if inspect.iscoroutinefunction(tool.fn):
                return await tool.fn(*args, **kwargs)
            return tool.fn(*args, **kwargs)
