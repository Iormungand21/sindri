# Guide: Testing with Sindri

**Generate comprehensive tests using Skald (test specialist)**

---

## Overview

Sindri's **Skald** agent specializes in test generation:
- Unit tests
- Integration tests
- Fixtures and mocks
- Test coverage

---

## Basic Unit Tests

### Testing Functions

**Task:**
```bash
sindri run "Write pytest tests for email_validator.py" --model llama3.1:8b
```

**Generated:**
```python
# test_email_validator.py
import pytest
from email_validator import validate_email

def test_valid_email():
    """Test valid email addresses."""
    assert validate_email("user@example.com")
    assert validate_email("test.user+tag@domain.co.uk")
    assert validate_email("admin_123@sub.domain.org")

def test_invalid_email():
    """Test invalid email addresses."""
    assert not validate_email("invalid")
    assert not validate_email("@example.com")
    assert not validate_email("user@")
    assert not validate_email("user @example.com")

def test_empty_email():
    """Test empty string."""
    assert not validate_email("")

def test_none_raises_exception():
    """Test None input raises TypeError."""
    with pytest.raises(TypeError):
        validate_email(None)
```

---

## Parametrized Tests

**Task:**
```
Write parametrized pytest tests for the calculator module with edge cases
```

**Generated:**
```python
import pytest
from calculator import add, subtract, multiply, divide

@pytest.mark.parametrize("a,b,expected", [
    (2, 3, 5),
    (-1, 1, 0),
    (0, 0, 0),
    (1.5, 2.5, 4.0),
])
def test_add(a, b, expected):
    assert add(a, b) == expected

@pytest.mark.parametrize("a,b,expected", [
    (5, 3, 2),
    (0, 1, -1),
    (-1, -1, 0),
])
def test_subtract(a, b, expected):
    assert subtract(a, b) == expected

@pytest.mark.parametrize("a,b", [
    (1, 0),
    (100, 0),
])
def test_divide_by_zero_raises(a, b):
    with pytest.raises(ZeroDivisionError):
        divide(a, b)
```

---

## Test Fixtures

### Basic Fixtures

**Task:**
```
Create pytest fixtures for database, user, and authentication testing
```

**Generated:**
```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User
from auth import create_token

@pytest.fixture
def db_engine():
    """Create in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    """Create database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def sample_user(db_session):
    """Create sample user."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture
def auth_token(sample_user):
    """Create authentication token."""
    return create_token(sample_user.id)
```

---

### Async Fixtures

**Task:**
```
Create pytest-asyncio fixtures for async database and HTTP client
```

**Generated:**
```python
import pytest
import pytest_asyncio
from httpx import AsyncClient
from app import app
from database import init_db, close_db

@pytest_asyncio.fixture
async def db():
    """Initialize test database."""
    await init_db("sqlite+aiosqlite:///:memory:")
    yield
    await close_db()

@pytest_asyncio.fixture
async def client(db):
    """Create async HTTP client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def authenticated_client(client, sample_user):
    """Client with authentication header."""
    token = create_token(sample_user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return client
```

---

## Mocking

### External API Mocks

**Task:**
```
Create unittest mocks for external GitHub API calls
```

**Generated:**
```python
from unittest.mock import Mock, patch, AsyncMock
import pytest
from github_client import GitHubClient

@pytest.fixture
def mock_response():
    """Mock HTTP response."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "id": 123,
        "name": "test-repo",
        "full_name": "user/test-repo"
    }
    return response

@patch("github_client.httpx.get")
def test_get_repo(mock_get, mock_response):
    """Test fetching repository."""
    mock_get.return_value = mock_response

    client = GitHubClient("fake-token")
    repo = client.get_repo("user/test-repo")

    assert repo["name"] == "test-repo"
    mock_get.assert_called_once_with(
        "https://api.github.com/repos/user/test-repo",
        headers={"Authorization": "token fake-token"}
    )

@pytest.mark.asyncio
@patch("github_client.httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_get_repo_async(mock_get, mock_response):
    """Test async repository fetch."""
    mock_get.return_value = mock_response

    client = GitHubClient("fake-token")
    repo = await client.get_repo_async("user/test-repo")

    assert repo["name"] == "test-repo"
```

---

## Integration Tests

### API Testing

**Task:**
```
Write integration tests for the FastAPI todo list API with full CRUD coverage
```

**Generated:**
```python
import pytest
from httpx import AsyncClient
from app import app

@pytest.mark.asyncio
async def test_create_todo():
    """Test creating a todo item."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/todos", json={
            "title": "Test todo",
            "description": "Test description"
        })

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test todo"
        assert "id" in data

@pytest.mark.asyncio
async def test_list_todos():
    """Test listing todos."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create some todos
        await client.post("/todos", json={"title": "Todo 1"})
        await client.post("/todos", json={"title": "Todo 2"})

        # List them
        response = await client.get("/todos")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

@pytest.mark.asyncio
async def test_update_todo():
    """Test updating a todo."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create
        create_response = await client.post("/todos", json={
            "title": "Original"
        })
        todo_id = create_response.json()["id"]

        # Update
        update_response = await client.put(f"/todos/{todo_id}", json={
            "title": "Updated",
            "completed": True
        })
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "Updated"

@pytest.mark.asyncio
async def test_delete_todo():
    """Test deleting a todo."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create
        create_response = await client.post("/todos", json={
            "title": "To delete"
        })
        todo_id = create_response.json()["id"]

        # Delete
        delete_response = await client.delete(f"/todos/{todo_id}")
        assert delete_response.status_code == 204

        # Verify deleted
        get_response = await client.get(f"/todos/{todo_id}")
        assert get_response.status_code == 404
```

