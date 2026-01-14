# Phase 2: Hierarchical Agent System

Building on Phase 1's foundation, implement the multi-agent orchestration system.

## Phase 2 Objectives

1. Agent definition system with specialized roles
2. Task queue with dependency resolution
3. Delegation protocol (parent → child tasks)
4. Model manager with VRAM tracking
5. Context passing between agents

## New Components to Add

```
sindri/
├── agents/
│   ├── __init__.py
│   ├── definitions.py      # AgentDefinition dataclass
│   ├── registry.py         # Agent registry
│   ├── orchestrator.py     # Top-level orchestrator agent
│   ├── coder.py           # Code implementation agent
│   ├── reviewer.py        # Code review agent
│   └── executor.py        # Simple command execution agent
├── core/
│   ├── scheduler.py       # Task queue and scheduling
│   ├── delegation.py      # Delegation protocol
│   └── tasks.py           # Task data model
└── llm/
    └── manager.py         # Model loading/VRAM management
```

## Agent Hierarchy

```
                    ┌─────────────────┐
                    │   BROKKR        │  (Orchestrator)
                    │   qwen2.5:14b   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│     HUGINN      │ │     MIMIR       │ │    RATATOSKR    │
│    (Coder)      │ │   (Reviewer)    │ │   (Executor)    │
│  deepseek:16b   │ │  qwen2.5:7b     │ │  qwen2.5:3b     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Implementation Details

### Agent Definition (agents/definitions.py)

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AgentDefinition:
    """Defines an agent's capabilities and configuration."""
    
    name: str                           # Unique identifier (e.g., "brokkr")
    role: str                           # Human description
    model: str                          # Ollama model name
    system_prompt: str                  # Role-specific prompt
    tools: list[str]                    # Allowed tool names
    
    # Context management
    max_context_tokens: int = 16384
    temperature: float = 0.3
    
    # Delegation
    can_delegate: bool = False
    delegate_to: list[str] = field(default_factory=list)
    
    # Resource hints
    estimated_vram_gb: float = 8.0
    priority: int = 1                   # Lower = higher priority
    max_iterations: int = 30
```

### Task Model (core/tasks.py)

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    PLANNING = "planning"
    WAITING = "waiting"       # Waiting on subtask
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"

@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None
    
    description: str = ""
    task_type: str = "general"        # plan, code, review, execute
    assigned_agent: str = "brokkr"
    
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 1
    
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    subtask_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    
    context: dict = field(default_factory=dict)
    result: Optional[dict] = None
    error: Optional[str] = None
```

### Scheduler (core/scheduler.py)

```python
from typing import Optional
from collections import deque
import heapq

from sindri.core.tasks import Task, TaskStatus
from sindri.llm.manager import ModelManager

class TaskScheduler:
    """Priority queue with dependency resolution."""
    
    def __init__(self, model_manager: ModelManager):
        self.tasks: dict[str, Task] = {}
        self.pending: list[tuple[int, str]] = []  # (priority, task_id) heap
        self.model_manager = model_manager
    
    def add_task(self, task: Task) -> str:
        """Add task to scheduler."""
        self.tasks[task.id] = task
        heapq.heappush(self.pending, (task.priority, task.id))
        return task.id
    
    def get_next_task(self) -> Optional[Task]:
        """Get next executable task."""
        
        ready = []
        while self.pending:
            priority, task_id = heapq.heappop(self.pending)
            task = self.tasks.get(task_id)
            
            if not task or task.status != TaskStatus.PENDING:
                continue
            
            if self._dependencies_satisfied(task) and self._resources_available(task):
                return task
            
            ready.append((priority, task_id))
        
        # Put back non-ready tasks
        for item in ready:
            heapq.heappush(self.pending, item)
        
        return None
    
    def _dependencies_satisfied(self, task: Task) -> bool:
        for dep_id in task.depends_on:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETE:
                return False
        return True
    
    def _resources_available(self, task: Task) -> bool:
        from sindri.agents.registry import AGENTS
        agent = AGENTS.get(task.assigned_agent)
        if not agent:
            return False
        return self.model_manager.can_load(agent.model, agent.estimated_vram_gb)
