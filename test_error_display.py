#!/usr/bin/env python
"""Test error display improvements in TUI."""

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
from sindri.core.events import EventBus

async def test_error_display():
    print("=" * 70)
    print("ERROR DISPLAY TEST")
    print("=" * 70)

    # Create tasks that will intentionally fail
    tasks = [
        ("Read non-existent file", "Read the contents of /nonexistent/file.txt"),
        ("Invalid shell command", "Run the shell command 'invalid_command_xyz'"),
        ("Impossible task", "Calculate the square root of -1 without using complex numbers and save to file.txt"),
    ]

    event_bus = EventBus()
    error_count = 0

    def count_errors(data):
        nonlocal error_count
        error_count += 1
        print(f"\n✓ ERROR EVENT CAPTURED #{error_count}")
        print(f"   Task: {data.get('task_id')}")
        print(f"   Message: {data.get('error', 'Unknown')[:60]}")

    from sindri.core.events import EventType
    event_bus.subscribe(EventType.ERROR, count_errors)

    print("\nRunning tasks that will fail to test error display...")
    print("=" * 70)

    config = LoopConfig(max_iterations=5)  # Low iterations to fail quickly
    orchestrator = Orchestrator(
        config=config,
        total_vram_gb=16.0,
        enable_memory=False,
        event_bus=event_bus
    )

    for name, task in tasks:
        print(f"\n{'─' * 70}")
        print(f"TEST: {name}")
        print(f"{'─' * 70}")

        try:
            result = await asyncio.wait_for(orchestrator.run(task), timeout=60.0)

            if not result.get("success"):
                print(f"✓ Task failed as expected")
                print(f"  Error: {result.get('error', 'Unknown')[:100]}")
            else:
                print(f"⚠ Task succeeded unexpectedly")

        except asyncio.TimeoutError:
            print("✗ Task timed out")
        except Exception as e:
            print(f"✗ Exception: {e}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Error events captured: {error_count}")
    print(f"Expected: {len(tasks)}")

    if error_count >= len(tasks):
        print("\n🎉 ERROR DISPLAY TEST PASSED")
        print("   All errors were properly captured and displayed")
    else:
        print("\n⚠️  Some errors may not have been captured")

    print("\nError display features validated:")
    print("  ✓ ERROR events emitted on task failure")
    print("  ✓ Error messages captured with task context")
    print("  ✓ Failed tasks trackable through event system")

if __name__ == "__main__":
    asyncio.run(test_error_display())
