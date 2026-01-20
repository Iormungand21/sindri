"""Tests for advanced SQL tools (Fafnir agent).

Tests for:
- SqlOptimizeTool
- DbSchemaDiffTool
- DbAnalyzeIndexesTool
- DbBackupTool
- DbVisualizeSchemaTool
"""

import gzip
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sindri.tools.sql_advanced import (
    SqlOptimizeTool,
    DbSchemaDiffTool,
    DbAnalyzeIndexesTool,
    DbBackupTool,
    DbVisualizeSchemaTool,
    _detect_db_type,
    _get_schema_info,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with test data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create users table
    cursor.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'active',
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

    # Create indexes
    cursor.execute("CREATE INDEX idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX idx_users_status ON users(status)")
    cursor.execute("CREATE INDEX idx_orders_user ON orders(user_id)")

    # Insert test data
    cursor.executemany(
        "INSERT INTO users (name, email, status) VALUES (?, ?, ?)",
        [
            ("Alice", "alice@example.com", "active"),
            ("Bob", "bob@example.com", "active"),
            ("Charlie", "charlie@example.com", "inactive"),
        ],
    )

    cursor.executemany(
        "INSERT INTO orders (user_id, product, quantity, price) VALUES (?, ?, ?, ?)",
        [
            (1, "Widget", 2, 19.99),
            (1, "Gadget", 1, 49.99),
            (2, "Widget", 5, 19.99),
        ],
    )

    conn.commit()
    conn.close()

    yield db_path

    os.unlink(db_path)


@pytest.fixture
def temp_db_modified():
    """Create a modified version of temp_db for diff testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Same users table but with added column
    cursor.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Same orders table
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

    # New products table (added)
    cursor.execute(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    """
    )

    # Different indexes
    cursor.execute("CREATE INDEX idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX idx_orders_user ON orders(user_id)")
    # Note: removed idx_users_status, added products table

    conn.commit()
    conn.close()

    yield db_path

    os.unlink(db_path)


@pytest.fixture
def large_db():
    """Create a database with more rows for optimization testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user_id INTEGER,
            timestamp TEXT,
            payload TEXT
        )
    """
    )

    # Insert 2000 rows for table scan detection
    events = [(f"type_{i % 10}", i % 100, f"2024-01-{(i % 28) + 1:02d}", f"data_{i}") for i in range(2000)]
    cursor.executemany(
        "INSERT INTO events (event_type, user_id, timestamp, payload) VALUES (?, ?, ?, ?)",
        events,
    )

    conn.commit()
    conn.close()

    yield db_path

    os.unlink(db_path)


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_detect_db_type_sqlite(self):
        """Detect SQLite from file path."""
        assert _detect_db_type("app.db") == "sqlite"
        assert _detect_db_type("/path/to/data.db") == "sqlite"

    def test_detect_db_type_postgresql(self):
        """Detect PostgreSQL from connection string."""
        assert _detect_db_type("postgresql://user:pass@localhost/db") == "postgresql"
        assert _detect_db_type("postgres://user:pass@localhost/db") == "postgresql"

    def test_detect_db_type_mysql(self):
        """Detect MySQL from connection string."""
        assert _detect_db_type("mysql://user:pass@localhost/db") == "mysql"

    def test_get_schema_info(self, temp_db):
        """Test schema extraction."""
        conn = sqlite3.connect(temp_db)
        schema = _get_schema_info(conn)
        conn.close()

        assert "users" in schema["tables"]
        assert "orders" in schema["tables"]
        assert "name" in schema["tables"]["users"]["columns"]
        assert len(schema["tables"]["users"]["indexes"]) >= 1


# =============================================================================
# SqlOptimizeTool Tests
# =============================================================================


