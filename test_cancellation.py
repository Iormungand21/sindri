#!/usr/bin/env python
"""Test task cancellation feature."""

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
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

from sindri.core.orchestrator import Orchestrator
from sindri.core.loop import LoopConfig
from sindri.core.tasks import TaskStatus

async def test_cancellation():
    print("=" * 70)
    print("TASK CANCELLATION TEST")
    print("=" * 70)

    # Create a task that will iterate multiple times
    task = """List all Python files in the current directory and subdirectories.
For each file, count the number of lines and show a summary."""

    print(f"\n📝 Test Task (will be cancelled after 5 seconds):\n{task[:100]}...")
    print("\n" + "=" * 70)
    print("TEST PROCEDURE")
    print("=" * 70)
    print("1. Start long-running task")
    print("2. Wait 5 seconds")
    print("3. Request cancellation")
    print("4. Verify task cancelled properly")
    print("=" * 70)

    # Create orchestrator
    config = LoopConfig(max_iterations=20)
    orchestrator = Orchestrator(
        config=config,
        total_vram_gb=16.0,
        enable_memory=False
    )

    # Start task in background
    print("\n▶ Starting task...")
    task_future = asyncio.create_task(orchestrator.run(task))

    # Wait 5 seconds then cancel
    print("⏱  Waiting 5 seconds before cancellation...")
    await asyncio.sleep(5)

    print("\n⊗ Requesting cancellation...")
    # Get root task ID (first task in scheduler)
    root_task_id = list(orchestrator.scheduler.tasks.keys())[0]
    root_task = orchestrator.scheduler.tasks[root_task_id]

    print(f"   Root task ID: {root_task_id}")
    print(f"   Status before cancel: {root_task.status.value}")

    # Cancel the task
    orchestrator.cancel_task(root_task_id)

    print("   cancel_requested flag set")
    print("   Waiting for task to abort...")

    # Wait for task to complete (longer timeout to allow LLM to finish current call)
    try:
        result = await asyncio.wait_for(task_future, timeout=60.0)

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Success: {result.get('success', False)}")
        print(f"Error: {result.get('error', 'None')}")
        print(f"Output: {result.get('output', 'No output')}")

        # Check task status
        print("\n" + "=" * 70)
        print("TASK STATUS")
        print("=" * 70)
        print(f"Status: {root_task.status.value}")
        print(f"Cancel requested: {root_task.cancel_requested}")
        print(f"Error: {root_task.error}")

        # Validation
        print("\n" + "=" * 70)
        print("VALIDATION")
        print("=" * 70)

        checks = [
            ("Task marked as cancelled", root_task.status == TaskStatus.CANCELLED),
            ("Cancel requested flag set", root_task.cancel_requested == True),
            ("Error message set", root_task.error is not None),
            ("Result indicates failure", result.get('success') == False),
            ("Cancellation message in output", 'cancelled' in result.get('error', '').lower())
        ]

        for check, passed in checks:
            status = "✅" if passed else "❌"
            print(f"{status} {check}")

        all_passed = all(passed for _, passed in checks)

        if all_passed:
            print("\n🎉 CANCELLATION TEST PASSED")
            print("Task was properly cancelled and status updated")
        else:
            print("\n⚠️  Some checks failed")

    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT - Task did not respond to cancellation within 10 seconds")
        print("   This indicates cancellation checking may not be working")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_cancellation())
