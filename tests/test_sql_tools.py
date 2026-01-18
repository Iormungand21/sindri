"""Tests for SQL tools (execute_query, describe_schema, explain_query)."""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from sindri.tools.sql import (
    ExecuteQueryTool,
    DescribeSchemaTool,
    ExplainQueryTool,
    SqlGenerateTool,
    DbSeedTool,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with test data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Set up test database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create users table
    cursor.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            age INTEGER,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create orders table with foreign key
    cursor.execute(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            price REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """
    )

    # Create index
    cursor.execute("CREATE INDEX idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX idx_orders_user ON orders(user_id)")

    # Insert test data
    cursor.executemany(
        "INSERT INTO users (name, email, age, active) VALUES (?, ?, ?, ?)",
        [
            ("Alice", "alice@example.com", 30, 1),
            ("Bob", "bob@example.com", 25, 1),
            ("Charlie", "charlie@example.com", 35, 0),
            ("Diana", "diana@example.com", 28, 1),
            ("Eve", "eve@example.com", 32, 1),
        ],
    )

    cursor.executemany(
        "INSERT INTO orders (user_id, product, quantity, price) VALUES (?, ?, ?, ?)",
        [
            (1, "Widget", 2, 19.99),
            (1, "Gadget", 1, 49.99),
            (2, "Widget", 5, 19.99),
            (3, "Gizmo", 1, 99.99),
            (4, "Widget", 3, 19.99),
        ],
    )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def empty_db():
    """Create an empty temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create empty database
    conn = sqlite3.connect(db_path)
    conn.close()

    yield db_path

    os.unlink(db_path)


# =============================================================================
# ExecuteQueryTool Tests - SELECT Queries
# =============================================================================


@pytest.mark.asyncio
async def test_execute_query_select_all(temp_db):
    """Test basic SELECT * query."""
    tool = ExecuteQueryTool()
    result = await tool.execute(database=temp_db, query="SELECT * FROM users")

    assert result.success is True
    assert "Alice" in result.output
    assert "Bob" in result.output
    assert result.metadata["type"] == "select"
    assert result.metadata["row_count"] == 5


@pytest.mark.asyncio
async def test_execute_query_select_with_where(temp_db):
    """Test SELECT with WHERE clause."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT name, email FROM users WHERE active = 1"
    )

    assert result.success is True
    assert "Alice" in result.output
    assert "Bob" in result.output
    assert "Charlie" not in result.output  # Charlie is inactive
    assert result.metadata["row_count"] == 4


@pytest.mark.asyncio
async def test_execute_query_select_with_params(temp_db):
    """Test SELECT with parameterized query."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE name = ?", params=["Alice"]
    )

    assert result.success is True
    assert "Alice" in result.output
    assert "Bob" not in result.output
    assert result.metadata["row_count"] == 1


@pytest.mark.asyncio
async def test_execute_query_select_with_join(temp_db):
    """Test SELECT with JOIN."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="""
            SELECT u.name, o.product, o.quantity, o.price
            FROM users u
            JOIN orders o ON u.id = o.user_id
            ORDER BY u.name
        """,
    )

    assert result.success is True
    assert "Alice" in result.output
    assert "Widget" in result.output
    assert result.metadata["row_count"] == 5


@pytest.mark.asyncio
async def test_execute_query_select_max_rows(temp_db):
    """Test max_rows limit."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM users", max_rows=2
    )

    assert result.success is True
    assert result.metadata["row_count"] == 2
    assert result.metadata["has_more"] is True
    assert "showing first 2 rows" in result.output


@pytest.mark.asyncio
async def test_execute_query_empty_result(temp_db):
    """Test query returning no results."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE name = 'NonExistent'"
    )

    assert result.success is True
    assert "(no results)" in result.output
    assert result.metadata["row_count"] == 0


@pytest.mark.asyncio
async def test_execute_query_aggregate(temp_db):
    """Test aggregate query."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="SELECT COUNT(*) as total, AVG(age) as avg_age FROM users WHERE active = 1",
    )

    assert result.success is True
    assert "4" in result.output  # 4 active users
    assert result.metadata["row_count"] == 1


