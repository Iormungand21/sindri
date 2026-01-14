#!/usr/bin/env python
"""Test memory system - project indexing, semantic search, episodic recall."""

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
    print("MEMORY SYSTEM TEST")
    print("=" * 70)
    print("\nThis test validates:")
    print("  1. Project indexing (semantic memory)")
    print("  2. Codebase context injection")
    print("  3. Episodic memory (past task recall)")
    print("  4. Memory-augmented agent responses")
    print("=" * 70)

    # Task 1: Ask about existing code (requires semantic search)
    task1 = """What agents are defined in the sindri codebase?
List their names and what they're used for based on the code."""

    print(f"\n📝 Task 1 (Semantic Search Test):\n{task1}")
    print("\n⭐ This should trigger:")
    print("   - Project indexing (if first run)")
    print("   - Semantic search for 'agents' in codebase")
    print("   - Context injection with relevant code snippets")
    print("\nStarting in 3 seconds...")
    await asyncio.sleep(3)

    # Create orchestrator WITH MEMORY ENABLED
    print("\n" + "=" * 70)
    print("INITIALIZING WITH MEMORY ENABLED")
    print("=" * 70)

    config = LoopConfig(max_iterations=10)
    orchestrator = Orchestrator(
        config=config,
        total_vram_gb=16.0,
        enable_memory=True  # ⭐ KEY: Memory enabled
    )

    print("\n" + "=" * 70)
    print("TASK 1 EXECUTION")
    print("=" * 70)

    try:
        result1 = await asyncio.wait_for(orchestrator.run(task1), timeout=180.0)

        print("\n" + "=" * 70)
        print("TASK 1 RESULT")
        print("=" * 70)
        print(f"Success: {result1.get('success', False)}")
        output1 = result1.get('output', 'No output')[:500]
        print(f"Output preview:\n{output1}")
        if len(result1.get('output', '')) > 500:
            print("... (truncated)")

        # Check memory indexing happened
        print("\n" + "=" * 70)
        print("MEMORY SYSTEM VALIDATION")
        print("=" * 70)

        if orchestrator.memory:
            print("✅ Memory system initialized")

            # Check if project was indexed
            project_id = f"project_{Path.cwd().as_posix().replace('/', '_')}"

            # Try a semantic search directly
            print(f"\n🔍 Testing semantic search for 'agents'...")
            semantic_results = orchestrator.memory.semantic.search(
                namespace=project_id,
                query="agent definitions names roles",
                limit=5
            )

            if semantic_results:
                print(f"✅ Semantic search working - {len(semantic_results)} results")
                print("\nTop results:")
                for i, (content, meta, score) in enumerate(semantic_results[:3], 1):
                    path = meta.get('path', 'unknown')
                    print(f"  {i}. {path} (score: {score:.3f})")
                    print(f"     Preview: {content[:80]}...")
            else:
                print("❌ No semantic results found")

        else:
            print("❌ Memory system not initialized")

        # Task 2: Follow-up question (tests episodic recall)
        print("\n" + "=" * 70)
        print("TASK 2 SETUP (Episodic Recall Test)")
        print("=" * 70)

        task2 = """Based on what you just learned about the agents,
which agent would be best for implementing a new feature?"""

        print(f"\n📝 Task 2:\n{task2}")
        print("\n⭐ This should trigger:")
        print("   - Episodic recall (remembering task 1)")
        print("   - Semantic search (finding agent code again)")
        print("   - Reasoning based on previous context")
        print("\nStarting in 2 seconds...")
        await asyncio.sleep(2)

        print("\n" + "=" * 70)
        print("TASK 2 EXECUTION")
        print("=" * 70)

        result2 = await asyncio.wait_for(orchestrator.run(task2), timeout=180.0)

        print("\n" + "=" * 70)
        print("TASK 2 RESULT")
        print("=" * 70)
        print(f"Success: {result2.get('success', False)}")
        output2 = result2.get('output', 'No output')[:500]
        print(f"Output preview:\n{output2}")
        if len(result2.get('output', '')) > 500:
            print("... (truncated)")

        # Final validation
        print("\n" + "=" * 70)
        print("FINAL VALIDATION")
        print("=" * 70)

        tasks = list(orchestrator.scheduler.tasks.values())
        print(f"Total tasks executed: {len(tasks)}")

        # Check if outputs reference actual code
        mentions_huginn = "huginn" in output1.lower() or "huginn" in output2.lower()
        mentions_brokkr = "brokkr" in output1.lower() or "brokkr" in output2.lower()
        mentions_mimir = "mimir" in output1.lower() or "mimir" in output2.lower()

        print(f"\n✅ Mentioned Huginn: {mentions_huginn}")
        print(f"✅ Mentioned Brokkr: {mentions_brokkr}")
        print(f"✅ Mentioned Mimir: {mentions_mimir}")

        if mentions_huginn and mentions_brokkr:
            print("\n🎉 Memory system appears to be working!")
            print("   Agent responses included specific code knowledge")
        else:
            print("\n⚠️  Unclear if memory context was used")
            print("   Responses don't clearly reference codebase details")

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        checks = []
        checks.append(("Memory initialized", orchestrator.memory is not None))
        checks.append(("Semantic search works", len(semantic_results) > 0 if semantic_results else False))
        checks.append(("Task 1 completed", result1.get('success', False)))
        checks.append(("Task 2 completed", result2.get('success', False)))
        checks.append(("Codebase knowledge used", mentions_huginn or mentions_brokkr))

        for check, passed in checks:
            status = "✅" if passed else "❌"
            print(f"{status} {check}")

        all_passed = all(passed for _, passed in checks)

        if all_passed:
            print("\n🎉 MEMORY SYSTEM TEST PASSED")
        else:
            print("\n⚠️  Some checks failed - review logs")

    except asyncio.TimeoutError:
        print("\n" + "=" * 70)
        print("TIMEOUT")
        print("=" * 70)
        print("Task exceeded 180 second timeout")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n🔍 WHAT TO LOOK FOR IN LOGS:")
    print("   'indexing_project' - Project codebase being indexed")
    print("   'project_indexed' - Number of files indexed")
    print("   'semantic_context_added' - Code context injected")
    print("   'episodic_context_added' - Past task context injected")
    print("")
    asyncio.run(main())