---

## Test Coverage

### Request Coverage Report

**Task:**
```
Write tests with 100% coverage for the auth module including edge cases
```

Skald will generate tests for:
- All functions
- All branches (if/else)
- Edge cases (empty, None, invalid input)
- Error paths (exceptions)

**Check coverage:**
```bash
pytest --cov=auth --cov-report=term-missing
```

---

## Property-Based Testing

**Task:**
```
Create Hypothesis property tests for the sort function
```

**Generated:**
```python
from hypothesis import given, strategies as st
import pytest
from sorting import merge_sort

@given(st.lists(st.integers()))
def test_merge_sort_returns_sorted_list(lst):
    """Property: Result should be sorted."""
    result = merge_sort(lst)
    assert result == sorted(lst)

@given(st.lists(st.integers()))
def test_merge_sort_preserves_length(lst):
    """Property: Length should be preserved."""
    result = merge_sort(lst)
    assert len(result) == len(lst)

@given(st.lists(st.integers()))
def test_merge_sort_preserves_elements(lst):
    """Property: All elements should be preserved."""
    result = merge_sort(lst)
    assert sorted(result) == sorted(lst)

@given(st.lists(st.integers(), min_size=1))
def test_merge_sort_min_max(lst):
    """Property: First should be min, last should be max."""
    result = merge_sort(lst)
    assert result[0] == min(lst)
    assert result[-1] == max(lst)
```

---

## Advanced Testing Patterns

### Test Factories

**Task:**
```
Create factory_boy factories for User, Post, and Comment models
```

**Generated:**
```python
import factory
from factory.fuzzy import FuzzyText, FuzzyInteger
from models import User, Post, Comment

class UserFactory(factory.Factory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password_hash = FuzzyText(length=60)

class PostFactory(factory.Factory):
    class Meta:
        model = Post

    title = factory.Faker('sentence', nb_words=6)
    content = factory.Faker('paragraph', nb_sentences=10)
    author = factory.SubFactory(UserFactory)

class CommentFactory(factory.Factory):
    class Meta:
        model = Comment

    content = factory.Faker('paragraph')
    post = factory.SubFactory(PostFactory)
    author = factory.SubFactory(UserFactory)

# Usage in tests
def test_create_post():
    user = UserFactory()
    post = PostFactory(author=user)
    assert post.author == user
```

---

## Best Practices

### Clear Test Names

**Task:**
```
Write tests with descriptive names following Given-When-Then pattern
```

**Generated:**
```python
def test_given_valid_credentials_when_login_then_returns_token():
    """Given valid username and password,
       When user attempts login,
       Then authentication token is returned."""
    ...

def test_given_invalid_password_when_login_then_raises_auth_error():
    """Given correct username but wrong password,
       When user attempts login,
       Then AuthenticationError is raised."""
    ...
```

---

### Test Organization

**Request structure:**
```
Organize tests for the auth module with:
- test_models.py for User model tests
- test_auth.py for authentication logic
- test_api.py for API endpoint tests
- conftest.py for shared fixtures
```

---

### Async Test Patterns

**Task:**
```
Write async tests for the WebSocket connection manager with proper cleanup
```

**Includes:**
- `pytest_asyncio` fixtures
- Proper resource cleanup (`try/finally`)
- Timeout handling
- Concurrent connection testing

---

## Troubleshooting

### Tests Not Found

**Issue:** pytest doesn't find tests

**Solution:**
```bash
# Ensure test files start with test_
mv email_tests.py test_email_validator.py

# Or configure pytest.ini
[pytest]
python_files = *_test.py test_*.py
```

---

### Fixtures Not Working

**Issue:** Fixture not available in test

**Solutions:**
- Move fixture to `conftest.py` for project-wide access
- Check fixture scope (function, module, session)
- Ensure fixture name matches parameter name

---

### Async Tests Failing

**Issue:** `RuntimeWarning: coroutine was never awaited`

**Solutions:**
- Add `@pytest.mark.asyncio` decorator
- Install `pytest-asyncio`: `pip install pytest-asyncio`
- Use `await` for async calls

---

## Task Templates

### Unit Tests
```
Write pytest unit tests for [module] covering:
- All public functions
- Edge cases (empty, None, invalid)
- Error conditions
- With type hints and docstrings
```

### Integration Tests
```
Write integration tests for [feature] including:
- Happy path scenario
- Error scenarios
- Database transactions
- API interactions
```

### Fixtures
```
Create pytest fixtures for:
- Database setup/teardown
- Sample data (users, posts, etc.)
- Authenticated client
- Mock external services
```

### Mocks
```
Create mocks for:
- External API calls to [service]
- Database queries
- File system operations
Using unittest.mock and pytest-mock
```

---

## See Also

- [code-generation.md](code-generation.md) - Generating testable code
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Test troubleshooting
- [AGENTS.md](../AGENTS.md) - Skald agent details
