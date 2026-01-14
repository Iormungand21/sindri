# Phase 5: Polish & Robustness

Final phase - make Sindri production-ready for daily use.

## Phase 5 Objectives

1. Error recovery and retry logic
2. Session resume after crash
3. Configuration validation
4. Comprehensive logging with structlog
5. Performance profiling
6. Documentation (README, docstrings)
7. Complete test suite
8. Package for distribution

## Components to Complete

```
sindri/
├── core/
│   ├── retry.py            # Retry logic with backoff
│   └── recovery.py         # Crash recovery
├── config.py               # Enhanced config validation
├── logging.py              # Structured logging setup
└── __init__.py             # Version and exports

tests/
├── test_tools.py
├── test_loop.py
├── test_memory.py
├── test_delegation.py
├── test_recovery.py
└── conftest.py             # Shared fixtures

docs/
├── README.md
├── CONFIGURATION.md
├── AGENTS.md
└── TROUBLESHOOTING.md
```

## Implementation Details

### Retry Logic (core/retry.py)

```python
"""Retry logic with exponential backoff."""

import asyncio
from dataclasses import dataclass
from typing import Callable, TypeVar, Optional
from functools import wraps
import structlog

log = structlog.get_logger()

T = TypeVar('T')

@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple = (Exception,)

def with_retry(config: RetryConfig = None):
    """Decorator for retry logic."""
    config = config or RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = min(
                            config.base_delay * (config.exponential_base ** attempt),
                            config.max_delay
                        )
                        log.warning(
                            "retry_attempt",
                            attempt=attempt + 1,
                            max_attempts=config.max_attempts,
                            delay=delay,
                            error=str(e)
                        )
                        await asyncio.sleep(delay)
            
            raise last_exception
        
        return wrapper
    return decorator

class RetryableOllamaClient:
    """Ollama client with automatic retries."""
    
    def __init__(self, client: 'OllamaClient', config: RetryConfig = None):
        self.client = client
        self.config = config or RetryConfig(
            retryable_exceptions=(ConnectionError, TimeoutError)
        )
    
    @with_retry()
    async def chat(self, **kwargs):
        return await self.client.chat(**kwargs)
```

### Crash Recovery (core/recovery.py)

```python
"""Session recovery after crashes."""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import structlog

from sindri.persistence.state import SessionState
from sindri.persistence.database import Database

log = structlog.get_logger()

class RecoveryManager:
    """Manages crash recovery and session restoration."""
    
    def __init__(self, db: Database, state_dir: str = "~/.sindri/state"):
        self.db = db
        self.state_dir = Path(state_dir).expanduser()
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    def save_checkpoint(self, session_id: str, state: dict):
        """Save checkpoint for crash recovery."""
        
        checkpoint_path = self.state_dir / f"{session_id}.checkpoint.json"
        
        checkpoint = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "state": state
        }
        
        # Atomic write
        temp_path = checkpoint_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(checkpoint, indent=2))
        temp_path.rename(checkpoint_path)
        
        log.debug("checkpoint_saved", session_id=session_id)
    
    def has_checkpoint(self, session_id: str) -> bool:
        """Check if session has a recoverable checkpoint."""
        return (self.state_dir / f"{session_id}.checkpoint.json").exists()
    
    def load_checkpoint(self, session_id: str) -> Optional[dict]:
        """Load checkpoint if available."""
        
        checkpoint_path = self.state_dir / f"{session_id}.checkpoint.json"
        
        if not checkpoint_path.exists():
            return None
        
        try:
            data = json.loads(checkpoint_path.read_text())
            log.info(
                "checkpoint_loaded",
                session_id=session_id,
                saved_at=data.get("timestamp")
            )
            return data.get("state")
        except Exception as e:
            log.error("checkpoint_load_failed", error=str(e))
            return None
    
    def clear_checkpoint(self, session_id: str):
        """Remove checkpoint after successful completion."""
        
        checkpoint_path = self.state_dir / f"{session_id}.checkpoint.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            log.debug("checkpoint_cleared", session_id=session_id)
    
    def list_recoverable_sessions(self) -> list[dict]:
        """List all sessions that can be recovered."""
        
        sessions = []
        
        for checkpoint_path in self.state_dir.glob("*.checkpoint.json"):
            try:
                data = json.loads(checkpoint_path.read_text())
                sessions.append({
                    "session_id": data.get("session_id"),
                    "timestamp": data.get("timestamp"),
                    "task": data.get("state", {}).get("task", "Unknown")
                })
            except:
                continue
        
        return sorted(sessions, key=lambda s: s.get("timestamp", ""), reverse=True)
```

### Logging Setup (logging.py)

