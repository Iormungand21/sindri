# Sindri Development Roadmap

**Vision:** A production-ready, local-first LLM orchestration system that intelligently coordinates specialized agents to build, refactor, and maintain codebases using local inference.

**Current Status:** Core functionality complete (v0.1.0) - hierarchical delegation, memory system, TUI, persistence all working. Ready for feature expansion.

---

## Guiding Principles

1. **Local-First:** No cloud dependencies, works offline, user owns all data
2. **Efficient:** Parallel execution, smart caching, minimal VRAM waste
3. **Intelligent:** Memory-augmented, learns from past work, specialized agents
4. **Developer-Friendly:** Great UX, clear feedback, easy to extend
5. **Production-Ready:** Robust error handling, crash recovery, comprehensive tests

---

## Roadmap Structure

- **Phase 5:** Polish & Production (Immediate - Q1 2026)
- **Phase 6:** Performance & Parallelism (Q2 2026)
- **Phase 7:** Intelligence & Learning (Q3 2026)
- **Phase 8:** Extensibility & Platform (Q4 2026)

---

## Tools & Models Reference

**See [TOOLS_AND_MODELS_ANALYSIS.md](TOOLS_AND_MODELS_ANALYSIS.md) for comprehensive analysis:**
- Current tools: 5 implemented (read_file, write_file, edit_file, shell, delegate)
- Recommended additions: 20 tools across 6 categories
- Current models: 7 active (qwen, llama, deepseek, sqlcoder)
- Recommended models: 9 additions (codellama, mistral, starcoder2, phi3, etc.)
- New agent proposals: 4 (Thor, Heimdall, Idunn, Loki)

**Immediate priorities:**
- Tools: list_directory, read_tree, search_code (Phase 5.2)
- Models: codellama:13b, mistral:7b, starcoder2:15b

---

## Phase 5: Polish & Production ✨
**Goal:** Make Sindri immediately useful for real projects

### 5.1 Missing CLI Commands (High Priority)

**Status:** Planned in README, not implemented

#### `sindri doctor`
- **Purpose:** Verify system health and configuration
- **Checks:**
  - Ollama running and responsive
  - Required models available (pull instructions if missing)
  - Database integrity (~/.sindri/sindri.db)
  - VRAM availability and GPU detection
  - Python version and dependencies
- **Output:** Clear diagnosis with fix suggestions
- **Files:** `sindri/cli.py` (new command), `sindri/core/doctor.py` (health checks)

#### `sindri orchestrate <task>`
- **Purpose:** Entry point for hierarchical multi-agent execution
- **Behavior:**
  - Always starts with Brokkr (orchestrator)
  - Enables memory system by default
  - Shows delegation tree in output
  - More verbose than `sindri run`
- **Options:**
  - `--no-memory` - Disable memory
  - `--max-depth N` - Limit delegation depth
  - `--explain` - Show planning before execution
- **Files:** `sindri/cli.py` (route to orchestrator with defaults)

#### `sindri sessions`
- **Purpose:** List and inspect past sessions
- **Features:**
  - List recent sessions with timestamp, description, status
  - Filter by date, agent, status
  - Show full conversation with `--id <session_id>`
  - Export session as markdown
- **Files:** `sindri/cli.py`, `sindri/persistence/queries.py` (session queries)

#### `sindri recover`
- **Purpose:** List and recover from crashes
- **Features:**
  - Detect incomplete sessions (status != COMPLETE/FAILED)
  - Show last known state, iteration count
  - Estimate likelihood of successful recovery
  - Resume with `sindri resume <id>`
- **Files:** `sindri/cli.py`, `sindri/core/recovery.py`

#### `sindri resume <id>`
- **Purpose:** Continue interrupted session
- **Behavior:**
  - Load session state from database
  - Restore task tree and parent-child relationships
  - Resume from last checkpoint
  - Handle model changes gracefully
- **Files:** `sindri/cli.py`, `sindri/core/recovery.py`

