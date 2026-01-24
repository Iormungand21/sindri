# Sindri Facts

Purpose: Local-first, single-user LLM orchestration system for code + ops on one machine.

Status:
- Mode: internal-only, single-user
- Date: 2026-01-23 (see STATUS.md)

Counts (authoritative):
- Agents: 27 (see docs/AGENTS.md)
- Tools: 268 (see README.md or sindri/tools/registry.py)
- Tests passing: 4,019 (see STATUS.md)

Core architecture:
- Execution: hierarchical Ralph loop with delegation and parallel batching
- Memory: five-tier (working, episodic, semantic, pattern, analysis)
- Interfaces: CLI, TUI, Web UI, Voice

Key capabilities:
- VRAM-aware model manager with caching and fallback
- Plan-first execution with approval gates
- Reproducible sessions (snapshots + tool output replay)
- Policy + guardrails (tool/file/runtime limits)
- Performance telemetry stream (SSE endpoint, trace export)

Primary documents:
- STATUS.md (current state)
- ARCHITECTURE.md (design)
- ROADMAP.md (future work)
- CLAUDE.md (coding conventions)
