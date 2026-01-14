#!/usr/bin/env python
"""Test error display with real failures (max iterations)."""

import asyncio
import logging
import structlog

# Configure logging
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
from sindri.core.events import EventBus, EventType

async def main():
    print("=" * 70)
    print("ERROR DISPLAY TEST - Max Iterations Failure")
    print("=" * 70)

    # Very complex task with only 2 iterations = guaranteed failure
    task = """Refactor the entire Sindri codebase to use async generators
instead of regular async functions, update all tests, add comprehensive
documentation for every function, and ensure 100% test coverage."""

    print(f"\nTask (will hit max iterations):\n{task[:100]}...")
    print("\n" + "=" * 70)

    event_bus = EventBus()
    error_captured = {}

    def capture_error(data):
        error_captured['task_id'] = data.get('task_id')
        error_captured['error'] = data.get('error')
        error_captured['agent'] = data.get('agent')
        print(f"\n✓ ERROR EVENT CAPTURED")
        print(f"   Task: {data.get('task_id')}")
        print(f"   Agent: {data.get('agent')}")
        print(f"   Error: {data.get('error')[:80]}")

    event_bus.subscribe(EventType.ERROR, capture_error)

    # Very low max iterations to force failure
    config = LoopConfig(max_iterations=2)
    orchestrator = Orchestrator(
        config=config,
        total_vram_gb=16.0,
        enable_memory=False,
        event_bus=event_bus
    )

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=120.0)

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Success: {result.get('success')}")
        print(f"Error: {result.get('error')}")

        # Validation
        print("\n" + "=" * 70)
        print("VALIDATION")
        print("=" * 70)

        checks = [
            ("Task failed", not result.get('success')),
            ("ERROR event emitted", 'task_id' in error_captured),
            ("Error message present", bool(error_captured.get('error'))),
            ("Agent identified", bool(error_captured.get('agent')))
        ]

        for check, passed in checks:
            status = "✅" if passed else "❌"
            print(f"{status} {check}")

        if all(passed for _, passed in checks):
            print("\n🎉 ERROR DISPLAY TEST PASSED")
            print("   Errors are properly captured and displayable in TUI")
        else:
            print("\n⚠️  Some checks failed")

    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
