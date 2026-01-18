"""Tests for database migration tools."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from sindri.tools.migrations import (
    GenerateMigrationTool,
    MigrationStatusTool,
    RunMigrationsTool,
    RollbackMigrationTool,
    ValidateMigrationsTool,
    MigrationDetector,
    MigrationInfo,
)


# ============================================================================
# MigrationDetector Tests
# ============================================================================


class TestMigrationDetector:
    """Tests for MigrationDetector."""

    def test_detect_alembic_by_ini(self, tmp_path: Path):
        """Test detection of Alembic by alembic.ini."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "alembic"
        assert info.language == "python"
        assert info.is_configured is True

    def test_detect_alembic_by_dir(self, tmp_path: Path):
        """Test detection of Alembic by directory."""
        (tmp_path / "alembic").mkdir()
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "alembic"

    def test_detect_django(self, tmp_path: Path):
        """Test detection of Django."""
        (tmp_path / "manage.py").write_text("#!/usr/bin/env python\nimport django\n")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "django"
        assert info.language == "python"

    def test_detect_prisma(self, tmp_path: Path):
        """Test detection of Prisma."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "prisma"
        assert info.language == "node"

    def test_detect_knex_js(self, tmp_path: Path):
        """Test detection of Knex (JS)."""
        (tmp_path / "knexfile.js").write_text("module.exports = {}")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "knex"
        assert info.config_file == "knexfile.js"

    def test_detect_knex_ts(self, tmp_path: Path):
        """Test detection of Knex (TS)."""
        (tmp_path / "knexfile.ts").write_text("export default {}")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "knex"
        assert info.config_file == "knexfile.ts"

    def test_detect_sequelize(self, tmp_path: Path):
        """Test detection of Sequelize."""
        (tmp_path / ".sequelizerc").write_text("module.exports = {}")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "sequelize"
        assert info.language == "node"

    def test_detect_goose(self, tmp_path: Path):
        """Test detection of Goose."""
        (tmp_path / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "go.mod").write_text("module test\nrequire github.com/pressly/goose")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "goose"
        assert info.language == "go"

    def test_detect_atlas(self, tmp_path: Path):
        """Test detection of Atlas."""
        (tmp_path / "atlas.hcl").write_text("env {}")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "atlas"
        assert info.language == "go"

    def test_detect_diesel(self, tmp_path: Path):
        """Test detection of Diesel."""
        (tmp_path / "diesel.toml").write_text("[print_schema]\n")
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "diesel"
        assert info.language == "rust"

    def test_detect_seaorm(self, tmp_path: Path):
        """Test detection of SeaORM."""
        (tmp_path / "Cargo.toml").write_text('[dependencies]\nsea-orm = "0.12"')
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "seaorm"
        assert info.language == "rust"

    def test_detect_from_pyproject(self, tmp_path: Path):
        """Test detection from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["alembic"]')
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "alembic"

    def test_detect_from_package_json_prisma(self, tmp_path: Path):
        """Test detection from package.json with Prisma."""
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"@prisma/client": "^5.0.0"}
        }))
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "prisma"

    def test_detect_from_package_json_knex(self, tmp_path: Path):
        """Test detection from package.json with Knex."""
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"knex": "^3.0.0"}
        }))
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is not None
        assert info.framework == "knex"

    def test_detect_no_framework(self, tmp_path: Path):
        """Test detection returns None when no framework found."""
        detector = MigrationDetector()
        info = detector.detect(tmp_path)

        assert info is None


# ============================================================================
# GenerateMigrationTool Tests
# ============================================================================