```python
"""Structured logging configuration."""

import sys
import structlog
from pathlib import Path

def setup_logging(
    level: str = "INFO",
    log_file: str = None,
    json_format: bool = False
):
    """Configure structured logging."""
    
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # File logging
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Add file handler...

def get_logger(name: str = None):
    """Get a configured logger."""
    return structlog.get_logger(name)
```

### Config Validation (config.py)

```python
"""Configuration with validation."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import toml
from pydantic import BaseModel, validator, Field

class ModelConfig(BaseModel):
    """Model configuration."""
    name: str
    vram_gb: float = Field(gt=0, le=24)
    
    @validator('name')
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Model name cannot be empty')
        return v

class AgentConfig(BaseModel):
    """Agent configuration."""
    model: str
    temperature: float = Field(ge=0, le=2, default=0.3)
    max_context_tokens: int = Field(gt=0, default=16384)
    max_iterations: int = Field(gt=0, default=30)

class MemoryConfig(BaseModel):
    """Memory system configuration."""
    episodic_limit: int = Field(gt=0, default=5)
    semantic_limit: int = Field(gt=0, default=10)
    max_context_tokens: int = Field(gt=0, default=16384)

class TUIConfig(BaseModel):
    """TUI configuration."""
    theme: str = "dark"
    refresh_rate_ms: int = Field(gt=0, default=100)

class SindriConfig(BaseModel):
    """Complete Sindri configuration."""
    
    # Paths
    data_dir: str = "~/.sindri"
    project_dir: str = "."
    
    # Ollama
    ollama_host: str = "http://localhost:11434"
    
    # Hardware
    total_vram_gb: float = 16.0
    reserve_vram_gb: float = 2.0
    
    # Models
    models: dict[str, ModelConfig] = {}
    
    # Agents
    agents: dict[str, AgentConfig] = {}
    
    # Memory
    memory: MemoryConfig = MemoryConfig()
    
    # TUI
    tui: TUIConfig = TUIConfig()
    
    # Execution
    default_max_iterations: int = 50
    checkpoint_interval: int = 5
    
    @classmethod
    def load(cls, path: str = None) -> 'SindriConfig':
        """Load configuration from TOML file."""
        
        if path is None:
            # Search order: ./sindri.toml, ~/.sindri/config.toml
            candidates = [
                Path("sindri.toml"),
                Path("~/.sindri/config.toml").expanduser()
            ]
            for candidate in candidates:
                if candidate.exists():
                    path = str(candidate)
                    break
        
        if path and Path(path).exists():
            data = toml.load(path)
            return cls(**data)
        
        return cls()
    
    def save(self, path: str):
        """Save configuration to TOML file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            toml.dump(self.dict(), f)

def validate_config(config: SindriConfig) -> list[str]:
    """Validate configuration and return warnings."""
    
    warnings = []
    
    # Check VRAM
    total_agent_vram = sum(
        config.models.get(a.model, ModelConfig(name=a.model, vram_gb=8)).vram_gb
        for a in config.agents.values()
    )
    available = config.total_vram_gb - config.reserve_vram_gb
    
    if total_agent_vram > available:
        warnings.append(
            f"Total agent VRAM ({total_agent_vram}GB) exceeds available ({available}GB)"
        )
    
    return warnings
```

### Test Suite (tests/)

```python
# tests/conftest.py
"""Shared test fixtures."""

import pytest
import tempfile
from pathlib import Path

@pytest.fixture
def temp_dir():
    """Temporary directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture
def mock_ollama(mocker):
    """Mock Ollama client."""
    mock = mocker.patch('sindri.llm.client.ollama.AsyncClient')
    return mock

@pytest.fixture
def db(temp_dir):
    """Test database."""
    from sindri.persistence.database import Database
    return Database(str(temp_dir / "test.db"))


# tests/test_loop.py
"""Test agent loop."""

import pytest
from sindri.core.loop import AgentLoop, LoopConfig

@pytest.mark.asyncio
async def test_loop_completes_on_marker(mock_ollama, db):
    """Loop should exit when completion marker found."""
    
    mock_ollama.return_value.chat.return_value = {
        "message": {
            "role": "assistant",
            "content": "Done! <sindri:complete/>"
        }
    }
    
    loop = AgentLoop(...)
    result = await loop.run("test task", "test-model")
    
    assert result.success
    assert result.iterations == 1


# tests/test_recovery.py
"""Test crash recovery."""

import pytest
from sindri.core.recovery import RecoveryManager

def test_checkpoint_save_load(temp_dir):
    """Checkpoints should save and load correctly."""
    
    recovery = RecoveryManager(None, str(temp_dir))
    
    state = {"task": "test", "iteration": 5}
    recovery.save_checkpoint("session-123", state)
    
    assert recovery.has_checkpoint("session-123")
    
    loaded = recovery.load_checkpoint("session-123")
    assert loaded == state


# tests/test_memory.py
"""Test memory system."""

import pytest
from sindri.memory.system import MuninnMemory

def test_context_fits_budget(temp_dir):
    """Context should not exceed token budget."""
    
    memory = MuninnMemory(str(temp_dir / "test.db"))
    
    # Create large conversation
    conversation = [
        {"role": "user", "content": "x" * 1000}
        for _ in range(100)
    ]
    
    context = memory.build_context(
        project_id="test",
        current_task="test task",
        conversation=conversation,
        max_tokens=1000
    )
    
    # Verify it fits
    total_tokens = sum(
        memory._count_tokens(m.get("content", ""))
        for m in context
    )
    assert total_tokens <= 1000
```

