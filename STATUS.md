# Sindri Status

**Date:** 2026-02-01
**Status:** Internal-only, single-user mode complete

## TL;DR
- Architecture transformation complete; internal-only single-user mode.
- System access controls + granular tool permissions + policy guardrails.
- Plan-first execution (approval gates) and reproducible sessions (snapshots + replay).
- Multi-project workspace index (background indexer, active contexts, per-project settings).
- Performance telemetry stream (SSE endpoint, trace export, regression checking).
- **Model-Aware Routing** (ROADMAP Item 10) - task-based model selection, VRAM-aware fallback, per-project preferences.
- **Triggers & Automations** (ROADMAP Item 9) - cron triggers, CLI commands, notification hooks, **REST API endpoints**.
- **Agents as Plugins** (ROADMAP Item 8) - SDK for packaging agents with prompts and tests, bundle validation, CLI commands.
- Event + API Contract v1 shipped; schema endpoints live.
- Tests: 4,202 passing (100%).
- Canonical facts: see `FACTS.md` and `docs/LLM_INDEX.md`.

## Recent Changes (latest first)
- 2026-02-01: **API /api/tasks Agent Selection Fix** - Fixed `/api/tasks` endpoint to pass `root_agent` parameter to `orchestrator.run()`. Previously the `agent` field was validated and stored but not used for actual task execution. All 15 models now installed and verified. +1 test.
- 2026-02-01: **Capability Registry + Doctor VRAM Fix** - Added ModelCapabilities entries for installed models (`codestral:22b`, `mistral-nemo:12b`, `gemma2:27b`, `qwen2.5:32b`) with verified context lengths via `ollama show`; fixed `check_gpu_vram()` to correctly parse rocm-smi byte output (was treating bytes as MB, reporting ~33M GB instead of ~32 GB).
- 2026-01-24: **Model-Aware Routing** (ROADMAP Item 10) - Lightweight router for task-based model selection; `TaskClassifier` for categorizing tasks (code_generation, reasoning, data, etc.); `ModelCapabilities` registry with 13 models and per-category strength scores; `ModelRouter` with VRAM-aware candidate filtering, latency optimization (prefer loaded models), and per-project preferences; `RoutingPreferences` for speed vs quality tradeoff, category overrides, and agent model locks; `RoutingConfig` in SindriConfig (opt-in via `routing.enabled`); `ProjectRoutingPreferences` for per-project customization; `MODEL_ROUTED` event type and schema; integration in `HierarchicalAgentLoop.run_task()` and `Orchestrator`; CLI commands (`sindri routing status/configure/capabilities/override/lock/unlock`); +41 tests.
- 2026-01-24: **Agents as Plugins** (ROADMAP Item 8) - SDK for packaging agents with prompts, tests, and metadata as distributable bundles; `AgentSDK` with `create_bundle()`, `from_definition()`, and `scaffold()` methods; `BundleValidator` with manifest validation, dependency checking, and pytest test execution; `BundleLoader` for bundle discovery and installation; `sindri-agent.toml` manifest format with schema versioning; `BundleMetadata` with version, sindri_version compatibility, author, category, tags; PluginManager integration for bundle discovery and registration; CLI commands (`sindri bundle create/validate/install/uninstall/export/test/list/info`); +35 tests.
- 2026-01-24: **Triggers REST API** (ROADMAP Item 9 completion) - 11 REST API endpoints for trigger management via HTTP: `GET/POST /api/triggers`, `GET/PUT/DELETE /api/triggers/{id}`, `POST /api/triggers/{id}/enable`, `POST /api/triggers/{id}/disable`, `POST /api/triggers/{id}/run`, `GET /api/triggers/{id}/runs`, `GET /api/triggers/{id}/runs/{run_id}`, `GET /api/triggers/stats`; Pydantic request/response models; event emission on state changes; cron validation; +31 tests.
- 2026-01-24: **Triggers & Automations** (ROADMAP Item 9) - Core foundation for scheduled task automation via cron expressions; `TriggerStore` for SQLite persistence (schema v9); `TriggerScheduler` background service with cron evaluation using croniter; `TriggerExecutor` for task creation via Orchestrator; `NotificationService` for desktop (notify-send) and log notifications; 11 `TRIGGER_*` event types; `TriggerConfig` in SindriConfig; CLI commands (`sindri triggers list/create/show/delete/enable/disable/run/history/stats`); +50 tests.
- 2026-01-23: **Telemetry Wiring to Active Orchestrator** - TelemetryCollector now uses registration pattern to aggregate VRAM/concurrency metrics from all active Orchestrators; Orchestrator registers its ModelManager and TaskScheduler on init and unregisters on cleanup; web API metrics now reflect real workloads; +13 tests.
- 2026-01-23: **MODEL_LOADED Event Emission** - Added `MODEL_LOADED` event emission in `hierarchical.py` when models are successfully loaded; emits for both primary and fallback models; enables `TelemetryCollector` to track agent→model relationships; event schema and handler already existed but were not being populated; +4 tests.
- 2026-01-23: **Fallback Model Recording in Session Metadata** - Added `primary_model`, `fallback_model_used`, and `degradation_reason` fields to `EnvironmentSnapshot`; updated `SnapshotCapture.capture()` to accept fallback info; fixed session creation bug in `hierarchical.py` (was using `agent.model` instead of `model_to_use`); snapshots now record when model degradation occurs; fixed persistence in `SnapshotStore` to save/load fallback fields via config_snapshot_json; +11 tests.
- 2026-01-23: **TOOL_CALLED Event Schema duration_ms** - Added `duration_ms` field to `ToolCalledData` schema in event_schemas.py; regenerated TypeScript types; updated contract tests. Formalizes timing field already being emitted and consumed by telemetry.
- 2026-01-23: **Session Status Persistence on Cancel/Failure** - Added `fail_session()` and `cancel_session()` methods to SessionState; sessions now properly marked as 'failed' or 'cancelled' instead of remaining 'active'; added error column to sessions table (schema v8); updated hierarchical.py and orchestrator.py failure/cancel paths; +7 tests.
- 2026-01-21: **Go TUI Migration** - Replaced Textual TUI with Go/Bubble Tea client over Unix socket event gateway; added gateway server, TASK_CREATED emission, and removed Textual-only tests/deps.
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
