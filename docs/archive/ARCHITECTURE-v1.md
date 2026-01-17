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
        # 1. Get LLM response
        response = await llm.chat(model, messages)
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

### Hierarchical Delegation

Sindri extends the Ralph loop with task delegation:

```
Root Task (User)
    ↓
┌─────────────────┐
│ Brokkr Loop     │ ← Orchestrator agent
└────┬────────────┘
     │
     ├─→ delegate("Implement feature X", agent="huginn")
     │      ↓
     │   ┌──────────────┐
     │   │ Huginn Loop  │ ← Code implementation agent
     │   └──┬───────────┘
     │      │
     │      ├─→ write_file(...)
     │      ├─→ delegate("Execute tests", agent="ratatoskr")
     │      │      ↓
     │      │   ┌────────────────┐
     │      │   │ Ratatoskr Loop │ ← Fast execution agent
     │      │   └────────────────┘
     │      │      ↓ (returns result)
     │      │   [Child completes]
     │      ├─→ [Receives child result]
     │      └─→ <sindri:complete/>
     │   [Huginn completes]
     ├─→ [Receives Huginn result]
     └─→ <sindri:complete/>
[Brokkr completes]
```

**Key Properties:**
- **Nested loops** - Each delegation spawns a new loop
- **Bidirectional communication** - Parent ↔ Child result passing
- **Context preservation** - Parent resumes with full history
- **Specialization** - Each agent has specific tools/capabilities

### Memory System (Muninn)

Three-tier memory architecture:

```
┌─────────────────────────────────────────┐
│ Context Window (32K tokens max)        │
├─────────────────────────────────────────┤
│ 60% Working Memory                      │
│ - Recent conversation (last 10 turns)   │
│ - Current task description              │
│ - Tool results                          │
├─────────────────────────────────────────┤
│ 20% Episodic Memory                     │
│ - Past task summaries (5 most relevant) │
│ - What worked, what didn't              │
│ - Retrieved via semantic similarity     │
├─────────────────────────────────────────┤
│ 20% Semantic Memory                     │
│ - Codebase chunks (10 most relevant)    │
│ - Retrieved via embedding similarity    │
│ - Indexed from project files            │
└─────────────────────────────────────────┘
```

**Benefits:**
- Agents have project context without reading all files
- Learn from past successes/failures
- Scale to large codebases (tested with 100+ files)

---

## System Architecture

### Component Diagram

