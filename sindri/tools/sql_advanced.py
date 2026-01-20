"""Advanced SQL tools for Fafnir agent.

Provides advanced database optimization, schema comparison, index analysis,
backup, and visualization capabilities.
"""

import asyncio
import gzip
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


def _format_table(headers: list[str], rows: list[tuple]) -> str:
    """Format query results as a readable table."""
    if not rows:
        return "(no results)"

    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val) if val is not None else "NULL"))

    widths = [min(w, 50) for w in widths]

    lines = []
    header_line = " | ".join(str(h)[:w].ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))

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


def _detect_db_type(database: str) -> str:
    """Detect database type from path or connection string.

    Returns: 'sqlite', 'postgresql', or 'mysql'
    """
    if database.startswith("postgresql://") or database.startswith("postgres://"):
        return "postgresql"
    elif database.startswith("mysql://"):
        return "mysql"
    else:
        return "sqlite"


def _get_schema_info(conn: sqlite3.Connection) -> dict:
    """Extract full schema information from SQLite database.

    Returns:
        Dict with tables, each containing columns, indexes, foreign_keys
    """
    cursor = conn.cursor()
    schema = {"tables": {}}

    # Get all tables
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    for table_name in tables:
        table_info = {
            "columns": {},
            "primary_key": [],
            "indexes": [],
            "foreign_keys": [],
        }

        # Get columns
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        for row in cursor.fetchall():
            cid, name, dtype, notnull, default, pk = row
            table_info["columns"][name] = {
                "cid": cid,
                "type": dtype,
                "notnull": bool(notnull),
                "default": default,
                "pk": bool(pk),
            }
            if pk:
                table_info["primary_key"].append(name)

        # Get indexes
        cursor.execute(f"PRAGMA index_list('{table_name}')")
        for idx_row in cursor.fetchall():
            idx_name = idx_row[1]
            is_unique = bool(idx_row[2])
            cursor.execute(f"PRAGMA index_info('{idx_name}')")
            idx_cols = [col[2] for col in cursor.fetchall()]
            table_info["indexes"].append({
                "name": idx_name,
                "unique": is_unique,
                "columns": idx_cols,
            })

        # Get foreign keys
        cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
        for fk_row in cursor.fetchall():
            table_info["foreign_keys"].append({
                "column": fk_row[3],
                "ref_table": fk_row[2],
                "ref_column": fk_row[4],
            })

        schema["tables"][table_name] = table_info

    return schema