### Documentation

```markdown
# docs/CONFIGURATION.md

# Sindri Configuration

Sindri uses TOML for configuration. Config is loaded from:
1. `./sindri.toml` (project-specific)
2. `~/.sindri/config.toml` (user default)

## Example Configuration

\`\`\`toml
# sindri.toml

[general]
data_dir = "~/.sindri"
ollama_host = "http://localhost:11434"
total_vram_gb = 16.0
reserve_vram_gb = 2.0

[models.orchestrator]
name = "qwen2.5:14b-instruct-q4_K_M"
vram_gb = 10.0

[models.coder]
name = "deepseek-coder-v2:16b-instruct-q4_K_M"
vram_gb = 10.0

[agents.brokkr]
model = "orchestrator"
temperature = 0.3
max_context_tokens = 32768
max_iterations = 30

[memory]
episodic_limit = 5
semantic_limit = 10

[tui]
theme = "dark"
\`\`\`
```

### Package Setup

```python
# sindri/__init__.py
"""Sindri - Local LLM Orchestration."""

__version__ = "1.0.0"
__author__ = "Ryan"

from sindri.core.loop import AgentLoop
from sindri.config import SindriConfig

__all__ = ["AgentLoop", "SindriConfig", "__version__"]
```

### CLI Enhancements

```python
# Add to cli.py

@cli.command()
def recover():
    """List and recover interrupted sessions."""
    
    from sindri.core.recovery import RecoveryManager
    
    recovery = RecoveryManager(...)
    sessions = recovery.list_recoverable_sessions()
    
    if not sessions:
        console.print("No recoverable sessions found.")
        return
    
    console.print("[bold]Recoverable Sessions:[/bold]\n")
    for i, s in enumerate(sessions, 1):
        console.print(f"  {i}. [{s['session_id']}] {s['task'][:50]}")
        console.print(f"     Saved: {s['timestamp']}")

@cli.command()
def doctor():
    """Check Sindri installation and configuration."""
    
    from sindri.config import SindriConfig, validate_config
    
    console.print("[bold]Sindri Doctor[/bold]\n")
    
    # Check Ollama
    console.print("Checking Ollama...", end=" ")
    try:
        import ollama
        models = ollama.list()
        console.print(f"[green]OK[/green] ({len(models.get('models', []))} models)")
    except Exception as e:
        console.print(f"[red]FAIL[/red] ({e})")
    
    # Check config
    console.print("Loading config...", end=" ")
    try:
        config = SindriConfig.load()
        console.print("[green]OK[/green]")
        
        warnings = validate_config(config)
        for w in warnings:
            console.print(f"  [yellow]⚠ {w}[/yellow]")
    except Exception as e:
        console.print(f"[red]FAIL[/red] ({e})")
```

## Final Testing Checklist

Run all tests:
```bash
pytest tests/ -v --cov=sindri --cov-report=term-missing
```

Manual testing:
```bash
# Basic task
sindri run "Create hello.py that prints hello world"

# Resume after Ctrl+C
sindri resume <session-id>

# Check recovery
sindri recover

# Validate setup
sindri doctor

# TUI mode
sindri tui "Build a calculator CLI"
```

## Completion Criteria

Phase 5 is complete when:

1. ✅ Retry logic handles transient failures
2. ✅ Sessions resume after crash/interrupt
3. ✅ Config validates and warns about issues
4. ✅ Logging is structured and configurable
5. ✅ Test coverage > 80%
6. ✅ README and docs are complete
7. ✅ `sindri doctor` validates installation
8. ✅ Package installs cleanly with `pip install .`

When ALL criteria met: `<promise>SINDRI_COMPLETE</promise>`

---

🎉 **Congratulations!** Sindri is ready for daily use.

*Forged in the fires of iteration, like Mjolnir in Sindri's forge.*
