# Sindri Status

**Date:** 2026-01-20  
**Status:** Internal-only, single-user mode complete

## Snapshot
- Architecture transformation complete (collaboration + IDE integration removed; marketplace local-only).
- Security relaxed for localhost/private IPs; cloud metadata endpoints still blocked.
- Configurable system access (restricted/supervised/full) + self-management + scheduling tools.
- Event + API Contract v1 shipped; schema endpoints live.
- Tests: 3,815 passing (100%).

## Key Capabilities (high level)
- Hierarchical multi-agent orchestration with 5-tier memory.
- Local-first tooling: TUI, Web UI, voice interface.
- Service management, scheduling, model management, and system access controls.
- Broad tool suite (code, infra, data, media, diagrams, LaTeX, OpenSCAD).

## Recent Changes (latest first)
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
