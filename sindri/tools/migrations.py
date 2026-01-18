"""Database migration tools for Sindri.

Provides tools for generating, running, and managing database migrations
across multiple frameworks and ORMs.

Supported frameworks:
- Python: Alembic (SQLAlchemy), Django
- Node.js: Prisma, Knex, Sequelize
- Go: Goose, GORM, Atlas
- Rust: Diesel, SeaORM
"""

import asyncio
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


@dataclass
class MigrationInfo:
    """Information about a detected migration framework."""

    framework: str  # alembic, django, prisma, knex, sequelize, goose, gorm, diesel, seaorm, atlas
    language: str  # python, node, go, rust
    migrations_dir: Optional[str] = None
    config_file: Optional[str] = None
    is_configured: bool = False
    database_url_env: str = "DATABASE_URL"
    command_prefix: list[str] = field(default_factory=list)


@dataclass
class Migration:
    """Represents a single migration."""

    id: str
    name: str
    applied: bool
    applied_at: Optional[datetime] = None
    file_path: Optional[str] = None


class MigrationDetector:
    """Detects migration frameworks in a project."""

    def detect(self, path: Path) -> Optional[MigrationInfo]:
        """Detect migration framework in the given path."""
        # Check Python frameworks
        if (path / "alembic.ini").exists() or (path / "alembic").exists():
            return self._detect_alembic(path)
        if (path / "manage.py").exists() and self._is_django(path):
            return self._detect_django(path)

        # Check Node.js frameworks
        if (path / "prisma" / "schema.prisma").exists():
            return self._detect_prisma(path)
        if (path / "knexfile.js").exists() or (path / "knexfile.ts").exists():
            return self._detect_knex(path)
        if self._has_sequelize(path):
            return self._detect_sequelize(path)

        # Check Go frameworks
        if (path / "atlas.hcl").exists():
            return self._detect_atlas(path)
        if (path / "db" / "migrations").exists() or self._has_goose(path):
            return self._detect_goose(path)

        # Check Rust frameworks
        if (path / "diesel.toml").exists():
            return self._detect_diesel(path)
        if self._has_seaorm(path):
            return self._detect_seaorm(path)

        # Check pyproject.toml for framework hints
        if (path / "pyproject.toml").exists():
            content = (path / "pyproject.toml").read_text().lower()
            if "alembic" in content:
                return MigrationInfo(
                    framework="alembic",
                    language="python",
                    is_configured=False,
                )
            if "django" in content:
                return MigrationInfo(
                    framework="django",
                    language="python",
                    is_configured=False,
                )

        # Check package.json for framework hints
        if (path / "package.json").exists():
            try:
                pkg = json.loads((path / "package.json").read_text())
                deps = {
                    **pkg.get("dependencies", {}),
                    **pkg.get("devDependencies", {}),
                }
                if "prisma" in deps or "@prisma/client" in deps:
                    return MigrationInfo(
                        framework="prisma",
                        language="node",
                        is_configured=False,
                    )
                if "knex" in deps:
                    return MigrationInfo(
                        framework="knex",
                        language="node",
                        is_configured=False,
                    )
                if "sequelize" in deps:
                    return MigrationInfo(
                        framework="sequelize",
                        language="node",
                        is_configured=False,
                    )
            except (json.JSONDecodeError, IOError):
                pass

        return None

    def _detect_alembic(self, path: Path) -> MigrationInfo:
        """Detect Alembic configuration."""
        # Alembic migrations go in versions subdirectory
        if (path / "alembic" / "versions").exists():
            migrations_dir = "alembic/versions"
        elif (path / "migrations" / "versions").exists():
            migrations_dir = "migrations/versions"
        elif (path / "alembic").exists():
            migrations_dir = "alembic/versions"
        else:
            migrations_dir = "migrations/versions"

        return MigrationInfo(
            framework="alembic",
            language="python",
            migrations_dir=migrations_dir,
            config_file="alembic.ini" if (path / "alembic.ini").exists() else None,
            is_configured=(path / "alembic.ini").exists(),
            command_prefix=["alembic"],
        )

    def _is_django(self, path: Path) -> bool:
        """Check if this is a Django project."""
        manage_py = path / "manage.py"
        if manage_py.exists():
            content = manage_py.read_text()
            return "django" in content.lower()
        return False

    def _detect_django(self, path: Path) -> MigrationInfo:
        """Detect Django configuration."""
        return MigrationInfo(
            framework="django",
            language="python",
            migrations_dir="migrations",
            config_file="manage.py",
            is_configured=True,
            command_prefix=["python", "manage.py"],
        )

    def _detect_prisma(self, path: Path) -> MigrationInfo:
        """Detect Prisma configuration."""
        return MigrationInfo(
            framework="prisma",
            language="node",
            migrations_dir="prisma/migrations",
            config_file="prisma/schema.prisma",
            is_configured=True,
            command_prefix=["npx", "prisma"],
        )

    def _detect_knex(self, path: Path) -> MigrationInfo:
        """Detect Knex configuration."""
        config_file = "knexfile.js"
        if (path / "knexfile.ts").exists():
            config_file = "knexfile.ts"

        return MigrationInfo(
            framework="knex",
            language="node",
            migrations_dir="migrations",
            config_file=config_file,
            is_configured=True,
            command_prefix=["npx", "knex"],
        )

    def _has_sequelize(self, path: Path) -> bool:
        """Check if project uses Sequelize."""
        config_files = [".sequelizerc", "config/config.json", "config/database.js"]
        return any((path / f).exists() for f in config_files)

    def _detect_sequelize(self, path: Path) -> MigrationInfo:
        """Detect Sequelize configuration."""
        config_file = None
        for f in [".sequelizerc", "config/config.json", "config/database.js"]:
            if (path / f).exists():
                config_file = f
                break

        return MigrationInfo(
            framework="sequelize",
            language="node",
            migrations_dir="migrations",
            config_file=config_file,
            is_configured=config_file is not None,
            command_prefix=["npx", "sequelize-cli"],
        )

    def _detect_atlas(self, path: Path) -> MigrationInfo:
        """Detect Atlas configuration."""
        return MigrationInfo(
            framework="atlas",
            language="go",
            migrations_dir="migrations",
            config_file="atlas.hcl",
            is_configured=True,
            command_prefix=["atlas"],
        )

    def _has_goose(self, path: Path) -> bool:
        """Check if project uses Goose."""
        if (path / "go.mod").exists():
            content = (path / "go.mod").read_text()
            return "pressly/goose" in content or "goose" in content.lower()
        return False

    def _detect_goose(self, path: Path) -> MigrationInfo:
        """Detect Goose configuration."""
        migrations_dir = "db/migrations"
        if (path / "migrations").exists():
            migrations_dir = "migrations"

        return MigrationInfo(
            framework="goose",
            language="go",
            migrations_dir=migrations_dir,
            is_configured=True,
            command_prefix=["goose"],
        )

    def _detect_diesel(self, path: Path) -> MigrationInfo:
        """Detect Diesel configuration."""
        return MigrationInfo(
            framework="diesel",
            language="rust",
            migrations_dir="migrations",
            config_file="diesel.toml",
            is_configured=True,
            command_prefix=["diesel"],
        )

    def _has_seaorm(self, path: Path) -> bool:
        """Check if project uses SeaORM."""
        if (path / "Cargo.toml").exists():
            content = (path / "Cargo.toml").read_text()
            return "sea-orm" in content.lower()
        return False

    def _detect_seaorm(self, path: Path) -> MigrationInfo:
        """Detect SeaORM configuration."""
        migrations_dir = "migration/src"
        if (path / "migrations").exists():
            migrations_dir = "migrations"

        return MigrationInfo(
            framework="seaorm",
            language="rust",
            migrations_dir=migrations_dir,
            is_configured=True,
            command_prefix=["sea-orm-cli"],
        )