class SqlOptimizeTool(Tool):
    """Analyze and optimize SQL queries.

    Provides detailed execution plan analysis with specific optimization
    recommendations based on table scans, index usage, and query patterns.
    """

    name = "sql_optimize"
    description = """Analyze a SQL query and suggest optimizations.

Examples:
- sql_optimize(database="app.db", query="SELECT * FROM users WHERE email = 'test@example.com'")
- sql_optimize(database="data.db", query="SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id WHERE u.status = 'active'")

Returns execution plan analysis with specific optimization recommendations."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "query": {
                "type": "string",
                "description": "SQL query to analyze and optimize",
            },
            "context": {
                "type": "string",
                "description": "Additional context about the query (e.g., expected row counts, usage patterns)",
            },
        },
        "required": ["database", "query"],
    }

    async def execute(
        self,
        database: str,
        query: str,
        context: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Analyze query and provide optimization recommendations.

        Args:
            database: Path to SQLite database file
            query: SQL query to analyze
            context: Additional context for optimization suggestions

        Returns:
            ToolResult with optimization analysis
        """
        db_path = self._resolve_path(database)

        if not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        log.info("sql_optimize", database=str(db_path), query=query[:100])

        def _analyze():
            """Analyze query in thread."""
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()

                # Get execution plan
                cursor.execute(f"EXPLAIN QUERY PLAN {query}")
                plan_rows = cursor.fetchall()

                # Get table statistics for recommendations
                tables_in_query = set()
                table_stats = {}

                # Build alias to table mapping from the query
                alias_to_table = {}
                # Match patterns like "FROM users u" or "JOIN orders o"
                alias_patterns = [
                    r"FROM\s+(\w+)\s+(\w+)(?:\s|$|,)",  # FROM table alias
                    r"JOIN\s+(\w+)\s+(\w+)(?:\s|$)",    # JOIN table alias
                    r"FROM\s+(\w+)(?:\s|$|,)",          # FROM table (no alias)
                    r"JOIN\s+(\w+)(?:\s|$)",            # JOIN table (no alias)
                ]
                for pattern in alias_patterns:
                    for match in re.finditer(pattern, query, re.IGNORECASE):
                        table = match.group(1)
                        if len(match.groups()) > 1 and match.group(2):
                            alias = match.group(2)
                            # Skip SQL keywords that might be matched
                            if alias.upper() not in {"ON", "WHERE", "AND", "OR", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS", "NATURAL"}:
                                alias_to_table[alias] = table
                        # Also map table name to itself
                        alias_to_table[table] = table

                # Parse tables from plan and resolve aliases
                for row in plan_rows:
                    detail = row[3] if len(row) > 3 else ""
                    # Extract table/alias names from SCAN/SEARCH operations
                    match = re.search(r"(?:SCAN|SEARCH)\s+(?:TABLE\s+)?(\w+)", detail)
                    if match:
                        name = match.group(1)
                        # Resolve alias to actual table name
                        table_name = alias_to_table.get(name, name)
                        tables_in_query.add(table_name)

                # If plan didn't reveal tables, use parsed tables directly
                if not tables_in_query:
                    tables_in_query.update(alias_to_table.values())

                # Get row counts and schema for referenced tables
                for table in tables_in_query:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        cursor.execute(f"PRAGMA table_info('{table}')")
                        columns = [row[1] for row in cursor.fetchall()]
                        cursor.execute(f"PRAGMA index_list('{table}')")
                        indexes = []
                        for idx in cursor.fetchall():
                            idx_name = idx[1]
                            cursor.execute(f"PRAGMA index_info('{idx_name}')")
                            idx_cols = [col[2] for col in cursor.fetchall()]
                            indexes.append({"name": idx_name, "columns": idx_cols})
                        table_stats[table] = {
                            "row_count": count,
                            "columns": columns,
                            "indexes": indexes,
                        }
                    except sqlite3.Error:
                        pass

                return {
                    "plan": plan_rows,
                    "tables": table_stats,
                }
            finally:
                conn.close()

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _analyze)

            # Build analysis
            lines = [
                "# Query Optimization Analysis",
                "",
                "## Original Query",
                "```sql",
                query,
                "```",
                "",
                "## Execution Plan",
            ]

            plan_text = ""
            for row in result["plan"]:
                detail = row[3] if len(row) > 3 else str(row)
                indent = "  " * row[1] if len(row) > 1 else ""
                lines.append(f"{indent}- {detail}")
                plan_text += detail + " "

            lines.extend(["", "## Table Statistics"])
            for table, stats in result["tables"].items():
                lines.append(f"\n### {table}")
                lines.append(f"- Rows: {stats['row_count']:,}")
                if stats["indexes"]:
                    lines.append(f"- Indexes: {len(stats['indexes'])}")
                    for idx in stats["indexes"]:
                        lines.append(f"  - {idx['name']}: ({', '.join(idx['columns'])})")
                else:
                    lines.append("- Indexes: None")

            # Generate recommendations
            recommendations = []

            # Check for table scans on large tables
            for table, stats in result["tables"].items():
                if stats["row_count"] > 1000:
                    if f"SCAN TABLE {table}" in plan_text or f"SCAN {table}" in plan_text:
                        # Find WHERE clause columns
                        where_match = re.search(
                            r"WHERE\s+.*?(\w+)\s*[=<>]",
                            query,
                            re.IGNORECASE,
                        )
                        if where_match:
                            col = where_match.group(1)
                            existing_idx = any(
                                col in idx["columns"]
                                for idx in stats["indexes"]
                            )
                            if not existing_idx:
                                recommendations.append(
                                    f"**Add index on `{table}.{col}`**: Full table scan detected "
                                    f"on {stats['row_count']:,} rows. Consider:\n"
                                    f"  ```sql\n  CREATE INDEX idx_{table}_{col} ON {table}({col});\n  ```"
                                )

            # Check for correlated subqueries
            if "CORRELATED" in plan_text:
                recommendations.append(
                    "**Rewrite correlated subquery as JOIN**: Correlated subqueries "
                    "execute once per row. Consider rewriting as a JOIN for better performance."
                )

            # Check for temp B-trees (sorting without index)
            if "TEMP B-TREE" in plan_text:
                order_match = re.search(r"ORDER BY\s+(\w+)", query, re.IGNORECASE)
                if order_match:
                    col = order_match.group(1)
                    recommendations.append(
                        f"**Add index for ORDER BY**: Temporary B-tree created for sorting. "
                        f"Consider adding an index on `{col}` if this query runs frequently."
                    )

            # Check for covering index opportunity
            if "SEARCH" in plan_text and "COVERING" not in plan_text:
                recommendations.append(
                    "**Consider covering index**: Query could benefit from a covering index "
                    "that includes all selected columns to avoid table lookups."
                )

            # Check JOIN without index
            if "NESTED LOOP" in plan_text or "SCAN" in plan_text:
                join_match = re.search(r"JOIN\s+\w+\s+\w*\s*ON\s+\w+\.(\w+)", query, re.IGNORECASE)
                if join_match:
                    recommendations.append(
                        "**Add index for JOIN column**: Consider indexing JOIN columns "
                        "to improve join performance."
                    )

            if recommendations:
                lines.extend(["", "## Recommendations"])
                for i, rec in enumerate(recommendations, 1):
                    lines.append(f"\n{i}. {rec}")
            else:
                lines.extend([
                    "",
                    "## Recommendations",
                    "",
                    "Query execution plan looks optimal. No immediate optimizations suggested.",
                ])

            # Add context if provided
            if context:
                lines.extend(["", "## Additional Context", "", context])

            output = "\n".join(lines)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "database": str(db_path),
                    "tables_analyzed": list(result["tables"].keys()),
                    "recommendation_count": len(recommendations),
                    "has_table_scan": "SCAN" in plan_text and "INDEX" not in plan_text,
                    "uses_index": "INDEX" in plan_text or "SEARCH" in plan_text,
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
            log.error("sql_optimize_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Optimization analysis failed: {str(e)}",
                metadata={"database": str(db_path)},
            )


