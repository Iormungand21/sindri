#!/usr/bin/env python
"""Test orchestrator with debug output."""

import asyncio
import logging
import structlog

# Configure structlog for DEBUG level
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

from sindri.core.orchestrator import Orchestrator
from sindri.core.loop import LoopConfig

async def main():
    print("Creating orchestrator...")
    config = LoopConfig(max_iterations=5)  # Lower iterations for faster debugging
    orchestrator = Orchestrator(config=config, total_vram_gb=16.0, enable_memory=False)

    print("\nStarting task...")
    task = 'Create a hello.txt file with the text "test"'

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=15.0)
        print(f"\nResult: {result}")
    except asyncio.TimeoutError:
        print("\n!!! TIMEOUT after 15 seconds !!!")
        print(f"Scheduler stats:")
        print(f"  Has work: {orchestrator.scheduler.has_work()}")
        print(f"  Pending: {orchestrator.scheduler.get_pending_count()}")
        print(f"  Running: {orchestrator.scheduler.get_running_count()}")
        print(f"  Tasks: {list(orchestrator.scheduler.tasks.keys())}")
        for tid, task in orchestrator.scheduler.tasks.items():
            print(f"    {tid}: {task.status.value} - {task.description[:50]}")

if __name__ == "__main__":
    asyncio.run(main())
