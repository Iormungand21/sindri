#!/usr/bin/env python
"""Test that tasks complete properly with the delegation fix."""

import asyncio
import logging
import structlog

# Configure structlog for INFO level
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

from sindri.core.orchestrator import Orchestrator
from sindri.core.loop import LoopConfig

async def main():
    print("\n=== Testing Task Completion with Delegation Fix ===\n")

    config = LoopConfig(max_iterations=5)
    orchestrator = Orchestrator(config=config, total_vram_gb=16.0, enable_memory=False)

    task = 'Create a file called test_completion.txt with the text "Delegation works!"'
    print(f"Task: {task}\n")

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=60.0)
        print(f"\n=== RESULT ===")
        print(f"Success: {result.get('success')}")
        print(f"Reason: {result.get('reason')}")
        print(f"Iterations: {result.get('iterations')}")

        # Check if file was created
        import os
        if os.path.exists('test_completion.txt'):
            with open('test_completion.txt', 'r') as f:
                content = f.read()
            print(f"\n✓ File created successfully!")
            print(f"Content: {content}")
        else:
            print(f"\n✗ File was not created")

    except asyncio.TimeoutError:
        print("\n!!! TIMEOUT after 60 seconds !!!")
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
