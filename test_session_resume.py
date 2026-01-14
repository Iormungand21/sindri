#!/usr/bin/env python3
"""Test session resume after delegation."""

import asyncio
import sys
import os

# Add sindri to path
sys.path.insert(0, os.path.dirname(__file__))

from sindri.core.tasks import Task, TaskStatus
from sindri.persistence.state import SessionState


async def test_session_resume():
    """Test that tasks resume their existing session instead of creating new ones."""

    print("🔧 Testing session resume functionality...\n")

    state = SessionState()

    # Simulate a parent task that gets a session
    task = Task(
        description="Parent task that will delegate",
        assigned_agent="brokkr"
    )

    print(f"1. Creating task: {task.id}")
    print(f"   Initial session_id: {task.session_id}")
    assert task.session_id is None, "New task should have no session_id"

    # Create first session (simulating first run)
    session1 = await state.create_session(task.description, "qwen2.5-coder:14b")
    task.session_id = session1.id

    print(f"\n2. Created session: {session1.id}")
    print(f"   Task session_id now: {task.session_id}")

    # Add some conversation to the session
    session1.add_turn("user", "Please create a file")
    session1.add_turn("assistant", "I'll delegate this to ratatoskr")
    session1.add_turn("tool", "Delegation successful")
    await state.save_session(session1)

    print(f"   Added 3 turns to session")
    print(f"   Session turn count: {len(session1.turns)}")

    # Simulate child completion - inject result into parent session
    session1_reloaded = await state.load_session(session1.id)
    session1_reloaded.add_turn("tool", "Child task completed successfully! File created.")
    await state.save_session(session1_reloaded)

    print(f"\n3. Child completed - injected result into session")
    print(f"   Session turn count now: {len(session1_reloaded.turns)}")

    # Now simulate parent resume - load the session using task.session_id
    if task.session_id:
        session_resumed = await state.load_session(task.session_id)
        print(f"\n4. Resumed session: {session_resumed.id}")
        print(f"   Session has {len(session_resumed.turns)} turns")
        print(f"   ✓ Session context preserved!")

        # Verify all turns are present
        assert len(session_resumed.turns) == 4, "Should have all 4 turns"
        assert session_resumed.turns[-1].content == "Child task completed successfully! File created."

        print(f"\n   Last turn content: '{session_resumed.turns[-1].content[:50]}...'")
        print(f"   ✓ Child result is present in resumed session!")
    else:
        print(f"\n4. ✗ Task has no session_id - would create new session!")
        return False

    print(f"\n{'='*60}")
    print(f"✅ Session resume test PASSED")
    print(f"{'='*60}")
    print(f"\nWith this fix:")
    print(f"  • Parents resume their existing session")
    print(f"  • Conversation context is preserved")
    print(f"  • Child results are visible to parent")
    print(f"  • No more 'what happened?' confusion")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_session_resume())
    sys.exit(0 if success else 1)
