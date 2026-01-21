# Sindri Status

**Date:** 2026-01-21
**Status:** Internal-only, single-user mode complete

## Snapshot
- Architecture transformation complete (collaboration + IDE integration removed; marketplace local-only).
- Security relaxed for localhost/private IPs; cloud metadata endpoints still blocked.
- Configurable system access (restricted/supervised/full) + self-management + scheduling tools.
- Event + API Contract v1 shipped; schema endpoints live.
- Policy + Guardrails: agent-level constraints (tool limits, file limits, runtime limits, escalation modes).
- **Plan-First Execution**: Two modes - agent-guided (default, pauses for approval then continues) and step-by-step (API/programmatic via PlanExecutor with checkpoints).
- Tests: 3,901 passing (100%).

## Key Capabilities (high level)
- Hierarchical multi-agent orchestration with 5-tier memory.
- Local-first tooling: TUI, Web UI, voice interface.
- Service management, scheduling, model management, and system access controls.
- Policy enforcement: per-agent limits on tool calls, files, runtime; escalation modes (deny/warn/escalate).
- Plan-First Execution: persistent plans, approval gates, step-level checkpointing, re-run capabilities.
- Broad tool suite (code, infra, data, media, diagrams, LaTeX, OpenSCAD).

## Recent Changes (latest first)
- 2026-01-21: Plan-First Execution feature (persistent plans, user approval gates, step-level checkpointing, re-run support, REST API endpoints; +30 tests).
- 2026-01-20: Policy + Guardrails feature (max_tool_calls, max_files_touched, max_runtime_seconds, file_scope, escalation modes; CLI commands; +27 tests).
- 2026-01-20: Granular Tool Permissions feature (allowlists/blocklists, audit log, dry-run mode; +21 tests).
- 2026-01-20: Add command timeout/cancellation support to shell tool (default 300s, max 3600s; +5 tests).
- 2026-01-20: Enforce system access levels for shell/filesystem tools (RESTRICTED blocks shell, write_file, edit_file; +11 tests).
- 2026-01-20: Tightened ModelManager.can_load() to avoid false positives when VRAM is insufficient (respects keep_warm models).
- 2026-01-20: Work dir memory indexing respects configured `--work-dir`.
- 2026-01-20: Sequential orchestrator path now handles exceptions like parallel path.
- 2026-01-20: Event + API Contract v1 (schema endpoints, TS type gen, contract tests).
- 2026-01-20: Git automation tools for Huginn/Brokkr.

## Known Issues / Risks
- CI tests may still fail in GitHub Actions; see workflow logs if it happens.

## Where To Look
- Overview + usage: `README.md`
- Architecture + patterns: `ARCHITECTURE.md`
- Roadmap + future work: `ROADMAP.md`
- Full history: `docs/archive/STATUS-full-history.md`