#### `sindri agents`
- **Purpose:** List available agents and capabilities
- **Features:**
  - Show all agents with roles, models, tools
  - Filter by capability (e.g., `--tool write_file`)
  - Show delegation graph
  - Estimate VRAM requirements
- **Files:** `sindri/cli.py`, `sindri/agents/inspector.py`

**Implementation Notes:**
- Add Click commands in `sindri/cli.py`
- Create helper modules in `sindri/core/` for complex logic
- Add tests in `tests/test_cli_commands.py`
- Update README with examples

---

### 5.2 Directory Exploration Tool (High Priority)

**Problem:** Agents can't easily understand project structure

**Solution:** Add `list_directory` and `read_tree` tools

#### `list_directory` Tool
```python
{
  "name": "list_directory",
  "description": "List files and directories in a path",
  "parameters": {
    "path": {"type": "string", "description": "Directory path (default: cwd)"},
    "recursive": {"type": "boolean", "description": "List recursively"},
    "pattern": {"type": "string", "description": "Glob pattern filter (e.g., '*.py')"},
    "ignore_hidden": {"type": "boolean", "description": "Skip hidden files/dirs"}
  }
}
```

#### `read_tree` Tool
```python
{
  "name": "read_tree",
  "description": "Show directory tree structure",
  "parameters": {
    "path": {"type": "string"},
    "max_depth": {"type": "integer", "description": "Tree depth limit"},
    "gitignore": {"type": "boolean", "description": "Respect .gitignore"}
  }
}
```

**Files:**
- `sindri/tools/filesystem.py` - Add new tool classes
- `sindri/tools/registry.py` - Register tools
- `sindri/agents/registry.py` - Add to Brokkr, Huginn tool lists
- `tests/test_tools.py` - Add tests

**Benefits:**
- Agents can explore unknown codebases
- Better context for refactoring tasks
- Useful for "review this project" tasks

---

### 5.3 Enable Memory by Default (Medium Priority)

**Status:** Memory system tested and working, but disabled in production

**Changes:**
1. **Orchestrator initialization** (`sindri/core/orchestrator.py`):
   - Enable MuninnMemory by default
   - Add `--no-memory` flag to disable

2. **First-run experience**:
   - Detect if project not indexed
   - Show "Indexing codebase..." progress
   - Cache embeddings for future runs

3. **Memory indicators in TUI** (`sindri/tui/widgets/header.py`):
   - Show memory stats: "📚 Memory: 47 files, 12 episodes"
   - Indicate when semantic/episodic memory is used

**Files:**
- `sindri/core/orchestrator.py` - Enable by default
- `sindri/cli.py` - Add `--no-memory` flag
- `sindri/tui/widgets/header.py` - Memory stats widget
- Update documentation

**Benefits:**
- Agents have better context on complex projects
- Learns from past work
- Validates memory system with real usage

---

### 5.4 TUI Enhancements (Medium Priority)

#### Task History Panel
- Show completed tasks in sidebar
- Click to view conversation
- Search/filter past tasks
- Useful for "what did I ask for earlier?"

#### Conversation Export
- Right-click task → "Export as markdown"
- Saves full agent dialogue with tool calls
- Useful for debugging, sharing, documentation

#### VRAM Gauge
- Visual indicator in header: `[████░░░░] 8.2/16GB VRAM`
- Show which models loaded
- Warn when approaching limit

#### Performance Metrics
- Task duration, iteration count
- Model load times
- Tool execution times
- Help identify bottlenecks

**Files:**
- `sindri/tui/widgets/history.py` - New widget
- `sindri/tui/widgets/header.py` - VRAM gauge
- `sindri/tui/app.py` - Wire up new widgets
- `sindri/tui/export.py` - Markdown export

---

### 5.5 Error Handling & Recovery (High Priority)

**Current State:** Basic error handling exists, but edge cases need work

#### Improvements Needed:

1. **Tool Execution Failures**
   - Retry transient failures (network, VRAM)
   - Better error messages for agents
   - Suggest fixes (e.g., "file not found" → suggest `list_directory`)

2. **Model Loading Failures**
   - Graceful degradation to smaller models
   - Clear "out of VRAM" errors with suggestions
   - Automatic model eviction if needed

3. **Agent Max Iterations**
   - Detect when agent is stuck in loop
   - Offer to switch agent or replan
   - Save state before failing

4. **Database Corruption**
   - Detect and repair common issues
   - Automatic backups before writes
   - Recovery from backup

**Files:**
- `sindri/core/retry.py` - Enhanced retry logic
- `sindri/llm/manager.py` - Better VRAM error handling
- `sindri/persistence/backup.py` - Backup/restore
- `sindri/core/hierarchical.py` - Iteration loop detection

---

## Phase 6: Performance & Parallelism ⚡
**Goal:** Dramatically improve execution speed

### 6.1 Parallel Task Execution (High Priority)

**Current Limitation:** Tasks execute sequentially, even when independent

#### Design:

**Task Dependency Graph**
```python
class Task:
    dependencies: List[str]  # Task IDs that must complete first
    blocks: List[str]        # Task IDs blocked by this task
```

**Scheduler Changes** (`sindri/core/scheduler.py`):
- Detect independent tasks
- Execute in parallel up to VRAM limit
- Smart model sharing (reuse loaded models)

**VRAM Coordination**:
- Lock models during parallel execution
- Prevent double-loading same model
- Queue tasks if VRAM exhausted

**Example Flow:**
```
Task: "Create API with models, routes, and tests"
→ Brokkr delegates to:
  ├─→ Huginn: "Create models.py" (8GB VRAM)
  ├─→ Huginn: "Create routes.py" (8GB VRAM) - BLOCKS: same model, runs sequentially
  └─→ Skald: "Write tests" (5GB VRAM) - INDEPENDENT, runs in parallel!

Before: 3 tasks × 20s = 60s
After: 2 parallel batches × 20s = 40s (33% faster)
```

**Files:**
- `sindri/core/scheduler.py` - Dependency resolution, parallel execution
- `sindri/core/tasks.py` - Add dependency fields
- `sindri/llm/manager.py` - Thread-safe model loading
- `tests/test_parallel_execution.py`

**Challenges:**
- Database locking (SQLite concurrent writes)
- Event ordering (TUI display)
- Error propagation (one task fails → cancel dependents?)

---

### 6.2 Model Caching & Hot-Swapping (Medium Priority)

**Current Behavior:** Models unloaded after each task

#### Smart Caching Strategy:

**LRU Model Cache** (`sindri/llm/manager.py`):
- Keep frequently-used models in VRAM
- Track: last_used, use_count, VRAM_size
- Evict least-recently-used when VRAM needed

**Pre-warming**:
- Before delegating to Huginn, pre-load model
- Reduces delegation latency from 5s → 0.5s

**Hot-Swapping**:
- If switching from Brokkr (14B) → Huginn (16B) and not enough VRAM:
  - Keep Brokkr in RAM (swap to system memory)
  - Load Huginn in VRAM
  - Swap back when resuming parent

**Metrics to Track**:
- Cache hit rate
- Average model load time
- VRAM utilization over time

**Files:**
- `sindri/llm/manager.py` - LRU cache, pre-warming
- `sindri/llm/swapper.py` - RAM ↔ VRAM swapping
- `sindri/config.py` - Cache settings

**Estimated Impact:** 50-70% reduction in model load times

---

### 6.3 Streaming Responses (Low Priority)

**Current:** Wait for full response before displaying

**Improvement:** Stream tokens to TUI in real-time

**Benefits:**
- Feels more responsive
- See agent "thinking" live
- Early cancellation possible

**Implementation:**
- `OllamaClient.chat_stream()` - Generator-based API
- TUI updates on each token
- Buffer for tool call parsing