# =============================================================================
# ExecuteQueryTool Tests - Write Operations
# =============================================================================


@pytest.mark.asyncio
async def test_execute_query_insert_blocked(temp_db):
    """Test INSERT blocked by default."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="INSERT INTO users (name, email) VALUES ('Frank', 'frank@example.com')",
    )

    assert result.success is False
    assert "Write operations not allowed" in result.error
    assert "allow_write=true" in result.error


@pytest.mark.asyncio
async def test_execute_query_insert_allowed(temp_db):
    """Test INSERT with allow_write=True."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="INSERT INTO users (name, email, age) VALUES ('Frank', 'frank@example.com', 40)",
        allow_write=True,
    )

    assert result.success is True
    assert "Write operation successful" in result.output
    assert result.metadata["rows_affected"] == 1
    assert result.metadata["type"] == "write"


@pytest.mark.asyncio
async def test_execute_query_update_blocked(temp_db):
    """Test UPDATE blocked by default."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="UPDATE users SET age = 31 WHERE name = 'Alice'"
    )

    assert result.success is False
    assert "Write operations not allowed" in result.error


@pytest.mark.asyncio
async def test_execute_query_update_allowed(temp_db):
    """Test UPDATE with allow_write=True."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="UPDATE users SET age = 31 WHERE name = 'Alice'",
        allow_write=True,
    )

    assert result.success is True
    assert result.metadata["rows_affected"] == 1


@pytest.mark.asyncio
async def test_execute_query_delete_blocked(temp_db):
    """Test DELETE blocked by default."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="DELETE FROM users WHERE name = 'Charlie'"
    )

    assert result.success is False
    assert "Write operations not allowed" in result.error


@pytest.mark.asyncio
async def test_execute_query_delete_allowed(temp_db):
    """Test DELETE with allow_write=True."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="DELETE FROM users WHERE name = 'Charlie'",
        allow_write=True,
    )

    assert result.success is True
    assert result.metadata["rows_affected"] == 1


# =============================================================================
# ExecuteQueryTool Tests - Error Cases
# =============================================================================


@pytest.mark.asyncio
async def test_execute_query_database_not_found():
    """Test error when database doesn't exist."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database="/nonexistent/path/database.db", query="SELECT 1"
    )

    assert result.success is False
    assert "Database not found" in result.error


@pytest.mark.asyncio
async def test_execute_query_invalid_sql(temp_db):
    """Test error on invalid SQL."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELCT * FORM users"  # Intentional typos
    )

    assert result.success is False
    assert "SQLite error" in result.error


@pytest.mark.asyncio
async def test_execute_query_table_not_found(temp_db):
    """Test error when table doesn't exist."""
    tool = ExecuteQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM nonexistent_table"
    )

    assert result.success is False
    assert "SQLite error" in result.error


@pytest.mark.asyncio
async def test_execute_query_work_dir(temp_db):
    """Test query with work_dir set."""
    db_name = Path(temp_db).name
    work_dir = Path(temp_db).parent

    tool = ExecuteQueryTool(work_dir=work_dir)
    result = await tool.execute(database=db_name, query="SELECT COUNT(*) FROM users")

    assert result.success is True


# =============================================================================
# DescribeSchemaTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_describe_schema_all_tables(temp_db):
    """Test describe all tables."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=temp_db)

    assert result.success is True
    assert "Table: users" in result.output
    assert "Table: orders" in result.output
    assert result.metadata["table_count"] == 2
    assert "users" in result.metadata["tables"]
    assert "orders" in result.metadata["tables"]


@pytest.mark.asyncio
async def test_describe_schema_single_table(temp_db):
    """Test describe specific table."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=temp_db, table="users")

    assert result.success is True
    assert "Table: users" in result.output
    assert "orders" not in result.output
    assert "id" in result.output
    assert "name" in result.output
    assert "email" in result.output
    assert "INTEGER" in result.output
    assert "TEXT" in result.output