```
┌──────────────────────────────────────────────────────────┐
│                         CLI Layer                        │
│  (sindri/cli.py, sindri/__main__.py)                   │
└────────────────────┬─────────────────────────────────────┘
                     │
         ┌───────────┴──────────┐
         │                      │
┌────────▼─────────┐   ┌───────▼──────────┐
│   TUI (Textual)  │   │  Orchestrator    │
│  sindri/tui/     │   │  sindri/core/    │
└────────┬─────────┘   └───────┬──────────┘
         │                     │
         └──────┬──────────────┘
                │
         ┌──────▼───────────────────────────┐
         │        EventBus                  │
         │   (Pub/Sub communication)        │
         └──────┬───────────────────────────┘
                │
    ┌───────────┼───────────┬─────────────┐
    │           │           │             │
┌───▼────┐ ┌───▼─────┐ ┌──▼──────┐ ┌────▼─────┐
│TaskSch │ │HierLoop │ │DelegMgr │ │  Memory  │
│eduler  │ │         │ │         │ │ (Muninn) │
└───┬────┘ └───┬─────┘ └──┬──────┘ └────┬─────┘
    │          │           │             │
    │      ┌───▼───────────▼────┐        │
    │      │   SessionState     │        │
    │      │  (Persistence)     │        │
    │      └────────────────────┘        │
    │                                    │
┌───▼──────────────┐          ┌──────────▼──────┐
│  ModelManager    │          │   Embedder      │
│  (VRAM tracking) │          │ (nomic-embed)   │
└───┬──────────────┘          └─────────────────┘
    │
┌───▼─────────┐
│OllamaClient │
│(LLM calls)  │
└─────────────┘
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
│   ├── hierarchical.py       # HierarchicalAgentLoop (295 lines)
│   ├── scheduler.py          # Priority queue, dependency resolution
│   ├── delegation.py         # Parent-child task management
│   ├── tasks.py              # Task, TaskStatus, TaskPriority models
│   ├── events.py             # EventBus, Event, EventType
│   ├── completion.py         # Completion marker detection
│   ├── context.py            # Message/context building
│   ├── recovery.py           # Crash recovery (planned)
│   └── retry.py              # Retry with exponential backoff (planned)
│
├── agents/                   # Agent definitions and prompts
│   ├── definitions.py        # AgentDefinition dataclass
│   ├── registry.py           # AGENTS dict (Brokkr, Huginn, etc.)
│   ├── prompts.py            # System prompts for each agent
│   └── patterns/             # Agent-specific pattern libraries (planned)
│
├── llm/                      # LLM interface layer
│   ├── client.py             # OllamaClient (async wrapper)
│   ├── manager.py            # ModelManager (VRAM tracking, LRU)
│   ├── tool_parser.py        # Parse JSON tool calls from text
│   └── streaming.py          # Streaming response support (planned)
│
├── tools/                    # Tool implementations
│   ├── base.py               # Tool ABC, ToolResult dataclass
│   ├── registry.py           # ToolRegistry, schema generation
│   ├── filesystem.py         # read_file, write_file, edit_file
│   ├── shell.py              # shell execution
│   ├── delegation.py         # DelegateTool (special)
│   ├── planning.py           # Planning tools (planned)
│   ├── sql.py                # SQL tools for Fenrir (planned)
│   └── testing.py            # Test tools for Skald (planned)
│
├── memory/                   # Memory system (Muninn)
│   ├── system.py             # MuninnMemory orchestrator
│   ├── episodic.py           # EpisodicMemory (task summaries)
│   ├── semantic.py           # SemanticMemory (codebase embeddings)
│   ├── embedder.py           # EmbeddingClient (nomic-embed-text)
│   ├── summarizer.py         # ConversationSummarizer
│   ├── indexer.py            # Codebase indexing
│   ├── patterns.py           # Pattern learning (planned)
│   └── global_memory.py      # Cross-project memory (planned)
│
├── persistence/              # Database layer
│   ├── database.py           # SQLite setup, migrations
│   ├── state.py              # SessionState (CRUD for sessions/turns)
│   ├── vectors.py            # sqlite-vec integration
│   ├── backup.py             # Backup/restore (planned)
│   └── migrations/           # Schema migrations
│
├── tui/                      # Terminal UI (Textual)
│   ├── app.py                # SindriApp (main Textual app)
│   ├── widgets/
│   │   ├── header.py         # Header with stats
│   │   ├── task_tree.py      # Task list (left panel)
│   │   ├── output.py         # Output viewer (right panel)
│   │   ├── input.py          # Task input (bottom)
│   │   ├── history.py        # Task history panel (planned)
│   │   └── plan_review.py    # Plan review widget (planned)
│   ├── export.py             # Export conversations (planned)
│   └── styles/               # CSS-like styling
│
├── web/                      # Web UI (planned)
│   ├── server.py             # FastAPI server
│   ├── api/                  # REST/WebSocket endpoints
│   └── static/               # React frontend
│
├── plugins/                  # Plugin system (planned)
│   ├── loader.py             # Plugin discovery
│   ├── validator.py          # Plugin validation
│   ├── manager.py            # Install/update plugins
│   └── api.py                # Plugin API docs
│
└── analysis/                 # Codebase analysis (planned)
    ├── dependencies.py       # Import graph
    ├── architecture.py       # Pattern detection
    └── style.py              # Style extraction
```

---

## Data Flow