class TestGenerateMigrationTool:
    """Tests for GenerateMigrationTool."""

    @pytest.fixture
    def tool(self, tmp_path: Path):
        return GenerateMigrationTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_generate_alembic_migration(self, tool, tmp_path: Path):
        """Test generating Alembic migration."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "alembic" / "versions").mkdir(parents=True)

        result = await tool.execute(
            name="add_users_table",
            message="Add users table",
            dry_run=True,
        )

        assert result.success
        assert "add_users_table" in result.output
        assert "alembic" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_migration_creates_file(self, tool, tmp_path: Path):
        """Test that migration file is created."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "alembic" / "versions").mkdir(parents=True)

        result = await tool.execute(
            name="create_posts",
            message="Create posts table",
        )

        assert result.success
        # Check that a migration file was created
        migrations = list((tmp_path / "alembic" / "versions").glob("*.py"))
        assert len(migrations) == 1
        assert "create_posts" in migrations[0].name

    @pytest.mark.asyncio
    async def test_generate_django_migration(self, tool, tmp_path: Path):
        """Test generating Django migration."""
        (tmp_path / "manage.py").write_text("import django")

        result = await tool.execute(
            name="add_comments",
            framework="django",
            dry_run=True,
        )

        assert result.success
        assert "django" in result.output.lower() or "Migration" in result.output

    @pytest.mark.asyncio
    async def test_generate_knex_migration(self, tool, tmp_path: Path):
        """Test generating Knex migration."""
        (tmp_path / "knexfile.js").write_text("module.exports = {}")

        result = await tool.execute(
            name="create_orders",
            dry_run=True,
        )

        assert result.success
        assert "create_orders" in result.output

    @pytest.mark.asyncio
    async def test_generate_goose_migration(self, tool, tmp_path: Path):
        """Test generating Goose migration."""
        (tmp_path / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "go.mod").write_text("module test\nrequire goose")

        result = await tool.execute(
            name="add_products",
            sql="CREATE TABLE products (id SERIAL PRIMARY KEY);",
            sql_down="DROP TABLE products;",
            dry_run=True,
        )

        assert result.success
        assert "+goose Up" in result.output
        assert "+goose Down" in result.output

    @pytest.mark.asyncio
    async def test_generate_diesel_migration(self, tool, tmp_path: Path):
        """Test generating Diesel migration."""
        (tmp_path / "diesel.toml").write_text("[print_schema]\n")
        (tmp_path / "migrations").mkdir()

        result = await tool.execute(
            name="add_inventory",
            sql="CREATE TABLE inventory (id SERIAL);",
            sql_down="DROP TABLE inventory;",
        )

        assert result.success
        # Diesel creates up.sql and down.sql
        migration_dirs = [d for d in (tmp_path / "migrations").iterdir() if d.is_dir()]
        assert len(migration_dirs) == 1
        assert (migration_dirs[0] / "up.sql").exists()
        assert (migration_dirs[0] / "down.sql").exists()

    @pytest.mark.asyncio
    async def test_generate_prisma_migration(self, tool, tmp_path: Path):
        """Test generating Prisma migration."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")
        (tmp_path / "prisma" / "migrations").mkdir()

        result = await tool.execute(
            name="add_categories",
            sql="CREATE TABLE categories (id SERIAL);",
            dry_run=True,
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_generate_with_sql_content(self, tool, tmp_path: Path):
        """Test generating migration with custom SQL."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "alembic" / "versions").mkdir(parents=True)

        result = await tool.execute(
            name="add_index",
            sql="CREATE INDEX idx_users_email ON users(email);",
            sql_down="DROP INDEX idx_users_email;",
        )

        assert result.success
        migrations = list((tmp_path / "alembic" / "versions").glob("*.py"))
        content = migrations[0].read_text()
        assert "idx_users_email" in content

    @pytest.mark.asyncio
    async def test_generate_no_framework_detected(self, tool, tmp_path: Path):
        """Test error when no framework detected."""
        result = await tool.execute(name="test_migration")

        assert not result.success
        assert "detect" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_force_framework(self, tool, tmp_path: Path):
        """Test forcing specific framework."""
        (tmp_path / "migrations").mkdir()

        result = await tool.execute(
            name="test_migration",
            framework="goose",
            dry_run=True,
        )

        assert result.success
        assert "+goose" in result.output

    @pytest.mark.asyncio
    async def test_generate_path_not_exists(self, tool, tmp_path: Path):
        """Test error when path doesn't exist."""
        result = await tool.execute(
            name="test",
            path="/nonexistent/path",
        )

        assert not result.success
        assert "not exist" in result.error

    @pytest.mark.asyncio
    async def test_generate_seaorm_migration(self, tool, tmp_path: Path):
        """Test generating SeaORM migration."""
        (tmp_path / "Cargo.toml").write_text('[dependencies]\nsea-orm = "0.12"')
        (tmp_path / "migration" / "src").mkdir(parents=True)

        result = await tool.execute(
            name="add_sessions",
            framework="seaorm",
            dry_run=True,
        )

        assert result.success
        assert "MigrationTrait" in result.output

    @pytest.mark.asyncio
    async def test_auto_generate_alembic(self, tool, tmp_path: Path):
        """Test auto-generation with Alembic."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "alembic" / "versions").mkdir(parents=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Generating migration...",
                stderr="",
            )

            result = await tool.execute(
                name="auto_migration",
                auto=True,
            )

            assert result.success
            mock_run.assert_called_once()
            assert "--autogenerate" in mock_run.call_args[0][0]


# ============================================================================
# MigrationStatusTool Tests
# ============================================================================


class TestMigrationStatusTool:
    """Tests for MigrationStatusTool."""

    @pytest.fixture
    def tool(self, tmp_path: Path):
        return MigrationStatusTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_status_alembic(self, tool, tmp_path: Path):
        """Test status check with Alembic."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Current revision: abc123",
                stderr="",
            )

            result = await tool.execute()

            assert result.success
            assert "Current revision" in result.output

    @pytest.mark.asyncio
    async def test_status_django(self, tool, tmp_path: Path):
        """Test status check with Django."""
        (tmp_path / "manage.py").write_text("import django")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="[X] 0001_initial\n[ ] 0002_add_users",
                stderr="",
            )

            result = await tool.execute(framework="django")

            assert result.success
            assert "0001_initial" in result.output

    @pytest.mark.asyncio
    async def test_status_prisma(self, tool, tmp_path: Path):
        """Test status check with Prisma."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Database is up to date",
                stderr="",
            )

            result = await tool.execute()

            assert result.success
            assert "up to date" in result.output

    @pytest.mark.asyncio
    async def test_status_tool_not_found(self, tool, tmp_path: Path):
        """Test error when migration tool not found."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("alembic not found")

            result = await tool.execute()

            assert not result.success
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_status_timeout(self, tool, tmp_path: Path):
        """Test timeout handling."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

            result = await tool.execute()

            assert not result.success
            assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_status_verbose(self, tool, tmp_path: Path):
        """Test verbose status."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Verbose output",
                stderr="",
            )

            result = await tool.execute(verbose=True)

            assert result.success
            # Check that -v flag was passed
            assert "-v" in mock_run.call_args[0][0]