@pytest.mark.asyncio
async def test_describe_schema_columns(temp_db):
    """Test column descriptions."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=temp_db, table="users")

    assert result.success is True
    # Check for column info
    assert "id:" in result.output
    assert "name:" in result.output
    assert "NOT NULL" in result.output
    assert "[PK]" in result.output  # Primary key marker


@pytest.mark.asyncio
async def test_describe_schema_with_indexes(temp_db):
    """Test describe schema with indexes."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=temp_db, include_indexes=True)

    assert result.success is True
    assert "Indexes:" in result.output
    assert "idx_users_email" in result.output
    assert "idx_orders_user" in result.output


@pytest.mark.asyncio
async def test_describe_schema_with_foreign_keys(temp_db):
    """Test describe schema with foreign keys."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=temp_db, table="orders")

    assert result.success is True
    assert "Foreign Keys:" in result.output
    assert "user_id" in result.output
    assert "users" in result.output


@pytest.mark.asyncio
async def test_describe_schema_with_sql(temp_db):
    """Test describe schema with CREATE statement."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=temp_db, table="users", include_sql=True)

    assert result.success is True
    assert "CREATE Statement:" in result.output
    assert "CREATE TABLE" in result.output


@pytest.mark.asyncio
async def test_describe_schema_empty_db(empty_db):
    """Test describe schema on empty database."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database=empty_db)

    assert result.success is True
    assert "No tables found" in result.output
    assert result.metadata["table_count"] == 0


@pytest.mark.asyncio
async def test_describe_schema_database_not_found():
    """Test error when database doesn't exist."""
    tool = DescribeSchemaTool()
    result = await tool.execute(database="/nonexistent/database.db")

    assert result.success is False
    assert "Database not found" in result.error


# =============================================================================
# ExplainQueryTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_explain_query_simple_select(temp_db):
    """Test explain simple SELECT."""
    tool = ExplainQueryTool()
    result = await tool.execute(database=temp_db, query="SELECT * FROM users")

    assert result.success is True
    assert "Query Execution Plan" in result.output
    assert "Analysis:" in result.output
    assert "plan_steps" in result.metadata


@pytest.mark.asyncio
async def test_explain_query_indexed_search(temp_db):
    """Test explain query using index."""
    tool = ExplainQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE email = 'alice@example.com'"
    )

    assert result.success is True
    # Should use the email index
    assert (
        result.metadata.get("uses_index", False)
        or "SEARCH" in result.output
        or "INDEX" in result.output
    )


@pytest.mark.asyncio
async def test_explain_query_table_scan(temp_db):
    """Test explain query with table scan."""
    tool = ExplainQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE age > 25"  # No index on age
    )

    assert result.success is True
    assert (
        "SCAN" in result.output
        or "full table scan" in result.output.lower()
        or "plan looks reasonable" in result.output
    )


@pytest.mark.asyncio
async def test_explain_query_join(temp_db):
    """Test explain JOIN query."""
    tool = ExplainQueryTool()
    result = await tool.execute(
        database=temp_db,
        query="""
            SELECT u.name, o.product
            FROM users u
            JOIN orders o ON u.id = o.user_id
        """,
    )

    assert result.success is True
    assert result.metadata["plan_steps"] >= 1


@pytest.mark.asyncio
async def test_explain_query_detailed(temp_db):
    """Test explain with detailed bytecode."""
    tool = ExplainQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE id = 1", detailed=True
    )

    assert result.success is True
    assert "Bytecode" in result.output


@pytest.mark.asyncio
async def test_explain_query_analysis_hints(temp_db):
    """Test explain provides useful analysis hints."""
    tool = ExplainQueryTool()

    # Query that should trigger table scan hint
    result = await tool.execute(
        database=temp_db, query="SELECT * FROM orders WHERE quantity > 2"
    )

    assert result.success is True
    assert "Analysis:" in result.output
    # Should have some analysis hint
    assert any(
        hint in result.output
        for hint in ["table scan", "index", "efficient", "plan looks reasonable"]
    )


@pytest.mark.asyncio
async def test_explain_query_database_not_found():
    """Test error when database doesn't exist."""
    tool = ExplainQueryTool()
    result = await tool.execute(database="/nonexistent/database.db", query="SELECT 1")

    assert result.success is False
    assert "Database not found" in result.error


