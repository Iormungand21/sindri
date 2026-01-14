# Sindri Python API Reference

**Use Sindri programmatically in your Python applications**

---

## Overview

While Sindri is primarily a CLI tool, you can use its core components as a Python library for custom integrations, automation, and tooling.

---

## Installation

```bash
pip install -e ".[dev]"  # Install in development mode
```

---

## Quick Start

```python
import asyncio
from sindri.core.orchestrator import Orchestrator
from sindri.config import Config

async def main():
    # Create orchestrator with default config
    config = Config()
    orchestrator = Orchestrator(config)

    # Execute a task
    result = await orchestrator.execute_task(
        description="Create a hello.py file",
        agent="brokkr"
    )

    print(f"Success: {result.success}")
    print(f"Output: {result.output}")

    # Cleanup
    await orchestrator.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Core Components

### Orchestrator

**Location:** `sindri.core.orchestrator`

Main entry point for task execution.

```python
from sindri.core.orchestrator import Orchestrator
from sindri.config import Config

config = Config(
    ollama_host="http://localhost:11434",
    total_vram_gb=16.0,
    data_dir="~/.sindri"
)

orchestrator = Orchestrator(config)
```

#### Methods

##### `execute_task()`

Execute a task with specified agent.

```python
async def execute_task(
    self,
    description: str,
    agent: str = "brokkr",
    max_iterations: Optional[int] = None
) -> TaskResult:
    """Execute task and return result.

    Args:
        description: Task description
        agent: Agent to use (default: brokkr)
        max_iterations: Override agent's max iterations

    Returns:
        TaskResult with success status and output

    Raises:
        VRAMError: Not enough VRAM for model
        ModelNotFoundError: Model not available in Ollama
    """
```

**Example:**
```python
result = await orchestrator.execute_task(
    description="Write a fibonacci function",
    agent="huginn",
    max_iterations=30
)

if result.success:
    print(f"Task completed: {result.output}")
else:
    print(f"Task failed: {result.error}")
```

##### `shutdown()`

Clean shutdown - unload models and close database.

```python
await orchestrator.shutdown()
```

---

### Configuration

**Location:** `sindri.config`

Pydantic-based configuration with validation.

```python
from sindri.config import Config

# From file
config = Config.from_file("sindri.toml")

# From dict
config = Config(
    ollama_host="http://192.168.1.100:11434",
    total_vram_gb=12.0,
    reserve_vram_gb=1.0,
    max_iterations=50
)

# Access properties
print(config.ollama_host)  # http://localhost:11434
print(config.available_vram)  # 11.0 (12.0 - 1.0)
```

#### Config Fields

```python
@dataclass
class Config:
    # General
    data_dir: str = "~/.sindri"
    project_dir: str = "."
    ollama_host: str = "http://localhost:11434"

    # Hardware
    total_vram_gb: float = 16.0
    reserve_vram_gb: float = 2.0

    # Execution
    max_iterations: int = 50
    checkpoint_interval: int = 5

    # Memory
    episodic_limit: int = 5
    semantic_limit: int = 10
    max_context_tokens: int = 32768

    # TUI
    theme: str = "dark"
    refresh_rate_ms: int = 100
```

---

### Task Management

**Location:** `sindri.core.tasks`

Task data models and status tracking.

```python
from sindri.core.tasks import Task, TaskStatus, TaskPriority

# Create a task
task = Task(
    id="task-123",
    description="Create hello.py",
    assigned_agent="brokkr",
    status=TaskStatus.PENDING,
    priority=TaskPriority.NORMAL
)

# Check status
if task.status == TaskStatus.COMPLETE:
    print(f"Result: {task.result}")
elif task.status == TaskStatus.FAILED:
    print(f"Error: {task.error}")
```

#### Task Model

```python
@dataclass
class Task:
    id: str
    description: str
    assigned_agent: str
    status: TaskStatus
    priority: TaskPriority
    parent_id: Optional[str] = None
    session_id: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    cancel_requested: bool = False
```

#### TaskStatus Enum

```python
class TaskStatus(Enum):
    PENDING = "pending"       # Ready to run
    RUNNING = "running"       # Currently executing
    WAITING = "waiting"       # Waiting for child task
    COMPLETE = "complete"     # Successfully finished
    FAILED = "failed"         # Error occurred
    CANCELLED = "cancelled"   # Cancelled by user
```

---

### Agents

**Location:** `sindri.agents.registry`

Agent definitions and capabilities.

```python
from sindri.agents.registry import AGENTS

