"""SQL tools for Fenrir agent."""

import asyncio
import re
import sqlite3
from typing import TYPE_CHECKING, Optional
import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    from faker import Faker

log = structlog.get_logger()


# Check if faker is available
try:
    from faker import Faker

    FAKER_AVAILABLE = True
except ImportError:
    FAKER_AVAILABLE = False


def _format_table(headers: list[str], rows: list[tuple]) -> str:
    """Format query results as a readable table.

    Args:
        headers: Column names
        rows: List of row tuples

    Returns:
        Formatted table string
    """
    if not rows:
        return "(no results)"

    # Calculate column widths
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val) if val is not None else "NULL"))

    # Cap column widths to prevent extremely wide output
    widths = [min(w, 50) for w in widths]

    # Build table
    lines = []

    # Header
    header_line = " | ".join(str(h)[:w].ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Rows
    for row in rows:
        row_parts = []
        for val, w in zip(row, widths):
            if val is None:
                s = "NULL"
            else:
                s = str(val)
            if len(s) > w:
                s = s[: w - 3] + "..."
            row_parts.append(s.ljust(w))
        lines.append(" | ".join(row_parts))

    return "\n".join(lines)


class ExecuteQueryTool(Tool):
    """Execute SQL queries against a SQLite database.

    Supports SELECT queries by default. Write operations (INSERT, UPDATE, DELETE)
    require explicit permission via the allow_write parameter.
    """

    name = "execute_query"
    description = """Execute SQL queries against a SQLite database.

Examples:
- execute_query(database="app.db", query="SELECT * FROM users LIMIT 10")
- execute_query(database="data.db", query="SELECT name, email FROM users WHERE active = 1")
- execute_query(database="app.db", query="INSERT INTO logs (msg) VALUES ('test')", allow_write=true)

Note: Write operations (INSERT, UPDATE, DELETE) require allow_write=true.
Results are limited to prevent memory issues."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "query": {"type": "string", "description": "SQL query to execute"},
            "params": {
                "type": "array",
                "items": {"type": ["string", "number", "boolean", "null"]},
                "description": "Query parameters for prepared statements (optional)",
            },
            "allow_write": {
                "type": "boolean",
                "description": "Allow write operations (INSERT, UPDATE, DELETE). Default: false",
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum rows to return (default: 100, max: 1000)",
            },
            "timeout": {
                "type": "number",
                "description": "Query timeout in seconds (default: 30)",
            },
        },
        "required": ["database", "query"],
    }

    # Default limits
    DEFAULT_MAX_ROWS = 100
    MAX_ROWS_LIMIT = 1000
    DEFAULT_TIMEOUT = 30.0

    # Write operation patterns
    WRITE_PATTERNS = [
        r"^\s*INSERT\s",
        r"^\s*UPDATE\s",
        r"^\s*DELETE\s",
        r"^\s*DROP\s",
        r"^\s*CREATE\s",
        r"^\s*ALTER\s",
        r"^\s*TRUNCATE\s",
        r"^\s*REPLACE\s",
    ]

    def _is_write_query(self, query: str) -> bool:
        """Check if query is a write operation."""
        query_upper = query.upper()
        for pattern in self.WRITE_PATTERNS:
            if re.match(pattern, query_upper, re.IGNORECASE):
                return True
        return False

    async def execute(
        self,
        database: str,
        query: str,
        params: Optional[list] = None,
        allow_write: bool = False,
        max_rows: int = DEFAULT_MAX_ROWS,
        timeout: float = DEFAULT_TIMEOUT,
        **kwargs,
    ) -> ToolResult:
        """Execute SQL query.

        Args:
            database: Path to SQLite database file
            query: SQL query to execute
            params: Query parameters for prepared statements
            allow_write: Allow write operations (default: False)
            max_rows: Maximum rows to return
            timeout: Query timeout in seconds

        Returns:
            ToolResult with query results or error
        """
        # Resolve database path
        db_path = self._resolve_path(database)

        # Validate database exists (for SELECT queries)
        is_write = self._is_write_query(query)
        if not is_write and not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        # Check write permission
        if is_write and not allow_write:
            return ToolResult(
                success=False,
                output="",
                error="Write operations not allowed. Set allow_write=true to enable INSERT/UPDATE/DELETE/etc.",
                metadata={"query_type": "write", "database": str(db_path)},
            )

        # Cap max_rows
        max_rows = min(max_rows, self.MAX_ROWS_LIMIT)

        log.info(
            "sql_execute_query",
            database=str(db_path),
            query=query[:100],
            is_write=is_write,
            max_rows=max_rows,
        )

        def _execute_in_thread():
            """Execute query in thread (sqlite3 is not async-native)."""
            conn = sqlite3.connect(str(db_path), timeout=timeout)
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Execute query
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if is_write:
                    # Commit write operations
                    conn.commit()
                    return {
                        "type": "write",
                        "rowcount": cursor.rowcount,
                        "lastrowid": cursor.lastrowid,
                    }
                else:
                    # Fetch results for SELECT
                    rows = cursor.fetchmany(max_rows + 1)
                    has_more = len(rows) > max_rows
                    if has_more:
                        rows = rows[:max_rows]

                    headers = (
                        [desc[0] for desc in cursor.description]
                        if cursor.description
                        else []
                    )
                    return {
                        "type": "select",
                        "headers": headers,
                        "rows": [tuple(row) for row in rows],
                        "row_count": len(rows),
                        "has_more": has_more,
                    }
            finally:
                conn.close()

        try:
            # Run in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _execute_in_thread),
                timeout=timeout + 5,  # Give extra buffer for connection
            )

            # Format output
            if result["type"] == "write":
                output = (
                    f"Write operation successful.\nRows affected: {result['rowcount']}"
                )
                if result["lastrowid"]:
                    output += f"\nLast inserted ID: {result['lastrowid']}"
                metadata = {
                    "type": "write",
                    "rows_affected": result["rowcount"],
                    "last_row_id": result["lastrowid"],
                }
            else:
                output = _format_table(result["headers"], result["rows"])
                if result["has_more"]:
                    output += f"\n\n(showing first {max_rows} rows, more available)"
                metadata = {
                    "type": "select",
                    "row_count": result["row_count"],
                    "column_count": len(result["headers"]),
                    "columns": result["headers"],
                    "has_more": result["has_more"],
                }

            return ToolResult(success=True, output=output, metadata=metadata)

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Query timed out after {timeout} seconds",
                metadata={"database": str(db_path)},
            )
        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path)},
            )
        except Exception as e:
            log.error("sql_execute_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Query execution failed: {str(e)}",
                metadata={"database": str(db_path)},
            )


class DescribeSchemaTool(Tool):
    """Get schema information from a SQLite database.

    Returns table names, column definitions, indexes, and other schema info.
    """

    name = "describe_schema"
    description = """Get schema information from a SQLite database.

Examples:
- describe_schema(database="app.db") - List all tables
- describe_schema(database="app.db", table="users") - Get columns for 'users' table
- describe_schema(database="app.db", include_indexes=true) - Include index information

Returns table names, column definitions, types, and constraints."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "table": {
                "type": "string",
                "description": "Specific table to describe (optional, defaults to all tables)",
            },
            "include_indexes": {
                "type": "boolean",
                "description": "Include index information (default: false)",
            },
            "include_sql": {
                "type": "boolean",
                "description": "Include CREATE statements (default: false)",
            },
        },
        "required": ["database"],
    }

    async def execute(
        self,
        database: str,
        table: Optional[str] = None,
        include_indexes: bool = False,
        include_sql: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Get schema information.

        Args:
            database: Path to SQLite database file
            table: Specific table to describe (optional)
            include_indexes: Include index information
            include_sql: Include CREATE statements

        Returns:
            ToolResult with schema information
        """
        db_path = self._resolve_path(database)

        if not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        log.info("sql_describe_schema", database=str(db_path), table=table)

        def _get_schema():
            """Get schema in thread."""
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()
                result = {"tables": {}}

                # Get list of tables
                if table:
                    tables = [(table,)]
                else:
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    )
                    tables = cursor.fetchall()

                for (table_name,) in tables:
                    table_info = {"columns": [], "primary_key": []}

                    # Get column info
                    cursor.execute(f"PRAGMA table_info('{table_name}')")
                    columns = cursor.fetchall()
                    for col in columns:
                        cid, name, dtype, notnull, default, pk = col
                        col_info = {
                            "name": name,
                            "type": dtype,
                            "nullable": not notnull,
                            "default": default,
                        }
                        table_info["columns"].append(col_info)
                        if pk:
                            table_info["primary_key"].append(name)

                    # Get foreign keys
                    cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
                    fks = cursor.fetchall()
                    if fks:
                        table_info["foreign_keys"] = []
                        for fk in fks:
                            table_info["foreign_keys"].append(
                                {
                                    "column": fk[3],
                                    "references_table": fk[2],
                                    "references_column": fk[4],
                                }
                            )

                    # Get indexes if requested
                    if include_indexes:
                        cursor.execute(f"PRAGMA index_list('{table_name}')")
                        indexes = cursor.fetchall()
                        if indexes:
                            table_info["indexes"] = []
                            for idx in indexes:
                                idx_name = idx[1]
                                cursor.execute(f"PRAGMA index_info('{idx_name}')")
                                idx_cols = cursor.fetchall()
                                table_info["indexes"].append(
                                    {
                                        "name": idx_name,
                                        "unique": bool(idx[2]),
                                        "columns": [col[2] for col in idx_cols],
                                    }
                                )

                    # Get CREATE statement if requested
                    if include_sql:
                        cursor.execute(
                            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                            (table_name,),
                        )
                        row = cursor.fetchone()
                        if row:
                            table_info["create_sql"] = row[0]

                    result["tables"][table_name] = table_info

                return result
            finally:
                conn.close()

        try:
            loop = asyncio.get_event_loop()
            schema = await loop.run_in_executor(None, _get_schema)

            # Format output
            lines = []
            for table_name, info in schema["tables"].items():
                lines.append(f"Table: {table_name}")
                lines.append("-" * (len(table_name) + 7))

                # Columns
                lines.append("Columns:")
                for col in info["columns"]:
                    nullable = "NULL" if col["nullable"] else "NOT NULL"
                    default = f" DEFAULT {col['default']}" if col["default"] else ""
                    pk = " [PK]" if col["name"] in info.get("primary_key", []) else ""
                    lines.append(
                        f"  - {col['name']}: {col['type']} {nullable}{default}{pk}"
                    )

                # Foreign keys
                if info.get("foreign_keys"):
                    lines.append("\nForeign Keys:")
                    for fk in info["foreign_keys"]:
                        lines.append(
                            f"  - {fk['column']} -> {fk['references_table']}.{fk['references_column']}"
                        )

                # Indexes
                if info.get("indexes"):
                    lines.append("\nIndexes:")
                    for idx in info["indexes"]:
                        unique = "UNIQUE " if idx["unique"] else ""
                        cols = ", ".join(idx["columns"])
                        lines.append(f"  - {idx['name']}: {unique}({cols})")

                # CREATE SQL
                if info.get("create_sql"):
                    lines.append(f"\nCREATE Statement:\n{info['create_sql']}")

                lines.append("")  # Blank line between tables

            output = "\n".join(lines).strip()
            if not output:
                output = "No tables found in database."

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "database": str(db_path),
                    "table_count": len(schema["tables"]),
                    "tables": list(schema["tables"].keys()),
                },
            )

        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path)},
            )
        except Exception as e:
            log.error("sql_schema_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get schema: {str(e)}",
                metadata={"database": str(db_path)},
            )


class ExplainQueryTool(Tool):
    """Explain a SQL query's execution plan.

    Uses SQLite's EXPLAIN QUERY PLAN to show how a query will be executed,
    helping optimize queries.
    """

    name = "explain_query"
    description = """Analyze and explain a SQL query's execution plan.

Examples:
- explain_query(database="app.db", query="SELECT * FROM users WHERE id = 1")
- explain_query(database="app.db", query="SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id")

Returns execution plan showing table scans, index usage, and join strategies.
Useful for optimizing slow queries."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "query": {"type": "string", "description": "SQL query to analyze"},
            "detailed": {
                "type": "boolean",
                "description": "Include detailed byte-code output (default: false)",
            },
        },
        "required": ["database", "query"],
    }

    async def execute(
        self, database: str, query: str, detailed: bool = False, **kwargs
    ) -> ToolResult:
        """Explain query execution plan.

        Args:
            database: Path to SQLite database file
            query: SQL query to analyze
            detailed: Include detailed byte-code output

        Returns:
            ToolResult with execution plan
        """
        db_path = self._resolve_path(database)

        if not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        log.info("sql_explain_query", database=str(db_path), query=query[:100])

        def _explain():
            """Get execution plan in thread."""
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()
                result = {"plan": [], "bytecode": None}

                # Get query plan
                cursor.execute(f"EXPLAIN QUERY PLAN {query}")
                plan_rows = cursor.fetchall()
                for row in plan_rows:
                    result["plan"].append(
                        {
                            "id": row[0],
                            "parent": row[1],
                            "notused": row[2],
                            "detail": row[3],
                        }
                    )

                # Get detailed bytecode if requested
                if detailed:
                    cursor.execute(f"EXPLAIN {query}")
                    bytecode_rows = cursor.fetchall()
                    result["bytecode"] = bytecode_rows

                return result
            finally:
                conn.close()

        try:
            loop = asyncio.get_event_loop()
            explain_result = await loop.run_in_executor(None, _explain)

            # Format output
            lines = ["Query Execution Plan:", "=" * 22, ""]

            # Build tree structure for plan
            if explain_result["plan"]:
                for step in explain_result["plan"]:
                    indent = "  " * step.get("parent", 0)
                    lines.append(f"{indent}{step['detail']}")
            else:
                lines.append("(empty plan - query may not access tables)")

            # Add analysis hints
            lines.append("")
            lines.append("Analysis:")
            lines.append("-" * 9)

            plan_text = " ".join(step["detail"] for step in explain_result["plan"])
            hints = []

            if "SCAN" in plan_text and "INDEX" not in plan_text:
                hints.append(
                    "- Full table scan detected. Consider adding an index on filtered columns."
                )
            if "SEARCH" in plan_text and "INDEX" in plan_text:
                hints.append("- Using index for search (efficient).")
            if "COVERING INDEX" in plan_text:
                hints.append(
                    "- Using covering index (very efficient - no table lookup needed)."
                )
            if "TEMP B-TREE" in plan_text:
                hints.append(
                    "- Creating temporary B-tree for sorting/grouping. Consider adding index if query is slow."
                )
            if "CORRELATED SCALAR SUBQUERY" in plan_text:
                hints.append(
                    "- Correlated subquery detected. Consider rewriting as JOIN for better performance."
                )
            if not hints:
                hints.append("- Query plan looks reasonable.")

            lines.extend(hints)

            # Detailed bytecode
            if detailed and explain_result["bytecode"]:
                lines.append("")
                lines.append("Bytecode (detailed):")
                lines.append("-" * 19)
                headers = ["addr", "opcode", "p1", "p2", "p3", "p4", "p5", "comment"]
                lines.append(_format_table(headers, explain_result["bytecode"]))

            output = "\n".join(lines)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "database": str(db_path),
                    "plan_steps": len(explain_result["plan"]),
                    "uses_index": "INDEX" in plan_text,
                    "has_table_scan": "SCAN" in plan_text and "INDEX" not in plan_text,
                },
            )

        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path)},
            )
        except Exception as e:
            log.error("sql_explain_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to explain query: {str(e)}",
                metadata={"database": str(db_path)},
            )