```

### Delegation Protocol (core/delegation.py)

```python
"""Delegation: spawning child tasks from parent agents."""

from dataclasses import dataclass
from typing import Optional

from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.agents.registry import AGENTS

@dataclass
class DelegationRequest:
    target_agent: str
    task_description: str
    context: dict
    constraints: list[str]
    success_criteria: list[str]

class DelegationManager:
    """Handles parent-child task relationships."""
    
    def __init__(self, scheduler: TaskScheduler):
        self.scheduler = scheduler
    
    async def delegate(
        self,
        parent_task: Task,
        request: DelegationRequest
    ) -> Task:
        """Create and schedule a child task."""
        
        agent = AGENTS.get(request.target_agent)
        if not agent:
            raise ValueError(f"Unknown agent: {request.target_agent}")
        
        child = Task(
            parent_id=parent_task.id,
            description=request.task_description,
            task_type=agent.name,
            assigned_agent=request.target_agent,
            priority=parent_task.priority + 1,  # Children are lower priority
            context={
                "parent_context": parent_task.context,
                "delegation": request.context,
                "constraints": request.constraints,
                "success_criteria": request.success_criteria,
            }
        )
        
        # Add to parent's subtasks
        parent_task.subtask_ids.append(child.id)
        parent_task.status = TaskStatus.WAITING
        
        # Schedule child
        self.scheduler.add_task(child)
        
        return child
    
    async def child_completed(self, child: Task):
        """Handle child task completion."""
        
        if not child.parent_id:
            return
        
        parent = self.scheduler.tasks.get(child.parent_id)
        if not parent:
            return
        
        # Check if all children complete
        all_complete = all(
            self.scheduler.tasks[sid].status == TaskStatus.COMPLETE
            for sid in parent.subtask_ids
            if sid in self.scheduler.tasks
        )
        
        if all_complete:
            parent.status = TaskStatus.RUNNING  # Resume parent
```

### Model Manager (llm/manager.py)

```python
"""VRAM-aware model management for AMD 6950XT (16GB)."""

from dataclasses import dataclass
from typing import Optional
import ollama

@dataclass
class LoadedModel:
    name: str
    vram_gb: float
    last_used: float  # timestamp

class ModelManager:
    """Manages model loading with VRAM constraints."""
    
    def __init__(self, total_vram_gb: float = 16.0, reserve_gb: float = 2.0):
        self.total_vram = total_vram_gb
        self.reserve = reserve_gb
        self.available = total_vram_gb - reserve_gb
        self.loaded: dict[str, LoadedModel] = {}
        self._client = ollama.Client()
    
    def can_load(self, model: str, required_vram: float) -> bool:
        """Check if model can be loaded."""
        if model in self.loaded:
            return True
        return self._get_free_vram() >= required_vram
    
    def _get_free_vram(self) -> float:
        used = sum(m.vram_gb for m in self.loaded.values())
        return self.available - used
    
    async def ensure_loaded(self, model: str, required_vram: float) -> bool:
        """Ensure model is loaded, evicting others if needed."""
        
        if model in self.loaded:
            return True
        
        # Need to free up space?
        while self._get_free_vram() < required_vram and self.loaded:
            # Evict least recently used
            lru = min(self.loaded.values(), key=lambda m: m.last_used)
            await self._unload(lru.name)
        
        if self._get_free_vram() < required_vram:
            return False  # Can't fit
        
        # Load the model (Ollama loads on first use)
        self.loaded[model] = LoadedModel(
            name=model,
            vram_gb=required_vram,
            last_used=time.time()
        )
        return True
    
    async def _unload(self, model: str):
        """Unload a model from VRAM."""
        # Ollama doesn't have explicit unload, but we track it
        if model in self.loaded:
            del self.loaded[model]
