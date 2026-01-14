#!/usr/bin/env python
"""Test complex delegation: Brokkr -> Huginn with session resume validation."""

import asyncio
import logging
import structlog
from pathlib import Path

# Configure detailed logging
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
    print("=" * 60)
    print("COMPLEX DELEGATION TEST: Brokkr -> Huginn")
    print("=" * 60)

    # Task designed to require Huginn delegation
    task = '''Create a Python class called Calculator in calculator.py with these methods:
- add(a, b) - returns sum
- subtract(a, b) - returns difference
- multiply(a, b) - returns product
Include docstrings for each method.'''

    print(f"\nTask: {task}")
    print("\nExpected behavior:")
    print("  1. Brokkr recognizes this as complex (multi-method implementation)")
    print("  2. Brokkr delegates to Huginn")
    print("  3. Huginn implements the Calculator class")
    print("  4. Brokkr resumes with EXISTING session (key test!)")
    print("  5. Brokkr sees child result and completes")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Create orchestrator
    config = LoopConfig(max_iterations=15)
    orchestrator = Orchestrator(
        config=config,
        total_vram_gb=16.0,
        enable_memory=False  # Keep memory disabled for now
    )

    # Track task IDs to verify delegation
    print("\n" + "=" * 60)
    print("EXECUTION LOG")
    print("=" * 60)

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=300.0)

        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Success: {result.get('success', False)}")
        print(f"Output: {result.get('output', 'No output')}")

        # Check if file was created
        calc_file = Path("calculator.py")
        if calc_file.exists():
            print("\n✅ calculator.py created!")
            print(f"Size: {calc_file.stat().st_size} bytes")
            print("\nContent preview:")
            print("-" * 40)
            content = calc_file.read_text()
            lines = content.split('\n')[:20]  # First 20 lines
            for i, line in enumerate(lines, 1):
                print(f"{i:3d}: {line}")
            if len(content.split('\n')) > 20:
                print("...")
        else:
            print("\n❌ calculator.py NOT created")

        # Analyze task execution
        print("\n" + "=" * 60)
        print("EXECUTION ANALYSIS")
        print("=" * 60)

        tasks = list(orchestrator.scheduler.tasks.values())
        print(f"Total tasks created: {len(tasks)}")

        for i, t in enumerate(tasks, 1):
            print(f"\nTask {i}:")
            print(f"  ID: {t.id}")
            print(f"  Agent: {t.assigned_agent}")
            print(f"  Status: {t.status.value}")
            print(f"  Description: {t.description[:80]}...")
            if t.session_id:
                print(f"  Session ID: {t.session_id}")
            if t.parent_id:
                print(f"  Parent ID: {t.parent_id}")
            if t.result:
                print(f"  Result: {str(t.result)[:100]}...")

        # Validation
        print("\n" + "=" * 60)
        print("VALIDATION")
        print("=" * 60)

        if len(tasks) >= 2:
            print("✅ Multiple tasks created (delegation occurred)")

            brokkr_tasks = [t for t in tasks if t.assigned_agent == "brokkr"]
            huginn_tasks = [t for t in tasks if t.assigned_agent == "huginn"]

            print(f"   Brokkr tasks: {len(brokkr_tasks)}")
            print(f"   Huginn tasks: {len(huginn_tasks)}")

            if huginn_tasks:
                print("✅ Huginn was involved (correct delegation)")
            else:
                print("❌ Huginn NOT involved (incorrect delegation)")

            # Check session resume
            if brokkr_tasks:
                brokkr = brokkr_tasks[0]
                if brokkr.session_id:
                    print(f"✅ Brokkr has session_id: {brokkr.session_id}")
                    print("   (Session should have been resumed after child completed)")
                else:
                    print("❌ Brokkr missing session_id")
        else:
            print("❌ Only 1 task created (NO delegation - unexpected!)")
            print("   Brokkr may have handled it directly")

        if calc_file.exists():
            print("✅ Output file created successfully")
        else:
            print("❌ Output file NOT created")

    except asyncio.TimeoutError:
        print("\n" + "=" * 60)
        print("TIMEOUT after 300 seconds")
        print("=" * 60)
        print("Scheduler state:")
        print(f"  Pending: {orchestrator.scheduler.get_pending_count()}")
        print(f"  Running: {orchestrator.scheduler.get_running_count()}")
        for tid, task in orchestrator.scheduler.tasks.items():
            print(f"  {tid}: {task.status.value} - {task.assigned_agent} - {task.description[:50]}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\nNOTE: Check logs for 'resuming_session' vs 'creating_new_session'")
    print("This is the KEY indicator that session resume is working!\n")
    asyncio.run(main())