@pytest.mark.asyncio
async def test_explain_query_invalid_sql(temp_db):
    """Test error on invalid SQL."""
    tool = ExplainQueryTool()
    result = await tool.execute(
        database=temp_db, query="SELCT * FORM users"  # Intentional typos
    )

    assert result.success is False
    assert "SQLite error" in result.error


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_workflow(temp_db):
    """Test a full workflow: describe, explain, query, write."""
    describe_tool = DescribeSchemaTool()
    explain_tool = ExplainQueryTool()
    query_tool = ExecuteQueryTool()

    # 1. Describe schema
    schema = await describe_tool.execute(database=temp_db)
    assert schema.success is True
    assert "users" in schema.metadata["tables"]

    # 2. Explain a query
    plan = await explain_tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE email = 'alice@example.com'"
    )
    assert plan.success is True

    # 3. Execute the query
    result = await query_tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE email = 'alice@example.com'"
    )
    assert result.success is True
    assert "Alice" in result.output

    # 4. Insert new record
    insert = await query_tool.execute(
        database=temp_db,
        query="INSERT INTO users (name, email, age) VALUES ('Zara', 'zara@example.com', 22)",
        allow_write=True,
    )
    assert insert.success is True

    # 5. Verify insertion
    verify = await query_tool.execute(
        database=temp_db, query="SELECT * FROM users WHERE name = 'Zara'"
    )
    assert verify.success is True
    assert "Zara" in verify.output


@pytest.mark.asyncio
async def test_tools_from_registry():
    """Test that SQL tools are properly registered."""
    from sindri.tools.registry import ToolRegistry

    registry = ToolRegistry.default()

    # Check all SQL tools are registered
    assert registry.get_tool("execute_query") is not None
    assert registry.get_tool("describe_schema") is not None
    assert registry.get_tool("explain_query") is not None


def test_fenrir_has_sql_tools():
    """Test that Fenrir agent has SQL tools configured."""
    from sindri.agents.registry import AGENTS

    fenrir = AGENTS.get("fenrir")
    assert fenrir is not None
    assert "execute_query" in fenrir.tools
    assert "describe_schema" in fenrir.tools
    assert "explain_query" in fenrir.tools


# =============================================================================
# Tool Schema Tests
# =============================================================================


def test_execute_query_schema():
    """Test ExecuteQueryTool schema format."""
    tool = ExecuteQueryTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "execute_query"
    assert "database" in schema["function"]["parameters"]["properties"]
    assert "query" in schema["function"]["parameters"]["properties"]
    assert "database" in schema["function"]["parameters"]["required"]
    assert "query" in schema["function"]["parameters"]["required"]


def test_describe_schema_schema():
    """Test DescribeSchemaTool schema format."""
    tool = DescribeSchemaTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "describe_schema"
    assert "database" in schema["function"]["parameters"]["properties"]
    assert "table" in schema["function"]["parameters"]["properties"]


def test_explain_query_schema():
    """Test ExplainQueryTool schema format."""
    tool = ExplainQueryTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "explain_query"
    assert "database" in schema["function"]["parameters"]["properties"]
    assert "query" in schema["function"]["parameters"]["properties"]
    assert "detailed" in schema["function"]["parameters"]["properties"]


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_execute_query_null_values(temp_db):
    """Test handling of NULL values in results."""
    tool = ExecuteQueryTool()

    # First insert a row with NULL
    await tool.execute(
        database=temp_db,
        query="INSERT INTO users (name, email) VALUES ('NullAge', 'null@example.com')",
        allow_write=True,
    )

    # Query the row
    result = await tool.execute(
        database=temp_db, query="SELECT name, age FROM users WHERE name = 'NullAge'"
    )

    assert result.success is True
    assert "NULL" in result.output