# ============================================================================
# RunMigrationsTool Tests
# ============================================================================


class TestRunMigrationsTool:
    """Tests for RunMigrationsTool."""

    @pytest.fixture
    def tool(self, tmp_path: Path):
        return RunMigrationsTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_run_alembic(self, tool, tmp_path: Path):
        """Test running Alembic migrations."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Running upgrade to head...\nMigration complete.",
                stderr="",
            )

            result = await tool.execute()

            assert result.success
            assert "alembic" in mock_run.call_args[0][0]
            assert "upgrade" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_run_with_target(self, tool, tmp_path: Path):
        """Test running to specific target."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Upgrade complete",
                stderr="",
            )

            result = await tool.execute(target="abc123")

            assert result.success
            assert "abc123" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_run_dry_run(self, tool, tmp_path: Path):
        """Test dry run mode."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="-- SQL output --",
                stderr="",
            )

            result = await tool.execute(dry_run=True)

            assert result.success
            assert "--sql" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_run_django(self, tool, tmp_path: Path):
        """Test running Django migrations."""
        (tmp_path / "manage.py").write_text("import django")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Operations to perform...",
                stderr="",
            )

            result = await tool.execute(framework="django")

            assert result.success
            assert "manage.py" in mock_run.call_args[0][0]
            assert "migrate" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_run_prisma(self, tool, tmp_path: Path):
        """Test running Prisma migrations."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Applying migrations...",
                stderr="",
            )

            result = await tool.execute()

            assert result.success
            assert "prisma" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_run_failure(self, tool, tmp_path: Path):
        """Test handling migration failure."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: Migration failed",
            )

            result = await tool.execute()

            assert not result.success
            assert "Migration failed" in result.error

    @pytest.mark.asyncio
    async def test_run_knex(self, tool, tmp_path: Path):
        """Test running Knex migrations."""
        (tmp_path / "knexfile.js").write_text("module.exports = {}")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Batch 1 run: 3 migrations",
                stderr="",
            )

            result = await tool.execute()

            assert result.success


# ============================================================================
# RollbackMigrationTool Tests
# ============================================================================


class TestRollbackMigrationTool:
    """Tests for RollbackMigrationTool."""

    @pytest.fixture
    def tool(self, tmp_path: Path):
        return RollbackMigrationTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_rollback_alembic(self, tool, tmp_path: Path):
        """Test Alembic rollback."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Downgrade complete",
                stderr="",
            )

            result = await tool.execute()

            assert result.success
            assert "downgrade" in mock_run.call_args[0][0]
            assert "-1" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rollback_multiple_steps(self, tool, tmp_path: Path):
        """Test rolling back multiple migrations."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Rolled back 3 migrations",
                stderr="",
            )

            result = await tool.execute(steps=3)

            assert result.success
            assert "-3" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rollback_to_target(self, tool, tmp_path: Path):
        """Test rolling back to specific target."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Rolled back to abc123",
                stderr="",
            )

            result = await tool.execute(target="abc123")

            assert result.success
            assert "abc123" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rollback_dry_run(self, tool, tmp_path: Path):
        """Test dry run rollback."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="-- SQL --",
                stderr="",
            )

            result = await tool.execute(dry_run=True)

            assert result.success
            assert "--sql" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rollback_prisma_not_supported(self, tool, tmp_path: Path):
        """Test Prisma rollback not supported."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")

        result = await tool.execute()

        assert not result.success
        assert "doesn't support" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rollback_django(self, tool, tmp_path: Path):
        """Test Django rollback."""
        (tmp_path / "manage.py").write_text("import django")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Migration reverted",
                stderr="",
            )

            result = await tool.execute(framework="django", target="myapp:0001")

            assert result.success
            assert "myapp:0001" in mock_run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rollback_goose(self, tool, tmp_path: Path):
        """Test Goose rollback."""
        (tmp_path / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "go.mod").write_text("module test\nrequire goose")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="OK",
                stderr="",
            )

            result = await tool.execute()

            assert result.success
            assert "goose" in mock_run.call_args[0][0]
            assert "down" in mock_run.call_args[0][0]