class GenerateMigrationTool(Tool):
    """Generate database migration files.

    Creates migration files based on the detected framework and
    naming conventions.
    """

    name = "generate_migration"
    description = """Generate a new database migration file.

Automatically detects the migration framework (Alembic, Django, Prisma, Knex,
Sequelize, Goose, Diesel, etc.) and creates appropriately formatted migrations.

Examples:
- generate_migration(name="add_users_table") - Generate migration
- generate_migration(name="create_orders", message="Add orders table") - With message
- generate_migration(framework="alembic") - Force specific framework
- generate_migration(auto=true) - Auto-generate from model changes (if supported)
- generate_migration(dry_run=true) - Preview without creating file"""

    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Migration name (e.g., 'add_users_table', 'create_orders')",
            },
            "message": {
                "type": "string",
                "description": "Migration description/message",
            },
            "path": {
                "type": "string",
                "description": "Project path (default: current directory)",
            },
            "framework": {
                "type": "string",
                "description": "Override detected framework: 'alembic', 'django', 'prisma', 'knex', 'sequelize', 'goose', 'diesel', 'seaorm', 'atlas'",
                "enum": [
                    "alembic",
                    "django",
                    "prisma",
                    "knex",
                    "sequelize",
                    "goose",
                    "diesel",
                    "seaorm",
                    "atlas",
                ],
            },
            "auto": {
                "type": "boolean",
                "description": "Auto-generate migration from model changes (supported by Alembic, Prisma, Django)",
            },
            "sql": {
                "type": "string",
                "description": "SQL content for the migration (up migration)",
            },
            "sql_down": {
                "type": "string",
                "description": "SQL content for rollback (down migration)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without creating file",
            },
        },
        "required": ["name"],
    }

    async def execute(
        self,
        name: str,
        message: Optional[str] = None,
        path: Optional[str] = None,
        framework: Optional[str] = None,
        auto: bool = False,
        sql: Optional[str] = None,
        sql_down: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate a new migration file."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect or use specified framework
        detector = MigrationDetector()
        info = detector.detect(project_path)

        if framework:
            # Override with specified framework
            info = MigrationInfo(
                framework=framework,
                language=self._get_language(framework),
                is_configured=info.is_configured if info else False,
            )
        elif not info:
            return ToolResult(
                success=False,
                output="",
                error="Could not detect migration framework. Please specify --framework or install a migration tool.",
            )

        log.info(
            "generate_migration",
            framework=info.framework,
            name=name,
            auto=auto,
        )

        # Generate based on framework
        if auto and info.framework in ("alembic", "prisma", "django"):
            return await self._auto_generate(project_path, info, name, message, dry_run)
        else:
            return await self._manual_generate(
                project_path, info, name, message, sql, sql_down, dry_run
            )

    def _get_language(self, framework: str) -> str:
        """Get language for framework."""
        lang_map = {
            "alembic": "python",
            "django": "python",
            "prisma": "node",
            "knex": "node",
            "sequelize": "node",
            "goose": "go",
            "atlas": "go",
            "diesel": "rust",
            "seaorm": "rust",
        }
        return lang_map.get(framework, "unknown")

    async def _auto_generate(
        self,
        path: Path,
        info: MigrationInfo,
        name: str,
        message: Optional[str],
        dry_run: bool,
    ) -> ToolResult:
        """Auto-generate migration from model changes."""
        if dry_run:
            return ToolResult(
                success=True,
                output=f"Would auto-generate migration '{name}' using {info.framework}",
                metadata={"dry_run": True, "framework": info.framework},
            )

        try:
            if info.framework == "alembic":
                cmd = ["alembic", "revision", "--autogenerate", "-m", message or name]
                result = subprocess.run(
                    cmd,
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            elif info.framework == "prisma":
                cmd = ["npx", "prisma", "migrate", "dev", "--name", name]
                if message:
                    cmd.extend(["--create-only"])
                result = subprocess.run(
                    cmd,
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            elif info.framework == "django":
                cmd = ["python", "manage.py", "makemigrations", "--name", name]
                result = subprocess.run(
                    cmd,
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Auto-generation not supported for {info.framework}",
                )

            if result.returncode == 0:
                output = result.stdout or result.stderr
                return ToolResult(
                    success=True,
                    output=f"Migration generated successfully:\n{output}",
                    metadata={
                        "framework": info.framework,
                        "name": name,
                        "auto": True,
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    output=result.stdout,
                    error=f"Migration generation failed: {result.stderr}",
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, output="", error="Migration generation timed out"
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Migration generation failed: {str(e)}"
            )

    async def _manual_generate(
        self,
        path: Path,
        info: MigrationInfo,
        name: str,
        message: Optional[str],
        sql: Optional[str],
        sql_down: Optional[str],
        dry_run: bool,
    ) -> ToolResult:
        """Manually generate migration file."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())

        # Determine migrations directory
        migrations_dir = path / (info.migrations_dir or "migrations")
        migrations_dir.mkdir(parents=True, exist_ok=True)

        # Generate content based on framework
        if info.framework == "alembic":
            content = self._alembic_template(timestamp, clean_name, message, sql, sql_down)
            filename = f"{timestamp}_{clean_name}.py"
        elif info.framework == "django":
            content = self._django_template(clean_name, message, sql)
            # Django uses numbered migrations per app
            filename = f"0001_{clean_name}.py"
        elif info.framework == "prisma":
            content = self._prisma_template(sql or "-- Add your SQL here")
            filename = f"{timestamp}_{clean_name}/migration.sql"
            migrations_dir = migrations_dir / f"{timestamp}_{clean_name}"
            migrations_dir.mkdir(parents=True, exist_ok=True)
            filename = "migration.sql"
        elif info.framework in ("knex", "sequelize"):
            content = self._knex_template(timestamp, clean_name, message, sql, sql_down)
            filename = f"{timestamp}_{clean_name}.js"
        elif info.framework == "goose":
            content = self._goose_template(timestamp, clean_name, sql, sql_down)
            filename = f"{timestamp}_{clean_name}.sql"
        elif info.framework == "diesel":
            # Diesel uses up.sql and down.sql
            up_content = sql or "-- Add your SQL here"
            down_content = sql_down or "-- Add rollback SQL here"
            migration_dir = migrations_dir / f"{timestamp}_{clean_name}"

            if dry_run:
                return ToolResult(
                    success=True,
                    output=f"Would create:\n{migration_dir}/up.sql:\n{up_content}\n\n{migration_dir}/down.sql:\n{down_content}",
                    metadata={"dry_run": True, "framework": info.framework},
                )

            migration_dir.mkdir(parents=True, exist_ok=True)
            (migration_dir / "up.sql").write_text(up_content)
            (migration_dir / "down.sql").write_text(down_content)

            return ToolResult(
                success=True,
                output=f"Created migration: {migration_dir}",
                metadata={
                    "framework": info.framework,
                    "path": str(migration_dir),
                    "files": ["up.sql", "down.sql"],
                },
            )
        elif info.framework == "seaorm":
            content = self._seaorm_template(timestamp, clean_name, message)
            filename = f"m{timestamp}_{clean_name}.rs"
        elif info.framework == "atlas":
            content = self._atlas_template(timestamp, clean_name, sql)
            filename = f"{timestamp}_{clean_name}.sql"
        else:
            content = self._generic_sql_template(timestamp, clean_name, sql, sql_down)
            filename = f"{timestamp}_{clean_name}.sql"

        file_path = migrations_dir / filename

        if dry_run:
            return ToolResult(
                success=True,
                output=f"Would create {file_path}:\n\n{content}",
                metadata={"dry_run": True, "framework": info.framework},
            )

        try:
            file_path.write_text(content)
            log.info(
                "migration_created",
                framework=info.framework,
                file=str(file_path),
            )
            return ToolResult(
                success=True,
                output=f"Created migration: {file_path}\n\n{content}",
                metadata={
                    "framework": info.framework,
                    "file_path": str(file_path),
                    "name": clean_name,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Failed to create migration: {str(e)}"
            )

    def _alembic_template(
        self,
        timestamp: str,
        name: str,
        message: Optional[str],
        sql: Optional[str],
        sql_down: Optional[str],
    ) -> str:
        """Generate Alembic migration template."""
        revision_id = timestamp[:12]
        return f'''"""
{message or name}

Revision ID: {revision_id}
Revises:
Create Date: {datetime.now().isoformat()}
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "{revision_id}"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    {f'op.execute("""{sql}""")' if sql else "# Add upgrade operations here"}
    pass


def downgrade() -> None:
    {f'op.execute("""{sql_down}""")' if sql_down else "# Add downgrade operations here"}
    pass
'''

    def _django_template(
        self, name: str, message: Optional[str], sql: Optional[str]
    ) -> str:
        """Generate Django migration template."""
        return f'''# Generated migration: {message or name}

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # Add dependencies here
    ]

    operations = [
        {f'migrations.RunSQL("{sql}"),' if sql else "# Add operations here"}
    ]
'''

    def _prisma_template(self, sql: str) -> str:
        """Generate Prisma migration SQL template."""
        return f"""-- Migration: Generated by Sindri
-- Created at: {datetime.now().isoformat()}

{sql}
"""

    def _knex_template(
        self,
        timestamp: str,
        name: str,
        message: Optional[str],
        sql: Optional[str],
        sql_down: Optional[str],
    ) -> str:
        """Generate Knex migration template."""
        return f'''/**
 * @param {{ import("knex").Knex }} knex
 * @returns {{ Promise<void> }}
 */
exports.up = function(knex) {{
  {f'return knex.raw(`{sql}`);' if sql else '// Add migration logic here'}
}};

/**
 * @param {{ import("knex").Knex }} knex
 * @returns {{ Promise<void> }}
 */
exports.down = function(knex) {{
  {f'return knex.raw(`{sql_down}`);' if sql_down else '// Add rollback logic here'}
}};
'''

    def _goose_template(
        self,
        timestamp: str,
        name: str,
        sql: Optional[str],
        sql_down: Optional[str],
    ) -> str:
        """Generate Goose migration template."""
        return f"""-- +goose Up
-- +goose StatementBegin
{sql or "-- Add your SQL here"}
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
{sql_down or "-- Add rollback SQL here"}
-- +goose StatementEnd
"""

    def _seaorm_template(
        self, timestamp: str, name: str, message: Optional[str]
    ) -> str:
        """Generate SeaORM migration template."""
        return f'''use sea_orm_migration::prelude::*;

#[derive(DeriveMigrationName)]
pub struct Migration;

#[async_trait::async_trait]
impl MigrationTrait for Migration {{
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {{
        // {message or name}
        todo!()
    }}

    async fn down(&self, manager: &SchemaManager) -> Result<(), DbErr> {{
        todo!()
    }}
}}
'''

    def _atlas_template(
        self, timestamp: str, name: str, sql: Optional[str]
    ) -> str:
        """Generate Atlas migration template."""
        return f"""-- Migration: {name}
-- Created at: {datetime.now().isoformat()}

{sql or "-- Add your SQL here"}
"""

    def _generic_sql_template(
        self,
        timestamp: str,
        name: str,
        sql: Optional[str],
        sql_down: Optional[str],
    ) -> str:
        """Generate generic SQL migration template."""
        return f"""-- Migration: {name}
-- Created at: {datetime.now().isoformat()}

-- Up Migration
{sql or "-- Add your SQL here"}

-- Down Migration (for rollback)
-- {sql_down or "-- Add rollback SQL here"}
"""


class MigrationStatusTool(Tool):
    """Check status of database migrations.

    Shows pending and applied migrations.
    """

    name = "migration_status"
    description = """Check the status of database migrations.

Shows which migrations have been applied and which are pending.

Examples:
- migration_status() - Show migration status
- migration_status(path="/app") - Specify project path
- migration_status(framework="alembic") - Force specific framework
- migration_status(verbose=true) - Show detailed information"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project path (default: current directory)",
            },
            "framework": {
                "type": "string",
                "description": "Override detected framework",
                "enum": [
                    "alembic",
                    "django",
                    "prisma",
                    "knex",
                    "sequelize",
                    "goose",
                    "diesel",
                    "seaorm",
                    "atlas",
                ],
            },
            "verbose": {
                "type": "boolean",
                "description": "Show detailed information",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        framework: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Check migration status."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect framework
        detector = MigrationDetector()
        info = detector.detect(project_path)

        if framework:
            lang_map = {
                "alembic": "python",
                "django": "python",
                "prisma": "node",
                "knex": "node",
                "sequelize": "node",
                "goose": "go",
                "atlas": "go",
                "diesel": "rust",
                "seaorm": "rust",
            }
            info = MigrationInfo(
                framework=framework,
                language=lang_map.get(framework, "unknown"),
                is_configured=info.is_configured if info else False,
            )
        elif not info:
            return ToolResult(
                success=False,
                output="",
                error="Could not detect migration framework.",
            )

        try:
            if info.framework == "alembic":
                cmd = ["alembic", "current"]
                if verbose:
                    cmd.append("-v")
            elif info.framework == "django":
                cmd = ["python", "manage.py", "showmigrations"]
            elif info.framework == "prisma":
                cmd = ["npx", "prisma", "migrate", "status"]
            elif info.framework == "knex":
                cmd = ["npx", "knex", "migrate:status"]
            elif info.framework == "sequelize":
                cmd = ["npx", "sequelize-cli", "db:migrate:status"]
            elif info.framework == "goose":
                cmd = ["goose", "status"]
            elif info.framework == "diesel":
                cmd = ["diesel", "migration", "list"]
            elif info.framework == "atlas":
                cmd = ["atlas", "migrate", "status"]
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Status check not supported for {info.framework}",
                )

            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            output = result.stdout or result.stderr
            return ToolResult(
                success=result.returncode == 0,
                output=f"Migration status ({info.framework}):\n{output}",
                error=result.stderr if result.returncode != 0 else None,
                metadata={
                    "framework": info.framework,
                    "command": " ".join(cmd),
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, output="", error="Migration status check timed out"
            )
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Migration tool not found: {str(e)}. Please install {info.framework}.",
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Status check failed: {str(e)}"
            )


class RunMigrationsTool(Tool):
    """Run pending database migrations.

    Applies all pending migrations to the database.
    """

    name = "run_migrations"
    description = """Run pending database migrations.

Applies all pending migrations to the database.

Examples:
- run_migrations() - Apply all pending migrations
- run_migrations(target="head") - Migrate to specific revision
- run_migrations(framework="alembic") - Force specific framework
- run_migrations(dry_run=true) - Preview without applying"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project path (default: current directory)",
            },
            "framework": {
                "type": "string",
                "description": "Override detected framework",
                "enum": [
                    "alembic",
                    "django",
                    "prisma",
                    "knex",
                    "sequelize",
                    "goose",
                    "diesel",
                    "seaorm",
                    "atlas",
                ],
            },
            "target": {
                "type": "string",
                "description": "Target revision/migration (default: latest)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview SQL without applying",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        framework: Optional[str] = None,
        target: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Run pending migrations."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect framework
        detector = MigrationDetector()
        info = detector.detect(project_path)

        if framework:
            lang_map = {
                "alembic": "python",
                "django": "python",
                "prisma": "node",
                "knex": "node",
                "sequelize": "node",
                "goose": "go",
                "atlas": "go",
                "diesel": "rust",
                "seaorm": "rust",
            }
            info = MigrationInfo(
                framework=framework,
                language=lang_map.get(framework, "unknown"),
                is_configured=info.is_configured if info else False,
            )
        elif not info:
            return ToolResult(
                success=False,
                output="",
                error="Could not detect migration framework.",
            )

        try:
            if info.framework == "alembic":
                cmd = ["alembic", "upgrade", target or "head"]
                if dry_run:
                    cmd = ["alembic", "upgrade", target or "head", "--sql"]
            elif info.framework == "django":
                cmd = ["python", "manage.py", "migrate"]
                if target:
                    cmd.extend([target])
                if dry_run:
                    cmd.append("--plan")
            elif info.framework == "prisma":
                if dry_run:
                    cmd = ["npx", "prisma", "migrate", "diff", "--preview-feature"]
                else:
                    cmd = ["npx", "prisma", "migrate", "deploy"]
            elif info.framework == "knex":
                cmd = ["npx", "knex", "migrate:latest"]
            elif info.framework == "sequelize":
                cmd = ["npx", "sequelize-cli", "db:migrate"]
            elif info.framework == "goose":
                cmd = ["goose", "up"]
                if target:
                    cmd = ["goose", "up-to", target]
            elif info.framework == "diesel":
                cmd = ["diesel", "migration", "run"]
            elif info.framework == "atlas":
                cmd = ["atlas", "migrate", "apply"]
                if dry_run:
                    cmd.append("--dry-run")
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Migration run not supported for {info.framework}",
                )

            if dry_run and info.framework not in ("alembic", "django", "prisma", "atlas"):
                return ToolResult(
                    success=True,
                    output=f"Would run: {' '.join(cmd)}",
                    metadata={"dry_run": True, "framework": info.framework},
                )

            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for migrations
            )

            output = result.stdout or result.stderr
            return ToolResult(
                success=result.returncode == 0,
                output=f"Migration result ({info.framework}):\n{output}",
                error=result.stderr if result.returncode != 0 else None,
                metadata={
                    "framework": info.framework,
                    "command": " ".join(cmd),
                    "dry_run": dry_run,
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, output="", error="Migration run timed out"
            )
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Migration tool not found: {str(e)}. Please install {info.framework}.",
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Migration run failed: {str(e)}"
            )


class RollbackMigrationTool(Tool):
    """Rollback database migrations.

    Reverts migrations to a previous state.
    """

    name = "rollback_migration"
    description = """Rollback database migrations.

Reverts migrations to a previous state.

Examples:
- rollback_migration() - Rollback last migration
- rollback_migration(steps=3) - Rollback 3 migrations
- rollback_migration(target="abc123") - Rollback to specific revision
- rollback_migration(dry_run=true) - Preview without rolling back"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project path (default: current directory)",
            },
            "framework": {
                "type": "string",
                "description": "Override detected framework",
                "enum": [
                    "alembic",
                    "django",
                    "prisma",
                    "knex",
                    "sequelize",
                    "goose",
                    "diesel",
                    "seaorm",
                    "atlas",
                ],
            },
            "steps": {
                "type": "integer",
                "description": "Number of migrations to rollback (default: 1)",
            },
            "target": {
                "type": "string",
                "description": "Target revision to rollback to",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview SQL without rolling back",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        framework: Optional[str] = None,
        steps: int = 1,
        target: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Rollback migrations."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect framework
        detector = MigrationDetector()
        info = detector.detect(project_path)

        if framework:
            lang_map = {
                "alembic": "python",
                "django": "python",
                "prisma": "node",
                "knex": "node",
                "sequelize": "node",
                "goose": "go",
                "atlas": "go",
                "diesel": "rust",
                "seaorm": "rust",
            }
            info = MigrationInfo(
                framework=framework,
                language=lang_map.get(framework, "unknown"),
                is_configured=info.is_configured if info else False,
            )
        elif not info:
            return ToolResult(
                success=False,
                output="",
                error="Could not detect migration framework.",
            )

        try:
            if info.framework == "alembic":
                if target:
                    cmd = ["alembic", "downgrade", target]
                else:
                    cmd = ["alembic", "downgrade", f"-{steps}"]
                if dry_run:
                    cmd.append("--sql")
            elif info.framework == "django":
                # Django requires app name and migration name
                cmd = ["python", "manage.py", "migrate"]
                if target:
                    cmd.extend([target])
                if dry_run:
                    cmd.append("--plan")
            elif info.framework == "prisma":
                # Prisma doesn't support direct rollback, suggest reset
                return ToolResult(
                    success=False,
                    output="",
                    error="Prisma doesn't support direct rollback. Use 'prisma migrate reset' or create a new migration to undo changes.",
                )
            elif info.framework == "knex":
                cmd = ["npx", "knex", "migrate:rollback"]
                if steps > 1:
                    cmd.extend(["--all"])  # Knex doesn't support step count well
            elif info.framework == "sequelize":
                cmd = ["npx", "sequelize-cli", "db:migrate:undo"]
                if steps > 1:
                    cmd = ["npx", "sequelize-cli", "db:migrate:undo:all"]
            elif info.framework == "goose":
                if target:
                    cmd = ["goose", "down-to", target]
                else:
                    cmd = ["goose", "down"]
            elif info.framework == "diesel":
                cmd = ["diesel", "migration", "revert"]
            elif info.framework == "atlas":
                cmd = ["atlas", "migrate", "down"]
                if steps:
                    cmd.extend(["--amount", str(steps)])
                if dry_run:
                    cmd.append("--dry-run")
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Rollback not supported for {info.framework}",
                )

            if dry_run and info.framework not in ("alembic", "django", "atlas"):
                return ToolResult(
                    success=True,
                    output=f"Would run: {' '.join(cmd)}",
                    metadata={"dry_run": True, "framework": info.framework},
                )

            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = result.stdout or result.stderr
            return ToolResult(
                success=result.returncode == 0,
                output=f"Rollback result ({info.framework}):\n{output}",
                error=result.stderr if result.returncode != 0 else None,
                metadata={
                    "framework": info.framework,
                    "command": " ".join(cmd),
                    "dry_run": dry_run,
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, output="", error="Rollback timed out"
            )
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Migration tool not found: {str(e)}. Please install {info.framework}.",
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Rollback failed: {str(e)}"
            )


class ValidateMigrationsTool(Tool):
    """Validate database migrations.

    Checks for consistency issues in migration files.
    """

    name = "validate_migrations"
    description = """Validate database migrations for consistency.

Checks for issues like missing down migrations, syntax errors, and consistency problems.

Examples:
- validate_migrations() - Validate all migrations
- validate_migrations(path="/app") - Specify project path
- validate_migrations(check_down=true) - Ensure down migrations exist"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project path (default: current directory)",
            },
            "framework": {
                "type": "string",
                "description": "Override detected framework",
                "enum": [
                    "alembic",
                    "django",
                    "prisma",
                    "knex",
                    "sequelize",
                    "goose",
                    "diesel",
                    "seaorm",
                    "atlas",
                ],
            },
            "check_down": {
                "type": "boolean",
                "description": "Verify down migrations exist",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        framework: Optional[str] = None,
        check_down: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Validate migrations."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect framework
        detector = MigrationDetector()
        info = detector.detect(project_path)

        if framework:
            lang_map = {
                "alembic": "python",
                "django": "python",
                "prisma": "node",
                "knex": "node",
                "sequelize": "node",
                "goose": "go",
                "atlas": "go",
                "diesel": "rust",
                "seaorm": "rust",
            }
            info = MigrationInfo(
                framework=framework,
                language=lang_map.get(framework, "unknown"),
                is_configured=info.is_configured if info else False,
            )
        elif not info:
            return ToolResult(
                success=False,
                output="",
                error="Could not detect migration framework.",
            )

        issues: list[str] = []
        warnings: list[str] = []
        valid_count = 0

        migrations_dir = project_path / (info.migrations_dir or "migrations")

        if not migrations_dir.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Migrations directory not found: {migrations_dir}",
            )

        # Framework-specific validation
        if info.framework == "alembic":
            issues, warnings, valid_count = self._validate_alembic(migrations_dir, check_down)
        elif info.framework == "django":
            issues, warnings, valid_count = self._validate_django(project_path)
        elif info.framework == "prisma":
            issues, warnings, valid_count = self._validate_prisma(migrations_dir)
        elif info.framework in ("knex", "sequelize"):
            issues, warnings, valid_count = self._validate_js_migrations(migrations_dir, check_down)
        elif info.framework == "goose":
            issues, warnings, valid_count = self._validate_goose(migrations_dir)
        elif info.framework == "diesel":
            issues, warnings, valid_count = self._validate_diesel(migrations_dir)
        else:
            issues, warnings, valid_count = self._validate_generic(migrations_dir)

        # Build output
        output_lines = [f"Migration validation ({info.framework}):"]
        output_lines.append(f"  Migrations found: {valid_count}")

        if issues:
            output_lines.append("\nErrors:")
            for issue in issues:
                output_lines.append(f"  - {issue}")

        if warnings:
            output_lines.append("\nWarnings:")
            for warn in warnings:
                output_lines.append(f"  - {warn}")

        if not issues and not warnings:
            output_lines.append("\nAll migrations valid!")

        return ToolResult(
            success=len(issues) == 0,
            output="\n".join(output_lines),
            metadata={
                "framework": info.framework,
                "valid_count": valid_count,
                "errors": issues,
                "warnings": warnings,
            },
        )

    def _validate_alembic(
        self, migrations_dir: Path, check_down: bool
    ) -> tuple[list[str], list[str], int]:
        """Validate Alembic migrations."""
        issues = []
        warnings = []
        count = 0

        versions_dir = migrations_dir / "versions"
        if not versions_dir.exists():
            versions_dir = migrations_dir

        for f in versions_dir.glob("*.py"):
            if f.name.startswith("__"):
                continue
            count += 1
            content = f.read_text()

            # Check for revision ID
            if "revision =" not in content:
                issues.append(f"{f.name}: Missing revision ID")

            # Check for upgrade function
            if "def upgrade" not in content:
                issues.append(f"{f.name}: Missing upgrade() function")

            # Check for downgrade function
            if check_down and "def downgrade" not in content:
                warnings.append(f"{f.name}: Missing downgrade() function")

            # Check for empty operations
            if "pass" in content and ("op." not in content):
                warnings.append(f"{f.name}: May have empty migration operations")

        return issues, warnings, count

    def _validate_django(self, project_path: Path) -> tuple[list[str], list[str], int]:
        """Validate Django migrations."""
        issues = []
        warnings = []
        count = 0

        # Find all migration directories
        for app_dir in project_path.iterdir():
            migrations_dir = app_dir / "migrations"
            if migrations_dir.exists():
                for f in migrations_dir.glob("*.py"):
                    if f.name.startswith("__"):
                        continue
                    count += 1
                    content = f.read_text()

                    if "class Migration" not in content:
                        issues.append(f"{app_dir.name}/{f.name}: Missing Migration class")

                    if "dependencies" not in content:
                        warnings.append(f"{app_dir.name}/{f.name}: Missing dependencies")

                    if "operations" not in content:
                        issues.append(f"{app_dir.name}/{f.name}: Missing operations")

        return issues, warnings, count

    def _validate_prisma(self, migrations_dir: Path) -> tuple[list[str], list[str], int]:
        """Validate Prisma migrations."""
        issues = []
        warnings = []
        count = 0

        for migration_dir in migrations_dir.iterdir():
            if not migration_dir.is_dir():
                continue

            migration_sql = migration_dir / "migration.sql"
            if migration_sql.exists():
                count += 1
                content = migration_sql.read_text()

                if not content.strip():
                    warnings.append(f"{migration_dir.name}: Empty migration")
            else:
                issues.append(f"{migration_dir.name}: Missing migration.sql")

        return issues, warnings, count

    def _validate_js_migrations(
        self, migrations_dir: Path, check_down: bool
    ) -> tuple[list[str], list[str], int]:
        """Validate JavaScript migrations (Knex/Sequelize)."""
        issues = []
        warnings = []
        count = 0

        for f in migrations_dir.glob("*.js"):
            count += 1
            content = f.read_text()

            if "exports.up" not in content and "up:" not in content:
                issues.append(f"{f.name}: Missing up migration")

            if check_down:
                if "exports.down" not in content and "down:" not in content:
                    warnings.append(f"{f.name}: Missing down migration")

        return issues, warnings, count

    def _validate_goose(self, migrations_dir: Path) -> tuple[list[str], list[str], int]:
        """Validate Goose migrations."""
        issues = []
        warnings = []
        count = 0

        for f in migrations_dir.glob("*.sql"):
            count += 1
            content = f.read_text()

            if "+goose Up" not in content:
                issues.append(f"{f.name}: Missing +goose Up directive")

            if "+goose Down" not in content:
                warnings.append(f"{f.name}: Missing +goose Down directive")

        return issues, warnings, count

    def _validate_diesel(self, migrations_dir: Path) -> tuple[list[str], list[str], int]:
        """Validate Diesel migrations."""
        issues = []
        warnings = []
        count = 0

        for migration_dir in migrations_dir.iterdir():
            if not migration_dir.is_dir():
                continue

            up_sql = migration_dir / "up.sql"
            down_sql = migration_dir / "down.sql"

            if up_sql.exists():
                count += 1
                if not up_sql.read_text().strip():
                    warnings.append(f"{migration_dir.name}: Empty up.sql")
            else:
                issues.append(f"{migration_dir.name}: Missing up.sql")

            if not down_sql.exists():
                warnings.append(f"{migration_dir.name}: Missing down.sql")
            elif not down_sql.read_text().strip():
                warnings.append(f"{migration_dir.name}: Empty down.sql")

        return issues, warnings, count

    def _validate_generic(self, migrations_dir: Path) -> tuple[list[str], list[str], int]:
        """Validate generic SQL migrations."""
        issues = []
        warnings = []
        count = 0

        for f in migrations_dir.glob("*.sql"):
            count += 1
            content = f.read_text()

            if not content.strip():
                warnings.append(f"{f.name}: Empty migration file")

        return issues, warnings, count