**Files:**
- `sindri/llm/client.py` - Add streaming methods
- `sindri/core/hierarchical.py` - Use streaming in loop
- `sindri/tui/widgets/output.py` - Live token display

---

## Phase 7: Intelligence & Learning 🧠
**Goal:** Make agents smarter and more specialized

### 7.1 Enhanced Agent Specialization (High Priority)

**Problem:** Agents overlap too much, not distinct enough

#### Agent-Specific Enhancements:

**Skald (Test Writer)**
- Trained patterns for pytest, jest, unittest
- Knows test file conventions (test_*.py, *.test.js)
- Generates fixtures, mocks, parametrized tests
- Understands coverage requirements

**Fenrir (SQL Specialist)**
- Schema awareness from semantic memory
- Migration pattern library (Alembic, Django, etc.)
- Query optimization suggestions
- Knows database-specific features (PostgreSQL vs MySQL)

**Huginn (Coder)**
- Language-specific best practices
- Knows when to use type hints, docstrings
- Follows project style (detect from existing files)
- Refactoring patterns (extract method, rename, etc.)

**Mimir (Reviewer)**
- Security vulnerability detection (OWASP top 10)
- Performance anti-patterns
- Code smell detection
- Suggests improvements with examples

**Implementation:**
- Enhanced system prompts (`sindri/agents/prompts.py`)
- Tool restrictions (Fenrir gets SQL tools, others don't)
- Pattern libraries (`sindri/agents/patterns/`)
- Few-shot examples in prompts

**Files:**
- `sindri/agents/prompts.py` - Rewrite prompts with specialization
- `sindri/agents/patterns/` - Pattern libraries
- `sindri/tools/sql.py` - SQL-specific tools for Fenrir
- `sindri/tools/testing.py` - Test-specific tools for Skald

---

### 7.2 Learning from Success (Medium Priority)

**Concept:** Store successful patterns and recall them

#### What to Learn:

**Successful Completions**
- Track tasks that completed in few iterations
- Extract the approach/pattern used
- Store in episodic memory with high relevance

**Common Patterns**
- File structure conventions (models/, views/, tests/)
- Code patterns (factory, singleton, etc.)
- Tool sequences (read → edit → shell test)

**Project Conventions**
- Naming conventions (snake_case, camelCase)
- Import styles (absolute vs relative)
- Test locations (tests/ vs **/*_test.py)

#### Storage:

**Pattern Database** (`~/.sindri/patterns.db`):
```sql
CREATE TABLE patterns (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    context TEXT,  -- When to use
    example TEXT,  -- Code snippet
    success_count INTEGER,
    last_used TIMESTAMP
);
```

**Memory Integration**:
- Semantic search retrieves relevant patterns
- Inject into agent context: "Similar tasks succeeded using..."
- Agents can reference patterns explicitly

**Files:**
- `sindri/memory/patterns.py` - Pattern storage/retrieval
- `sindri/memory/learner.py` - Extract patterns from completions
- `sindri/persistence/patterns.db` - Pattern database

---

### 7.3 Interactive Planning Mode (Medium Priority)

**UX Flow:**
```
User: "Implement user authentication with JWT"
↓
Brokkr: [Thinks]
↓
┌─────────────────────────────────────────┐
│ Proposed Plan:                          │
│                                         │
│ 1. Create models/user.py with User     │
│    model (password hashing, JWT)       │
│                                         │
│ 2. Create routes/auth.py with:         │
│    - POST /register                     │
│    - POST /login                        │
│    - GET /me                            │
│                                         │
│ 3. Create middleware/jwt.py for        │
│    token validation                     │
│                                         │
│ 4. Write tests for all endpoints       │
│                                         │
│ Delegation: Huginn (steps 1-3),        │
│             Skald (step 4)              │
│                                         │
│ Estimated: 4-6 minutes, ~10GB VRAM     │
└─────────────────────────────────────────┘

[A]pprove  [E]dit  [C]ancel
```

**Implementation:**
- New tool: `propose_plan` (returns plan, doesn't execute)
- Brokkr uses this before delegating
- User can modify plan before execution
- TUI shows plan in dedicated panel

**Files:**
- `sindri/tools/planning.py` - Planning tools
- `sindri/tui/widgets/plan_review.py` - Plan display widget
- `sindri/agents/prompts.py` - Update Brokkr to plan first

**Benefits:**
- User stays in control
- Prevents wasted work on wrong approach
- Educational (see how agents think)

---

### 7.4 Codebase Understanding (High Priority)

**Goal:** Help agents deeply understand project structure

#### Features:

**Dependency Graph**
- Parse imports/requires
- Build module dependency graph
- Identify circular dependencies
- Suggest refactoring opportunities

**Architecture Detection**
- Detect patterns (MVC, layered, microservices)
- Identify entry points (main.py, index.js)
- Map data flow

**Style Analysis**
- Extract coding conventions from existing files
- Detect formatter config (.prettierrc, .editorconfig)
- Apply project style to new code

**Documentation Parsing**
- Read README, CONTRIBUTING.md
- Extract project-specific conventions
- Understand custom tools/scripts

**Implementation:**
- Run on first `sindri orchestrate` in new project
- Store in semantic memory
- Update incrementally as files change

**Files:**
- `sindri/analysis/dependencies.py` - Import graph
- `sindri/analysis/architecture.py` - Pattern detection
- `sindri/analysis/style.py` - Convention extraction
- `sindri/memory/codebase.py` - Store analysis results

---

## Phase 8: Extensibility & Platform 🔧
**Goal:** Make Sindri customizable and shareable

### 8.1 Plugin System (High Priority)

**Concept:** Users can add custom tools and agents without modifying Sindri

#### Plugin Structure:

```python
# ~/.sindri/plugins/my_plugin.py
from sindri.tools import Tool, ToolResult

class MyCustomTool(Tool):
    @property
    def schema(self):
        return {
            "name": "my_tool",
            "description": "Does something custom",
            "parameters": {...}
        }

    async def execute(self, **params) -> ToolResult:
        # Custom logic
        return ToolResult(success=True, output="...")

# Auto-discovered and registered
```

#### Custom Agents:

```toml
# ~/.sindri/agents/my_agent.toml
[agent]
name = "thor"
role = "Performance Optimizer"
model = "qwen2.5-coder:14b"
tools = ["read_file", "write_file", "my_tool"]
max_iterations = 30

[prompt]
file = "thor_prompt.txt"
```

**Discovery:**
- Scan `~/.sindri/plugins/` on startup
- Validate plugin structure
- Register tools/agents dynamically
- Handle errors gracefully

**Files:**
- `sindri/plugins/loader.py` - Plugin discovery
- `sindri/plugins/validator.py` - Plugin validation
- `sindri/plugins/api.py` - Plugin API documentation
- Documentation: `docs/PLUGINS.md`

---

### 8.2 Agent Marketplace (Low Priority)

**Concept:** Share and discover community agents/tools

#### Features:

**CLI Integration:**
```bash
# Browse available plugins
sindri plugins search "testing"

# Install plugin
sindri plugins install community/playwright-tool

# List installed
sindri plugins list

# Update all
sindri plugins update
```

**Plugin Repository:**
- GitHub-based (like Homebrew)
- Versioned plugins
- Community ratings/reviews
- Security scanning

**Plugin Manager** (`sindri/plugins/manager.py`):
- Install/uninstall
- Dependency resolution
- Version pinning
- Automatic updates

---

### 8.3 Web UI (Medium Priority)

**Goal:** Alternative to TUI with richer visualization

#### Features:

**Agent Collaboration Graph**
```
     Brokkr
       │
   ┌───┼───┬───┐
   │   │   │   │
Huginn │ Skald Fenrir
   │  Mimir
Ratatoskr
```
- Animated delegation flow
- Click node → see conversation
- Real-time VRAM usage
- Task dependency visualization

**Code Diff Viewer**
- Before/after for file edits
- Syntax highlighting
- Accept/reject changes
- Commit integration

**Timeline View**
- Horizontal timeline of all tasks
- Show parallel execution
- Filter by agent, status
- Export as Gantt chart

**Dashboard**
- Recent tasks, success rate
- Total time saved
- Most-used agents
- VRAM usage over time

**Tech Stack:**
- Backend: FastAPI
- Frontend: React + D3.js
- WebSocket for real-time updates
- Share EventBus with TUI

**Files:**
- `sindri/web/` - New directory
- `sindri/web/server.py` - FastAPI app
- `sindri/web/static/` - React frontend
- `sindri/cli.py` - Add `sindri web` command

---

### 8.4 Multi-Project Memory (Low Priority)

**Concept:** Learn patterns across all projects, not just one

#### Global Semantic Memory:

**Shared Embeddings** (`~/.sindri/global_memory.db`):
- Index all projects you've worked on
- Cross-project pattern search
- "I used FastAPI auth in project X, similar to this"

**Project Tagging**:
```bash
sindri projects tag current "fastapi,postgresql,auth"
sindri projects tag ~/other-project "django,mysql"
```

**Cross-Project Search**:
- "Find all authentication implementations"
- Returns snippets from all projects
- Agents can reference other projects

**Privacy Controls**:
- Opt-in per project
- Exclude sensitive projects
- Local-only (never uploaded)

**Files:**
- `sindri/memory/global_memory.py`
- `sindri/cli.py` - Project management commands
- `~/.sindri/projects.json` - Project registry

---

## Phase 9: Advanced Features 🚀
**Future possibilities (2027+)**

### 9.1 Multi-Language Support
- Python, JavaScript, TypeScript, Rust, Go
- Language-specific agents
- Cross-language refactoring

### 9.2 Remote Collaboration
- Share sessions with team
- Real-time co-coding
- Review mode for code review

### 9.3 CI/CD Integration
- GitHub Actions integration
- Automatic PR reviews
- Test generation in CI

### 9.4 Agent Fine-Tuning
- Collect successful interactions
- Fine-tune models on your coding style
- Personal AI pair programmer

### 9.5 Voice Interface
- Voice commands to TUI
- "Refactor this function to use async"
- Text-to-speech for agent responses

---

## Implementation Priority Matrix

| Feature | Impact | Effort | Priority | Phase |
|---------|--------|--------|----------|-------|
| `sindri doctor` | High | Low | 🔴 Immediate | 5.1 |
| Directory tools | High | Low | 🔴 Immediate | 5.2 |
| Enable memory | High | Low | 🔴 Immediate | 5.3 |
| `sindri orchestrate` | High | Low | 🔴 Immediate | 5.1 |
| Error handling | High | Medium | 🔴 Immediate | 5.5 |
| Parallel execution | Very High | High | 🟠 Next | 6.1 |
| Model caching | High | Medium | 🟠 Next | 6.2 |
| Agent specialization | High | Medium | 🟠 Next | 7.1 |
| `sindri sessions` | Medium | Low | 🟡 Soon | 5.1 |
| TUI enhancements | Medium | Medium | 🟡 Soon | 5.4 |
| Interactive planning | Medium | Medium | 🟡 Soon | 7.3 |
| Plugin system | Medium | High | 🟢 Later | 8.1 |
| Learning system | Medium | High | 🟢 Later | 7.2 |
| Web UI | High | Very High | 🟢 Later | 8.3 |
| Streaming | Low | Medium | ⚪ Optional | 6.3 |

---

## Quick Wins (Can Implement Today) ⚡

These are high-impact, low-effort improvements:

1. **`sindri doctor`** (30 min)
   - Check Ollama status
   - List available models
   - Verify database

2. **Directory exploration tools** (1 hour)
   - `list_directory` and `read_tree`
   - Add to Brokkr's tools
   - Immediate usefulness

3. **Enable memory by default** (30 min)
   - Change orchestrator default
   - Add `--no-memory` flag
   - Test with real project

4. **`sindri orchestrate`** (15 min)
   - Alias to `run` with Brokkr + memory
   - Different output formatting
   - Entry point for multi-agent

5. **VRAM gauge in TUI** (45 min)
   - Show in header
   - Pull from ModelManager
   - Visual indicator

**Total: ~3 hours for major UX improvements**

---

## Testing Strategy

**For Each Feature:**

1. **Unit Tests** - Core logic in isolation
2. **Integration Tests** - Feature with real Ollama
3. **E2E Tests** - Full workflow with TUI
4. **Performance Tests** - Benchmark impact
5. **Documentation** - Update README, add examples

**Test Coverage Goals:**
- Core: 90%+
- Tools: 80%+
- TUI: 60%+ (Textual is hard to test)
- Overall: 75%+

---

## Documentation Plan

**For Developers:**
- `ARCHITECTURE.md` - System design deep dive
- `CONTRIBUTING.md` - How to add features
- `TESTING.md` - Test strategy and helpers
- `docs/API.md` - Public API reference

**For Users:**
- `docs/QUICKSTART.md` - 5-minute getting started
- `docs/GUIDES/` - Task-specific guides
- `docs/AGENTS.md` - When to use which agent
- `docs/TROUBLESHOOTING.md` - Common issues

**For Plugin Developers:**
- `docs/PLUGINS.md` - Plugin API guide
- `docs/PLUGIN_EXAMPLES/` - Example plugins
- Plugin template repository

---

## Success Metrics

**Technical:**
- ✅ All tests passing (currently 50/50)
- ✅ Test coverage >75%
- ⏳ Average task completion <2 minutes
- ⏳ Model cache hit rate >60%
- ⏳ Zero data loss (crash recovery works)

**UX:**
- ⏳ Time to first useful output <10 seconds
- ⏳ Clear error messages (user can fix without docs)
- ⏳ TUI responsive (<100ms interaction)
- ⏳ Documentation covers 90% of use cases

**Real-World:**
- ⏳ Successfully used on 5+ real projects
- ⏳ Can handle multi-file refactoring
- ⏳ Agents complete tasks in <80% of max iterations
- ⏳ User satisfaction (dogfooding)

---

## Notes for Future Workers

### Starting a New Phase:

1. **Read this roadmap** - Understand the vision
2. **Check STATUS.md** - Current implementation state
3. **Pick a section** - Start with Quick Wins or highest priority
4. **Create branch** - `git checkout -b feature/doctor-command`
5. **Write tests first** - TDD approach
6. **Implement feature** - Follow existing patterns
7. **Update docs** - README, CHANGELOG, this roadmap
8. **Test manually** - Use TUI, try edge cases
9. **Update STATUS.md** - Mark as complete

### Code Patterns to Follow:

- **Async everywhere** - All I/O should be async
- **Structured logging** - Use `structlog`, not print
- **Type hints** - All functions fully typed
- **Pydantic models** - For all data structures
- **Error handling** - Always return ToolResult, never raise in tools
- **Tests** - One test file per module, use pytest fixtures

### When Stuck:

- Check `STATUS.md` for similar past work
- Look at existing tests for patterns
- Run `pytest tests/test_X.py -v` for that module
- Check logs with DEBUG level
- Ask "what would make this easier to test?"

---

## Changelog

| Date | Phase | Changes |
|------|-------|---------|
| 2026-01-14 | 5.0 | Initial roadmap created |

---

**Last Updated:** 2026-01-14
**Next Review:** When starting Phase 6
**Maintained By:** Project maintainers and contributors

---

*"Like Sindri forging Mjolnir, we build Sindri itself through iteration."* ⚒️