### Task Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CLI Entry                                                │
│    sindri run "Create hello.py"                            │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Orchestrator.execute_task()                             │
│    - Create root task (status: PENDING)                    │
│    - Add to TaskScheduler                                  │
│    - Emit TASK_CREATED event                               │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. TaskScheduler.get_next()                                │
│    - Check dependencies (all satisfied?)                   │
│    - Check VRAM (enough for model?)                        │
│    - Return highest priority ready task                    │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. HierarchicalAgentLoop.run()                             │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 4a. Load or create session                          │ │
│    │     - If task.session_id exists → load_session()    │ │
│    │     - Else → create_session()                       │ │
│    └─────────────────────────────────────────────────────┘ │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 4b. Load model                                      │ │
│    │     - ModelManager.load_model(agent.model)          │ │
│    │     - Track VRAM usage                              │ │
│    └─────────────────────────────────────────────────────┘ │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 4c. Iteration loop                                  │ │
│    │     FOR i in range(max_iterations):                 │ │
│    │       - Build context (working + episodic + semantic)│ │
│    │       - Emit ITERATION_START event                  │ │
│    │       - Call LLM (OllamaClient.chat)                │ │
│    │       - Emit AGENT_OUTPUT event                     │ │
│    │       - Check completion marker                     │ │
│    │       - Parse tool calls                            │ │
│    │       - Execute tools                               │ │
│    │       - Emit TOOL_CALLED event                      │ │
│    │       - Save turn to database                       │ │
│    │       - If delegate: GOTO 5                         │ │
│    └─────────────────────────────────────────────────────┘ │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 4d. Return result                                   │ │
│    │     - Extract output from messages                  │ │
│    │     - Store on task.result                          │ │
│    │     - Emit TASK_STATUS_CHANGED (COMPLETE/FAILED)    │ │
│    └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Delegation (if delegate tool called)                    │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 5a. DelegationManager.create_child()                │ │
│    │     - Create child task                             │ │
│    │     - Set parent_id, assigned_agent                 │ │
│    │     - Add to scheduler                              │ │
│    │     - Set parent status: WAITING                    │ │
│    └─────────────────────────────────────────────────────┘ │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 5b. Execute child (GOTO 4)                          │ │
│    │     - Recursive call to HierarchicalAgentLoop.run() │ │
│    └─────────────────────────────────────────────────────┘ │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 5c. Child completes                                 │ │
│    │     - DelegationManager.child_completed()           │ │
│    │     - Load parent session                           │ │
│    │     - Inject child result as tool message           │ │
│    │     - Save parent session                           │ │
│    │     - Set parent status: PENDING                    │ │
│    └─────────────────────────────────────────────────────┘ │
│    ┌─────────────────────────────────────────────────────┐ │
│    │ 5d. Resume parent (GOTO 4)                          │ │
│    │     - Parent sees child result in context           │ │
│    │     - Continues iteration loop                      │ │
│    └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Completion                                               │
│    - Task status: COMPLETE                                  │
│    - Emit final TASK_STATUS_CHANGED event                   │
│    - Return result to user                                  │
└─────────────────────────────────────────────────────────────┘
```

### Event Flow (TUI Updates)

```
HierarchicalAgentLoop               EventBus                  TUI
        │                               │                      │
        ├─ emit(TASK_CREATED) ──────────►│                      │
        │                               ├────── notify ────────►│
        │                               │              TaskTree.update()
        │                               │                      │
        ├─ emit(ITERATION_START) ───────►│                      │
        │                               ├────── notify ────────►│
        │                               │              Output.add_iteration()
        │                               │                      │
        ├─ emit(AGENT_OUTPUT) ──────────►│                      │
        │                               ├────── notify ────────►│
        │                               │              Output.add_output()
        │                               │                      │
        ├─ emit(TOOL_CALLED) ───────────►│                      │
        │                               ├────── notify ────────►│
        │                               │              Output.add_tool()
        │                               │                      │
        ├─ emit(TASK_STATUS_CHANGED) ───►│                      │
        │                               ├────── notify ────────►│
        │                               │              TaskTree.update_status()
        │                               │                      │
        ├─ emit(ERROR) ─────────────────►│                      │
        │                               ├────── notify ────────►│
        │                               │              show_error_box()
        │                               │                      │
