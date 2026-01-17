# Sindri Architecture

**Technical design documentation for developers**

This document explains the internal architecture, design patterns, and technical decisions behind Sindri. For feature planning, see [ROADMAP.md](ROADMAP.md). For current status, see [STATUS.md](STATUS.md).

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [System Architecture](#system-architecture)
3. [Data Flow](#data-flow)
4. [Key Components](#key-components)
5. [Design Patterns](#design-patterns)
6. [Extension Points](#extension-points)
7. [Performance Considerations](#performance-considerations)
8. [Database Schema](#database-schema)

---

## Core Concepts

### The Ralph Loop

Sindri's execution model is based on the "Ralph loop" pattern:

```python
async def ralph_loop(task: str, max_iterations: int = 50) -> LoopResult:
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": task}]

    for iteration in range(max_iterations):
        # 1. Get LLM response (with streaming)
        response = await llm.chat_stream(model, messages)
        messages.append({"role": "assistant", "content": response})

        # 2. Check for completion
        if "<sindri:complete/>" in response:
            return LoopResult(success=True, output=extract_output(messages))

        # 3. Parse and execute tools
        tool_calls = parse_tools(response)
        tool_results = await execute_tools(tool_calls)
        messages.append({"role": "tool", "content": tool_results})

    # Max iterations reached
    return LoopResult(success=False, error="Max iterations exceeded")
```

**Key Properties:**
- **Iterative refinement** - Agent learns from tool results
- **Self-correcting** - Errors become context for next iteration
- **Bounded** - Max iterations prevents infinite loops
- **Explicit completion** - Agent signals when done
- **Streaming** - Real-time token display in TUI

### Hierarchical Delegation

Sindri extends the Ralph loop with task delegation:

```
Root Task (User)
    |
+------------------+
| Brokkr Loop      | <- Orchestrator agent
+-------+----------+
        |
        +-> delegate("Implement feature X", agent="huginn")
        |      |
        |   +---------------+
        |   | Huginn Loop   | <- Code implementation agent
        |   +------+--------+
        |          |
        |          +-> write_file(...)
        |          +-> delegate("Execute tests", agent="skald")
        |          |      |
        |          |   +-----------------+
        |          |   | Skald Loop      | <- Testing agent
        |          |   +-----------------+
        |          |      | (returns result)
        |          |   [Child completes]
        |          +-> [Receives child result]
        |          +-> <sindri:complete/>
        |   [Huginn completes]
        +-> [Receives Huginn result]
        +-> <sindri:complete/>
[Brokkr completes]
```

**Key Properties:**
- **Nested loops** - Each delegation spawns a new loop
- **Bidirectional communication** - Parent <-> Child result passing
- **Context preservation** - Parent resumes with full history
- **Specialization** - Each agent has specific tools/capabilities
- **Parallel execution** - Independent tasks run concurrently

### Memory System (Muninn)

Five-tier memory architecture:

```
+-------------------------------------------+
| Context Window (32K tokens max)           |
+-------------------------------------------+
| 50% Working Memory                        |
| - Recent conversation (last 10 turns)     |
| - Current task description                |
| - Tool results                            |
+-------------------------------------------+
| 18% Episodic Memory                       |
| - Past task summaries (5 most relevant)   |
| - What worked, what didn't                |
| - Retrieved via semantic similarity       |
+-------------------------------------------+
| 18% Semantic Memory                       |
| - Codebase chunks (10 most relevant)      |
| - Retrieved via embedding similarity      |
| - Indexed from project files              |
+-------------------------------------------+
| 5% Pattern Memory                         |
| - Learned successful patterns             |
| - Tool sequences that worked              |
| - Context-matched suggestions             |
+-------------------------------------------+
| 9% Analysis Memory                        |
| - Codebase architecture info              |
| - Dependency graphs                       |
| - Style conventions                       |
+-------------------------------------------+
```

**Benefits:**
- Agents have project context without reading all files
- Learn from past successes/failures
- Scale to large codebases (tested with 100+ files)
- Cross-project memory via GlobalMemoryStore

---

## System Architecture

### Component Diagram

```
+-----------------------------------------------------------+
|                         CLI Layer                          |
|  (sindri/cli.py, sindri/__main__.py)                      |
+------------------------+----------------------------------+
                         |
          +--------------+--------------+
          |                             |
+---------v----------+    +-------------v-----------+
|   TUI (Textual)    |    |    Web UI (FastAPI)     |
|  sindri/tui/       |    |  sindri/web/            |
+---------+----------+    +-------------+-----------+
          |                             |
          +-------------+---------------+
                        |
          +-------------v--------------+
          |        EventBus            |
          |   (Pub/Sub communication)  |
          +-------------+--------------+
                        |
    +--------+----------+----------+-----------+
    |        |          |          |           |
+---v----+ +-v------+ +-v-------+ +v--------+ +v----------+
|TaskSch | |HierLoop| |DelegMgr | | Memory  | | Collab    |
|eduler  | |        | |         | |(Muninn) | | Manager   |
+---+----+ +---+----+ +---+-----+ +----+----+ +-----------+
    |          |           |           |
    |      +---v-----------v----+      |
    |      |   SessionState     |      |
    |      |  (Persistence)     |      |
    |      +--------------------+      |
    |                                  |
+---v--------------+        +----------v-------+
|  ModelManager    |        |   Embedder       |
|  (VRAM tracking) |        | (nomic-embed)    |
+---+--------------+        +------------------+
    |
+---v----------+
|OllamaClient  |
|(LLM calls)   |
+--------------+
```

### Directory Structure

```
sindri/
├── cli.py                    # Click commands, entry points
├── __main__.py               # Python -m sindri entry
├── config.py                 # Pydantic config models
├── logging.py                # Structured logging setup
│
├── core/                     # Core orchestration logic
│   ├── orchestrator.py       # Main coordinator, owns all managers
│   ├── hierarchical.py       # HierarchicalAgentLoop
│   ├── scheduler.py          # Priority queue, dependency resolution, parallel batching
│   ├── delegation.py         # Parent-child task management, model pre-warming
│   ├── tasks.py              # Task, TaskStatus, TaskPriority models
│   ├── events.py             # EventBus, Event, EventType (20+ event types)
│   ├── completion.py         # Completion marker detection
│   ├── context.py            # Message/context building
│   ├── recovery.py           # Crash recovery, checkpointing
│   ├── errors.py             # Error classification (TRANSIENT, RESOURCE, FATAL, AGENT)
│   └── doctor.py             # System health checks
│
├── agents/                   # Agent definitions and prompts
│   ├── definitions.py        # AgentDefinition dataclass (with fallback models)
│   ├── registry.py           # AGENTS dict (11 agents)
│   └── prompts.py            # System prompts for each agent (~2500 lines)
│
├── llm/                      # LLM interface layer
│   ├── client.py             # OllamaClient (async wrapper, streaming)
│   ├── manager.py            # ModelManager (VRAM tracking, LRU, pre-warming, caching)
│   ├── tool_parser.py        # Parse JSON tool calls from text
│   └── streaming.py          # StreamingBuffer for tool detection
│
├── tools/                    # Tool implementations (32 tools)
│   ├── base.py               # Tool ABC, ToolResult dataclass
│   ├── registry.py           # ToolRegistry, schema generation
│   ├── filesystem.py         # read_file, write_file, edit_file, list_directory, read_tree
│   ├── shell.py              # shell execution
│   ├── delegation.py         # DelegateTool (special)
│   ├── planning.py           # ProposePlanTool
│   ├── search.py             # SearchCodeTool, FindSymbolTool
│   ├── git.py                # git_status, git_diff, git_log, git_branch
│   ├── http.py               # http_request, http_get, http_post
│   ├── testing.py            # run_tests, check_syntax
│   ├── formatting.py         # format_code, lint_code
│   ├── refactoring.py        # rename_symbol, extract_function, inline_variable,
│   │                         # move_file, batch_rename, split_file, merge_files
│   ├── sql.py                # execute_query, describe_schema, explain_query
│   └── cicd.py               # generate_workflow, validate_workflow
│
├── memory/                   # Memory system (Muninn)
│   ├── system.py             # MuninnMemory orchestrator (5-tier)
│   ├── episodic.py           # EpisodicMemory (task summaries)
│   ├── semantic.py           # SemanticMemory (codebase embeddings)
│   ├── embedder.py           # EmbeddingClient (nomic-embed-text)
│   ├── summarizer.py         # ConversationSummarizer
│   ├── indexer.py            # Codebase indexing
│   ├── patterns.py           # PatternStore, PatternLearner
│   ├── codebase.py           # CodebaseAnalyzer, CodebaseAnalysisStore
│   ├── projects.py           # ProjectRegistry (multi-project)
│   └── global_memory.py      # GlobalMemoryStore (cross-project search)
│
├── analysis/                 # Codebase analysis
│   ├── results.py            # CodebaseAnalysis, DependencyInfo, etc.
│   ├── dependencies.py       # DependencyAnalyzer (import graphs)
│   ├── architecture.py       # ArchitectureDetector (pattern detection)
│   └── style.py              # StyleAnalyzer (conventions)
│
├── persistence/              # Database layer
│   ├── database.py           # SQLite setup, migrations (schema v4)
│   ├── state.py              # SessionState (CRUD for sessions/turns)
│   ├── vectors.py            # sqlite-vec integration
│   ├── backup.py             # DatabaseBackup (backup/restore)
│   ├── metrics.py            # MetricsCollector, MetricsStore
│   ├── export.py             # MarkdownExporter
│   ├── feedback.py           # SessionFeedback, FeedbackStore
│   └── training_export.py    # TrainingDataExporter (JSONL, ChatML, Ollama)
│
├── plugins/                  # Plugin system
│   ├── loader.py             # Plugin discovery (*.py tools, *.toml agents)
│   ├── validator.py          # Safety validation
│   └── manager.py            # PluginManager lifecycle
│
├── collaboration/            # Remote collaboration
│   ├── sharing.py            # SessionShare, ShareStore
│   ├── comments.py           # SessionComment, CommentStore
│   └── presence.py           # Participant, PresenceManager
│
├── tui/                      # Terminal UI (Textual)
│   ├── app.py                # SindriApp (main Textual app)
│   └── widgets/
│       ├── header.py         # Header with VRAM gauge, metrics
│       ├── task_tree.py      # Task list (left panel)
│       ├── output.py         # Output viewer (right panel)
│       ├── input.py          # Task input (bottom)
│       └── history.py        # Task history panel
│
└── web/                      # Web UI
    ├── server.py             # FastAPI server (REST + WebSocket)
    └── static/               # React frontend
        ├── src/
        │   ├── components/   # Dashboard, AgentList, SessionDetail, etc.
        │   │                 # CodeDiffViewer, TimelineView, SessionReplay
        │   ├── hooks/        # useApi, useWebSocket
        │   └── api/          # API client
        └── package.json      # React + Vite + TailwindCSS
```

---

## Data Flow

### Task Execution Flow

```
1. CLI Entry: sindri run "Create hello.py"
                    |
                    v
2. Orchestrator.execute_task()
   - Create root task (status: PENDING)
   - Add to TaskScheduler
   - Emit TASK_CREATED event
                    |
                    v
3. TaskScheduler.get_ready_batch(max_vram)
   - Check dependencies (all satisfied?)
   - Check VRAM (enough for model?)
   - Return batch of parallel-ready tasks
                    |
                    v
4. HierarchicalAgentLoop.run() [parallel via asyncio.gather]
   - Load or create session
   - Load model (with pre-warming for delegation)
   - Iteration loop:
     * Build context (5-tier memory)
     * Emit ITERATION_START, STREAMING_START
     * Call LLM with streaming (on_token callback)
     * Emit STREAMING_TOKEN events
     * Check completion marker
     * Parse tool calls
     * Execute tools (with retry for transient errors)
     * Emit TOOL_CALLED event
     * Save turn to database
     * If delegate: spawn child loop
   - Return result, emit TASK_STATUS_CHANGED
                    |
                    v
5. Delegation (if delegate tool called)
   - DelegationManager.create_child()
   - Pre-warm child model
   - Execute child loop (recursive)
   - child_completed() injects result to parent
   - Resume parent loop
                    |
                    v
6. Completion
   - Task status: COMPLETE
   - Learn patterns from success
   - Store metrics
   - Emit final events
```

### Event Types

```python
class EventType(Enum):
    # Task lifecycle
    TASK_CREATED = "task_created"
    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_CANCELLED = "task_cancelled"

    # Agent execution
    ITERATION_START = "iteration_start"
    ITERATION_WARNING = "iteration_warning"  # 5, 3, 1 remaining
    AGENT_OUTPUT = "agent_output"
    TOOL_CALLED = "tool_called"
    DELEGATION_START = "delegation_start"

    # Streaming
    STREAMING_START = "streaming_start"
    STREAMING_TOKEN = "streaming_token"
    STREAMING_END = "streaming_end"

    # Parallel execution
    PARALLEL_BATCH_START = "parallel_batch_start"
    PARALLEL_BATCH_END = "parallel_batch_end"

    # Planning
    PLAN_PROPOSED = "plan_proposed"
    PLAN_APPROVED = "plan_approved"

    # Learning
    PATTERN_LEARNED = "pattern_learned"

    # Metrics
    METRICS_UPDATED = "metrics_updated"

    # Model management
    MODEL_LOADED = "model_loaded"
    MODEL_UNLOADED = "model_unloaded"
    MODEL_DEGRADED = "model_degraded"  # Fallback triggered

    # Errors
    ERROR = "error"
```

---

## Key Components

### Agents (11 total)

| Agent | Role | Model | VRAM | Delegates To |
|-------|------|-------|------|--------------|
| **Brokkr** | Orchestrator | qwen2.5-coder:14b | ~9GB | All agents |
| **Huginn** | Coder | qwen2.5-coder:7b | ~5GB | ratatoskr |
| **Mimir** | Reviewer | llama3.1:8b | ~5GB | - |
| **Ratatoskr** | Executor | qwen2.5-coder:3b | ~2GB | - |
| **Skald** | Tester | qwen2.5-coder:7b | ~5GB | ratatoskr |
| **Fenrir** | SQL Expert | sqlcoder:7b | ~5GB | ratatoskr |
| **Odin** | Planner | deepseek-r1:14b | ~9GB | brokkr |
| **Heimdall** | Security | qwen3:14b | ~10GB | - |
| **Baldr** | Debugger | deepseek-r1:14b | ~9GB | huginn |
| **Idunn** | Documentation | llama3.1:8b | ~5GB | - |
| **Vidar** | Multi-lang | codestral:22b | ~14GB | ratatoskr |

### Tools (32 total)

**Filesystem:** read_file, write_file, edit_file, list_directory, read_tree
**Search:** search_code, find_symbol
**Git:** git_status, git_diff, git_log, git_branch
**HTTP:** http_request, http_get, http_post
**Testing:** run_tests, check_syntax
**Formatting:** format_code, lint_code
**Refactoring:** rename_symbol, extract_function, inline_variable, move_file, batch_rename, split_file, merge_files
**SQL:** execute_query, describe_schema, explain_query
**CI/CD:** generate_workflow, validate_workflow
**Planning:** propose_plan
**Core:** shell, delegate

---

## Design Patterns

### 1. Pub/Sub (EventBus)
Decouples TUI/Web from orchestrator. Components subscribe to event types and receive updates without tight coupling.

### 2. Repository Pattern (SessionState)
Database abstraction with async CRUD operations. Easy to mock in tests, clear separation of concerns.

### 3. Strategy Pattern (Tool System)
Abstract Tool base class with execute method. All tools return ToolResult, never raise exceptions.

### 4. Facade Pattern (Orchestrator)
Single entry point that owns all managers. Hides complexity behind simple execute_task() API.

### 5. Recursive Decomposition (Delegation)
Agents recursively delegate to specialists. Complex tasks naturally decompose into subtasks.

---

## Extension Points

### Adding a New Tool

1. Create class in `sindri/tools/<name>.py` inheriting from `Tool`
2. Register in `sindri/tools/registry.py`
3. Add to agent tool lists in `sindri/agents/registry.py`
4. Write tests in `tests/test_<name>.py`

### Adding a New Agent

1. Define in `sindri/agents/registry.py` with AgentDefinition
2. Create system prompt in `sindri/agents/prompts.py`
3. Add to parent agent's `delegate_to` list
4. Write tests

### Adding via Plugins

Users can add custom tools and agents without modifying Sindri:
- Tools: `~/.sindri/plugins/*.py`
- Agents: `~/.sindri/agents/*.toml`

---

## Performance Considerations

### VRAM Management
- LRU eviction with keep-warm protection
- Model pre-warming during delegation
- Cache metrics tracking (hits, misses, evictions)
- Fallback to smaller models when VRAM insufficient

### Parallel Execution
- Independent tasks run via asyncio.gather()
- VRAM-aware batching (tasks sharing models count once)
- Thread-safe ModelManager with per-model locks

### Database Performance
- WAL mode for concurrent access
- Batch writes where possible
- Async operations throughout

---

## Database Schema (v4)

### Core Tables
- **sessions** - Task sessions with status
- **turns** - Conversation turns (system, user, assistant, tool)
- **episodes** - Episodic memory summaries
- **chunks** - Semantic memory with embeddings (sqlite-vec)

### Extended Tables
- **session_metrics** - Performance metrics JSON
- **session_feedback** - User ratings and quality tags
- **session_shares** - Share links with permissions
- **session_comments** - Review comments with threading
- **patterns** - Learned successful patterns
- **codebase_analysis** - Cached analysis results
- **projects** - Multi-project registry

---

## Testing

**Test Count:** 1284 backend tests + 104 frontend tests (100% passing)

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run specific module
.venv/bin/pytest tests/test_tools.py -v

# Frontend tests
cd sindri/web/static && npm test -- --run
```

---

**Last Updated:** 2026-01-17
**Maintained By:** Project contributors
