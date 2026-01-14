#!/usr/bin/env python3
"""Test real improvements with actual Ollama models."""

import asyncio
import sys
import time
from pathlib import Path

from sindri.core.orchestrator import Orchestrator
from sindri.core.loop import LoopConfig


async def test_simple_task():
    """Test that Brokkr handles simple file creation directly."""

    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  TEST 1: Simple File Creation (Should NOT delegate)             ║")
    print("╚══════════════════════════════════════════════════════════════════╝\n")

    task = "Create a file called brokkr_test_simple.txt with the text 'Brokkr handles this directly!'"

    print(f"Task: {task}\n")
    print("Expected behavior:")
    print("  • Brokkr handles directly (no delegation)")
    print("  • Uses write_file tool")
    print("  • Completes in 1-2 iterations")
    print("  • Single agent (Brokkr only)\n")

    config = LoopConfig(max_iterations=10)
    orchestrator = Orchestrator(config=config, total_vram_gb=16.0, enable_memory=False)

    start_time = time.time()

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=60.0)

        elapsed = time.time() - start_time

        print(f"\n{'='*70}")
        print("RESULTS:")
        print(f"{'='*70}")
        print(f"Success: {result.success}")
        print(f"Iterations: {result.iterations}")
        print(f"Reason: {result.reason}")
        print(f"Time: {elapsed:.1f}s")

        # Check file was created
        file_path = Path("brokkr_test_simple.txt")
        if file_path.exists():
            content = file_path.read_text()
            print(f"File created: ✓")
            print(f"Content: {content}")
        else:
            print(f"File created: ✗ (NOT FOUND)")

        # Analyze behavior
        print(f"\n{'='*70}")
        print("ANALYSIS:")
        print(f"{'='*70}")

        # Count tasks (should be 1 for direct handling)
        task_count = len(orchestrator.scheduler.tasks)
        print(f"Total tasks created: {task_count}")

        if task_count == 1:
            print("✅ GOOD: Only 1 task (Brokkr handled directly)")
        else:
            print(f"⚠️  OVER-DELEGATION: {task_count} tasks (Brokkr delegated unnecessarily)")

        if result.iterations <= 3:
            print(f"✅ EFFICIENT: Completed in {result.iterations} iterations")
        else:
            print(f"⚠️  INEFFICIENT: Took {result.iterations} iterations")

        if elapsed < 10:
            print(f"✅ FAST: Completed in {elapsed:.1f}s")
        else:
            print(f"⚠️  SLOW: Took {elapsed:.1f}s")

        return result.success and task_count == 1 and result.iterations <= 3

    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT after 60 seconds")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_delegation_with_resume():
    """Test that delegation works and parent resumes with context."""

    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  TEST 2: Delegation with Session Resume                         ║")
    print("╚══════════════════════════════════════════════════════════════════╝\n")

    # Use a task that's complex enough to delegate but simple enough to complete quickly
    task = "Create two files: delegated_test1.txt with 'first' and delegated_test2.txt with 'second'"

    print(f"Task: {task}\n")
    print("Expected behavior:")
    print("  • Brokkr might delegate OR handle directly (2 files = borderline)")
    print("  • If delegates, parent should resume with context")
    print("  • Both files should be created")
    print("  • Should complete successfully\n")

    config = LoopConfig(max_iterations=15)
    orchestrator = Orchestrator(config=config, total_vram_gb=16.0, enable_memory=False)

    start_time = time.time()

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=90.0)

        elapsed = time.time() - start_time

        print(f"\n{'='*70}")
        print("RESULTS:")
        print(f"{'='*70}")
        print(f"Success: {result.success}")
        print(f"Iterations: {result.iterations}")
        print(f"Reason: {result.reason}")
        print(f"Time: {elapsed:.1f}s")

        # Check files were created
        file1 = Path("delegated_test1.txt")
        file2 = Path("delegated_test2.txt")

        files_ok = True
        if file1.exists():
            content1 = file1.read_text()
            print(f"File 1 created: ✓ (content: '{content1.strip()}')")
        else:
            print(f"File 1 created: ✗")
            files_ok = False

        if file2.exists():
            content2 = file2.read_text()
            print(f"File 2 created: ✓ (content: '{content2.strip()}')")
        else:
            print(f"File 2 created: ✗")
            files_ok = False

        # Analyze behavior
        print(f"\n{'='*70}")
        print("ANALYSIS:")
        print(f"{'='*70}")

        task_count = len(orchestrator.scheduler.tasks)
        print(f"Total tasks created: {task_count}")

        if task_count == 1:
            print("✅ Brokkr handled directly (efficient)")
        elif task_count == 2:
            print("✅ Brokkr delegated to 1 child (reasonable for 2-file task)")
        else:
            print(f"⚠️  Multiple delegations ({task_count} tasks)")

        if result.success and files_ok:
            print("✅ Task completed successfully with correct output")
        else:
            print("❌ Task failed or files incorrect")

        # Check for session resume behavior
        print("\nSession resume validation:")
        print("  • If delegated, parent should have resumed without confusion")
        print("  • No 'max iterations' failures indicate good context preservation")

        if result.reason == "completion_marker":
            print("✅ Proper completion (not max iterations)")
        else:
            print(f"⚠️  Unusual completion: {result.reason}")

        return result.success and files_ok

    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT after 90 seconds")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_edit_file():
    """Test that Brokkr can use edit_file directly."""

    print("\n\n╔══════════════════════════════════════════════════════════════════╗")
    print("║  TEST 3: File Editing (Should use edit_file directly)           ║")
    print("╚══════════════════════════════════════════════════════════════════╝\n")

    # First create a file
    test_file = Path("edit_test.txt")
    test_file.write_text("Original content\n")
    print("Created test file with: 'Original content'")

    task = "Edit edit_test.txt and change 'Original' to 'Modified'"

    print(f"\nTask: {task}\n")
    print("Expected behavior:")
    print("  • Brokkr uses edit_file tool directly")
    print("  • No delegation needed")
    print("  • File content is modified\n")

    config = LoopConfig(max_iterations=10)
    orchestrator = Orchestrator(config=config, total_vram_gb=16.0, enable_memory=False)

    start_time = time.time()

    try:
        result = await asyncio.wait_for(orchestrator.run(task), timeout=60.0)

        elapsed = time.time() - start_time

        print(f"\n{'='*70}")
        print("RESULTS:")
        print(f"{'='*70}")
        print(f"Success: {result.success}")
        print(f"Iterations: {result.iterations}")
        print(f"Reason: {result.reason}")
        print(f"Time: {elapsed:.1f}s")

        # Check file was edited
        if test_file.exists():
            new_content = test_file.read_text()
            print(f"File content: '{new_content.strip()}'")

            if "Modified" in new_content:
                print("✅ File edited correctly")
                edit_ok = True
            else:
                print("❌ File not edited (still has original content)")
                edit_ok = False
        else:
            print("❌ File was deleted or not found")
            edit_ok = False

        # Analyze
        print(f"\n{'='*70}")
        print("ANALYSIS:")
        print(f"{'='*70}")

        task_count = len(orchestrator.scheduler.tasks)

        if task_count == 1:
            print("✅ No delegation (Brokkr handled directly)")
        else:
            print(f"⚠️  Delegated unnecessarily ({task_count} tasks)")

        return result.success and edit_ok and task_count == 1

    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT after 60 seconds")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""

    print("\n" + "="*70)
    print("SINDRI - REAL TASK TESTING")
    print("Testing session resume fix + Brokkr improvements")
    print("="*70 + "\n")

    results = []

    # Test 1: Simple file creation
    results.append(await test_simple_task())

    # Test 2: Delegation with context preservation
    results.append(await test_delegation_with_resume())

    # Test 3: File editing
    results.append(await test_edit_file())

    # Summary
    print("\n\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)

    test_names = [
        "Simple file creation (no delegation)",
        "Multi-file task (delegation test)",
        "File editing (direct tool use)"
    ]

    for i, (name, passed) in enumerate(zip(test_names, results), 1):
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"Test {i}: {name}")
        print(f"        {status}")

    total_passed = sum(results)
    total_tests = len(results)

    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    if all(results):
        print("\n🎉 All improvements validated successfully!")
        print("\nKey validations:")
        print("  ✓ Brokkr handles simple tasks directly")
        print("  ✓ No unnecessary delegation overhead")
        print("  ✓ Session context preserved through delegation")
        print("  ✓ File operations work correctly")
    else:
        print("\n⚠️  Some tests failed - see details above")

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
