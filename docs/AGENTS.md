# Sindri Agents

Sindri uses a hierarchical multi-agent system inspired by Norse mythology. Each agent is specialized for specific tasks and can delegate to other agents.

## Agent Hierarchy

```
                    ┌─────────────┐
                    │   Brokkr    │  Master Orchestrator
                    │ qwen2.5:14b │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┬──────────────────┐
        │                  │                  │                  │
        ▼                  ▼                  ▼                  ▼
  ┌──────────┐       ┌──────────┐       ┌──────────┐       ┌──────────┐
  │  Huginn  │       │  Mimir   │       │  Skald   │       │  Fenrir  │
  │deepseek  │       │qwen2.5:7b│       │llama3.1  │       │qwen2.5:7b│
  │  :16b    │       │          │       │   :8b    │       │          │
  └────┬─────┘       └──────────┘       └──────────┘       └──────────┘
       │
       ▼
  ┌──────────┐
  │Ratatoskr │
  │qwen2.5:3b│
  └──────────┘
```

## All Agents

### Brokkr (Orchestrator)
**Role:** Master orchestrator - breaks down complex tasks into subtasks

| Property | Value |
|----------|-------|
| **Model** | `qwen2.5-coder:14b-instruct-q4_K_M` |
| **VRAM** | 10.0 GB |
| **Can Delegate** | Yes → All agents |
| **Priority** | 0 (highest) |
| **Max Iterations** | 30 |

**Tools:** `read_file`, `list_directory`, `search_codebase`, `delegate`

**When to use:**
- Complex multi-step projects
- Tasks requiring planning and coordination
- When you want automatic task decomposition

**Example:**
```bash
sindri orchestrate "Build a REST API with authentication"
# Brokkr plans, then delegates:
# → Huginn for implementation
# → Skald for tests
# → Mimir for review
```

---

### Huginn (Coder)
**Role:** Code implementation specialist - writes production code

| Property | Value |
|----------|-------|
| **Model** | `deepseek-coder-v2:16b-instruct-q4_K_M` |
| **VRAM** | 10.0 GB |
| **Can Delegate** | Yes → Ratatoskr |
| **Priority** | 1 |
| **Max Iterations** | 40 |

**Tools:** `read_file`, `write_file`, `edit_file`, `shell`, `delegate`

**When to use:**
- Writing new functions, classes, modules
- Implementing features from specifications
- Complex algorithmic work

**Example:**
```bash
# Direct invocation (no orchestration)
sindri run "Implement OAuth2 authentication flow" --model deepseek-coder-v2:16b
```

**Mythology:** In Norse myth, Huginn ("thought") is one of Odin's ravens that flies around the world gathering information.

---

### Mimir (Reviewer)
**Role:** Code reviewer and quality checker

| Property | Value |
|----------|-------|
| **Model** | `qwen2.5-coder:7b-instruct-q4_K_M` |
| **VRAM** | 5.0 GB |
| **Can Delegate** | No |
| **Priority** | 1 |
| **Max Iterations** | 20 |

**Tools:** `read_file`, `list_directory`, `shell`

**When to use:**
- Code review and quality checking
- Security analysis
- Best practices validation

**Example:**
```python
# Delegated from Brokkr:
await delegate(
    agent="mimir",
    task="Review the authentication module for security issues"
)
```

**Mythology:** Mimir was the wisest of the Aesir gods, keeper of the Well of Wisdom.

---

### Ratatoskr (Executor)
**Role:** Fast executor for simple, well-defined tasks

| Property | Value |
|----------|-------|
| **Model** | `qwen2.5-coder:3b-instruct-q8_0` |
| **VRAM** | 3.0 GB |
| **Can Delegate** | No |
| **Priority** | 2 |
| **Max Iterations** | 15 |

**Tools:** `shell`, `read_file`, `write_file`

**When to use:**
- Simple file operations
- Running tests
- Basic shell commands
- Quick fixes

**Example:**
```python
# Huginn delegates simple file ops to Ratatoskr:
await delegate(
    agent="ratatoskr",
    task="Create __init__.py with imports"
)
```

**Mythology:** Ratatoskr is the squirrel that runs up and down Yggdrasil carrying messages.

---

### Skald (Test Writer)
**Role:** Test generation specialist

| Property | Value |
|----------|-------|
| **Model** | `llama3.1:8b-instruct-q8_0` |
| **VRAM** | 5.0 GB |
| **Can Delegate** | No |
| **Priority** | 1 |
| **Max Iterations** | 30 |

**Tools:** `read_file`, `write_file`, `edit_file`, `shell`

**When to use:**
- Writing unit tests
- Integration tests
- Test fixtures and mocks

**Example:**
```bash
sindri run "Write pytest tests for the auth module" --model llama3.1:8b
```

**Mythology:** Skalds were Norse poets who composed and recited epic poetry.

---

### Fenrir (SQL Specialist)
**Role:** SQL and database operations

