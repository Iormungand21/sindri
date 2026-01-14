#!/usr/bin/env python3
"""Test Brokkr's improved prompting - should handle simple tasks directly."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.core.tasks import Task
from sindri.core.loop import LoopConfig
from sindri.persistence.state import Session
from sindri.agents.registry import AGENTS


async def test_brokkr_has_necessary_tools():
    """Verify Brokkr has tools to handle simple tasks."""

    brokkr = AGENTS["brokkr"]

    print("🔧 Testing Brokkr's tool set...")
    print(f"\nBrokkr tools: {brokkr.tools}")

    required_tools = ["read_file", "write_file", "edit_file", "shell", "delegate"]

    for tool in required_tools:
        if tool in brokkr.tools:
            print(f"  ✓ Has {tool}")
        else:
            print(f"  ✗ Missing {tool}")
            return False

    print(f"\n✅ Brokkr has all necessary tools to handle simple tasks!")
    return True


async def test_brokkr_prompt_guidance():
    """Verify Brokkr's prompt includes proper guidance."""

    brokkr = AGENTS["brokkr"]
    prompt = brokkr.system_prompt

    print("\n📋 Testing Brokkr's prompt guidance...")

    # Check for key phrases that indicate improved prompting
    checks = {
        "simple tasks": "SIMPLE TASKS" in prompt,
        "do yourself": "DO YOURSELF" in prompt or "do it yourself" in prompt.lower(),
        "only delegate when": "Only delegate when" in prompt or "only delegate" in prompt.lower(),
        "examples": "Examples:" in prompt or "Example:" in prompt,
        "trust": "trust" in prompt.lower() or "Trust" in prompt,
        "don't verify": "don't verify" in prompt.lower() or "Don't verify" in prompt,
    }

    for check_name, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} Includes guidance on: {check_name}")

    if all(checks.values()):
        print(f"\n✅ Brokkr's prompt has proper delegation guidance!")
        return True
    else:
        print(f"\n⚠️  Some guidance missing from prompt")
        return False


async def test_brokkr_delegation_list():
    """Verify Brokkr's delegation list is appropriate."""

    brokkr = AGENTS["brokkr"]

    print("\n👥 Testing Brokkr's delegation targets...")
    print(f"\nCan delegate to: {brokkr.delegate_to}")

    # Should NOT include ratatoskr (simple executor) since brokkr can do that now
    if "ratatoskr" in brokkr.delegate_to:
        print("  ⚠️  Still delegates to Ratatoskr (should handle simple tasks itself)")
        return False
    else:
        print("  ✓ Ratatoskr removed (Brokkr handles simple tasks)")

    # Should include specialist agents
    specialists = ["huginn", "mimir", "skald", "fenrir", "odin"]
    for specialist in specialists:
        if specialist in brokkr.delegate_to:
            print(f"  ✓ Can delegate to {specialist}")
        else:
            print(f"  ✗ Cannot delegate to {specialist}")

    print(f"\n✅ Brokkr's delegation list is appropriate!")
    return True


async def test_brokkr_reduced_iterations():
    """Verify Brokkr has reduced max_iterations for efficiency."""

    brokkr = AGENTS["brokkr"]

    print("\n⏱️  Testing Brokkr's iteration limit...")
    print(f"\nMax iterations: {brokkr.max_iterations}")

    # Should be reduced from 20 to ~10-15 since simple tasks don't need many iterations
    if brokkr.max_iterations <= 15:
        print(f"  ✓ Efficient iteration limit ({brokkr.max_iterations} ≤ 15)")
        print(f"  → Simple tasks won't waste iterations")
        return True
    else:
        print(f"  ⚠️  High iteration limit ({brokkr.max_iterations})")
        return False


def print_prompt_summary():
    """Print key sections of Brokkr's new prompt."""

    brokkr = AGENTS["brokkr"]
    prompt = brokkr.system_prompt

    print("\n" + "="*70)
    print("BROKKR'S NEW PROMPT - KEY SECTIONS")
    print("="*70)

    # Extract key sections
    lines = prompt.split('\n')
    in_section = False
    current_section = []

    for line in lines:
        if 'SIMPLE TASKS' in line or 'COMPLEX TASKS' in line or 'DELEGATION RULES' in line:
            if current_section:
                print('\n'.join(current_section))
                print()
            current_section = [line]
            in_section = True
        elif in_section and '═' in line:
            if current_section:
                print('\n'.join(current_section))
                print(line)
                print()
            current_section = []
            in_section = False
        elif in_section:
            current_section.append(line)


async def main():
    """Run all tests."""

    print("╔════════════════════════════════════════════════════════════════╗")
    print("║     BROKKR IMPROVEMENTS - REDUCE OVER-DELEGATION              ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    results = []

    results.append(await test_brokkr_has_necessary_tools())
    results.append(await test_brokkr_prompt_guidance())
    results.append(await test_brokkr_delegation_list())
    results.append(await test_brokkr_reduced_iterations())

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(results)
    total = len(results)

    print(f"\nTests passed: {passed}/{total}")

    if all(results):
        print("\n✅ All improvements verified!")
        print("\nBrokkr should now:")
        print("  • Handle simple file operations itself")
        print("  • Only delegate complex multi-file tasks")
        print("  • Trust specialist results without re-verification")
        print("  • Complete tasks more efficiently")

        print_prompt_summary()

        return True
    else:
        print("\n⚠️  Some improvements missing")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