class SqlGenerateTool(Tool):
    """Generate SQL queries from natural language descriptions.

    Uses pattern matching to convert common query descriptions into SQL.
    Optionally validates against the database schema.
    """

    name = "sql_generate"
    description = """Generate SQL queries from natural language descriptions.

Examples:
- sql_generate(description="Get all users")
- sql_generate(description="Find active users where age > 25", database="app.db")
- sql_generate(description="Count orders per customer", database="app.db")
- sql_generate(description="Top 10 products by price", database="app.db", table="products")

Returns generated SQL query. Use with execute_query to run the query."""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of the query",
            },
            "database": {
                "type": "string",
                "description": "Path to database file (optional, for schema context and validation)",
            },
            "table": {
                "type": "string",
                "description": "Primary table name (optional, will infer from description)",
            },
            "dialect": {
                "type": "string",
                "enum": ["sqlite", "postgresql", "mysql"],
                "description": "SQL dialect (default: sqlite)",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated SQL against schema (default: true if database provided)",
            },
        },
        "required": ["description"],
    }

    # Query patterns for natural language parsing
    QUERY_PATTERNS = {
        # SELECT patterns
        "select_all": [
            r"^(get|find|show|list|select|fetch|retrieve)\s+(all\s+)?(\w+)$",
            r"^(get|find|show|list)\s+everything\s+(from\s+)?(\w+)$",
        ],
        "select_where": [
            r"^(get|find|show|list|select)\s+(all\s+)?(\w+)\s+(where|with|having)\s+(.+)$",
            r"^(get|find|show|list)\s+(\w+)\s+(that|which)\s+(are|is|have|has)\s+(.+)$",
        ],
        "count": [
            r"^count\s+(all\s+)?(\w+)$",
            r"^how\s+many\s+(\w+)(\s+are\s+there)?$",
            r"^(get|find)\s+(the\s+)?(count|number)\s+of\s+(\w+)$",
        ],
        "count_where": [
            r"^count\s+(\w+)\s+(where|with|having)\s+(.+)$",
            r"^how\s+many\s+(\w+)\s+(where|with|having|are)\s+(.+)$",
        ],
        "top_n": [
            r"^(top|first)\s+(\d+)\s+(\w+)(\s+by\s+(\w+))?(\s+(asc|desc))?$",
            r"^(get|find|show)\s+(the\s+)?(top|first)\s+(\d+)\s+(\w+)(\s+by\s+(\w+))?$",
        ],
        "group_by": [
            r"^(count|sum|avg|average|min|max)\s+(\w+)\s+(per|by|for each|grouped by)\s+(\w+)$",
            r"^(\w+)\s+(per|by|for each)\s+(\w+)$",
        ],
        "join": [
            r"^(get|find|show|list)\s+(\w+)\s+with\s+(their\s+)?(\w+)$",
            r"^(get|find|show)\s+(\w+)\s+(and|with)\s+(\w+)\s+from\s+(\w+)$",
        ],
        "order_by": [
            r"^(get|find|show|list)\s+(all\s+)?(\w+)\s+(sorted|ordered)\s+by\s+(\w+)(\s+(asc|desc))?$",
        ],
        "distinct": [
            r"^(get|find|show|list)\s+(unique|distinct)\s+(\w+)(\s+from\s+(\w+))?$",
        ],
    }

    # Column/condition patterns
    CONDITION_PATTERNS = {
        "equals": r"(\w+)\s*=\s*['\"]?([^'\"]+)['\"]?",
        "not_equals": r"(\w+)\s*(!?=|<>)\s*['\"]?([^'\"]+)['\"]?",
        "greater": r"(\w+)\s*>\s*(\d+(?:\.\d+)?)",
        "less": r"(\w+)\s*<\s*(\d+(?:\.\d+)?)",
        "like": r"(\w+)\s+(like|contains|starts with|ends with)\s+['\"]?([^'\"]+)['\"]?",
        "is_true": r"(\w+)\s+is\s+(true|active|enabled)",
        "is_false": r"(\w+)\s+is\s+(false|inactive|disabled)",
        "is_null": r"(\w+)\s+is\s+(null|empty|none)",
        "is_not_null": r"(\w+)\s+is\s+not\s+(null|empty|none)",
    }

    def _parse_description(self, description: str, table_hint: Optional[str] = None) -> dict:
        """Parse natural language description into query components.

        Args:
            description: Natural language query description
            table_hint: Optional table name hint

        Returns:
            Dict with query_type, table, columns, conditions, etc.
        """
        desc_lower = description.lower().strip()
        result = {
            "query_type": "select",
            "table": table_hint,
            "columns": ["*"],
            "conditions": [],
            "order_by": None,
            "limit": None,
            "group_by": None,
            "aggregate": None,
            "join": None,
        }

        # Try to match patterns
        for pattern_type, patterns in self.QUERY_PATTERNS.items():
            for pattern in patterns:
                match = re.match(pattern, desc_lower, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    return self._process_pattern_match(pattern_type, groups, result, desc_lower)

        # Fallback: extract table from description if not matched
        words = desc_lower.split()
        for i, word in enumerate(words):
            if word in ("from", "in"):
                if i + 1 < len(words):
                    result["table"] = words[i + 1].rstrip("s")  # Singularize
                    break

        # If still no table, use the first noun-like word
        if not result["table"]:
            for word in words:
                if word not in (
                    "get",
                    "find",
                    "show",
                    "list",
                    "all",
                    "the",
                    "a",
                    "an",
                    "select",
                    "from",
                    "where",
                ):
                    result["table"] = word
                    break

        return result

    def _process_pattern_match(
        self, pattern_type: str, groups: tuple, result: dict, description: str
    ) -> dict:
        """Process a matched pattern and update result dict."""
        if pattern_type == "select_all":
            # Groups: (verb, 'all ', table)
            result["table"] = groups[-1] if groups[-1] else groups[-2]

        elif pattern_type == "select_where":
            # Groups: (verb, 'all ', table, 'where', condition)
            result["table"] = groups[2] if len(groups) > 2 else groups[1]
            if len(groups) > 4:
                result["conditions"] = [self._parse_condition(groups[-1])]
            elif len(groups) > 3:
                result["conditions"] = [self._parse_condition(groups[-1])]

        elif pattern_type == "count":
            result["query_type"] = "count"
            result["aggregate"] = "COUNT"
            # Find the table name
            for g in groups:
                if g and g not in ("all ", "the ", "count", "number"):
                    result["table"] = g
                    break

        elif pattern_type == "count_where":
            result["query_type"] = "count"
            result["aggregate"] = "COUNT"
            result["table"] = groups[0]
            if len(groups) > 2:
                result["conditions"] = [self._parse_condition(groups[-1])]

        elif pattern_type == "top_n":
            # Groups vary: (verb?, 'the '?, 'top', n, table, 'by col', col, 'asc/desc')
            for g in groups:
                if g and g.isdigit():
                    result["limit"] = int(g)
                elif g and g not in ("top", "first", "get", "find", "show", "the "):
                    if not g.startswith("by") and not g in ("asc", "desc"):
                        result["table"] = g
                    elif g in ("asc", "desc"):
                        result["order_by"] = (result.get("order_by_col"), g.upper())
                    elif g.startswith("by"):
                        result["order_by_col"] = g[3:] if g.startswith("by ") else None
            # Extract order_by column from description if present
            by_match = re.search(r"by\s+(\w+)", description)
            if by_match:
                direction = "DESC"  # Default for "top N" is descending
                if "asc" in description.lower():
                    direction = "ASC"
                result["order_by"] = (by_match.group(1), direction)

        elif pattern_type == "group_by":
            # Groups: (agg, col, 'per', group_col) or (col, 'per', group_col)
            result["query_type"] = "aggregate"
            if groups[0].upper() in ("COUNT", "SUM", "AVG", "AVERAGE", "MIN", "MAX"):
                result["aggregate"] = groups[0].upper().replace("AVERAGE", "AVG")
                result["columns"] = [groups[1]]
                result["group_by"] = groups[-1]
                result["table"] = groups[1]  # Infer table from column
            else:
                result["aggregate"] = "COUNT"
                result["columns"] = [groups[0]]
                result["group_by"] = groups[-1]
                result["table"] = groups[0]

        elif pattern_type == "join":
            # Groups: (verb, table1, 'their ', table2)
            result["table"] = groups[1]
            result["join"] = {"table": groups[-1], "type": "LEFT"}

        elif pattern_type == "order_by":
            result["table"] = groups[2] if groups[2] else groups[1]
            direction = groups[-1].upper() if groups[-1] else "ASC"
            result["order_by"] = (groups[-3] or groups[-2], direction)

        elif pattern_type == "distinct":
            result["query_type"] = "distinct"
            result["columns"] = [groups[2]]
            if groups[-1]:
                result["table"] = groups[-1]
            else:
                result["table"] = groups[2]

        return result

    def _parse_condition(self, condition_str: str) -> str:
        """Parse a condition string into SQL WHERE clause."""
        condition_str = condition_str.strip()

        # Check for explicit comparisons
        for pattern_name, pattern in self.CONDITION_PATTERNS.items():
            match = re.search(pattern, condition_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                col = groups[0]

                if pattern_name == "equals":
                    val = groups[1]
                    if val.isdigit():
                        return f"{col} = {val}"
                    return f"{col} = '{val}'"
                elif pattern_name == "greater":
                    return f"{col} > {groups[1]}"
                elif pattern_name == "less":
                    return f"{col} < {groups[1]}"
                elif pattern_name == "like":
                    val = groups[2]
                    if "starts with" in condition_str.lower():
                        return f"{col} LIKE '{val}%'"
                    elif "ends with" in condition_str.lower():
                        return f"{col} LIKE '%{val}'"
                    else:
                        return f"{col} LIKE '%{val}%'"
                elif pattern_name == "is_true":
                    return f"{col} = 1"
                elif pattern_name == "is_false":
                    return f"{col} = 0"
                elif pattern_name == "is_null":
                    return f"{col} IS NULL"
                elif pattern_name == "is_not_null":
                    return f"{col} IS NOT NULL"

        # Fallback: try to interpret as "column = value" or boolean
        words = condition_str.split()
        if len(words) >= 1:
            col = words[0]
            if len(words) == 1:
                # Single word might be a boolean column
                return f"{col} = 1"
            elif len(words) >= 2:
                # Try to extract value
                val = " ".join(words[1:])
                if val.isdigit():
                    return f"{col} = {val}"
                return f"{col} = '{val}'"

        return condition_str

    def _build_sql(self, parsed: dict, schema_info: Optional[dict] = None) -> str:
        """Build SQL query from parsed components.

        Args:
            parsed: Parsed query components
            schema_info: Optional schema information for validation

        Returns:
            SQL query string
        """
        table = parsed["table"]
        if not table:
            return "-- Could not determine table from description"

        # Clean up table name (remove trailing 's' for plurals if needed)
        if schema_info and table not in schema_info.get("tables", {}):
            # Try singular form
            singular = table.rstrip("s")
            if singular in schema_info.get("tables", {}):
                table = singular

        query_type = parsed["query_type"]

        if query_type == "count":
            sql = f"SELECT COUNT(*) FROM {table}"
        elif query_type == "aggregate":
            agg = parsed["aggregate"]
            col = parsed["columns"][0] if parsed["columns"] else "*"
            group_col = parsed["group_by"]
            sql = f"SELECT {group_col}, {agg}({col}) FROM {table}"
            if group_col:
                sql += f" GROUP BY {group_col}"
        elif query_type == "distinct":
            col = parsed["columns"][0] if parsed["columns"] else "*"
            sql = f"SELECT DISTINCT {col} FROM {table}"
        else:
            # Regular SELECT
            columns = ", ".join(parsed["columns"])
            sql = f"SELECT {columns} FROM {table}"

        # Add JOIN
        if parsed.get("join"):
            join_info = parsed["join"]
            join_table = join_info["table"]
            join_type = join_info.get("type", "LEFT")
            # Infer join condition (assume table_id pattern)
            join_col = f"{table.rstrip('s')}_id"
            sql += f" {join_type} JOIN {join_table} ON {table}.id = {join_table}.{join_col}"

        # Add WHERE
        if parsed["conditions"]:
            where_clauses = " AND ".join(c for c in parsed["conditions"] if c)
            if where_clauses:
                sql += f" WHERE {where_clauses}"

        # Add ORDER BY
        if parsed["order_by"]:
            col, direction = parsed["order_by"]
            sql += f" ORDER BY {col} {direction}"

        # Add LIMIT
        if parsed["limit"]:
            sql += f" LIMIT {parsed['limit']}"

        return sql

    def _get_schema_info(self, db_path: str) -> Optional[dict]:
        """Get schema information from database."""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get tables
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = {row[0]: {} for row in cursor.fetchall()}

            # Get columns for each table
            for table_name in tables:
                cursor.execute(f"PRAGMA table_info('{table_name}')")
                columns = cursor.fetchall()
                tables[table_name] = {col[1]: col[2] for col in columns}

            conn.close()
            return {"tables": tables}
        except Exception:
            return None

    def _validate_sql(self, sql: str, db_path: str) -> tuple[bool, str]:
        """Validate SQL against database schema.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # Use EXPLAIN to check syntax without executing
            cursor.execute(f"EXPLAIN {sql}")
            conn.close()
            return True, ""
        except sqlite3.Error as e:
            return False, str(e)

    async def execute(
        self,
        description: str,
        database: Optional[str] = None,
        table: Optional[str] = None,
        dialect: str = "sqlite",
        validate: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Generate SQL from natural language description.

        Args:
            description: Natural language description of the query
            database: Optional database path for schema context
            table: Optional primary table name
            dialect: SQL dialect (default: sqlite)
            validate: Validate generated SQL against schema

        Returns:
            ToolResult with generated SQL
        """
        log.info("sql_generate", description=description[:100], table=table)

        # Get schema info if database provided
        schema_info = None
        if database:
            db_path = self._resolve_path(database)
            if db_path.exists():
                schema_info = self._get_schema_info(str(db_path))

        # Parse description
        parsed = self._parse_description(description, table)

        # If table hint provided, use it
        if table:
            parsed["table"] = table
        # If schema available and table not found, try to match
        elif schema_info and not parsed["table"]:
            tables = list(schema_info.get("tables", {}).keys())
            if len(tables) == 1:
                parsed["table"] = tables[0]

        # Build SQL
        sql = self._build_sql(parsed, schema_info)

        # Validate if requested and database provided
        validation_note = ""
        if validate and database:
            db_path = self._resolve_path(database)
            if db_path.exists():
                is_valid, error = self._validate_sql(sql, str(db_path))
                if not is_valid:
                    validation_note = f"\n\n⚠️ Validation warning: {error}"

        output = f"Generated SQL:\n\n{sql}{validation_note}"

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "sql": sql,
                "parsed": {
                    "table": parsed.get("table"),
                    "query_type": parsed.get("query_type"),
                    "has_conditions": bool(parsed.get("conditions")),
                    "has_order": bool(parsed.get("order_by")),
                    "has_limit": bool(parsed.get("limit")),
                    "has_join": bool(parsed.get("join")),
                },
                "dialect": dialect,
                "validated": validate and database is not None,
            },
        )


