# Phase 1: Foundation - Basic Agent Loop

You are building **Sindri**, a local-first LLM orchestration CLI. This is Phase 1: establishing the foundation.

## Phase 1 Objectives

Build a working single-agent loop that can:
1. Accept a task via CLI
2. Call Ollama with the task
3. Parse and execute tool calls
4. Iterate until completion
5. Persist state to SQLite

## Directory Structure to Create

```
sindri/
├── pyproject.toml
├── README.md
├── sindri/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── loop.py
│   │   ├── completion.py
│   │   └── context.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── models.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── filesystem.py
│   │   └── shell.py
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── state.py
│   └── prompts/
│       ├── __init__.py
│       └── system.py
└── tests/
    ├── __init__.py
    ├── test_tools.py
    ├── test_loop.py
    └── test_ollama.py
```

## Implementation Details

### pyproject.toml

```toml
[project]
name = "sindri"
version = "0.1.0"
description = "Local LLM orchestration - forge code with Ollama"
requires-python = ">=3.11"
dependencies = [
    "ollama>=0.4.0",
    "click>=8.0.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
    "aiofiles>=24.0.0",
    "structlog>=24.0.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]
tui = ["textual>=0.89.0"]

[project.scripts]
sindri = "sindri.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Core Loop (sindri/core/loop.py)

```python
"""
The Ralph-style agent loop - heart of Sindri.

Iterates until:
- Completion marker detected
- Max iterations reached
- Unrecoverable error
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
import structlog

from sindri.llm.client import OllamaClient
from sindri.tools.registry import ToolRegistry
from sindri.persistence.state import SessionState
from sindri.core.completion import CompletionDetector
from sindri.core.context import ContextBuilder

log = structlog.get_logger()

@dataclass
class LoopConfig:
    max_iterations: int = 50
    completion_marker: str = "<sindri:complete/>"
    stuck_threshold: int = 3
    checkpoint_interval: int = 5

@dataclass
class LoopResult:
    success: bool
    iterations: int
    reason: str = ""
    final_output: str = ""

class AgentLoop:
    """Core iteration loop."""
    
    def __init__(
        self,
        client: OllamaClient,
        tools: ToolRegistry,
        state: SessionState,
        config: LoopConfig = None
    ):
        self.client = client
        self.tools = tools
        self.state = state
        self.config = config or LoopConfig()
        self.completion = CompletionDetector()
        self.context = ContextBuilder()
    
    async def run(self, task: str, model: str) -> LoopResult:
        """Execute the loop until completion."""
        
        session = await self.state.create_session(task)
        recent_responses = []
        
        for iteration in range(self.config.max_iterations):
            log.info("iteration_start", iteration=iteration + 1)
            
            # 1. Build messages
            messages = self.context.build(
                task=task,
                history=session.turns,
                tools=self.tools.get_schemas()
            )
            
            # 2. Call LLM
            response = await self.client.chat(
                model=model,
                messages=messages,
                tools=self.tools.get_schemas()
            )
            
            assistant_content = response.message.content
            log.info("llm_response", content=assistant_content[:200])
            
            # 3. Check completion
            if self.completion.is_complete(assistant_content):
                await self.state.complete_session(session.id)
                return LoopResult(
                    success=True,
                    iterations=iteration + 1,
                    reason="completion_marker",
                    final_output=assistant_content
                )
            
            # 4. Check stuck
            recent_responses.append(assistant_content)
            if len(recent_responses) > self.config.stuck_threshold:
                recent_responses.pop(0)
            
            if self._is_stuck(recent_responses):
                log.warning("stuck_detected")
                # Add nudge
                session.add_turn("user", "You seem stuck. Try a different approach or ask for clarification.")
                recent_responses.clear()
                continue
            
            # 5. Execute tool calls
            tool_results = []
            if response.message.tool_calls:
                for call in response.message.tool_calls:
                    result = await self.tools.execute(
                        call.function.name,
                        call.function.arguments
                    )
                    tool_results.append({
                        "tool": call.function.name,
                        "result": result.output if result.success else f"ERROR: {result.error}"
                    })
            
            # 6. Update session
            session.add_turn("assistant", assistant_content, tool_calls=response.message.tool_calls)
            if tool_results:
                session.add_turn("tool", str(tool_results))
            
            # 7. Checkpoint
            if iteration % self.config.checkpoint_interval == 0:
                await self.state.save_session(session)
        
        return LoopResult(
            success=False,
            iterations=self.config.max_iterations,
            reason="max_iterations_reached"
        )
    
    def _is_stuck(self, responses: list[str]) -> bool:
        """Detect if we're getting the same response repeatedly."""
        if len(responses) < self.config.stuck_threshold:
            return False
        return len(set(responses)) == 1