# List all agents
for name, agent in AGENTS.items():
    print(f"{name}: {agent.role}")

# Get specific agent
brokkr = AGENTS["brokkr"]
print(f"Model: {brokkr.model}")
print(f"Tools: {brokkr.tools}")
print(f"Can delegate to: {brokkr.delegate_to}")
```

#### AgentDefinition

```python
@dataclass
class AgentDefinition:
    name: str
    role: str
    model: str
    system_prompt: str
    tools: List[str]
    can_delegate: bool
    delegate_to: List[str]
    estimated_vram_gb: float
    priority: int
    max_iterations: int
```

---

### Tools

**Location:** `sindri.tools`

Create custom tools for agents.

```python
from sindri.tools.base import Tool, ToolResult

class MyCustomTool(Tool):
    @property
    def schema(self) -> dict:
        """Tool schema for LLM."""
        return {
            "name": "my_tool",
            "description": "Does something useful",
            "parameters": {
                "type": "object",
                "properties": {
                    "param": {"type": "string", "description": "A parameter"}
                },
                "required": ["param"]
            }
        }

    async def execute(self, param: str) -> ToolResult:
        """Execute the tool."""
        try:
            result = do_something(param)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

# Register tool
from sindri.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(MyCustomTool())
```

---

### Memory System

**Location:** `sindri.memory.system`

Access memory for context retrieval.

```python
from sindri.memory.system import MuninnMemory
from sindri.config import Config

config = Config()
memory = MuninnMemory(config)

# Index a project
await memory.index_project("/path/to/project")

# Get context for a task
context = await memory.get_context(
    task_description="Add authentication",
    working_memory=recent_messages,
    max_tokens=32768
)

# Context includes:
# - Working memory (recent conversation)
# - Episodic memory (past task summaries)
# - Semantic memory (relevant code chunks)
```

---

### Event System

**Location:** `sindri.core.events`

Subscribe to orchestrator events.

```python
from sindri.core.events import EventBus, EventType, Event

# Create event bus
event_bus = EventBus()

# Subscribe to events
def on_task_created(event: Event):
    print(f"Task created: {event.data['task_id']}")

def on_agent_output(event: Event):
    print(f"Agent said: {event.data['output']}")

event_bus.subscribe(EventType.TASK_CREATED, on_task_created)
event_bus.subscribe(EventType.AGENT_OUTPUT, on_agent_output)

# Pass to orchestrator
orchestrator = Orchestrator(config, event_bus=event_bus)

# Events will be emitted during execution
await orchestrator.execute_task("Create hello.py")
```

#### Event Types

```python
class EventType(Enum):
    TASK_CREATED = "task_created"
    TASK_STATUS_CHANGED = "task_status_changed"
    ITERATION_START = "iteration_start"
    AGENT_OUTPUT = "agent_output"
    TOOL_CALLED = "tool_called"
    ERROR = "error"
```

---

### Session Persistence

**Location:** `sindri.persistence.state`

Access session history and state.

```python
from sindri.persistence.state import SessionState
from sindri.config import Config

config = Config()
state = SessionState(config)

# Create session
session = await state.create_session(
    description="Create auth module",
    model="qwen2.5-coder:14b"
)

# Add conversation turns
session.add_turn("user", "Create user model")
session.add_turn("assistant", "I'll create a User model...")
session.add_turn("tool", "File created successfully", tool_call_id="call_1")

# Save session
await state.save_session(session)

# Load session later
loaded = await state.load_session(session.id)

# List all sessions
sessions = await state.list_sessions(limit=10)
for s in sessions:
    print(f"{s.id}: {s.description} - {s.status}")
```

---

## Advanced Usage

### Custom Agent Loop

Create your own agent loop with custom behavior:

```python
from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.llm.client import OllamaClient
from sindri.agents.registry import AGENTS

client = OllamaClient("http://localhost:11434")
loop = HierarchicalAgentLoop(
    llm=client,
    state=state,
    event_bus=event_bus,
    scheduler=scheduler,
    delegation=delegation_manager,
    memory=memory
)

# Run custom task
task = Task(
    id="custom-1",
    description="Custom task",
    assigned_agent="huginn",
    status=TaskStatus.PENDING,
    priority=TaskPriority.HIGH
)

result = await loop.run(task)
```

---

### Batch Processing

Process multiple tasks:

```python
from sindri.core.orchestrator import Orchestrator

orchestrator = Orchestrator(config)

tasks = [
    "Create models.py with User model",
    "Create routes.py with auth routes",
    "Write tests for auth module"
]

results = []
for task_desc in tasks:
    result = await orchestrator.execute_task(task_desc)
    results.append(result)