@pytest.mark.asyncio
async def test_execute_query_unicode(temp_db):
    """Test handling of unicode characters."""
    tool = ExecuteQueryTool()

    # Insert unicode data
    await tool.execute(
        database=temp_db,
        query="INSERT INTO users (name, email) VALUES ('Tëst Üser', 'unicode@example.com')",
        allow_write=True,
    )

    result = await tool.execute(
        database=temp_db,
        query="SELECT name FROM users WHERE email = 'unicode@example.com'",
    )

    assert result.success is True
    assert "Tëst" in result.output


@pytest.mark.asyncio
async def test_execute_query_long_text(temp_db):
    """Test handling of long text values."""
    tool = ExecuteQueryTool()
    long_name = "A" * 200

    await tool.execute(
        database=temp_db,
        query=f"INSERT INTO users (name, email) VALUES ('{long_name}', 'long@example.com')",
        allow_write=True,
    )

    result = await tool.execute(
        database=temp_db,
        query="SELECT name FROM users WHERE email = 'long@example.com'",
    )

    assert result.success is True
    # Output should be truncated
    assert "..." in result.output or long_name[:50] in result.output


# =============================================================================
# SqlGenerateTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_sql_generate_select_all():
    """Test generating SELECT * query."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Get all users")

    assert result.success is True
    assert "SELECT" in result.output.upper()
    assert "users" in result.output.lower()
    assert result.metadata["sql"] is not None


@pytest.mark.asyncio
async def test_sql_generate_select_all_with_database(temp_db):
    """Test generating SELECT * query with database context."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Get all users", database=temp_db)

    assert result.success is True
    assert "SELECT" in result.output.upper()
    assert "users" in result.output.lower()


@pytest.mark.asyncio
async def test_sql_generate_count():
    """Test generating COUNT query."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Count users")

    assert result.success is True
    assert "COUNT" in result.output.upper()


@pytest.mark.asyncio
async def test_sql_generate_count_how_many():
    """Test generating COUNT query with 'how many' phrasing."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="How many orders are there")

    assert result.success is True
    assert "COUNT" in result.output.upper()


@pytest.mark.asyncio
async def test_sql_generate_top_n():
    """Test generating TOP N query."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Top 10 products by price")

    assert result.success is True
    assert "LIMIT" in result.output.upper()
    assert "10" in result.output
    assert "ORDER BY" in result.output.upper()


@pytest.mark.asyncio
async def test_sql_generate_with_table_hint():
    """Test generating query with explicit table hint."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Get all items", table="products")

    assert result.success is True
    assert "products" in result.output.lower()


@pytest.mark.asyncio
async def test_sql_generate_validation(temp_db):
    """Test SQL validation against schema."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(
        description="Get all users", database=temp_db, validate=True
    )

    assert result.success is True
    assert result.metadata.get("validated") is True


@pytest.mark.asyncio
async def test_sql_generate_group_by():
    """Test generating GROUP BY query."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Count orders per customer")

    assert result.success is True
    assert "COUNT" in result.output.upper()
    assert "GROUP BY" in result.output.upper()


@pytest.mark.asyncio
async def test_sql_generate_schema():
    """Test SqlGenerateTool schema format."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "sql_generate"
    assert "description" in schema["function"]["parameters"]["properties"]
    assert "database" in schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_sql_generate_returns_metadata():
    """Test that sql_generate returns proper metadata."""
    from sindri.tools.sql import SqlGenerateTool

    tool = SqlGenerateTool()
    result = await tool.execute(description="Get all users")

    assert result.success is True
    assert "sql" in result.metadata
    assert "parsed" in result.metadata
    assert "dialect" in result.metadata


# =============================================================================
# DbSeedTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_db_seed_basic(temp_db):
    """Test basic data seeding."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    result = await tool.execute(database=temp_db, table="users", rows=5)

    assert result.success is True
    assert result.metadata.get("rows_inserted") == 5
    assert "Seeded 5 rows" in result.output


