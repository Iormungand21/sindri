# Guide: Code Generation with Sindri

**Learn how to effectively generate code with Sindri's agents**

---

## Overview

Sindri excels at generating clean, production-ready code through specialized agents:
- **Huginn** - Complex implementations
- **Brokkr** - Multi-file projects with orchestration
- **Ratatoskr** - Simple, quick code generation

---

## Basic Code Generation

### Single Function

**Task:**
```bash
sindri run "Create a function to validate email addresses using regex"
```

**Result:**
```python
# email_validator.py
import re

def validate_email(email: str) -> bool:
    """Validate email address using regex.

    Args:
        email: Email address to validate

    Returns:
        True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
```

**Tips:**
- Be specific about requirements (regex, validation rules, return type)
- Mention if you want docstrings, type hints
- Specify edge cases to handle

---

### Module Creation

**Task:**
```bash
sindri run "Create a user authentication module with bcrypt password hashing"
```

**What to include in your task:**
- Main functionality (authentication)
- Specific libraries (bcrypt)
- Structure (module vs single file)
- Additional requirements (logging, error handling)

**Expected output:**
```
auth/
├── __init__.py
├── models.py      # User model
├── hash.py        # Password hashing utilities
└── auth.py        # Authentication logic
```

---

## Class Design

### Data Classes

**Task:**
```bash
sindri run "Create a User dataclass with fields: id, username, email, created_at"
```

**Result:**
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class User:
    """User data model."""
    id: int
    username: str
    email: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate fields after initialization."""
        if not self.username:
            raise ValueError("Username cannot be empty")
        if "@" not in self.email:
            raise ValueError("Invalid email format")
```

**Tips:**
- Mention if you want dataclass, Pydantic model, or regular class
- Specify validation requirements
- Include default values if needed

---

### API Clients

**Task:**
```bash
sindri run "Create an async GitHub API client with methods for repos and issues"
```

**Best practices to mention:**
- Async vs sync
- Error handling approach
- Rate limiting
- Authentication method

---

## Multi-File Projects

### REST API

**Use Brokkr for orchestration:**
```bash
sindri tui
```

**Task:**
```
Build a REST API with FastAPI for a todo list application:
- Models: Todo with id, title, description, completed
- Routes: GET /todos, POST /todos, PUT /todos/{id}, DELETE /todos/{id}
- In-memory storage for now
- Include request/response models
```

**Brokkr will:**
1. Plan the project structure
2. Delegate model creation to Huginn
3. Delegate route implementation to Huginn
4. Delegate tests to Skald (if requested)

---

### CLI Application

**Task:**
```
Create a CLI tool using Click with these commands:
- init: Initialize config
- run: Execute task
- status: Show status
Include help text and option validation
```

**Expected structure:**
```
cli/
├── __init__.py
├── main.py       # Click app
├── commands/
│   ├── init.py
│   ├── run.py
│   └── status.py
└── config.py     # Configuration
```

---

## Code Quality

### Type Hints

Include in your task description:
```
Create a cache decorator with full type hints and generic support
```

Sindri will generate:
```python
from typing import TypeVar, Callable, Any
from functools import wraps

T = TypeVar('T')

def cache(func: Callable[..., T]) -> Callable[..., T]:
    """Cache function results."""
    cache_dict: dict[tuple[Any, ...], T] = {}

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache_dict:
            cache_dict[key] = func(*args, **kwargs)
        return cache_dict[key]

    return wrapper
```

---

### Docstrings

**Request explicitly:**
```
Create a binary search function with Google-style docstrings
```

**Result:**
```python
def binary_search(arr: list[int], target: int) -> int:
    """Search for target in sorted array using binary search.

    Args:
        arr: Sorted list of integers to search
        target: Value to find

    Returns:
        Index of target if found, -1 otherwise

    Examples:
        >>> binary_search([1, 2, 3, 4, 5], 3)
        2
        >>> binary_search([1, 2, 3, 4, 5], 6)
        -1
    """
    left, right = 0, len(arr) - 1

    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1
```

---

## Language-Specific Generation

### Python

**Async/Await:**
```
Create an async database connection pool using aiosqlite
```

**Decorators:**
```
Create a retry decorator with exponential backoff for async functions
```

**Context Managers:**
```
Create a context manager for temporary file creation that auto-cleans
```

---

### JavaScript/TypeScript

**Task:**
```
Create a React hook for fetching and caching API data with TypeScript
```

Specify:
- Framework (React, Vue, etc.)
- Language (JS vs TS)
- Style (hooks vs classes)

---

## Advanced Patterns

### Design Patterns

**Factory Pattern:**
```
Create a database connection factory that supports PostgreSQL and MySQL
```

**Observer Pattern:**
```
Implement an event system with subscribe/publish using the Observer pattern
```

**Singleton Pattern:**
```
Create a thread-safe singleton configuration manager
```

---

### Algorithm Implementation

**Use Odin for complex algorithms:**
```bash
sindri run "Implement Dijkstra's shortest path algorithm with heap optimization" --model deepseek-r1:8b
```

Odin provides:
- Step-by-step reasoning
- Complexity analysis
- Edge case handling
- Optimization suggestions

---

## Error Handling

### Include Error Handling

**Task:**
```
Create a file downloader with comprehensive error handling for:
- Network errors
- File system errors
- Invalid URLs
- Timeouts
```

**Result includes:**
```python
class DownloadError(Exception):
    """Base exception for download errors."""
    pass

class NetworkError(DownloadError):
    """Network-related errors."""
    pass

async def download_file(url: str, dest: Path) -> None:
    """Download file with error handling."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                response.raise_for_status()
                dest.write_bytes(await response.read())
    except aiohttp.ClientError as e:
        raise NetworkError(f"Network error: {e}") from e
    except asyncio.TimeoutError as e:
        raise NetworkError("Download timeout") from e
    except OSError as e:
        raise DownloadError(f"File system error: {e}") from e