# ============================================================================
# ValidateMigrationsTool Tests
# ============================================================================


class TestValidateMigrationsTool:
    """Tests for ValidateMigrationsTool."""

    @pytest.fixture
    def tool(self, tmp_path: Path):
        return ValidateMigrationsTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_validate_alembic_valid(self, tool, tmp_path: Path):
        """Test validating valid Alembic migrations."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        versions_dir = tmp_path / "alembic" / "versions"
        versions_dir.mkdir(parents=True)

        (versions_dir / "001_initial.py").write_text('''
revision = "001"
down_revision = None

def upgrade():
    op.create_table("users")

def downgrade():
    op.drop_table("users")
''')

        result = await tool.execute()

        assert result.success
        assert "All migrations valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_alembic_missing_revision(self, tool, tmp_path: Path):
        """Test detecting missing revision ID."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        versions_dir = tmp_path / "alembic" / "versions"
        versions_dir.mkdir(parents=True)

        (versions_dir / "bad_migration.py").write_text('''
def upgrade():
    pass
''')

        result = await tool.execute()

        assert not result.success
        assert "Missing revision ID" in result.output

    @pytest.mark.asyncio
    async def test_validate_alembic_missing_upgrade(self, tool, tmp_path: Path):
        """Test detecting missing upgrade function."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        versions_dir = tmp_path / "alembic" / "versions"
        versions_dir.mkdir(parents=True)

        (versions_dir / "bad_migration.py").write_text('''
revision = "001"

def downgrade():
    pass
''')

        result = await tool.execute()

        assert not result.success
        assert "Missing upgrade" in result.output

    @pytest.mark.asyncio
    async def test_validate_alembic_warning_missing_downgrade(self, tool, tmp_path: Path):
        """Test warning for missing downgrade."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        versions_dir = tmp_path / "alembic" / "versions"
        versions_dir.mkdir(parents=True)

        (versions_dir / "migration.py").write_text('''
revision = "001"

def upgrade():
    op.create_table("users")
''')

        result = await tool.execute()

        assert result.success  # Warning, not error
        assert "Missing downgrade" in result.output
        assert "Warning" in result.output

    @pytest.mark.asyncio
    async def test_validate_goose_valid(self, tool, tmp_path: Path):
        """Test validating valid Goose migrations."""
        (tmp_path / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "go.mod").write_text("module test\nrequire goose")

        (tmp_path / "db" / "migrations" / "001_init.sql").write_text('''
-- +goose Up
CREATE TABLE users (id SERIAL);

-- +goose Down
DROP TABLE users;
''')

        result = await tool.execute()

        assert result.success
        assert "All migrations valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_goose_missing_up(self, tool, tmp_path: Path):
        """Test detecting missing +goose Up."""
        (tmp_path / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "go.mod").write_text("module test\nrequire goose")

        (tmp_path / "db" / "migrations" / "001_init.sql").write_text('''
-- +goose Down
DROP TABLE users;
''')

        result = await tool.execute()

        assert not result.success
        assert "Missing +goose Up" in result.output

    @pytest.mark.asyncio
    async def test_validate_diesel_valid(self, tool, tmp_path: Path):
        """Test validating valid Diesel migrations."""
        (tmp_path / "diesel.toml").write_text("[print_schema]\n")
        migration_dir = tmp_path / "migrations" / "2024_01_01_init"
        migration_dir.mkdir(parents=True)

        (migration_dir / "up.sql").write_text("CREATE TABLE users (id SERIAL);")
        (migration_dir / "down.sql").write_text("DROP TABLE users;")

        result = await tool.execute()

        assert result.success
        assert "All migrations valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_diesel_missing_up(self, tool, tmp_path: Path):
        """Test detecting missing up.sql in Diesel."""
        (tmp_path / "diesel.toml").write_text("[print_schema]\n")
        migration_dir = tmp_path / "migrations" / "2024_01_01_init"
        migration_dir.mkdir(parents=True)

        (migration_dir / "down.sql").write_text("DROP TABLE users;")

        result = await tool.execute()

        assert not result.success
        assert "Missing up.sql" in result.output

    @pytest.mark.asyncio
    async def test_validate_prisma_valid(self, tool, tmp_path: Path):
        """Test validating valid Prisma migrations."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")
        migration_dir = tmp_path / "prisma" / "migrations" / "20240101_init"
        migration_dir.mkdir(parents=True)

        (migration_dir / "migration.sql").write_text("CREATE TABLE users (id INT);")

        result = await tool.execute()

        assert result.success

    @pytest.mark.asyncio
    async def test_validate_prisma_missing_sql(self, tool, tmp_path: Path):
        """Test detecting missing migration.sql in Prisma."""
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("generator client {}")
        migration_dir = tmp_path / "prisma" / "migrations" / "20240101_init"
        migration_dir.mkdir(parents=True)

        result = await tool.execute()

        assert not result.success
        assert "Missing migration.sql" in result.output

    @pytest.mark.asyncio
    async def test_validate_knex_valid(self, tool, tmp_path: Path):
        """Test validating valid Knex migrations."""
        (tmp_path / "knexfile.js").write_text("module.exports = {}")
        (tmp_path / "migrations").mkdir()

        (tmp_path / "migrations" / "001_init.js").write_text('''
exports.up = function(knex) { return knex.schema.createTable("users"); };
exports.down = function(knex) { return knex.schema.dropTable("users"); };
''')

        result = await tool.execute()

        assert result.success
        assert "All migrations valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_knex_missing_up(self, tool, tmp_path: Path):
        """Test detecting missing up function in Knex."""
        (tmp_path / "knexfile.js").write_text("module.exports = {}")
        (tmp_path / "migrations").mkdir()

        (tmp_path / "migrations" / "001_init.js").write_text('''
exports.down = function(knex) { return knex.schema.dropTable("users"); };
''')

        result = await tool.execute()

        assert not result.success
        assert "Missing up" in result.output

    @pytest.mark.asyncio
    async def test_validate_no_migrations_dir(self, tool, tmp_path: Path):
        """Test error when migrations directory doesn't exist."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")

        result = await tool.execute()

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_validate_metadata(self, tool, tmp_path: Path):
        """Test validation metadata."""
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        versions_dir = tmp_path / "alembic" / "versions"
        versions_dir.mkdir(parents=True)

        (versions_dir / "001.py").write_text('''
revision = "001"
def upgrade():
    pass
def downgrade():
    pass
''')
        (versions_dir / "002.py").write_text('''
revision = "002"
def upgrade():
    pass
def downgrade():
    pass
''')

        result = await tool.execute()

        assert result.success
        assert result.metadata["valid_count"] == 2
        assert result.metadata["framework"] == "alembic"