@pytest.mark.asyncio
async def test_db_seed_with_count(temp_db):
    """Test seeding with specific row count."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    result = await tool.execute(database=temp_db, table="users", rows=20)

    assert result.success is True
    assert result.metadata.get("rows_inserted") == 20


@pytest.mark.asyncio
async def test_db_seed_reproducible_seed(temp_db):
    """Test seeding with seed is reproducible."""
    from sindri.tools.sql import DbSeedTool, ExecuteQueryTool

    tool = DbSeedTool()
    query_tool = ExecuteQueryTool()

    # Seed with specific seed
    await tool.execute(
        database=temp_db,
        table="users",
        rows=3,
        seed=42,
        clear_existing=True,
    )

    # Query the data
    data1 = await query_tool.execute(
        database=temp_db,
        query="SELECT name, email FROM users ORDER BY id LIMIT 3",
    )

    # Clear and reseed with same seed
    await tool.execute(
        database=temp_db,
        table="users",
        rows=3,
        seed=42,
        clear_existing=True,
    )

    data2 = await query_tool.execute(
        database=temp_db,
        query="SELECT name, email FROM users ORDER BY id LIMIT 3",
    )

    # Should be identical
    assert data1.output == data2.output


@pytest.mark.asyncio
async def test_db_seed_different_seeds_different_data(temp_db):
    """Test that different seeds produce different data."""
    from sindri.tools.sql import DbSeedTool, ExecuteQueryTool

    tool = DbSeedTool()
    query_tool = ExecuteQueryTool()

    # Seed with seed 1
    await tool.execute(
        database=temp_db, table="users", rows=3, seed=1, clear_existing=True
    )
    data1 = await query_tool.execute(
        database=temp_db, query="SELECT name FROM users ORDER BY id"
    )

    # Seed with seed 2
    await tool.execute(
        database=temp_db, table="users", rows=3, seed=2, clear_existing=True
    )
    data2 = await query_tool.execute(
        database=temp_db, query="SELECT name FROM users ORDER BY id"
    )

    # Should be different
    assert data1.output != data2.output


@pytest.mark.asyncio
async def test_db_seed_clear_existing(temp_db):
    """Test clearing existing data before seeding."""
    from sindri.tools.sql import DbSeedTool, ExecuteQueryTool

    tool = DbSeedTool()
    query_tool = ExecuteQueryTool()

    # Check initial count (should have 5 from fixture)
    initial = await query_tool.execute(
        database=temp_db, query="SELECT COUNT(*) as cnt FROM users"
    )
    assert "5" in initial.output

    # Seed without clearing - should add
    await tool.execute(database=temp_db, table="users", rows=3, clear_existing=False)
    after_add = await query_tool.execute(
        database=temp_db, query="SELECT COUNT(*) as cnt FROM users"
    )
    assert "8" in after_add.output  # 5 + 3

    # Seed with clearing - should replace
    result = await tool.execute(
        database=temp_db, table="users", rows=2, clear_existing=True
    )
    after_clear = await query_tool.execute(
        database=temp_db, query="SELECT COUNT(*) as cnt FROM users"
    )
    assert "2" in after_clear.output  # Only the 2 new ones
    assert result.metadata.get("rows_deleted") == 8  # Deleted the 8


@pytest.mark.asyncio
async def test_db_seed_table_not_found(temp_db):
    """Test error when table doesn't exist."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    result = await tool.execute(database=temp_db, table="nonexistent_table", rows=5)

    assert result.success is False
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_db_seed_database_not_found():
    """Test error when database doesn't exist."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    result = await tool.execute(database="/nonexistent/database.db", table="users", rows=5)

    assert result.success is False
    assert "Database not found" in result.error


@pytest.mark.asyncio
async def test_db_seed_max_rows_limit(empty_db):
    """Test that rows are capped at MAX_ROWS."""
    import sqlite3
    from sindri.tools.sql import DbSeedTool

    # Create a simple table with no uniqueness constraints
    conn = sqlite3.connect(empty_db)
    conn.execute(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            value REAL
        )
    """
    )
    conn.commit()
    conn.close()

    tool = DbSeedTool()
    # Request more than MAX_ROWS (10000)
    result = await tool.execute(database=empty_db, table="items", rows=20000)

    assert result.success is True
    # Should be capped at 10000
    assert result.metadata.get("rows_inserted") == 10000