```

---

## Key Components

### Orchestrator

**Location:** `sindri/core/orchestrator.py`

**Responsibilities:**
- Owns all managers (Scheduler, DelegationManager, ModelManager, etc.)
- Entry point for task execution
- Coordinates between components
- Emits high-level events

**Key Methods:**
```python
class Orchestrator:
    async def execute_task(self, description: str, agent: str = "brokkr") -> TaskResult:
        """Execute a task with specified agent."""

    async def shutdown(self):
        """Clean shutdown - unload models, close DB."""
```

### HierarchicalAgentLoop

**Location:** `sindri/core/hierarchical.py` (295 lines)

**Responsibilities:**
- Execute the Ralph loop for a single task
- Handle delegation by spawning child loops
- Manage session creation/resumption
- Emit detailed events (iteration, output, tools)
- Detect completion markers

**Key Methods:**
```python
class HierarchicalAgentLoop:
    async def run(self, task: Task) -> LoopResult:
        """Execute task with Ralph loop pattern."""
        # 1. Load/create session
        # 2. Load model
        # 3. Iteration loop
        # 4. Return result

    async def _run_loop(self, task: Task, session: Session) -> LoopResult:
        """Internal loop implementation."""
```

**Critical Sections:**

1. **Session Resume** (lines 138-151):
```python
if task.session_id:
    # Resume existing session
    session = await self.state.load_session(task.session_id)
else:
    # Create new session
    session = await self.state.create_session(...)
```

2. **Cancellation Check** (lines 180-191, 251-262):
```python
if task.cancel_requested:
    task.status = TaskStatus.CANCELLED
    return LoopResult(success=False)
```

3. **Tool Execution** (lines 300-340):
```python
for tool_call in tool_calls:
    result = await tool.execute(**params)
    if tool_call.name == "delegate" and result.success:
        # Spawn child loop (recursive call)
```

### TaskScheduler

**Location:** `sindri/core/scheduler.py`

**Responsibilities:**
- Priority queue for tasks
- Dependency resolution
- VRAM-aware scheduling

**Key Methods:**
```python
class TaskScheduler:
    def add_task(self, task: Task):
        """Add task to queue."""

    async def get_next(self) -> Optional[Task]:
        """Get next ready task (dependencies satisfied, VRAM available)."""

    def get_waiting_children(self, parent_id: str) -> List[Task]:
        """Get children blocked on parent."""
```

**Scheduling Algorithm:**
```python
def get_next(self) -> Optional[Task]:
    ready_tasks = [
        t for t in self.queue
        if t.status == PENDING
        and all_dependencies_satisfied(t)
        and vram_available_for(t)
    ]

    if not ready_tasks:
        return None

    # Sort by priority, then creation time
    return sorted(ready_tasks, key=lambda t: (t.priority, t.created_at))[0]
```

### DelegationManager

**Location:** `sindri/core/delegation.py`

**Responsibilities:**
- Create child tasks
- Track parent-child relationships
- Inject child results into parent sessions

**Key Methods:**
```python
class DelegationManager:
    async def create_child(
        self,
        parent: Task,
        agent_name: str,
        task_description: str
    ) -> Task:
        """Create child task and link to parent."""

    async def child_completed(self, child: Task):
        """Handle child completion - inject result to parent."""
```

**Child Result Injection:**
```python
async def child_completed(self, child: Task):
    parent = self.task_map[child.parent_id]
    parent_session = await self.state.load_session(parent.session_id)

    # Format result message
    result_text = f"""Child task completed successfully!
Agent: {child.assigned_agent}
Task: {child.description}
Result: {child.result['output']}"""

    # Inject as tool message
    parent_session.add_turn("tool", result_text, tool_call_id=...)
    await self.state.save_session(parent_session)

    # Resume parent
    parent.status = TaskStatus.PENDING