# ============================================================================
# Integration Tests
# ============================================================================


class TestMigrationWorkflow:
    """Integration tests for migration workflow."""

    @pytest.mark.asyncio
    async def test_create_and_validate_workflow(self, tmp_path: Path):
        """Test creating and validating a migration."""
        # Setup Alembic project
        (tmp_path / "alembic.ini").write_text("[alembic]\n")
        (tmp_path / "alembic" / "versions").mkdir(parents=True)

        # Generate migration
        gen_tool = GenerateMigrationTool(work_dir=tmp_path)
        result = await gen_tool.execute(
            name="add_users",
            message="Add users table",
            sql="CREATE TABLE users (id SERIAL PRIMARY KEY);",
            sql_down="DROP TABLE users;",
        )
        assert result.success

        # Validate migration
        validate_tool = ValidateMigrationsTool(work_dir=tmp_path)
        result = await validate_tool.execute()
        assert result.success
        assert result.metadata["valid_count"] == 1

    @pytest.mark.asyncio
    async def test_diesel_create_and_validate(self, tmp_path: Path):
        """Test Diesel migration workflow."""
        # Setup Diesel project
        (tmp_path / "diesel.toml").write_text("[print_schema]\n")
        (tmp_path / "migrations").mkdir()

        # Generate migration
        gen_tool = GenerateMigrationTool(work_dir=tmp_path)
        result = await gen_tool.execute(
            name="create_posts",
            sql="CREATE TABLE posts (id SERIAL, title TEXT);",
            sql_down="DROP TABLE posts;",
        )
        assert result.success

        # Validate migration
        validate_tool = ValidateMigrationsTool(work_dir=tmp_path)
        result = await validate_tool.execute()
        assert result.success

    @pytest.mark.asyncio
    async def test_goose_create_and_validate(self, tmp_path: Path):
        """Test Goose migration workflow."""
        # Setup Goose project
        (tmp_path / "db" / "migrations").mkdir(parents=True)
        (tmp_path / "go.mod").write_text("module test\nrequire goose")

        # Generate migration
        gen_tool = GenerateMigrationTool(work_dir=tmp_path)
        result = await gen_tool.execute(
            name="add_comments",
            sql="CREATE TABLE comments (id SERIAL);",
            sql_down="DROP TABLE comments;",
        )
        assert result.success

        # Validate migration
        validate_tool = ValidateMigrationsTool(work_dir=tmp_path)
        result = await validate_tool.execute()
        assert result.success