```

---

## Best Practices

### Clear Requirements

**❌ Vague:**
```
Create authentication
```

**✅ Specific:**
```
Create JWT-based authentication with:
- User registration with email/password
- Login returning access + refresh tokens
- Token validation middleware
- Password hashing with bcrypt
```

---

### Context Provision

**Include relevant context:**
```
Create a database migration for the User model.
The model has: id (int), username (str), email (str), created_at (datetime).
We use Alembic for migrations.
Generate an Alembic migration file.
```

---

### Iterative Refinement

1. **Start simple:**
```
Create a basic TODO CLI
```

2. **Then enhance:**
```
Add persistence using SQLite to the TODO CLI
```

3. **Then test:**
```
Write pytest tests for the TODO CLI
```

---

## Troubleshooting

### Code Not Compiling

**Issue:** Generated code has syntax errors

**Solutions:**
- Specify Python version: "Create with Python 3.11+ syntax"
- Request validation: "Ensure code is syntactically valid"
- Use Mimir for review: Delegate to code review agent

---

### Incomplete Implementation

**Issue:** Missing edge cases or error handling

**Solutions:**
- Be explicit: "Handle all edge cases including empty lists"
- Request tests: "Include test cases for edge cases"
- Increase iterations: `--max-iter 50`

---

### Wrong Libraries

**Issue:** Used wrong library or outdated patterns

**Solutions:**
- Specify library versions: "Use FastAPI 0.100+"
- Mention preferred libraries: "Use httpx for HTTP, not requests"
- Provide examples: "Similar to this pattern: [example]"

---

## Examples by Use Case

### Web Development
```bash
# FastAPI endpoint
sindri run "Create FastAPI endpoint POST /users with Pydantic validation"

# Django model
sindri run "Create Django model for BlogPost with title, content, author, published_at"
```

### Data Processing
```bash
# Pandas analysis
sindri run "Create function to clean and aggregate CSV data using pandas"

# Data validation
sindri run "Create Pydantic models for validating API responses with nested objects"
```

### DevOps
```bash
# Docker automation
sindri run "Create Python script to manage Docker containers via API"

# CI/CD helper
sindri run "Create GitHub Actions workflow validator using PyYAML"
```

### Testing
```bash
# Fixtures
sindri run "Create pytest fixtures for database, user, and authentication"

# Mocks
sindri run "Create unittest mocks for external API calls"
```

---

## See Also

- [testing.md](testing.md) - Writing tests
- [refactoring.md](refactoring.md) - Code refactoring
- [AGENTS.md](../AGENTS.md) - Agent capabilities