class DbSeedTool(Tool):
    """Generate realistic test data for database tables using Faker.

    Automatically detects appropriate data generators based on column names.
    """

    name = "db_seed"
    description = """Generate realistic test data for a database table using Faker.

Examples:
- db_seed(database="app.db", table="users", rows=100)
- db_seed(database="app.db", table="orders", rows=50, seed=42)
- db_seed(database="app.db", table="products", rows=20, clear_existing=true)

Automatically detects data types from column names (email, name, phone, etc.)."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "table": {
                "type": "string",
                "description": "Table name to seed with data",
            },
            "rows": {
                "type": "integer",
                "description": "Number of rows to generate (default: 10, max: 10000)",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducible data generation",
            },
            "locale": {
                "type": "string",
                "description": "Faker locale for localized data (default: en_US)",
            },
            "batch_size": {
                "type": "integer",
                "description": "Rows per INSERT batch (default: 100)",
            },
            "clear_existing": {
                "type": "boolean",
                "description": "Delete existing rows before seeding (default: false)",
            },
        },
        "required": ["database", "table"],
    }

    # Default row limits
    DEFAULT_ROWS = 10
    MAX_ROWS = 10000
    DEFAULT_BATCH_SIZE = 100

    # Column name to Faker method mapping
    COLUMN_FAKER_MAP = {
        # Names
        "name": "name",
        "full_name": "name",
        "first_name": "first_name",
        "last_name": "last_name",
        "username": "user_name",
        "user_name": "user_name",
        # Contact
        "email": "email",
        "phone": "phone_number",
        "phone_number": "phone_number",
        "mobile": "phone_number",
        "address": "address",
        "street": "street_address",
        "city": "city",
        "state": "state",
        "country": "country",
        "zip": "zipcode",
        "zipcode": "zipcode",
        "postal": "zipcode",
        "postal_code": "zipcode",
        # Dates
        "created_at": "date_time",
        "updated_at": "date_time",
        "birth_date": "date_of_birth",
        "birthday": "date_of_birth",
        "date": "date",
        "datetime": "date_time",
        "timestamp": "date_time",
        # Text content
        "description": "text",
        "content": "paragraph",
        "body": "paragraph",
        "title": "sentence",
        "headline": "sentence",
        "summary": "sentence",
        "bio": "paragraph",
        "about": "paragraph",
        # Business
        "company": "company",
        "company_name": "company",
        "job": "job",
        "job_title": "job",
        "position": "job",
        "department": "bs",
        # Money
        "price": "pydecimal",
        "amount": "pydecimal",
        "cost": "pydecimal",
        "total": "pydecimal",
        "salary": "pydecimal",
        # Identifiers
        "uuid": "uuid4",
        "guid": "uuid4",
        "url": "url",
        "website": "url",
        "ip": "ipv4",
        "ip_address": "ipv4",
        # Product
        "product": "word",
        "product_name": "word",
        "category": "word",
        "color": "color_name",
        "size": "word",
        # Status
        "status": "word",
        "active": "boolean",
        "enabled": "boolean",
        "verified": "boolean",
        "is_active": "boolean",
    }

    def _get_faker_method(
        self, column_name: str, column_type: str, faker: "Faker"
    ) -> callable:
        """Get appropriate Faker method for a column.

        Args:
            column_name: Name of the column
            column_type: SQLite column type
            faker: Faker instance

        Returns:
            Callable that generates appropriate data
        """
        col_lower = column_name.lower()

        # Check column name mapping first
        if col_lower in self.COLUMN_FAKER_MAP:
            method_name = self.COLUMN_FAKER_MAP[col_lower]
            method = getattr(faker, method_name, None)
            if method:
                # Special handling for decimal types
                if method_name == "pydecimal":
                    return lambda: float(faker.pydecimal(min_value=1, max_value=1000, right_digits=2))
                return method

        # Check for partial matches
        for pattern, method_name in self.COLUMN_FAKER_MAP.items():
            if pattern in col_lower:
                method = getattr(faker, method_name, None)
                if method:
                    if method_name == "pydecimal":
                        return lambda: float(faker.pydecimal(min_value=1, max_value=1000, right_digits=2))
                    return method

        # Fall back to type-based generation
        type_upper = column_type.upper() if column_type else "TEXT"

        if "INT" in type_upper:
            return lambda: faker.random_int(min=1, max=10000)
        elif "REAL" in type_upper or "FLOAT" in type_upper or "DOUBLE" in type_upper:
            return lambda: float(faker.pydecimal(min_value=1, max_value=1000, right_digits=2))
        elif "BOOL" in type_upper:
            return faker.boolean
        elif "DATE" in type_upper or "TIME" in type_upper:
            return faker.date_time
        else:
            # Default to text
            return lambda: faker.sentence(nb_words=4)

    def _get_table_info(self, conn: sqlite3.Connection, table: str) -> list[dict]:
        """Get column information for a table.

        Returns:
            List of dicts with column info (name, type, nullable, pk, has_default)
        """
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info('{table}')")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "not_null": bool(row[3]),
                "default": row[4],
                "pk": bool(row[5]),
            })
        return columns

    def _get_foreign_keys(self, conn: sqlite3.Connection, table: str) -> dict:
        """Get foreign key constraints for a table.

        Returns:
            Dict mapping column name to (ref_table, ref_column)
        """
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA foreign_key_list('{table}')")
        fks = {}
        for row in cursor.fetchall():
            fks[row[3]] = (row[2], row[4])  # column -> (ref_table, ref_column)
        return fks

    def _get_valid_fk_values(
        self, conn: sqlite3.Connection, ref_table: str, ref_column: str
    ) -> list:
        """Get valid values for a foreign key column."""
        cursor = conn.cursor()
        cursor.execute(f"SELECT {ref_column} FROM {ref_table}")
        return [row[0] for row in cursor.fetchall()]

    async def execute(
        self,
        database: str,
        table: str,
        rows: int = DEFAULT_ROWS,
        seed: Optional[int] = None,
        locale: str = "en_US",
        batch_size: int = DEFAULT_BATCH_SIZE,
        clear_existing: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate and insert test data.

        Args:
            database: Path to SQLite database file
            table: Table name to seed
            rows: Number of rows to generate
            seed: Random seed for reproducibility
            locale: Faker locale
            batch_size: Rows per INSERT batch
            clear_existing: Delete existing rows before seeding

        Returns:
            ToolResult with seeding results
        """
        if not FAKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Faker library not installed. Install with: pip install faker",
                suggestion="Run: pip install faker>=24.0.0",
            )

        db_path = self._resolve_path(database)
        if not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        # Cap rows
        rows = min(rows, self.MAX_ROWS)

        log.info(
            "db_seed",
            database=str(db_path),
            table=table,
            rows=rows,
            seed=seed,
        )

        def _seed_in_thread():
            """Execute seeding in thread."""
            # Import here to avoid issues if not installed
            from faker import Faker as FakerClass

            faker = FakerClass(locale)
            if seed is not None:
                FakerClass.seed(seed)

            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()

                # Verify table exists
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                if not cursor.fetchone():
                    return {"error": f"Table '{table}' not found in database"}

                # Get table structure
                columns = self._get_table_info(conn, table)
                fks = self._get_foreign_keys(conn, table)

                # Get valid FK values
                fk_values = {}
                for col, (ref_table, ref_col) in fks.items():
                    values = self._get_valid_fk_values(conn, ref_table, ref_col)
                    if values:
                        fk_values[col] = values

                # Filter out auto-increment primary keys
                insertable_columns = [
                    c for c in columns
                    if not (c["pk"] and c["type"].upper() == "INTEGER")
                ]

                if not insertable_columns:
                    return {"error": "No insertable columns found (all are auto-increment PKs)"}

                # Clear existing data if requested
                deleted = 0
                if clear_existing:
                    cursor.execute(f"DELETE FROM {table}")
                    deleted = cursor.rowcount
                    conn.commit()

                # Generate data
                col_names = [c["name"] for c in insertable_columns]
                col_types = {c["name"]: c["type"] for c in insertable_columns}

                # Get Faker methods for each column
                faker_methods = {}
                for col in insertable_columns:
                    col_name = col["name"]
                    if col_name in fks and col_name in fk_values:
                        # Foreign key: select from valid values
                        valid = fk_values[col_name]
                        faker_methods[col_name] = lambda v=valid: faker.random_element(v)
                    else:
                        faker_methods[col_name] = self._get_faker_method(
                            col_name, col_types[col_name], faker
                        )

                # Insert in batches
                inserted = 0
                placeholders = ", ".join(["?" for _ in col_names])
                insert_sql = f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})"

                batch = []
                for _ in range(rows):
                    row_data = []
                    for col_name in col_names:
                        value = faker_methods[col_name]()
                        # Convert special types
                        if hasattr(value, "isoformat"):  # datetime
                            value = value.isoformat()
                        elif isinstance(value, bool):
                            value = 1 if value else 0
                        row_data.append(value)
                    batch.append(tuple(row_data))

                    if len(batch) >= batch_size:
                        cursor.executemany(insert_sql, batch)
                        inserted += len(batch)
                        batch = []

                # Insert remaining
                if batch:
                    cursor.executemany(insert_sql, batch)
                    inserted += len(batch)

                conn.commit()

                # Get sample data
                cursor.execute(f"SELECT * FROM {table} LIMIT 5")
                sample_rows = cursor.fetchall()
                sample_headers = [desc[0] for desc in cursor.description]

                return {
                    "inserted": inserted,
                    "deleted": deleted,
                    "columns": col_names,
                    "sample_headers": sample_headers,
                    "sample_rows": sample_rows,
                }
            finally:
                conn.close()

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _seed_in_thread)

            if "error" in result:
                return ToolResult(
                    success=False,
                    output="",
                    error=result["error"],
                    metadata={"database": str(db_path), "table": table},
                )

            # Format output
            lines = [f"✓ Seeded {result['inserted']} rows into '{table}'"]
            if result["deleted"]:
                lines.append(f"  (deleted {result['deleted']} existing rows)")
            lines.append("")
            lines.append("Columns seeded:")
            for col in result["columns"]:
                lines.append(f"  - {col}")
            lines.append("")
            lines.append("Sample data:")
            lines.append(_format_table(result["sample_headers"], result["sample_rows"]))

            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={
                    "database": str(db_path),
                    "table": table,
                    "rows_inserted": result["inserted"],
                    "rows_deleted": result["deleted"],
                    "columns": result["columns"],
                    "seed": seed,
                },
            )

        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path), "table": table},
            )
        except Exception as e:
            log.error("db_seed_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to seed database: {str(e)}",
                metadata={"database": str(db_path), "table": table},
            )
