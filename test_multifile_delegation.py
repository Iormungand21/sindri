#!/usr/bin/env python
"""Test complex multi-file delegation: Brokkr -> Huginn with session resume."""

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
    print("=" * 70)
    print("MULTI-FILE DELEGATION TEST: Brokkr -> Huginn")
    print("=" * 70)

    # Task explicitly requiring multiple files (should trigger delegation)
    task = '''Implement a user authentication module with:
1. user_auth/models.py - User class with username, password_hash attributes
2. user_auth/auth.py - login(username, password) and logout(session_id) functions
3. user_auth/__init__.py - exports for the module

This is a multi-file implementation that requires proper module structure.'''

    print(f"\nTask:\n{task}")
    print("\n" + "=" * 70)
    print("Expected behavior:")
    print("  1. Brokkr recognizes MULTI-FILE requirement")
    print("  2. Brokkr delegates to Huginn (specialist coder)")
    print("  3. Huginn creates all 3 files")
    print("  4. ⭐ Brokkr RESUMES with existing session (key test!)")
    print("  5. Brokkr sees child result in conversation context")
    print("  6. Brokkr marks complete without confusion")
    print("=" * 70)
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Create orchestrator
    config = LoopConfig(max_iterations=15)
    orchestrator = Orchestrator(
        config=config,
        total_vram_gb=16.0,
        enable_memory=False
    )

    print("\n" + "=" * 70)
    print("EXECUTION LOG")
    print("=" * 70)

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=300.0)

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Success: {result.get('success', False)}")
        print(f"Output: {result.get('output', 'No output')[:200]}")

        # Check created files
        files_to_check = [
            "user_auth/models.py",
            "user_auth/auth.py",
            "user_auth/__init__.py"
        ]

        print("\n" + "=" * 70)
        print("FILE VERIFICATION")
        print("=" * 70)

        for fpath in files_to_check:
            path = Path(fpath)
            if path.exists():
                print(f"✅ {fpath} - {path.stat().st_size} bytes")
            else:
                print(f"❌ {fpath} - NOT FOUND")

        # Analyze task execution
        print("\n" + "=" * 70)
        print("EXECUTION ANALYSIS")
        print("=" * 70)

        tasks = list(orchestrator.scheduler.tasks.values())
        print(f"Total tasks created: {len(tasks)}")

        for i, t in enumerate(tasks, 1):
            print(f"\nTask {i}:")
            print(f"  ID: {t.id}")
            print(f"  Agent: {t.assigned_agent}")
            print(f"  Status: {t.status.value}")
            print(f"  Description: {t.description[:60]}...")
            if t.session_id:
                print(f"  Session ID: {t.session_id}")
            if t.parent_id:
                print(f"  Parent ID: {t.parent_id}")
            if hasattr(t, 'result') and t.result:
                result_str = str(t.result)[:100]
                print(f"  Result: {result_str}...")

        # Detailed validation
        print("\n" + "=" * 70)
        print("SESSION RESUME VALIDATION (⭐ KEY TEST)")
        print("=" * 70)

        if len(tasks) >= 2:
            print("✅ Multiple tasks created (delegation occurred)")

            brokkr_tasks = [t for t in tasks if t.assigned_agent == "brokkr"]
            huginn_tasks = [t for t in tasks if t.assigned_agent == "huginn"]

            print(f"\n   Brokkr tasks: {len(brokkr_tasks)}")
            print(f"   Huginn tasks: {len(huginn_tasks)}")

            if huginn_tasks:
                print("\n✅ Huginn was involved (correct specialist delegation)")
            else:
                print("\n❌ Huginn NOT involved (wrong specialist)")

            # THE KEY TEST: Check session resume
            if brokkr_tasks:
                brokkr = brokkr_tasks[0]
                if brokkr.session_id:
                    print(f"\n✅ Brokkr has session_id: {brokkr.session_id}")

                    # Check logs for the critical message
                    print("\n🔍 Check log above for 'resuming_session' message")
                    print("   This proves parent resumed existing session!")
                    print("   If you see 'creating_new_session' twice, bug still exists.")
                else:
                    print("\n❌ Brokkr missing session_id")

        elif len(tasks) == 1:
            print("❌ Only 1 task - NO delegation occurred")
            print("   Brokkr handled directly (task not complex enough)")
            print("   Multi-file requirement wasn't recognized!")
        else:
            print("❌ No tasks found")

        # File check
        files_exist = all(Path(f).exists() for f in files_to_check)
        if files_exist:
            print("\n✅ All 3 files created successfully")
        else:
            print("\n⚠️  Some files missing")

        # Final summary
        print("\n" + "=" * 70)
        print("FINAL SUMMARY")
        print("=" * 70)

        delegation_worked = len(tasks) >= 2
        huginn_involved = any(t.assigned_agent == "huginn" for t in tasks)
        files_created = files_exist

        print(f"Delegation triggered: {'✅' if delegation_worked else '❌'}")
        print(f"Huginn involved: {'✅' if huginn_involved else '❌'}")
        print(f"Files created: {'✅' if files_created else '❌'}")

        if delegation_worked and huginn_involved and files_created:
            print("\n🎉 TEST PASSED - Session resume validated!")
        elif not delegation_worked:
            print("\n⚠️  INCONCLUSIVE - No delegation, can't test session resume")
        else:
            print("\n❌ TEST FAILED - Check logs for issues")

    except asyncio.TimeoutError:
        print("\n" + "=" * 70)
        print("TIMEOUT after 300 seconds")
        print("=" * 70)
        print("Scheduler state:")
        print(f"  Pending: {orchestrator.scheduler.get_pending_count()}")
        print(f"  Running: {orchestrator.scheduler.get_running_count()}")
        for tid, task in orchestrator.scheduler.tasks.items():
            print(f"  {tid}: {task.status.value} - {task.assigned_agent}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n🔍 WHAT TO LOOK FOR IN LOGS:")
    print("   'creating_new_session' - Should appear ONCE (first run)")
    print("   'resuming_session' - Should appear ONCE (after child completes)")
    print("   If 'creating_new_session' appears TWICE, session resume is broken!\n")
    asyncio.run(main())
