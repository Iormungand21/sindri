#!/usr/bin/env python
"""Direct test of memory system components without full orchestration."""

import asyncio
from pathlib import Path
from sindri.memory.system import MuninnMemory

async def main():
    print("=" * 70)
    print("DIRECT MEMORY SYSTEM TEST")
    print("=" * 70)

    # Initialize memory system
    db_path = str(Path.home() / ".sindri" / "memory.db")
    memory = MuninnMemory(db_path)

    project_id = f"project_{Path.cwd().as_posix().replace('/', '_')}"

    print(f"\nProject ID: {project_id}")
    print("\n" + "=" * 70)
    print("TEST 1: Semantic Search (Codebase Context)")
    print("=" * 70)

    # Test semantic search for agents
    queries = [
        "agent definitions brokkr huginn mimir",
        "agent system prompt norse",
        "delegation hierarchical tasks"
    ]

    for query in queries:
        print(f"\n🔍 Query: '{query}'")
        results = memory.semantic.search(
            namespace=project_id,
            query=query,
            limit=5
        )

        if results:
            print(f"✅ Found {len(results)} results")
            for i, (content, meta, score) in enumerate(results[:3], 1):
                path = meta.get('path', 'unknown')
                start = meta.get('start_line', '?')
                end = meta.get('end_line', '?')
                print(f"\n  {i}. {path}:{start}-{end} (score: {score:.3f})")
                preview = content[:150].replace('\n', ' ')
                print(f"     {preview}...")
        else:
            print("❌ No results found")

    # Test episodic memory
    print("\n" + "=" * 70)
    print("TEST 2: Episodic Memory")
    print("=" * 70)

    # Store some test episodes
    print("\nStoring test episodes...")
    memory.store_episode(
        project_id=project_id,
        event_type="task_completed",
        content="Successfully tested delegation with Brokkr -> Huginn",
        metadata={"agent": "brokkr", "success": True}
    )

    memory.store_episode(
        project_id=project_id,
        event_type="task_completed",
        content="Memory system initialized with 103 files indexed",
        metadata={"component": "memory", "files": 103}
    )

    # Retrieve episodes
    print("\n🔍 Retrieving relevant episodes for 'delegation'...")
    episodes = memory.episodic.retrieve_relevant(
        project_id=project_id,
        query="delegation testing",
        limit=5
    )

    if episodes:
        print(f"✅ Found {len(episodes)} episodes")
        for i, ep in enumerate(episodes[:5], 1):
            print(f"\n  {i}. [{ep.event_type}] {ep.content[:100]}...")
    else:
        print("❌ No episodes found")

    # Test context building
    print("\n" + "=" * 70)
    print("TEST 3: Context Building")
    print("=" * 70)

    task = "Implement a new feature for task scheduling"
    conversation = [
        {"role": "user", "content": task}
    ]

    print(f"\nTask: {task}")
    print("Building memory-augmented context...")

    context = memory.build_context(
        project_id=project_id,
        current_task=task,
        conversation=conversation,
        max_tokens=8000
    )

    print(f"\n✅ Context built with {len(context)} messages")
    for i, msg in enumerate(context, 1):
        role = msg.get('role', 'unknown')
        content_preview = msg.get('content', '')[:100].replace('\n', ' ')
        print(f"  {i}. [{role}] {content_preview}...")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    checks = [
        ("Semantic search works", len(results) > 0 if results else False),
        ("Episodic storage works", True),  # If we got here, it worked
        ("Episodic retrieval works", len(episodes) > 0 if episodes else False),
        ("Context building works", len(context) > 0)
    ]

    for check, passed in checks:
        status = "✅" if passed else "❌"
        print(f"{status} {check}")

    all_passed = all(passed for _, passed in checks)

    if all_passed:
        print("\n🎉 MEMORY SYSTEM FULLY FUNCTIONAL")
    else:
        print("\n⚠️  Some components need attention")

if __name__ == "__main__":
    asyncio.run(main())