# Check results
for i, result in enumerate(results):
    status = "✓" if result.success else "✗"
    print(f"{status} Task {i+1}: {tasks[i]}")
```

---

### Custom Configuration

Programmatic configuration:

```python
from pathlib import Path
from sindri.config import Config

# Custom paths
config = Config(
    data_dir=Path.home() / ".my_app" / "sindri",
    project_dir=Path.cwd(),
    ollama_host="http://gpu-server:11434"
)

# Custom VRAM limits
config.total_vram_gb = 12.0
config.reserve_vram_gb = 1.0

# Custom iteration limits
config.max_iterations = 100

# Use with orchestrator
orchestrator = Orchestrator(config)
```

---

## Error Handling

```python
from sindri.core.orchestrator import Orchestrator
from sindri.errors import (
    VRAMError,
    ModelNotFoundError,
    TaskExecutionError
)

orchestrator = Orchestrator(config)

try:
    result = await orchestrator.execute_task(
        "Complex task",
        agent="huginn"
    )

    if not result.success:
        print(f"Task failed: {result.error}")

except VRAMError as e:
    print(f"Not enough VRAM: {e}")
    # Maybe try with smaller model

except ModelNotFoundError as e:
    print(f"Model not available: {e}")
    # Pull model: ollama pull model-name

except TaskExecutionError as e:
    print(f"Execution error: {e}")
    # Check logs, adjust task

finally:
    await orchestrator.shutdown()
```

---

## Type Hints

Sindri is fully typed for IDE support:

```python
from typing import Optional
from sindri.core.orchestrator import Orchestrator
from sindri.core.tasks import TaskResult
from sindri.config import Config

async def run_task(
    description: str,
    agent: str = "brokkr",
    config: Optional[Config] = None
) -> TaskResult:
    """Run a Sindri task programmatically."""
    if config is None:
        config = Config()

    orchestrator = Orchestrator(config)

    try:
        result: TaskResult = await orchestrator.execute_task(
            description=description,
            agent=agent
        )
        return result
    finally:
        await orchestrator.shutdown()
```

---

## Testing with Sindri

Mock Sindri components in your tests:

```python
import pytest
from unittest.mock import AsyncMock, Mock
from sindri.core.orchestrator import Orchestrator

@pytest.fixture
def mock_orchestrator(monkeypatch):
    """Mock orchestrator for testing."""
    mock = AsyncMock(spec=Orchestrator)

    # Mock successful execution
    mock.execute_task.return_value = Mock(
        success=True,
        output="Task completed"
    )

    return mock

async def test_my_function(mock_orchestrator):
    """Test function that uses Sindri."""
    result = await mock_orchestrator.execute_task("Test task")

    assert result.success
    mock_orchestrator.execute_task.assert_called_once()
```

---

## Examples

### Automation Script

```python
#!/usr/bin/env python3
"""Automate code generation with Sindri."""
import asyncio
from pathlib import Path
from sindri.core.orchestrator import Orchestrator
from sindri.config import Config

async def generate_project(name: str):
    """Generate a new FastAPI project."""
    config = Config(project_dir=Path.cwd() / name)
    orchestrator = Orchestrator(config)

    tasks = [
        "Create main.py with FastAPI app initialization",
        "Create models/ directory with User and Item models",
        "Create routes/ with CRUD endpoints",
        "Create tests/ with API tests",
        "Create README.md with setup instructions"
    ]

    try:
        for task in tasks:
            print(f"▶ {task}")
            result = await orchestrator.execute_task(task)

            if result.success:
                print(f"  ✓ {task}")
            else:
                print(f"  ✗ Failed: {result.error}")
                break
    finally:
        await orchestrator.shutdown()

if __name__ == "__main__":
    project_name = input("Project name: ")
    asyncio.run(generate_project(project_name))
```

---

### CI/CD Integration

```python
"""Run Sindri in CI/CD pipeline."""
import asyncio
import sys
from sindri.core.orchestrator import Orchestrator
from sindri.config import Config

async def ci_task(task: str) -> bool:
    """Execute task in CI environment."""
    config = Config(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434")
    )

    orchestrator = Orchestrator(config)

    try:
        result = await orchestrator.execute_task(task, agent="brokkr")
        return result.success
    finally:
        await orchestrator.shutdown()

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Write unit tests"

    success = asyncio.run(ci_task(task))
    sys.exit(0 if success else 1)
```

---

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System design and patterns
- [AGENTS.md](AGENTS.md) - Agent capabilities
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration options
