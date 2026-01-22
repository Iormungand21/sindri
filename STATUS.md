# Sindri Status

**Date:** 2026-01-21
**Status:** Internal-only, single-user mode complete

## TL;DR
- Architecture transformation complete; internal-only single-user mode.
- System access controls + granular tool permissions + policy guardrails.
- Plan-first execution (approval gates) and reproducible sessions (snapshots + replay).
- Multi-project workspace index (background indexer, active contexts, per-project settings).
- Performance telemetry stream (SSE endpoint, trace export, regression checking).
- Event + API Contract v1 shipped; schema endpoints live.
- Tests: 4,036 passing (100%).
- Canonical facts: see `FACTS.md` and `docs/LLM_INDEX.md`.

## Recent Changes (latest first)
- 2026-01-21: **Performance Telemetry Stream** (ROADMAP Item 7) - Real-time telemetry via `/api/metrics/live` SSE endpoint, `TelemetryCollector` with rolling statistics, VRAM and concurrency time-series history, `TraceExporter` for JSON trace export and regression comparison, CLI commands (`sindri telemetry stream/snapshot/export/compare`); +39 tests.
- 2026-01-21: **Multi-Project Workspace Index** (ROADMAP Item 4) - Background indexer with priority queue, incremental MD5-based indexing, active/pinned projects for context injection, per-project embedder settings (chunk size, exclude patterns), CLI commands (`sindri projects activate/deactivate/settings/index-incremental/active`); +47 tests.
- 2026-01-21: Reproducible Sessions (snapshots, tool output recording, `sindri replay`, session comparison; +44 tests).
- 2026-01-21: Plan-First Execution (persistent plans, approval gates, checkpointed steps; +30 tests).
- 2026-01-20: Policy + Guardrails (tool/file/runtime limits; +27 tests).
- 2026-01-20: Granular Tool Permissions (allow/block, audit, dry-run; +21 tests).
- 2026-01-20: Context length optimization (dynamic memory sizing).
- 2026-01-20: Event + API Contract v1 (schema endpoints, TS gen, contract tests).

## Known Issues / Risks
- CI tests may still fail in GitHub Actions; see workflow logs if it happens.

## Where To Look
- Overview + usage: `README.md`
- Architecture + patterns: `ARCHITECTURE.md`
- Roadmap + future work: `ROADMAP.md`
- Full history: `docs/archive/STATUS-full-history.md`