```

### ModelManager

**Location:** `sindri/llm/manager.py`

**Responsibilities:**
- Load/unload models via Ollama
- Track VRAM usage
- LRU eviction when VRAM full

**Key Methods:**
```python
class ModelManager:
    async def load_model(self, model_name: str):
        """Load model, evict LRU if needed."""

    async def unload_model(self, model_name: str):
        """Explicitly unload model."""

    def get_vram_usage(self) -> float:
        """Current VRAM used in GB."""
```

**VRAM Tracking:**
```python
# Model sizes (hardcoded for now, could query Ollama)
MODEL_SIZES = {
    "qwen2.5-coder:14b": 9.0,
    "deepseek-coder-v2:16b": 10.5,
    "qwen2.5-coder:7b": 4.7,
    "qwen2.5:3b-instruct-q8_0": 3.3,
    ...
}

async def load_model(self, model_name: str):
    required = MODEL_SIZES[model_name]
    available = self.total_vram - self.reserve_vram - self.current_usage

    while available < required and self.loaded_models:
        # Evict LRU model
        lru_model = min(self.loaded_models, key=lambda m: m.last_used)
        await self.unload_model(lru_model.name)
        available = self.total_vram - self.reserve_vram - self.current_usage

    if available < required:
        raise VRAMError("Not enough VRAM")

    await ollama.load(model_name)
    self.current_usage += required
```

### MuninnMemory

**Location:** `sindri/memory/system.py`

**Responsibilities:**
- Orchestrate three memory tiers
- Build context within token budget
- Index new files

**Key Methods:**
```python
class MuninnMemory:
    async def get_context(
        self,
        task_description: str,
        working_memory: List[Message],
        max_tokens: int = 32768
    ) -> List[Message]:
        """Build context from all three memory tiers."""

    async def index_project(self, path: str):
        """Index project files into semantic memory."""

    async def store_episode(self, session: Session):
        """Summarize and store session in episodic memory."""
```

**Context Building:**
```python
async def get_context(self, task, working, max_tokens):
    # Allocate token budget: 60/20/20 split
    working_budget = int(max_tokens * 0.6)
    episodic_budget = int(max_tokens * 0.2)
    semantic_budget = int(max_tokens * 0.2)

    # Build context
    context = []

    # 1. Working memory (recent conversation)
    context.extend(working[-10:])  # Last 10 turns

    # 2. Episodic memory (past task summaries)
    episodes = await self.episodic.search(task, limit=5)
    context.append(format_episodes(episodes))

    # 3. Semantic memory (relevant code chunks)
    chunks = await self.semantic.search(task, limit=10)
    context.append(format_chunks(chunks))

    return context
```

---

## Design Patterns

### 1. Pub/Sub (EventBus)

**Problem:** TUI needs real-time updates from orchestrator without tight coupling

**Solution:** EventBus with topic-based subscriptions

```python
# Publisher (HierarchicalAgentLoop)
await self.event_bus.emit(Event(
    type=EventType.AGENT_OUTPUT,
    data={"task_id": task.id, "output": response}
))

# Subscriber (TUI)
def on_agent_output(self, event: Event):
    task_id = event.data["task_id"]
    output = event.data["output"]
    self.output_panel.add_text(output)

# Registration
event_bus.subscribe(EventType.AGENT_OUTPUT, tui.on_agent_output)
```

**Benefits:**
- Decoupled components
- Easy to add new subscribers
- Testable in isolation

### 2. Repository Pattern (SessionState)

**Problem:** Need database abstraction, easy to test without real DB

**Solution:** Repository pattern with async CRUD operations

```python
class SessionState:
    async def create_session(self, description: str, model: str) -> Session:
        """Create new session in DB."""

    async def load_session(self, session_id: str) -> Optional[Session]:
        """Load session by ID."""

    async def save_session(self, session: Session):
        """Update session in DB."""
```

**Benefits:**
- Easy to mock in tests
- Can swap DB implementations
- Clear separation of concerns

### 3. Strategy Pattern (Tool System)

**Problem:** Different tools, common interface

**Solution:** Abstract base class with execute method

```python
class Tool(ABC):
    @property
    @abstractmethod
    def schema(self) -> dict:
        """Ollama-compatible tool schema."""

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """Execute tool, return result."""

