"""SQL tools for Fenrir agent."""

import asyncio
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional, Any
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


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
                s = s[:w-3] + "..."
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
                "description": "Path to SQLite database file"
            },
            "query": {
                "type": "string",
                "description": "SQL query to execute"
            },
            "params": {
                "type": "array",
                "items": {"type": ["string", "number", "boolean", "null"]},
                "description": "Query parameters for prepared statements (optional)"
            },
            "allow_write": {
                "type": "boolean",
                "description": "Allow write operations (INSERT, UPDATE, DELETE). Default: false"
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum rows to return (default: 100, max: 1000)"
            },
            "timeout": {
                "type": "number",
                "description": "Query timeout in seconds (default: 30)"
            }
        },
        "required": ["database", "query"]
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
        **kwargs
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
                metadata={"database": str(db_path)}
            )

        # Check write permission
        if is_write and not allow_write:
            return ToolResult(
                success=False,
                output="",
                error="Write operations not allowed. Set allow_write=true to enable INSERT/UPDATE/DELETE/etc.",
                metadata={"query_type": "write", "database": str(db_path)}
            )

        # Cap max_rows
        max_rows = min(max_rows, self.MAX_ROWS_LIMIT)

        log.info(
            "sql_execute_query",
            database=str(db_path),
            query=query[:100],
            is_write=is_write,
            max_rows=max_rows
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

                    headers = [desc[0] for desc in cursor.description] if cursor.description else []
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
                timeout=timeout + 5  # Give extra buffer for connection
            )

            # Format output
            if result["type"] == "write":
                output = f"Write operation successful.\nRows affected: {result['rowcount']}"
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

            return ToolResult(
                success=True,
                output=output,
                metadata=metadata
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Query timed out after {timeout} seconds",
                metadata={"database": str(db_path)}
            )
        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path)}
            )
        except Exception as e:
            log.error("sql_execute_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Query execution failed: {str(e)}",
                metadata={"database": str(db_path)}
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
                "description": "Path to SQLite database file"
            },
            "table": {
                "type": "string",
                "description": "Specific table to describe (optional, defaults to all tables)"
            },
            "include_indexes": {
                "type": "boolean",
                "description": "Include index information (default: false)"
            },
            "include_sql": {
                "type": "boolean",
                "description": "Include CREATE statements (default: false)"
            }
        },
        "required": ["database"]
    }

    async def execute(
        self,
        database: str,
        table: Optional[str] = None,
        include_indexes: bool = False,
        include_sql: bool = False,
        **kwargs
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
                metadata={"database": str(db_path)}
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
                            table_info["foreign_keys"].append({
                                "column": fk[3],
                                "references_table": fk[2],
                                "references_column": fk[4],
                            })

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
                                table_info["indexes"].append({
                                    "name": idx_name,
                                    "unique": bool(idx[2]),
                                    "columns": [col[2] for col in idx_cols],
                                })

                    # Get CREATE statement if requested
                    if include_sql:
                        cursor.execute(
                            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                            (table_name,)
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
                    lines.append(f"  - {col['name']}: {col['type']} {nullable}{default}{pk}")

                # Foreign keys
                if info.get("foreign_keys"):
                    lines.append("\nForeign Keys:")
                    for fk in info["foreign_keys"]:
                        lines.append(f"  - {fk['column']} -> {fk['references_table']}.{fk['references_column']}")

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
                }
            )

        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path)}
            )
        except Exception as e:
            log.error("sql_schema_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get schema: {str(e)}",
                metadata={"database": str(db_path)}
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
                "description": "Path to SQLite database file"
            },
            "query": {
                "type": "string",
                "description": "SQL query to analyze"
            },
            "detailed": {
                "type": "boolean",
                "description": "Include detailed byte-code output (default: false)"
            }
        },
        "required": ["database", "query"]
    }

    async def execute(
        self,
        database: str,
        query: str,
        detailed: bool = False,
        **kwargs
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
                metadata={"database": str(db_path)}
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
                    result["plan"].append({
                        "id": row[0],
                        "parent": row[1],
                        "notused": row[2],
                        "detail": row[3],
                    })

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
                hints.append("- Full table scan detected. Consider adding an index on filtered columns.")
            if "SEARCH" in plan_text and "INDEX" in plan_text:
                hints.append("- Using index for search (efficient).")
            if "COVERING INDEX" in plan_text:
                hints.append("- Using covering index (very efficient - no table lookup needed).")
            if "TEMP B-TREE" in plan_text:
                hints.append("- Creating temporary B-tree for sorting/grouping. Consider adding index if query is slow.")
            if "CORRELATED SCALAR SUBQUERY" in plan_text:
                hints.append("- Correlated subquery detected. Consider rewriting as JOIN for better performance.")
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
                }
            )

        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database": str(db_path)}
            )
        except Exception as e:
            log.error("sql_explain_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to explain query: {str(e)}",
                metadata={"database": str(db_path)}
            )
