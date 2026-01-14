# Sindri Agent Quick Reference

## Available Agents (7 Total)

### Core Orchestration Agents

#### 🔨 Brokkr - Master Orchestrator
```yaml
Model: qwen2.5-coder:14b
Role: Breaks down complex tasks into subtasks
Tools: read_file, delegate
Can Delegate: ✓ (to all agents)
VRAM: 9.0 GB
Max Iterations: 20
Use For: Complex multi-step projects, coordination
```

**When to use**: Any complex task requiring multiple specialists.

**Example tasks**:
- "Create a web application with authentication"
- "Build a data pipeline with tests"
- "Refactor the codebase and add documentation"

---

#### 🧠 Odin - Deep Reasoning Specialist
```yaml
Model: deepseek-r1:8b
Role: Deep planning, architectural decisions, trade-off analysis
Tools: read_file, delegate
Can Delegate: ✓ (to huginn, skald, fenrir)
VRAM: 6.0 GB
Max Iterations: 15
Temperature: 0.7
Use For: Complex planning, architecture, design decisions
```

**When to use**: Tasks requiring careful thought and planning.

**Example tasks**:
- "Design a microservices architecture"
- "Analyze trade-offs between SQL and NoSQL"
- "Plan a migration strategy from monolith to services"

**Special**: Uses `<think>` tags to show reasoning process.

---

### Implementation Agents

#### ⚡ Huginn - Code Implementation
```yaml
Model: qwen2.5-coder:7b
Role: Write and modify code
Tools: read_file, write_file, edit_file, shell, delegate
Can Delegate: ✓ (to ratatoskr, skald)
VRAM: 5.0 GB
Max Iterations: 30
Use For: Writing new code, implementing features
```

**When to use**: Code implementation tasks.

**Example tasks**:
- "Implement user authentication with JWT"
- "Add error handling to the API"
- "Create a CLI tool for data processing"

---

#### 🧪 Skald - Test Writer
```yaml
Model: qwen2.5-coder:7b
Role: Write comprehensive tests, ensure quality
Tools: read_file, write_file, shell
Can Delegate: ✗
VRAM: 5.0 GB
Max Iterations: 25
Use For: Test generation, quality assurance
```

**When to use**: Need tests for code.

**Example tasks**:
- "Write unit tests for the authentication module"
- "Create integration tests for the API"
- "Generate test fixtures for the database"

---

#### 🐺 Fenrir - SQL Specialist
```yaml
Model: sqlcoder:7b
Role: SQL queries, database design, data operations
Tools: read_file, write_file, shell
Can Delegate: ✗
VRAM: 5.0 GB
Max Iterations: 20
Use For: Database work, SQL queries, data analysis
```

**When to use**: Anything involving SQL or databases.

**Example tasks**:
- "Design a database schema for an e-commerce site"
- "Write an optimized query for user analytics"
- "Create a migration to add indexing"

---

### Support Agents

#### 📖 Mimir - Code Reviewer
```yaml
Model: llama3.1:8b
Role: Review code quality, find bugs, suggest improvements
Tools: read_file, shell
Can Delegate: ✗
VRAM: 5.0 GB
Max Iterations: 20
Use For: Code review, quality checks
```

**When to use**: Review existing code.

**Example tasks**:
- "Review the authentication code for security issues"
- "Check the API endpoints for bugs"
- "Suggest improvements to this module"

---

#### 🐿️ Ratatoskr - Swift Executor
```yaml
Model: qwen2.5:3b-instruct-q8_0
Role: Execute simple, fast operations
Tools: shell, read_file, write_file
Can Delegate: ✗
VRAM: 3.0 GB
Max Iterations: 10
Use For: Simple file operations, quick tasks
```

**When to use**: Simple, single-step tasks.

**Example tasks**:
- "Create a file with hello world"
- "Run the tests"
- "List all Python files"

---

## Delegation Chains

```
Brokkr (Orchestrator)
  ├─> Odin (Reasoning)
  │     ├─> Huginn (Code)
  │     ├─> Skald (Tests)
  │     └─> Fenrir (SQL)
  ├─> Huginn (Code)
  │     ├─> Skald (Tests)
  │     └─> Ratatoskr (Executor)
  ├─> Mimir (Review)
  ├─> Skald (Tests)
  ├─> Fenrir (SQL)
  └─> Ratatoskr (Executor)
```

## Common Workflows

### Full Stack Feature
```
Brokkr receives: "Add user profile feature"
  ├─> Odin plans architecture
  ├─> Huginn implements backend
  │     └─> Skald writes backend tests
  ├─> Fenrir creates database schema
  ├─> Huginn implements frontend
  │     └─> Skald writes frontend tests
  └─> Mimir reviews all code
```

### Database-Heavy Task
```
Brokkr receives: "Build analytics dashboard"
  ├─> Fenrir designs database schema
  ├─> Fenrir writes aggregation queries
  ├─> Huginn creates API endpoints
  │     └─> Skald tests API
  └─> Mimir reviews queries for performance
```

### Quick Task (Direct)
```
# Use single agent directly
sindri run "Format all Python files" --model qwen2.5-coder:7b
```

## CLI Commands

### List All Agents
```bash
sindri agents
```
Shows table with all agents, models, VRAM, and capabilities.

### Orchestrate (Hierarchical)
```bash
sindri orchestrate "Build a REST API with tests"
```
Brokkr coordinates multiple agents.

### Direct Agent (Single)
```bash
sindri run "Simple task" --model qwen2.5-coder:7b
```
Use one agent directly.

### View Sessions
```bash
sindri sessions
```
List recent work sessions.

## Choosing the Right Agent

| If you need... | Use... |
|----------------|--------|
| Complex multi-step task | Brokkr (orchestrates) |
| Deep architectural planning | Odin (reasons) |
| Code implementation | Huginn (codes) |
| Test generation | Skald (tests) |
| SQL/database work | Fenrir (SQL) |
| Code review | Mimir (reviews) |
| Simple file operation | Ratatoskr (executes) |

## VRAM Planning

| Scenario | Agents | Total VRAM |
|----------|--------|------------|
| Big orchestration | Brokkr | 9 GB |
| Planning → Code | Odin → Huginn | 6 + 5 = 11 GB |
| Code + Review | Huginn + Mimir | 5 + 5 = 10 GB |
| SQL + Code | Fenrir + Huginn | 5 + 5 = 10 GB |
| Multiple small | 3x Ratatoskr | 3 + 3 + 3 = 9 GB |

**Available**: 14 GB (16 GB total - 2 GB reserved)

## Tips

1. **Let Brokkr orchestrate** complex tasks - it knows which agents to use
2. **Use Odin for planning** before implementation
3. **Skald + Huginn** work great together for TDD
4. **Fenrir is specialized** - use it for SQL over general agents
5. **Ratatoskr is fast** for simple operations
6. **Mimir provides** good code review feedback

## Model Capabilities

All agents now support **text-based tool calling** as fallback:
- Works even if model doesn't natively support function calling
- Automatically detects and parses JSON tool calls from text
- Transparent to the agent - same interface

---

**Quick Start**: Try `sindri agents` to see all available agents!