class ReadFileTool(Tool):
    @property
    def schema(self):
        return {
            "name": "read_file",
            "description": "Read a file from disk",
            "parameters": {...}
        }

    async def execute(self, file_path: str) -> ToolResult:
        try:
            with open(file_path) as f:
                return ToolResult(success=True, output=f.read())
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

**Benefits:**
- Easy to add new tools
- Uniform error handling
- Auto-generate schemas for LLM

### 4. Facade Pattern (Orchestrator)

**Problem:** Complex subsystem with many managers

**Solution:** Orchestrator as simple entry point

```python
class Orchestrator:
    def __init__(self, config: Config):
        # Create all managers
        self.scheduler = TaskScheduler()
        self.delegation = DelegationManager()
        self.model_manager = ModelManager(config)
        self.memory = MuninnMemory(config)
        self.state = SessionState(config)
        ...

    async def execute_task(self, description: str) -> TaskResult:
        # High-level API, hides complexity
        task = self.create_task(description)
        result = await self._execute(task)
        return result
```

**Benefits:**
- Simple external API
- Hides internal complexity
- Single point of initialization

### 5. Recursive Decomposition (Delegation)

**Problem:** Complex tasks need breakdown

**Solution:** Agents recursively delegate to specialists

```python
# Brokkr (orchestrator)
if task_is_complex(task):
    await delegate(agent="huginn", task="Implement feature X")

# Huginn (coder)
if needs_execution(implementation):
    await delegate(agent="ratatoskr", task="Run tests")

# Ratatoskr (executor)
result = await execute_shell("pytest tests/")
return result

# Results bubble up
```

**Benefits:**
- Natural task decomposition
- Specialization at each level
- Parallel execution possible (future)

---

## Extension Points

### Adding a New Tool

1. **Create tool class** (`sindri/tools/my_tool.py`):
```python
from sindri.tools.base import Tool, ToolResult

class MyTool(Tool):
    @property
    def schema(self):
        return {
            "name": "my_tool",
            "description": "What this tool does",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "..."}
                },
                "required": ["param1"]
            }
        }

    async def execute(self, param1: str) -> ToolResult:
        try:
            result = do_something(param1)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

2. **Register tool** (`sindri/tools/registry.py`):
```python
from sindri.tools.my_tool import MyTool

def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(MyTool())  # Add here
    return registry
```

3. **Add to agent** (`sindri/agents/registry.py`):
```python
AGENTS = {
    "brokkr": AgentDefinition(
        name="brokkr",
        tools=["read_file", "my_tool"],  # Add here
        ...
    )
}
```

4. **Test** (`tests/test_tools.py`):
```python
async def test_my_tool():
    tool = MyTool()
    result = await tool.execute(param1="test")
    assert result.success
    assert "expected" in result.output
```

### Adding a New Agent

1. **Define agent** (`sindri/agents/registry.py`):
```python
AGENTS = {
    "thor": AgentDefinition(
        name="thor",
        role="Performance Optimizer",
        model="qwen2.5-coder:14b",
        tools=["read_file", "write_file", "benchmark"],
        delegate_to=["ratatoskr"],
        max_iterations=30
    )
}
```

2. **Create system prompt** (`sindri/agents/prompts.py`):
```python
AGENT_PROMPTS = {
    "thor": """You are Thor, the Performance Optimizer.

Your role is to analyze code and optimize for performance.

Available tools:
- read_file: Read source files
- write_file: Write optimized versions
- benchmark: Run performance tests

When you find optimizations:
1. Measure current performance
2. Apply optimization
3. Verify improvement
4. Document changes

Complete tasks with: <sindri:complete/>
"""
}
```

3. **Add delegation paths** (in parent agents):
```python
AGENTS = {
    "brokkr": AgentDefinition(
        delegate_to=["huginn", "mimir", "thor"],  # Add thor
        ...
    )
}
```

### Adding Event Types

1. **Define event** (`sindri/core/events.py`):
```python
class EventType(Enum):
    TASK_CREATED = "task_created"
    MY_EVENT = "my_event"  # Add here