@pytest.mark.asyncio
async def test_db_seed_schema():
    """Test DbSeedTool schema format."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "db_seed"
    assert "database" in schema["function"]["parameters"]["properties"]
    assert "table" in schema["function"]["parameters"]["properties"]
    assert "rows" in schema["function"]["parameters"]["properties"]
    assert "seed" in schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_db_seed_foreign_keys(temp_db):
    """Test seeding table with foreign keys."""
    from sindri.tools.sql import DbSeedTool, ExecuteQueryTool

    tool = DbSeedTool()
    query_tool = ExecuteQueryTool()

    # Seed users first (table fixture already has 5)
    # Now seed orders (has FK to users)
    result = await tool.execute(database=temp_db, table="orders", rows=10)

    assert result.success is True

    # Verify FK integrity - all user_ids should exist in users
    integrity = await query_tool.execute(
        database=temp_db,
        query="""
            SELECT COUNT(*) FROM orders o
            WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = o.user_id)
        """,
    )
    assert "0" in integrity.output  # No orphaned records


@pytest.mark.asyncio
async def test_db_seed_shows_sample_data(temp_db):
    """Test that seeding shows sample data in output."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    result = await tool.execute(database=temp_db, table="users", rows=5, clear_existing=True)

    assert result.success is True
    assert "Sample data:" in result.output
    assert "Columns seeded:" in result.output


@pytest.mark.asyncio
async def test_db_seed_metadata(temp_db):
    """Test that db_seed returns proper metadata."""
    from sindri.tools.sql import DbSeedTool

    tool = DbSeedTool()
    result = await tool.execute(
        database=temp_db, table="users", rows=5, seed=123, clear_existing=True
    )

    assert result.success is True
    assert "rows_inserted" in result.metadata
    assert "rows_deleted" in result.metadata
    assert "columns" in result.metadata
    assert "seed" in result.metadata
    assert result.metadata["seed"] == 123


# =============================================================================
# Integration Tests for New Tools
# =============================================================================


@pytest.mark.asyncio
async def test_sql_generate_and_execute(temp_db):
    """Test generating SQL and executing it."""
    from sindri.tools.sql import SqlGenerateTool, ExecuteQueryTool

    gen_tool = SqlGenerateTool()
    exec_tool = ExecuteQueryTool()

    # Generate SQL
    gen_result = await gen_tool.execute(
        description="Get all users", database=temp_db
    )
    assert gen_result.success is True

    # Extract the SQL from metadata
    sql = gen_result.metadata.get("sql")
    assert sql is not None

    # Execute the generated SQL
    exec_result = await exec_tool.execute(database=temp_db, query=sql)
    assert exec_result.success is True
    # Should find the 5 users from fixture
    assert exec_result.metadata.get("row_count") == 5


@pytest.mark.asyncio
async def test_seed_and_query(temp_db):
    """Test seeding data and querying it."""
    from sindri.tools.sql import DbSeedTool, ExecuteQueryTool

    seed_tool = DbSeedTool()
    query_tool = ExecuteQueryTool()

    # Seed some data
    seed_result = await seed_tool.execute(
        database=temp_db, table="users", rows=10, clear_existing=True
    )
    assert seed_result.success is True

    # Query the seeded data
    query_result = await query_tool.execute(
        database=temp_db, query="SELECT COUNT(*) as cnt FROM users"
    )
    assert query_result.success is True
    assert "10" in query_result.output


@pytest.mark.asyncio
async def test_fenrir_has_new_sql_tools():
    """Test that Fenrir agent has new SQL tools configured."""
    from sindri.agents.registry import AGENTS

    fenrir = AGENTS.get("fenrir")
    assert fenrir is not None
    assert "sql_generate" in fenrir.tools
    assert "db_seed" in fenrir.tools


@pytest.mark.asyncio
async def test_new_tools_in_registry():
    """Test that new SQL tools are properly registered."""
    from sindri.tools.registry import ToolRegistry

    registry = ToolRegistry.default()

    # Check all SQL tools are registered
    assert registry.get_tool("sql_generate") is not None
    assert registry.get_tool("db_seed") is not None