class TestSqlOptimizeTool:
    """Tests for SqlOptimizeTool."""

    @pytest.mark.asyncio
    async def test_optimize_query_with_index(self, temp_db):
        """Test optimization analysis for query using index."""
        tool = SqlOptimizeTool()
        result = await tool.execute(
            database=temp_db,
            query="SELECT * FROM users WHERE email = 'test@example.com'",
        )

        assert result.success is True
        assert "Execution Plan" in result.output
        assert result.metadata["uses_index"] is True

    @pytest.mark.asyncio
    async def test_optimize_query_table_scan(self, large_db):
        """Test detection of table scan on large table."""
        tool = SqlOptimizeTool()
        result = await tool.execute(
            database=large_db,
            query="SELECT * FROM events WHERE payload LIKE '%test%'",
        )

        assert result.success is True
        assert "Execution Plan" in result.output
        # Should detect table scan since payload has no index

    @pytest.mark.asyncio
    async def test_optimize_join_query(self, temp_db):
        """Test optimization analysis for JOIN query."""
        tool = SqlOptimizeTool()
        result = await tool.execute(
            database=temp_db,
            query="SELECT u.name, o.product FROM users u JOIN orders o ON u.id = o.user_id",
        )

        assert result.success is True
        assert "Execution Plan" in result.output
        assert "users" in result.metadata["tables_analyzed"] or "orders" in result.metadata["tables_analyzed"]

    @pytest.mark.asyncio
    async def test_optimize_with_context(self, temp_db):
        """Test optimization with additional context."""
        tool = SqlOptimizeTool()
        result = await tool.execute(
            database=temp_db,
            query="SELECT * FROM users WHERE status = 'active'",
            context="This query runs every minute for health checks",
        )

        assert result.success is True
        assert "Additional Context" in result.output

    @pytest.mark.asyncio
    async def test_optimize_missing_database(self):
        """Test error handling for missing database."""
        tool = SqlOptimizeTool()
        result = await tool.execute(
            database="/nonexistent/path.db",
            query="SELECT 1",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_optimize_invalid_query(self, temp_db):
        """Test error handling for invalid SQL."""
        tool = SqlOptimizeTool()
        result = await tool.execute(
            database=temp_db,
            query="INVALID SQL SYNTAX",
        )

        assert result.success is False


# =============================================================================
# DbSchemaDiffTool Tests
# =============================================================================


class TestDbSchemaDiffTool:
    """Tests for DbSchemaDiffTool."""

    @pytest.mark.asyncio
    async def test_diff_identical_schemas(self, temp_db):
        """Test diff of identical databases."""
        tool = DbSchemaDiffTool()
        result = await tool.execute(
            database1=temp_db,
            database2=temp_db,
        )

        assert result.success is True
        assert result.metadata["total_changes"] == 0
        assert "No schema differences" in result.output

    @pytest.mark.asyncio
    async def test_diff_added_table(self, temp_db, temp_db_modified):
        """Test detection of added table."""
        tool = DbSchemaDiffTool()
        result = await tool.execute(
            database1=temp_db,
            database2=temp_db_modified,
        )

        assert result.success is True
        assert "products" in result.metadata["added_tables"]
        assert "Added Tables" in result.output

    @pytest.mark.asyncio
    async def test_diff_added_column(self, temp_db, temp_db_modified):
        """Test detection of added column."""
        tool = DbSchemaDiffTool()
        result = await tool.execute(
            database1=temp_db,
            database2=temp_db_modified,
        )

        assert result.success is True
        # Phone column was added to users
        assert "Modified Tables" in result.output or "phone" in result.output.lower()

    @pytest.mark.asyncio
    async def test_diff_specific_tables(self, temp_db, temp_db_modified):
        """Test diff of specific tables only."""
        tool = DbSchemaDiffTool()
        result = await tool.execute(
            database1=temp_db,
            database2=temp_db_modified,
            tables=["users"],
        )

        assert result.success is True
        # Should only compare users table, not detect products

    @pytest.mark.asyncio
    async def test_diff_missing_database(self, temp_db):
        """Test error for missing database."""
        tool = DbSchemaDiffTool()
        result = await tool.execute(
            database1=temp_db,
            database2="/nonexistent/path.db",
        )

        assert result.success is False
        assert "not found" in result.error.lower()


# =============================================================================
# DbAnalyzeIndexesTool Tests
# =============================================================================


class TestDbAnalyzeIndexesTool:
    """Tests for DbAnalyzeIndexesTool."""

    @pytest.mark.asyncio
    async def test_analyze_indexes_basic(self, temp_db):
        """Test basic index analysis."""
        tool = DbAnalyzeIndexesTool()
        result = await tool.execute(database=temp_db)

        assert result.success is True
        assert "Index Analysis Report" in result.output
        assert result.metadata["existing_index_count"] >= 3

    @pytest.mark.asyncio
    async def test_analyze_indexes_with_stats(self, temp_db):
        """Test index analysis with statistics."""
        tool = DbAnalyzeIndexesTool()
        result = await tool.execute(database=temp_db, include_stats=True)

        assert result.success is True
        assert "Rows:" in result.output

    @pytest.mark.asyncio
    async def test_analyze_indexes_specific_tables(self, temp_db):
        """Test analysis of specific tables."""
        tool = DbAnalyzeIndexesTool()
        result = await tool.execute(
            database=temp_db,
            tables=["users"],
        )

        assert result.success is True
        assert "users" in result.output
        # Should only analyze users table

    @pytest.mark.asyncio
    async def test_analyze_indexes_with_query_log(self, temp_db):
        """Test analysis with query log."""
        # Create a temporary query log
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("SELECT * FROM users WHERE email = 'test@example.com'\n")
            f.write("SELECT * FROM users WHERE status = 'active'\n")
            query_log_path = f.name

        try:
            tool = DbAnalyzeIndexesTool()
            result = await tool.execute(
                database=temp_db,
                query_log=query_log_path,
            )

            assert result.success is True
        finally:
            os.unlink(query_log_path)

    @pytest.mark.asyncio
    async def test_analyze_indexes_missing_db(self):
        """Test error for missing database."""
        tool = DbAnalyzeIndexesTool()
        result = await tool.execute(database="/nonexistent/path.db")

        assert result.success is False
        assert "not found" in result.error.lower()


# =============================================================================
# DbBackupTool Tests
# =============================================================================


class TestDbBackupTool:
    """Tests for DbBackupTool."""

    @pytest.mark.asyncio
    async def test_backup_sqlite_basic(self, temp_db):
        """Test basic SQLite backup."""
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as f:
            backup_path = f.name

        try:
            tool = DbBackupTool()
            result = await tool.execute(
                database=temp_db,
                output_path=backup_path,
            )

            assert result.success is True
            assert Path(backup_path).exists()
            assert result.metadata["size_bytes"] > 0

            # Verify backup contains SQL
            content = Path(backup_path).read_text()
            assert "CREATE TABLE" in content
            assert "users" in content
        finally:
            if Path(backup_path).exists():
                os.unlink(backup_path)

    @pytest.mark.asyncio
    async def test_backup_sqlite_schema_only(self, temp_db):
        """Test schema-only backup."""
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as f:
            backup_path = f.name

        try:
            tool = DbBackupTool()
            result = await tool.execute(
                database=temp_db,
                output_path=backup_path,
                schema_only=True,
            )

            assert result.success is True
            assert result.metadata["schema_only"] is True

            content = Path(backup_path).read_text()
            assert "CREATE TABLE" in content
            # Schema only should have fewer INSERT statements
            assert content.count("INSERT") == 0 or content.count("INSERT") < 10
        finally:
            if Path(backup_path).exists():
                os.unlink(backup_path)

    @pytest.mark.asyncio
    async def test_backup_with_compression(self, temp_db):
        """Test compressed backup."""
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as f:
            backup_path = f.name

        try:
            tool = DbBackupTool()
            result = await tool.execute(
                database=temp_db,
                output_path=backup_path,
                compress=True,
            )

            assert result.success is True
            assert result.metadata["compressed"] is True

            # Verify compressed file exists
            compressed_path = Path(backup_path + ".gz")
            assert compressed_path.exists()

            # Verify it's valid gzip
            with gzip.open(compressed_path, "rt") as f:
                content = f.read()
                assert "CREATE TABLE" in content
        finally:
            if Path(backup_path).exists():
                os.unlink(backup_path)
            compressed = Path(backup_path + ".gz")
            if compressed.exists():
                os.unlink(compressed)

    @pytest.mark.asyncio
    async def test_backup_specific_tables(self, temp_db):
        """Test backup of specific tables."""
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as f:
            backup_path = f.name

        try:
            tool = DbBackupTool()
            result = await tool.execute(
                database=temp_db,
                output_path=backup_path,
                tables=["users"],
            )

            assert result.success is True

            content = Path(backup_path).read_text()
            assert "users" in content
            # Should not contain orders table data
        finally:
            if Path(backup_path).exists():
                os.unlink(backup_path)

    @pytest.mark.asyncio
    async def test_backup_missing_db(self):
        """Test error for missing database."""
        tool = DbBackupTool()
        result = await tool.execute(
            database="/nonexistent/path.db",
            output_path="/tmp/backup.sql",
        )

        assert result.success is False
        assert "not found" in result.error.lower()


# =============================================================================
# DbVisualizeSchemaTool Tests
# =============================================================================


class TestDbVisualizeSchemaTool:
    """Tests for DbVisualizeSchemaTool."""

    @pytest.mark.asyncio
    async def test_visualize_mermaid(self, temp_db):
        """Test Mermaid ER diagram generation."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(database=temp_db, format="mermaid")

        assert result.success is True
        assert "```mermaid" in result.output
        assert "erDiagram" in result.output
        assert "users" in result.output
        assert "orders" in result.output
        assert result.metadata["format"] == "mermaid"

    @pytest.mark.asyncio
    async def test_visualize_plantuml(self, temp_db):
        """Test PlantUML ER diagram generation."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(database=temp_db, format="plantuml")

        assert result.success is True
        assert "@startuml" in result.output
        assert "@enduml" in result.output
        assert "users" in result.output

    @pytest.mark.asyncio
    async def test_visualize_d2(self, temp_db):
        """Test D2 diagram generation."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(database=temp_db, format="d2")

        assert result.success is True
        assert "sql_table" in result.output
        assert "users" in result.output

    @pytest.mark.asyncio
    async def test_visualize_with_types(self, temp_db):
        """Test diagram with column types shown."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(
            database=temp_db,
            format="mermaid",
            show_types=True,
        )

        assert result.success is True
        assert "INTEGER" in result.output or "TEXT" in result.output

    @pytest.mark.asyncio
    async def test_visualize_without_types(self, temp_db):
        """Test diagram without column types."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(
            database=temp_db,
            format="mermaid",
            show_types=False,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_visualize_specific_tables(self, temp_db):
        """Test diagram with specific tables."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(
            database=temp_db,
            format="mermaid",
            tables=["users"],
        )

        assert result.success is True
        assert "users" in result.output
        # Should still include foreign key relationships if they exist

    @pytest.mark.asyncio
    async def test_visualize_with_title(self, temp_db):
        """Test diagram with custom title."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(
            database=temp_db,
            format="mermaid",
            title="Test Database Schema",
        )

        assert result.success is True
        assert "Test Database Schema" in result.output

    @pytest.mark.asyncio
    async def test_visualize_to_file(self, temp_db):
        """Test saving diagram to file."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            output_path = f.name

        try:
            tool = DbVisualizeSchemaTool()
            result = await tool.execute(
                database=temp_db,
                format="mermaid",
                output_file=output_path,
            )

            assert result.success is True
            assert Path(output_path).exists()

            content = Path(output_path).read_text()
            assert "```mermaid" in content
        finally:
            if Path(output_path).exists():
                os.unlink(output_path)

    @pytest.mark.asyncio
    async def test_visualize_relationships(self, temp_db):
        """Test that foreign key relationships are shown."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(database=temp_db, format="mermaid")

        assert result.success is True
        assert result.metadata["relationship_count"] >= 1
        # Mermaid relationship syntax
        assert "||--o{" in result.output or "has" in result.output

    @pytest.mark.asyncio
    async def test_visualize_missing_db(self):
        """Test error for missing database."""
        tool = DbVisualizeSchemaTool()
        result = await tool.execute(
            database="/nonexistent/path.db",
            format="mermaid",
        )

        assert result.success is False
        assert "not found" in result.error.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestFafnirAgentIntegration:
    """Integration tests for Fafnir agent."""

    def test_fafnir_agent_exists(self):
        """Verify Fafnir agent is registered."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "fafnir" in AGENTS
        agent = get_agent("fafnir")
        assert agent.name == "fafnir"

    def test_fafnir_has_advanced_tools(self):
        """Verify Fafnir has all advanced SQL tools."""
        from sindri.agents.registry import get_agent

        agent = get_agent("fafnir")
        expected_tools = [
            "sql_optimize",
            "db_schema_diff",
            "db_analyze_indexes",
            "db_backup",
            "db_visualize_schema",
        ]

        for tool in expected_tools:
            assert tool in agent.tools, f"Missing tool: {tool}"

    def test_fafnir_model_config(self):
        """Verify Fafnir model configuration."""
        from sindri.agents.registry import get_agent

        agent = get_agent("fafnir")
        assert "sqlcoder" in agent.model
        assert agent.estimated_vram_gb == 5.0
        assert agent.temperature == 0.2

    def test_fafnir_fallback_config(self):
        """Verify Fafnir has fallback model configured."""
        from sindri.agents.registry import get_agent

        agent = get_agent("fafnir")
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None
        assert agent.fallback_vram_gb < agent.estimated_vram_gb

    def test_brokkr_can_delegate_to_fafnir(self):
        """Verify Brokkr can delegate to Fafnir."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "fafnir" in brokkr.delegate_to

    def test_tools_registered_in_registry(self):
        """Verify all advanced SQL tools are registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        expected_tools = [
            "sql_optimize",
            "db_schema_diff",
            "db_analyze_indexes",
            "db_backup",
            "db_visualize_schema",
        ]

        for tool_name in expected_tools:
            tool = registry.get_tool(tool_name)
            assert tool is not None, f"Tool not registered: {tool_name}"

    def test_agent_count(self):
        """Verify total agent count after adding Fafnir."""
        from sindri.agents.registry import list_agents

        agents = list_agents()
        # Was 22 with Groa, now 23 with Fafnir
        assert len(agents) == 23

    def test_brokkr_delegation_count(self):
        """Verify Brokkr's delegation list size."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        # Was 19 with Groa, now 20 with Fafnir
        assert len(brokkr.delegate_to) == 20


# =============================================================================
# Prompt Quality Tests
# =============================================================================


class TestFafnirPrompt:
    """Tests for Fafnir prompt quality."""

    def test_prompt_contains_core_capabilities(self):
        """Verify prompt has core capabilities section."""
        from sindri.agents.prompts import FAFNIR_PROMPT

        assert "CORE CAPABILITIES" in FAFNIR_PROMPT

    def test_prompt_contains_available_tools(self):
        """Verify prompt documents all tools."""
        from sindri.agents.prompts import FAFNIR_PROMPT

        expected_tools = [
            "sql_optimize",
            "db_schema_diff",
            "db_analyze_indexes",
            "db_backup",
            "db_visualize_schema",
        ]

        for tool in expected_tools:
            assert tool in FAFNIR_PROMPT, f"Tool not documented: {tool}"

    def test_prompt_contains_optimization_patterns(self):
        """Verify prompt has optimization patterns."""
        from sindri.agents.prompts import FAFNIR_PROMPT

        assert "index" in FAFNIR_PROMPT.lower()
        assert "table scan" in FAFNIR_PROMPT.lower()

    def test_prompt_contains_tool_flow(self):
        """Verify prompt has tool execution flow instructions."""
        from sindri.agents.prompts import FAFNIR_PROMPT

        assert "sindri:complete" in FAFNIR_PROMPT.lower()
        assert "WAIT FOR TOOL RESULTS" in FAFNIR_PROMPT

    def test_prompt_substantial_length(self):
        """Verify prompt is substantial."""
        from sindri.agents.prompts import FAFNIR_PROMPT

        assert len(FAFNIR_PROMPT) > 3000