```

2. **Emit event** (wherever it originates):
```python
await self.event_bus.emit(Event(
    type=EventType.MY_EVENT,
    data={"key": "value"}
))
```

3. **Subscribe in TUI** (`sindri/tui/app.py`):
```python
def on_mount(self):
    self.event_bus.subscribe(EventType.MY_EVENT, self.on_my_event)

def on_my_event(self, event: Event):
    # Handle event
    self.notify(f"My event: {event.data}")
```

---

## Performance Considerations

### VRAM Management

**Challenge:** Models are large (3-16GB), GPU memory is limited

**Strategies:**

1. **LRU Eviction**
   - Track last_used timestamp
   - Evict oldest when needed
   - Keep frequently-used models loaded

2. **Model Sharing**
   - Reuse loaded models across tasks
   - Batch tasks by model when possible

3. **Smart Preloading**
   - Load child model before delegation
   - Reduces delegation latency

4. **Graceful Degradation**
   - If VRAM full, suggest smaller model
   - Or queue task until VRAM available

### Database Performance

**Challenge:** SQLite can be slow, especially with concurrent writes

**Strategies:**

1. **Write-Ahead Logging (WAL)**
```python
# In database.py
conn.execute("PRAGMA journal_mode=WAL")
```

2. **Batch Writes**
```python
# Instead of N individual writes
for turn in turns:
    await save_turn(turn)

# Batch them
await save_turns_batch(turns)
```

3. **Connection Pooling**
```python
# Reuse connections
async with self.pool.acquire() as conn:
    await conn.execute(...)
```

4. **Async Operations**
```python
# All DB ops should be async
async def save_session(self, session: Session):
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute(...)
```

### Context Window Optimization

**Challenge:** LLMs have token limits (32K), long conversations exceed

**Strategies:**

1. **Summarization**
   - Summarize old turns
   - Keep summaries, discard details
   - ConversationSummarizer does this

2. **Memory Tiering**
   - Only load relevant memory
   - Semantic search for retrieval
   - 60/20/20 token budget

3. **Turn Pruning**
   - Keep only recent N turns
   - Keep critical turns (completion, errors)
   - Prune verbose tool outputs

### Parallel Execution (Future)

**Goal:** Execute independent tasks concurrently

**Challenges:**

1. **VRAM Conflicts**
   - Two tasks need same 10GB model
   - Solution: Share model, serialize execution

2. **Database Locking**
   - SQLite doesn't love concurrent writes
   - Solution: WAL mode + write queuing

3. **Event Ordering**
   - TUI expects sequential events
   - Solution: Timestamp events, replay in order

**Implementation Plan:**
```python
# In scheduler
async def execute_batch(self) -> List[Task]:
    ready_tasks = self.get_ready_tasks()

    # Group by model (can share)
    by_model = group_by(ready_tasks, key=lambda t: t.model)

    # Execute groups in parallel
    results = await asyncio.gather(*[
        self.execute_group(group)
        for group in by_model.values()
    ])

    return flatten(results)
```

---

## Database Schema

### Sessions Table

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, running, complete, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Turns Table

```sql
CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- system, user, assistant, tool
    content TEXT,
    tool_calls TEXT,  -- JSON array
    tool_call_id TEXT,
    name TEXT,  -- For tool role
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

### Episodes Table (Episodic Memory)

```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,  -- Summarized session
    outcome TEXT,  -- success, failure
    agent TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

### Chunks Table (Semantic Memory)

```sql
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    content TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    embedding BLOB,  -- sqlite-vec vector
    created_at TIMESTAMP
);