class DbSchemaDiffTool(Tool):
    """Compare schemas between two databases.

    Detects added, removed, and modified tables/columns between databases.
    """

    name = "db_schema_diff"
    description = """Compare schemas of two SQLite databases.

Examples:
- db_schema_diff(database1="dev.db", database2="prod.db")
- db_schema_diff(database1="before.db", database2="after.db", tables=["users", "orders"])

Returns detailed diff of schema changes between databases."""

    parameters = {
        "type": "object",
        "properties": {
            "database1": {
                "type": "string",
                "description": "Path to first SQLite database (baseline)",
            },
            "database2": {
                "type": "string",
                "description": "Path to second SQLite database (to compare)",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific tables to compare (default: all tables)",
            },
            "ignore_order": {
                "type": "boolean",
                "description": "Ignore column order differences (default: true)",
            },
        },
        "required": ["database1", "database2"],
    }

    async def execute(
        self,
        database1: str,
        database2: str,
        tables: Optional[list[str]] = None,
        ignore_order: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Compare two database schemas.

        Args:
            database1: Path to first (baseline) database
            database2: Path to second (comparison) database
            tables: Specific tables to compare (None = all)
            ignore_order: Ignore column order differences

        Returns:
            ToolResult with schema differences
        """
        db1_path = self._resolve_path(database1)
        db2_path = self._resolve_path(database2)

        for db_path, name in [(db1_path, "database1"), (db2_path, "database2")]:
            if not db_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"{name} not found: {db_path}",
                    metadata={"database1": str(db1_path), "database2": str(db2_path)},
                )

        log.info(
            "db_schema_diff",
            database1=str(db1_path),
            database2=str(db2_path),
            tables=tables,
        )

        def _compare():
            """Compare schemas in thread."""
            conn1 = sqlite3.connect(str(db1_path))
            conn2 = sqlite3.connect(str(db2_path))
            try:
                schema1 = _get_schema_info(conn1)
                schema2 = _get_schema_info(conn2)

                # Filter tables if specified
                if tables:
                    schema1["tables"] = {
                        k: v for k, v in schema1["tables"].items() if k in tables
                    }
                    schema2["tables"] = {
                        k: v for k, v in schema2["tables"].items() if k in tables
                    }

                tables1 = set(schema1["tables"].keys())
                tables2 = set(schema2["tables"].keys())

                diff = {
                    "added_tables": list(tables2 - tables1),
                    "removed_tables": list(tables1 - tables2),
                    "modified_tables": {},
                }

                # Compare common tables
                common_tables = tables1 & tables2
                for table in common_tables:
                    t1 = schema1["tables"][table]
                    t2 = schema2["tables"][table]

                    table_diff = {
                        "added_columns": [],
                        "removed_columns": [],
                        "modified_columns": [],
                        "index_changes": [],
                        "fk_changes": [],
                    }

                    # Compare columns
                    cols1 = set(t1["columns"].keys())
                    cols2 = set(t2["columns"].keys())

                    for col in cols2 - cols1:
                        table_diff["added_columns"].append({
                            "name": col,
                            "type": t2["columns"][col]["type"],
                            "notnull": t2["columns"][col]["notnull"],
                        })

                    for col in cols1 - cols2:
                        table_diff["removed_columns"].append({
                            "name": col,
                            "type": t1["columns"][col]["type"],
                        })

                    for col in cols1 & cols2:
                        c1 = t1["columns"][col]
                        c2 = t2["columns"][col]
                        changes = []

                        if c1["type"] != c2["type"]:
                            changes.append(f"type: {c1['type']} -> {c2['type']}")
                        if c1["notnull"] != c2["notnull"]:
                            changes.append(
                                f"nullable: {not c1['notnull']} -> {not c2['notnull']}"
                            )
                        if c1["default"] != c2["default"]:
                            changes.append(
                                f"default: {c1['default']} -> {c2['default']}"
                            )

                        if changes:
                            table_diff["modified_columns"].append({
                                "name": col,
                                "changes": changes,
                            })

                    # Compare indexes
                    idx1 = {idx["name"]: idx for idx in t1["indexes"]}
                    idx2 = {idx["name"]: idx for idx in t2["indexes"]}

                    for name in set(idx2.keys()) - set(idx1.keys()):
                        table_diff["index_changes"].append({
                            "action": "added",
                            "name": name,
                            "columns": idx2[name]["columns"],
                        })

                    for name in set(idx1.keys()) - set(idx2.keys()):
                        table_diff["index_changes"].append({
                            "action": "removed",
                            "name": name,
                            "columns": idx1[name]["columns"],
                        })

                    # Check for actual changes
                    has_changes = (
                        table_diff["added_columns"]
                        or table_diff["removed_columns"]
                        or table_diff["modified_columns"]
                        or table_diff["index_changes"]
                    )

                    if has_changes:
                        diff["modified_tables"][table] = table_diff

                return diff
            finally:
                conn1.close()
                conn2.close()

        try:
            loop = asyncio.get_event_loop()
            diff = await loop.run_in_executor(None, _compare)

            # Format output
            lines = [
                f"# Schema Diff: {db1_path.name} vs {db2_path.name}",
                "",
            ]

            total_changes = (
                len(diff["added_tables"])
                + len(diff["removed_tables"])
                + len(diff["modified_tables"])
            )

            if total_changes == 0:
                lines.append("**No schema differences found.**")
            else:
                lines.append(f"**{total_changes} table(s) with changes**")
                lines.append("")

                if diff["added_tables"]:
                    lines.append("## Added Tables")
                    for table in sorted(diff["added_tables"]):
                        lines.append(f"- `{table}`")
                    lines.append("")

                if diff["removed_tables"]:
                    lines.append("## Removed Tables")
                    for table in sorted(diff["removed_tables"]):
                        lines.append(f"- `{table}`")
                    lines.append("")

                if diff["modified_tables"]:
                    lines.append("## Modified Tables")
                    for table, changes in sorted(diff["modified_tables"].items()):
                        lines.append(f"\n### {table}")

                        if changes["added_columns"]:
                            lines.append("\n**Added columns:**")
                            for col in changes["added_columns"]:
                                null = "NOT NULL" if col["notnull"] else "NULL"
                                lines.append(f"- `{col['name']}` ({col['type']}, {null})")

                        if changes["removed_columns"]:
                            lines.append("\n**Removed columns:**")
                            for col in changes["removed_columns"]:
                                lines.append(f"- `{col['name']}` ({col['type']})")

                        if changes["modified_columns"]:
                            lines.append("\n**Modified columns:**")
                            for col in changes["modified_columns"]:
                                lines.append(f"- `{col['name']}`: {', '.join(col['changes'])}")

                        if changes["index_changes"]:
                            lines.append("\n**Index changes:**")
                            for idx in changes["index_changes"]:
                                action = "+" if idx["action"] == "added" else "-"
                                lines.append(
                                    f"- {action} `{idx['name']}` ({', '.join(idx['columns'])})"
                                )

            output = "\n".join(lines)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "database1": str(db1_path),
                    "database2": str(db2_path),
                    "added_tables": diff["added_tables"],
                    "removed_tables": diff["removed_tables"],
                    "modified_table_count": len(diff["modified_tables"]),
                    "total_changes": total_changes,
                },
            )

        except sqlite3.Error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SQLite error: {str(e)}",
                metadata={"database1": str(db1_path), "database2": str(db2_path)},
            )
        except Exception as e:
            log.error(
                "db_schema_diff_error",
                error=str(e),
                database1=str(db1_path),
                database2=str(db2_path),
            )
            return ToolResult(
                success=False,
                output="",
                error=f"Schema comparison failed: {str(e)}",
                metadata={"database1": str(db1_path), "database2": str(db2_path)},
            )


class DbAnalyzeIndexesTool(Tool):
    """Analyze database indexes and suggest improvements.

    Examines existing indexes, identifies unused or redundant indexes,
    and suggests new indexes based on query patterns.
    """

    name = "db_analyze_indexes"
    description = """Analyze database indexes and suggest improvements.

Examples:
- db_analyze_indexes(database="app.db")
- db_analyze_indexes(database="app.db", tables=["users", "orders"])
- db_analyze_indexes(database="app.db", query_log="queries.txt")

Returns analysis of existing indexes with suggestions for improvements."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific tables to analyze (default: all tables)",
            },
            "query_log": {
                "type": "string",
                "description": "Path to file with frequently-run queries (one per line)",
            },
            "include_stats": {
                "type": "boolean",
                "description": "Include table statistics (default: true)",
            },
        },
        "required": ["database"],
    }

    async def execute(
        self,
        database: str,
        tables: Optional[list[str]] = None,
        query_log: Optional[str] = None,
        include_stats: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Analyze indexes and provide recommendations.

        Args:
            database: Path to SQLite database file
            tables: Specific tables to analyze
            query_log: Path to query log file
            include_stats: Include table statistics

        Returns:
            ToolResult with index analysis
        """
        db_path = self._resolve_path(database)

        if not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        # Load query log if provided
        queries = []
        if query_log:
            query_log_path = self._resolve_path(query_log)
            if query_log_path.exists():
                queries = query_log_path.read_text().strip().split("\n")

        log.info("db_analyze_indexes", database=str(db_path), tables=tables)

        def _analyze():
            """Analyze indexes in thread."""
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()
                schema = _get_schema_info(conn)

                # Filter tables if specified
                if tables:
                    schema["tables"] = {
                        k: v for k, v in schema["tables"].items() if k in tables
                    }

                analysis = {"tables": {}}

                for table_name, table_info in schema["tables"].items():
                    table_analysis = {
                        "row_count": 0,
                        "existing_indexes": [],
                        "suggested_indexes": [],
                        "redundant_indexes": [],
                        "columns_in_queries": set(),
                    }

                    # Get row count
                    if include_stats:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        table_analysis["row_count"] = cursor.fetchone()[0]

                    # Existing indexes
                    for idx in table_info["indexes"]:
                        table_analysis["existing_indexes"].append(idx)

                    # Analyze queries for this table
                    if queries:
                        for query in queries:
                            query_upper = query.upper()
                            if table_name.upper() in query_upper:
                                # Extract WHERE columns
                                where_match = re.findall(
                                    rf"{table_name}\.(\w+)\s*[=<>]|WHERE\s+(\w+)\s*[=<>]",
                                    query,
                                    re.IGNORECASE,
                                )
                                for match in where_match:
                                    col = match[0] or match[1]
                                    if col in table_info["columns"]:
                                        table_analysis["columns_in_queries"].add(col)

                                # Extract ORDER BY columns
                                order_match = re.findall(
                                    r"ORDER BY\s+(\w+)",
                                    query,
                                    re.IGNORECASE,
                                )
                                for col in order_match:
                                    if col in table_info["columns"]:
                                        table_analysis["columns_in_queries"].add(col)

                    # Find indexed columns
                    indexed_cols = set()
                    for idx in table_info["indexes"]:
                        indexed_cols.update(idx["columns"])

                    # Suggest indexes for frequently queried columns
                    for col in table_analysis["columns_in_queries"]:
                        if col not in indexed_cols:
                            table_analysis["suggested_indexes"].append({
                                "columns": [col],
                                "reason": "Frequently used in WHERE/ORDER BY",
                            })

                    # Check for redundant indexes (covered by other indexes)
                    for idx in table_info["indexes"]:
                        for other_idx in table_info["indexes"]:
                            if idx["name"] != other_idx["name"]:
                                # Check if idx is prefix of other_idx
                                if (
                                    len(idx["columns"]) < len(other_idx["columns"])
                                    and idx["columns"]
                                    == other_idx["columns"][: len(idx["columns"])]
                                ):
                                    table_analysis["redundant_indexes"].append({
                                        "name": idx["name"],
                                        "covered_by": other_idx["name"],
                                    })

                    # Suggest composite indexes for common column pairs
                    if len(table_analysis["columns_in_queries"]) >= 2:
                        query_cols = list(table_analysis["columns_in_queries"])
                        # Check if common pairs are indexed together
                        for i, col1 in enumerate(query_cols):
                            for col2 in query_cols[i + 1 :]:
                                pair_indexed = any(
                                    col1 in idx["columns"] and col2 in idx["columns"]
                                    for idx in table_info["indexes"]
                                )
                                if not pair_indexed:
                                    table_analysis["suggested_indexes"].append({
                                        "columns": [col1, col2],
                                        "reason": "Frequently queried together",
                                    })

                    # Convert set to list for JSON serialization
                    table_analysis["columns_in_queries"] = list(
                        table_analysis["columns_in_queries"]
                    )

                    analysis["tables"][table_name] = table_analysis

                return analysis
            finally:
                conn.close()

        try:
            loop = asyncio.get_event_loop()
            analysis = await loop.run_in_executor(None, _analyze)

            # Format output
            lines = ["# Index Analysis Report", ""]

            total_indexes = 0
            total_suggestions = 0
            total_redundant = 0

            for table_name, table_analysis in sorted(analysis["tables"].items()):
                lines.append(f"## {table_name}")
                if include_stats:
                    lines.append(f"**Rows:** {table_analysis['row_count']:,}")
                lines.append("")

                # Existing indexes
                if table_analysis["existing_indexes"]:
                    lines.append("### Existing Indexes")
                    for idx in table_analysis["existing_indexes"]:
                        unique = "UNIQUE " if idx["unique"] else ""
                        cols = ", ".join(idx["columns"])
                        lines.append(f"- `{idx['name']}`: {unique}({cols})")
                        total_indexes += 1
                else:
                    lines.append("### Existing Indexes")
                    lines.append("- None")
                lines.append("")

                # Suggested indexes
                if table_analysis["suggested_indexes"]:
                    lines.append("### Suggested Indexes")
                    for suggestion in table_analysis["suggested_indexes"]:
                        cols = ", ".join(suggestion["columns"])
                        idx_name = f"idx_{table_name}_{'_'.join(suggestion['columns'])}"
                        lines.append(f"- `{idx_name}` ({cols})")
                        lines.append(f"  - Reason: {suggestion['reason']}")
                        lines.append(
                            f"  - SQL: `CREATE INDEX {idx_name} ON {table_name}({cols});`"
                        )
                        total_suggestions += 1
                    lines.append("")

                # Redundant indexes
                if table_analysis["redundant_indexes"]:
                    lines.append("### Potentially Redundant Indexes")
                    for redundant in table_analysis["redundant_indexes"]:
                        lines.append(
                            f"- `{redundant['name']}` (covered by `{redundant['covered_by']}`)"
                        )
                        lines.append(
                            f"  - Consider: `DROP INDEX {redundant['name']};`"
                        )
                        total_redundant += 1
                    lines.append("")

            # Summary
            lines.insert(2, "## Summary")
            lines.insert(3, f"- **Tables analyzed:** {len(analysis['tables'])}")
            lines.insert(4, f"- **Existing indexes:** {total_indexes}")
            lines.insert(5, f"- **Suggested indexes:** {total_suggestions}")
            lines.insert(6, f"- **Potentially redundant:** {total_redundant}")
            lines.insert(7, "")

            output = "\n".join(lines)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "database": str(db_path),
                    "tables_analyzed": list(analysis["tables"].keys()),
                    "existing_index_count": total_indexes,
                    "suggested_index_count": total_suggestions,
                    "redundant_index_count": total_redundant,
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
            log.error("db_analyze_indexes_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Index analysis failed: {str(e)}",
                metadata={"database": str(db_path)},
            )


class DbBackupTool(Tool):
    """Create database backups.

    Supports SQLite (native), PostgreSQL (pg_dump), and MySQL (mysqldump).
    """

    name = "db_backup"
    description = """Create a database backup.

Examples:
- db_backup(database="app.db", output_path="backup.sql")
- db_backup(database="app.db", output_path="backup.sql.gz", compress=true)
- db_backup(database="app.db", output_path="schema.sql", schema_only=true)

Supports SQLite, PostgreSQL, and MySQL databases."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database or connection string for PostgreSQL/MySQL",
            },
            "output_path": {
                "type": "string",
                "description": "Path for backup file",
            },
            "format": {
                "type": "string",
                "enum": ["sql", "dump", "archive"],
                "description": "Backup format (default: sql)",
            },
            "compress": {
                "type": "boolean",
                "description": "Compress backup with gzip (default: false)",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific tables to backup (default: all tables)",
            },
            "schema_only": {
                "type": "boolean",
                "description": "Backup schema only, no data (default: false)",
            },
        },
        "required": ["database", "output_path"],
    }

    async def execute(
        self,
        database: str,
        output_path: str,
        format: str = "sql",
        compress: bool = False,
        tables: Optional[list[str]] = None,
        schema_only: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Create database backup.

        Args:
            database: Database path or connection string
            output_path: Path for backup file
            format: Backup format
            compress: Compress with gzip
            tables: Specific tables to backup
            schema_only: Schema only, no data

        Returns:
            ToolResult with backup status
        """
        out_path = self._resolve_path(output_path)
        db_type = _detect_db_type(database)

        log.info(
            "db_backup",
            database=database[:50],
            output=str(out_path),
            db_type=db_type,
        )

        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if db_type == "sqlite":
                result = await self._backup_sqlite(
                    database, out_path, tables, schema_only
                )
            elif db_type == "postgresql":
                result = await self._backup_postgresql(
                    database, out_path, tables, schema_only
                )
            elif db_type == "mysql":
                result = await self._backup_mysql(
                    database, out_path, tables, schema_only
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported database type: {db_type}",
                )

            if not result["success"]:
                return ToolResult(
                    success=False,
                    output="",
                    error=result["error"],
                )

            # Compress if requested
            if compress:
                compressed_path = Path(str(out_path) + ".gz")
                with open(out_path, "rb") as f_in:
                    with gzip.open(compressed_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                out_path.unlink()  # Remove uncompressed
                out_path = compressed_path

            # Get file size
            size_bytes = out_path.stat().st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes} bytes"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

            output = f"""Backup created successfully.

**Database:** {database[:100]}
**Output:** {out_path}
**Size:** {size_str}
**Tables:** {result.get('table_count', 'all')}
**Schema only:** {schema_only}
**Compressed:** {compress}"""

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "database": database,
                    "output_path": str(out_path),
                    "size_bytes": size_bytes,
                    "table_count": result.get("table_count"),
                    "schema_only": schema_only,
                    "compressed": compress,
                    "db_type": db_type,
                },
            )

        except Exception as e:
            log.error("db_backup_error", error=str(e), database=database[:50])
            return ToolResult(
                success=False,
                output="",
                error=f"Backup failed: {str(e)}",
            )

    async def _backup_sqlite(
        self,
        database: str,
        output_path: Path,
        tables: Optional[list[str]],
        schema_only: bool,
    ) -> dict:
        """Backup SQLite database using iterdump."""
        db_path = self._resolve_path(database)

        if not db_path.exists():
            return {"success": False, "error": f"Database not found: {db_path}"}

        def _dump():
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()

                # Get table list
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                all_tables = [row[0] for row in cursor.fetchall()]

                if tables:
                    dump_tables = [t for t in tables if t in all_tables]
                else:
                    dump_tables = all_tables

                lines = [
                    f"-- SQLite backup",
                    f"-- Database: {db_path.name}",
                    f"-- Tables: {len(dump_tables)}",
                    "",
                    "BEGIN TRANSACTION;",
                    "",
                ]

                for table in dump_tables:
                    # Get CREATE statement
                    cursor.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    )
                    create_sql = cursor.fetchone()
                    if create_sql and create_sql[0]:
                        lines.append(f"-- Table: {table}")
                        lines.append(f"{create_sql[0]};")
                        lines.append("")

                    if not schema_only:
                        # Get data
                        cursor.execute(f"SELECT * FROM {table}")
                        rows = cursor.fetchall()
                        if rows:
                            # Get column names
                            col_names = [desc[0] for desc in cursor.description]
                            cols_str = ", ".join(col_names)

                            for row in rows:
                                values = []
                                for val in row:
                                    if val is None:
                                        values.append("NULL")
                                    elif isinstance(val, str):
                                        escaped = val.replace("'", "''")
                                        values.append(f"'{escaped}'")
                                    else:
                                        values.append(str(val))
                                vals_str = ", ".join(values)
                                lines.append(
                                    f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str});"
                                )
                            lines.append("")

                    # Get indexes
                    cursor.execute(
                        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                        (table,),
                    )
                    for idx_row in cursor.fetchall():
                        if idx_row[0]:
                            lines.append(f"{idx_row[0]};")
                    lines.append("")

                lines.append("COMMIT;")

                return {
                    "success": True,
                    "content": "\n".join(lines),
                    "table_count": len(dump_tables),
                }
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _dump)

        if result["success"]:
            output_path.write_text(result["content"])

        return result

    async def _backup_postgresql(
        self,
        connection_string: str,
        output_path: Path,
        tables: Optional[list[str]],
        schema_only: bool,
    ) -> dict:
        """Backup PostgreSQL database using pg_dump."""
        cmd = ["pg_dump", connection_string]

        if schema_only:
            cmd.append("--schema-only")

        if tables:
            for table in tables:
                cmd.extend(["-t", table])

        cmd.extend(["-f", str(output_path)])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                return {
                    "success": False,
                    "error": f"pg_dump failed: {stderr.decode()}",
                }

            return {
                "success": True,
                "table_count": len(tables) if tables else "all",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "pg_dump not found. Install PostgreSQL client tools.",
            }

    async def _backup_mysql(
        self,
        connection_string: str,
        output_path: Path,
        tables: Optional[list[str]],
        schema_only: bool,
    ) -> dict:
        """Backup MySQL database using mysqldump."""
        # Parse connection string: mysql://user:pass@host:port/database
        match = re.match(
            r"mysql://([^:]+):([^@]+)@([^:]+):?(\d+)?/(.+)",
            connection_string,
        )
        if not match:
            return {
                "success": False,
                "error": "Invalid MySQL connection string format",
            }

        user, password, host, port, database = match.groups()
        port = port or "3306"

        cmd = [
            "mysqldump",
            f"-h{host}",
            f"-P{port}",
            f"-u{user}",
            f"-p{password}",
            database,
        ]

        if schema_only:
            cmd.append("--no-data")

        if tables:
            cmd.extend(tables)

        try:
            with open(output_path, "w") as f:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=f,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await process.communicate()

            if process.returncode != 0:
                return {
                    "success": False,
                    "error": f"mysqldump failed: {stderr.decode()}",
                }

            return {
                "success": True,
                "table_count": len(tables) if tables else "all",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "mysqldump not found. Install MySQL client tools.",
            }


class DbVisualizeSchemaTool(Tool):
    """Generate ER diagrams from database schema.

    Creates visual representations of database structure in Mermaid,
    PlantUML, or D2 format.
    """

    name = "db_visualize_schema"
    description = """Generate an ER diagram from a database schema.

Examples:
- db_visualize_schema(database="app.db")
- db_visualize_schema(database="app.db", format="plantuml", show_indexes=true)
- db_visualize_schema(database="app.db", tables=["users", "orders"], output_file="schema.md")

Returns ER diagram in Mermaid, PlantUML, or D2 format."""

    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific tables to include (default: all tables)",
            },
            "format": {
                "type": "string",
                "enum": ["mermaid", "plantuml", "d2"],
                "description": "Output format (default: mermaid)",
            },
            "show_types": {
                "type": "boolean",
                "description": "Show column types (default: true)",
            },
            "show_indexes": {
                "type": "boolean",
                "description": "Show indexed columns (default: false)",
            },
            "output_file": {
                "type": "string",
                "description": "Save diagram to file (optional)",
            },
            "title": {
                "type": "string",
                "description": "Diagram title (optional)",
            },
        },
        "required": ["database"],
    }

    async def execute(
        self,
        database: str,
        tables: Optional[list[str]] = None,
        format: str = "mermaid",
        show_types: bool = True,
        show_indexes: bool = False,
        output_file: Optional[str] = None,
        title: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate ER diagram.

        Args:
            database: Path to SQLite database file
            tables: Specific tables to include
            format: Output format (mermaid, plantuml, d2)
            show_types: Show column types
            show_indexes: Show indexed columns
            output_file: Save to file
            title: Diagram title

        Returns:
            ToolResult with diagram
        """
        db_path = self._resolve_path(database)

        if not db_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Database not found: {db_path}",
                metadata={"database": str(db_path)},
            )

        log.info("db_visualize_schema", database=str(db_path), format=format)

        def _generate():
            """Generate diagram in thread."""
            conn = sqlite3.connect(str(db_path))
            try:
                schema = _get_schema_info(conn)

                # Filter tables if specified
                if tables:
                    schema["tables"] = {
                        k: v for k, v in schema["tables"].items() if k in tables
                    }

                return schema
            finally:
                conn.close()

        try:
            loop = asyncio.get_event_loop()
            schema = await loop.run_in_executor(None, _generate)

            # Generate diagram based on format
            if format == "mermaid":
                diagram = self._generate_mermaid(schema, show_types, show_indexes, title)
            elif format == "plantuml":
                diagram = self._generate_plantuml(schema, show_types, show_indexes, title)
            elif format == "d2":
                diagram = self._generate_d2(schema, show_types, show_indexes, title)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported format: {format}",
                )

            # Save to file if requested
            if output_file:
                out_path = self._resolve_path(output_file)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(diagram)

            # Count relationships
            relationship_count = sum(
                len(t["foreign_keys"]) for t in schema["tables"].values()
            )

            return ToolResult(
                success=True,
                output=diagram,
                metadata={
                    "database": str(db_path),
                    "format": format,
                    "table_count": len(schema["tables"]),
                    "relationship_count": relationship_count,
                    "output_file": str(output_file) if output_file else None,
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
            log.error("db_visualize_error", error=str(e), database=str(db_path))
            return ToolResult(
                success=False,
                output="",
                error=f"Diagram generation failed: {str(e)}",
                metadata={"database": str(db_path)},
            )

    def _generate_mermaid(
        self,
        schema: dict,
        show_types: bool,
        show_indexes: bool,
        title: Optional[str],
    ) -> str:
        """Generate Mermaid ER diagram."""
        lines = ["```mermaid", "erDiagram"]

        if title:
            lines[0] = f"```mermaid\n---\ntitle: {title}\n---"

        # Generate tables
        for table_name, table_info in schema["tables"].items():
            lines.append(f"    {table_name} {{")

            # Get indexed columns
            indexed_cols = set()
            if show_indexes:
                for idx in table_info["indexes"]:
                    indexed_cols.update(idx["columns"])

            for col_name, col_info in table_info["columns"].items():
                col_type = col_info["type"] if show_types else ""
                pk = "PK" if col_info["pk"] else ""
                fk = ""
                for fk_info in table_info["foreign_keys"]:
                    if fk_info["column"] == col_name:
                        fk = "FK"
                        break

                markers = " ".join(filter(None, [pk, fk]))
                idx_marker = " *" if col_name in indexed_cols else ""

                if col_type:
                    lines.append(f"        {col_type} {col_name}{idx_marker} {markers}".strip())
                else:
                    lines.append(f"        {col_name}{idx_marker} {markers}".strip())

            lines.append("    }")

        # Generate relationships from foreign keys
        for table_name, table_info in schema["tables"].items():
            for fk in table_info["foreign_keys"]:
                ref_table = fk["ref_table"]
                # Determine relationship type (simplified)
                lines.append(f"    {ref_table} ||--o{{ {table_name} : has")

        lines.append("```")
        return "\n".join(lines)

    def _generate_plantuml(
        self,
        schema: dict,
        show_types: bool,
        show_indexes: bool,
        title: Optional[str],
    ) -> str:
        """Generate PlantUML ER diagram."""
        lines = ["@startuml"]

        if title:
            lines.append(f"title {title}")
            lines.append("")

        lines.append("skinparam linetype ortho")
        lines.append("")

        # Generate tables as entities
        for table_name, table_info in schema["tables"].items():
            lines.append(f"entity \"{table_name}\" as {table_name} {{")

            # Primary keys first
            for col_name, col_info in table_info["columns"].items():
                if col_info["pk"]:
                    col_type = f" : {col_info['type']}" if show_types else ""
                    lines.append(f"    * {col_name}{col_type} <<PK>>")

            lines.append("    --")

            # Other columns
            for col_name, col_info in table_info["columns"].items():
                if not col_info["pk"]:
                    col_type = f" : {col_info['type']}" if show_types else ""
                    fk_marker = ""
                    for fk in table_info["foreign_keys"]:
                        if fk["column"] == col_name:
                            fk_marker = " <<FK>>"
                            break
                    nullable = "" if col_info["notnull"] else " (nullable)"
                    lines.append(f"    {col_name}{col_type}{fk_marker}{nullable}")

            lines.append("}")
            lines.append("")

        # Generate relationships
        for table_name, table_info in schema["tables"].items():
            for fk in table_info["foreign_keys"]:
                ref_table = fk["ref_table"]
                lines.append(f"{ref_table} ||--o{{ {table_name}")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_d2(
        self,
        schema: dict,
        show_types: bool,
        show_indexes: bool,
        title: Optional[str],
    ) -> str:
        """Generate D2 diagram."""
        lines = []

        if title:
            lines.append(f"title: {title}")
            lines.append("")

        # Generate tables
        for table_name, table_info in schema["tables"].items():
            lines.append(f"{table_name}: {{")
            lines.append("    shape: sql_table")

            for col_name, col_info in table_info["columns"].items():
                col_type = col_info["type"] if show_types else ""
                constraint = ""
                if col_info["pk"]:
                    constraint = " {constraint: primary_key}"
                for fk in table_info["foreign_keys"]:
                    if fk["column"] == col_name:
                        constraint = " {constraint: foreign_key}"
                        break

                if col_type:
                    lines.append(f"    {col_name}: {col_type}{constraint}")
                else:
                    lines.append(f"    {col_name}{constraint}")

            lines.append("}")
            lines.append("")

        # Generate relationships
        for table_name, table_info in schema["tables"].items():
            for fk in table_info["foreign_keys"]:
                ref_table = fk["ref_table"]
                ref_col = fk["ref_column"]
                col = fk["column"]
                lines.append(f"{ref_table}.{ref_col} -> {table_name}.{col}")

        return "\n".join(lines)