| Property | Value |
|----------|-------|
| **Model** | `qwen2.5-coder:7b-instruct-q4_K_M` |
| **VRAM** | 5.0 GB |
| **Can Delegate** | No |
| **Priority** | 1 |
| **Max Iterations** | 25 |

**Tools:** `read_file`, `write_file`, `shell`

**When to use:**
- Writing SQL queries
- Database migrations
- Schema design

**Example:**
```python
await delegate(
    agent="fenrir",
    task="Create migration to add user_sessions table"
)
```

**Mythology:** Fenrir is the monstrous wolf, son of Loki.

---

### Odin (Deep Reasoner)
**Role:** Complex reasoning and algorithm design

| Property | Value |
|----------|-------|
| **Model** | `deepseek-r1:8b` |
| **VRAM** | 5.0 GB |
| **Can Delegate** | No |
| **Priority** | 1 |
| **Max Iterations** | 40 |

**Tools:** `read_file`, `list_directory`

**When to use:**
- Complex algorithm design
- Architecture decisions
- Mathematical/logical problems

**Example:**
```python
await delegate(
    agent="odin",
    task="Design an efficient caching strategy for this API"
)
```

**Mythology:** Odin is the All-Father, god of wisdom, war, and poetry.

---

## Delegation Protocol

Agents use the `delegate` tool to spawn child tasks:

```python
await delegate(
    agent="target_agent",     # Which agent to delegate to
    task="Task description",  # Clear, specific task
    context={                 # Optional context
        "files": ["main.py"],
        "constraints": ["use asyncio"]
    }
)
```

### Delegation Rules

1. **Parent waits** - Parent enters `WAITING` status while child runs
2. **Priority inheritance** - Children get `parent_priority + 1` (lower priority)
3. **Context passing** - Child receives parent's context + delegation context
4. **Result bubbling** - Child result is passed back to parent

### Example Delegation Chain

```
Brokkr receives: "Build a web API with tests"
   │
   ├─→ Delegates to Huginn: "Implement FastAPI endpoints"
   │      │
   │      └─→ Delegates to Ratatoskr: "Create __init__.py"
   │      └─→ Ratatoskr completes
   │   └─→ Huginn resumes and completes
   │
   ├─→ Delegates to Skald: "Write tests for the API"
   │   └─→ Skald completes
   │
   └─→ Brokkr verifies all complete
```

## Choosing the Right Agent

| Task Type | Recommended Agent | Why |
|-----------|------------------|-----|
| Complex project | Brokkr | Breaks down and coordinates |
| New feature | Huginn | Best code generation |
| Bug fix | Huginn or Mimir | Huginn for fix, Mimir for analysis |
| Write tests | Skald | Specialized test generation |
| SQL queries | Fenrir | SQL expertise |
| Algorithm design | Odin | Deep reasoning capability |
| Simple file ops | Ratatoskr | Fast, low VRAM |
| Code review | Mimir | Quality and security focus |

## Model Selection

### By VRAM Availability

| Available VRAM | Recommended Agents |
|----------------|-------------------|
| 4-6 GB | Ratatoskr only |
| 6-10 GB | Mimir, Fenrir, Skald, Odin |
| 10-14 GB | Brokkr or Huginn (one at a time) |
| 14+ GB | Full orchestration with all agents |

### By Task Complexity

| Complexity | Approach |
|------------|----------|
| Simple | Direct `sindri run` with small model |
| Medium | Single specialized agent |
| Complex | Full `sindri orchestrate` with Brokkr |

## Customizing Agents

Edit `sindri/agents/registry.py`:

```python
AGENTS = {
    "brokkr": AgentDefinition(
        name="brokkr",
        role="Master orchestrator",
        model="qwen2.5-coder:14b-instruct-q4_K_M",
        system_prompt=BROKKR_PROMPT,  # Edit in prompts.py
        tools=["read_file", "delegate"],
        can_delegate=True,
        delegate_to=["huginn", "mimir"],  # Add/remove delegates
        estimated_vram_gb=10.0,
        priority=0,
        max_iterations=30,  # Increase for complex tasks
    )
}
```

### Custom Agent Example

```python
# Add a documentation specialist
AGENTS["munin"] = AgentDefinition(
    name="munin",
    role="Documentation writer",
    model="llama3.1:8b-instruct-q8_0",
    system_prompt=MUNIN_PROMPT,
    tools=["read_file", "write_file"],
    can_delegate=False,
    estimated_vram_gb=5.0,
    priority=1,
    max_iterations=25,
)
```

## Agent Performance Tips

1. **Start small** - Use `sindri run` with single agent for simple tasks
2. **Orchestrate complex** - Use `sindri orchestrate` for multi-step projects
3. **Monitor VRAM** - Use TUI to watch model loading
4. **Adjust iterations** - Increase `max_iterations` for complex tasks
5. **Specialize** - Create custom agents for your domain

## See Also

- [CONFIGURATION.md](CONFIGURATION.md) - Agent configuration options
- [README.md](../README.md) - Usage examples