-- Virtual table for vector search
CREATE VIRTUAL TABLE chunks_vec USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[768]
);
```

### Tasks Table (Future - for recovery)

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER,
    parent_id TEXT,
    session_id TEXT,
    assigned_agent TEXT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP,
    result TEXT,  -- JSON
    FOREIGN KEY (parent_id) REFERENCES tasks(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

---

## Testing Strategy

### Unit Tests

**What to test:**
- Individual tools (read_file, write_file, etc.)
- Task scheduling logic
- Memory retrieval
- Tool parsing
- Completion detection

**Example:**
```python
# tests/test_tools.py
async def test_read_file_success():
    tool = ReadFileTool()
    result = await tool.execute(file_path="/tmp/test.txt")
    assert result.success
    assert "expected content" in result.output

async def test_read_file_not_found():
    tool = ReadFileTool()
    result = await tool.execute(file_path="/nonexistent")
    assert not result.success
    assert "not found" in result.error.lower()
```

### Integration Tests

**What to test:**
- Full task execution with real Ollama
- Delegation flow
- Memory system
- Session persistence

**Example:**
```python
# tests/test_delegation.py
async def test_delegation_flow():
    orchestrator = Orchestrator(config)
    result = await orchestrator.execute_task(
        "Create test.txt with 'hello'"
    )

    # Verify task completed
    assert result.success

    # Verify file created
    assert Path("test.txt").exists()

    # Verify delegation occurred
    tasks = orchestrator.scheduler.get_all_tasks()
    assert len(tasks) == 2  # Parent + child
    assert tasks[1].parent_id == tasks[0].id
```

### End-to-End Tests

**What to test:**
- Full workflows from CLI
- TUI interactions (harder, use Textual test utilities)
- Error recovery
- Performance benchmarks

**Example:**
```python
# tests/test_e2e.py
def test_cli_run_command(tmp_path):
    # Run CLI command
    result = subprocess.run(
        ["sindri", "run", "Create hello.py"],
        cwd=tmp_path,
        capture_output=True
    )

    assert result.returncode == 0
    assert (tmp_path / "hello.py").exists()
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from sindri.core.orchestrator import Orchestrator
from sindri.config import Config

@pytest.fixture
async def orchestrator():
    config = Config(data_dir="/tmp/test-sindri")
    orch = Orchestrator(config)
    yield orch
    await orch.shutdown()

@pytest.fixture
def mock_ollama(monkeypatch):
    async def fake_chat(model, messages):
        return "Mocked response"

    monkeypatch.setattr("sindri.llm.client.OllamaClient.chat", fake_chat)
```

---

## Notes for Future Developers

### Code Style

- **Async everywhere** - All I/O should be async/await
- **Type hints** - All functions must have type annotations
- **Docstrings** - Public APIs need docstrings (Google style)
- **Logging** - Use structlog, not print
- **Error handling** - Tools return ToolResult, never raise

### Common Pitfalls

1. **Session Resume Bug**
   - Always check for existing `task.session_id` before creating new session
   - See `hierarchical.py:138-151` for correct pattern

2. **JSON Serialization**
   - Ollama ToolCall objects aren't JSON serializable
   - Use `serialize_tool_calls()` helper in `state.py`

3. **Event Bus Wiring**
   - Create EventBus ONCE in CLI
   - Pass to both Orchestrator and TUI
   - Don't create multiple buses

4. **VRAM Accounting**
   - Always track loaded models
   - Unload before loading if needed
   - Reserve VRAM for system (2GB default)

### Debugging Tips

1. **Enable DEBUG logging**
```python
import structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
)
```

2. **Inspect database**
```bash
sqlite3 ~/.sindri/sindri.db
sqlite> SELECT * FROM sessions ORDER BY created_at DESC LIMIT 5;
```

3. **Check Ollama**
```bash
curl http://localhost:11434/api/tags  # List loaded models
ollama ps  # Show running models
```

4. **Use TUI for visibility**
```bash
sindri tui  # Real-time view of execution
```

---

**Last Updated:** 2026-01-14
**Maintained By:** Project maintainers

---

*For the roadmap, see [ROADMAP.md](ROADMAP.md)*
*For current status, see [STATUS.md](STATUS.md)*
*For contributing, see [CONTRIBUTING.md](CONTRIBUTING.md)*