```

### Hierarchical Loop (Update core/loop.py)

```python
class HierarchicalAgentLoop(AgentLoop):
    """Agent loop with delegation support."""
    
    def __init__(
        self,
        client: OllamaClient,
        tools: ToolRegistry,
        state: SessionState,
        scheduler: TaskScheduler,
        delegation: DelegationManager,
        config: LoopConfig = None
    ):
        super().__init__(client, tools, state, config)
        self.scheduler = scheduler
        self.delegation = delegation
    
    async def run_task(self, task: Task) -> LoopResult:
        """Run a specific task with its assigned agent."""
        
        from sindri.agents.registry import AGENTS
        agent = AGENTS[task.assigned_agent]
        
        # Ensure model is loaded
        await self.scheduler.model_manager.ensure_loaded(
            agent.model, agent.estimated_vram_gb
        )
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        result = await self._run_loop(task, agent)
        
        if result.success:
            task.status = TaskStatus.COMPLETE
            task.completed_at = datetime.now()
            await self.delegation.child_completed(task)
        else:
            task.status = TaskStatus.FAILED
            task.error = result.reason
        
        return result
    
    async def _handle_tool_call(self, call, task: Task):
        """Handle tool call, including delegation."""
        
        if call.function.name == "delegate":
            # Parse delegation request
            args = call.function.arguments
            request = DelegationRequest(
                target_agent=args["agent"],
                task_description=args["task"],
                context=args.get("context", {}),
                constraints=args.get("constraints", []),
                success_criteria=args.get("criteria", [])
            )
            
            child = await self.delegation.delegate(task, request)
            return ToolResult(
                success=True,
                output=f"Delegated to {request.target_agent}: {child.id}"
            )
        
        return await self.tools.execute(call.function.name, call.function.arguments)
```

## Agent Definitions

Create these agents in `agents/registry.py`:

```python
AGENTS = {
    "brokkr": AgentDefinition(
        name="brokkr",
        role="Master orchestrator - breaks down complex tasks",
        model="qwen2.5:14b-instruct-q4_K_M",
        system_prompt=BROKKR_PROMPT,
        tools=["read_file", "list_directory", "search_codebase", "delegate"],
        can_delegate=True,
        delegate_to=["huginn", "mimir", "ratatoskr"],
        estimated_vram_gb=10.0,
        priority=0,
    ),
    
    "huginn": AgentDefinition(
        name="huginn",
        role="Code implementation specialist",
        model="deepseek-coder-v2:16b-instruct-q4_K_M",
        system_prompt=HUGINN_PROMPT,
        tools=["read_file", "write_file", "edit_file", "shell", "delegate"],
        can_delegate=True,
        delegate_to=["ratatoskr"],
        estimated_vram_gb=10.0,
        priority=1,
    ),
    
    "mimir": AgentDefinition(
        name="mimir",
        role="Code reviewer and quality checker",
        model="qwen2.5:7b-instruct-q4_K_M",
        system_prompt=MIMIR_PROMPT,
        tools=["read_file", "list_directory", "shell"],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
    ),
    
    "ratatoskr": AgentDefinition(
        name="ratatoskr",
        role="Fast executor for simple tasks",
        model="qwen2.5:3b-instruct-q8_0",
        system_prompt=RATATOSKR_PROMPT,
        tools=["shell", "read_file", "write_file"],
        can_delegate=False,
        estimated_vram_gb=3.0,
        priority=2,
    ),
}
```

## Testing

1. Test scheduler picks highest priority ready task
2. Test delegation creates child with correct parent
3. Test VRAM manager evicts LRU model
4. Test parent waits for children to complete

## Completion Criteria

Phase 2 is complete when:

1. ✅ Agent definitions for all 4 agents
2. ✅ Task scheduler with dependency resolution
3. ✅ Delegation creates and tracks child tasks
4. ✅ Model manager tracks VRAM usage
5. ✅ Orchestrator can delegate to coder
6. ✅ Tests pass

Test with:
```bash
sindri run "Create a Python package with a CLI that greets the user"
```

This should:
1. Brokkr plans the task
2. Delegates code implementation to Huginn
3. Delegates simple file ops to Ratatoskr
4. Brokkr verifies completion

When complete: `<promise>PHASE2_COMPLETE</promise>`