```

### Ollama Client (sindri/llm/client.py)

```python
"""Async Ollama client wrapper."""

import ollama
from dataclasses import dataclass
from typing import AsyncIterator, Optional
import asyncio

@dataclass
class Message:
    role: str
    content: str
    tool_calls: Optional[list] = None

@dataclass
class Response:
    message: Message
    model: str
    done: bool

class OllamaClient:
    """Wrapper around Ollama with async support."""
    
    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host
        self._client = ollama.Client(host=host)
        self._async_client = ollama.AsyncClient(host=host)
    
    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] = None
    ) -> Response:
        """Send chat request to Ollama."""
        
        kwargs = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        
        response = await self._async_client.chat(**kwargs)
        
        return Response(
            message=Message(
                role=response["message"]["role"],
                content=response["message"].get("content", ""),
                tool_calls=response["message"].get("tool_calls")
            ),
            model=response["model"],
            done=response.get("done", True)
        )
    
    async def stream(
        self,
        model: str,
        messages: list[dict]
    ) -> AsyncIterator[str]:
        """Stream response tokens."""
        
        async for chunk in await self._async_client.chat(
            model=model,
            messages=messages,
            stream=True
        ):
            if chunk.get("message", {}).get("content"):
                yield chunk["message"]["content"]
    
    def list_models(self) -> list[str]:
        """List available models."""
        response = self._client.list()
        return [m["name"] for m in response.get("models", [])]
```

### Tool Base (sindri/tools/base.py)

```python
"""Tool base class and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

class Tool(ABC):
    """Base class for all tools."""
    
    name: str
    description: str
    parameters: dict  # JSON Schema
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        pass
    
    def get_schema(self) -> dict:
        """Get Ollama-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
```

### CLI (sindri/cli.py)

```python
"""Sindri CLI - forge code with local LLMs."""

import asyncio
import click
from rich.console import Console
from rich.panel import Panel

from sindri.core.loop import AgentLoop, LoopConfig
from sindri.llm.client import OllamaClient
from sindri.tools.registry import ToolRegistry
from sindri.persistence.state import SessionState

console = Console()

@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Sindri - Local LLM Orchestration"""
    pass

@cli.command()
@click.argument("task")
@click.option("--model", "-m", default="qwen2.5-coder:14b", help="Ollama model to use")
@click.option("--max-iter", default=50, help="Maximum iterations")
def run(task: str, model: str, max_iter: int):
    """Run a task with Sindri."""
    
    console.print(Panel(f"[bold blue]Task:[/] {task}", title="Sindri"))
    
    async def execute():
        client = OllamaClient()
        tools = ToolRegistry.default()
        state = SessionState()
        config = LoopConfig(max_iterations=max_iter)
        
        loop = AgentLoop(client, tools, state, config)
        
        with console.status("[bold green]Forging..."):
            result = await loop.run(task, model)
        
        if result.success:
            console.print(f"[green]✓ Completed in {result.iterations} iterations[/]")
        else:
            console.print(f"[red]✗ {result.reason} after {result.iterations} iterations[/]")
        
        return result
    
    asyncio.run(execute())

@cli.command()
@click.argument("session_id")
def resume(session_id: str):
    """Resume an interrupted session."""
    console.print(f"Resuming session {session_id}...")
    # TODO: Implement resume logic

@cli.command()
def list():
    """List recent sessions."""
    # TODO: Implement list logic
    console.print("Recent sessions:")

if __name__ == "__main__":
    cli()
```

## Testing

After implementing, verify with:

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Manual test
sindri run "Create a file called hello.py that prints 'Hello from Sindri!'"
```

## Completion Criteria

Phase 1 is complete when:

1. ✅ All files created per structure above
2. ✅ `pip install -e .` succeeds
3. ✅ `sindri run "create hello.py printing hello world"` works
4. ✅ Tool execution (file creation, shell) works
5. ✅ State persists to SQLite
6. ✅ Tests pass

When all criteria met, output: `<promise>PHASE1_COMPLETE</promise>`

## Iteration Instructions

Work step by step:
1. Create pyproject.toml first
2. Create directory structure
3. Implement persistence (database.py, state.py)
4. Implement Ollama client
5. Implement tools
6. Implement core loop
7. Wire up CLI
8. Test everything
9. Fix any issues

If stuck, describe the blocker clearly.
