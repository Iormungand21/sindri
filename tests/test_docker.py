"""Tests for Docker file generation tools."""

import pytest
import json

from sindri.tools.docker import (
    GenerateDockerfileTool,
    GenerateDockerComposeTool,
    ValidateDockerfileTool,
    DockerProjectInfo,
)


class TestDockerProjectDetection:
    """Tests for project type detection for Docker generation."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateDockerfileTool instance."""
        return GenerateDockerfileTool(work_dir=tmp_path)

    def test_detect_python_pyproject(self, tool, tmp_path):
        """Test Python project detection with pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[tool.poetry]
name = "myproject"

[tool.poetry.dependencies]
fastapi = "^0.100.0"
uvicorn = "^0.23.0"
"""
        )
        (tmp_path / "main.py").write_text("# main app")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert info.package_manager == "poetry"
        assert info.has_pyproject is True
        assert info.entry_point == "main.py"

    def test_detect_python_requirements(self, tool, tmp_path):
        """Test Python project detection with requirements.txt."""
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (tmp_path / "app.py").write_text("# app")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert info.package_manager == "pip"
        assert info.has_requirements is True
        assert info.entry_point == "app.py"

    def test_detect_python_flask(self, tool, tmp_path):
        """Test Python project detection with Flask."""
        (tmp_path / "requirements.txt").write_text("flask\n")
        (tmp_path / "app.py").write_text("# flask app")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert "flask" in info.start_command.lower()
        assert info.port == 5000

    def test_detect_python_django(self, tool, tmp_path):
        """Test Python project detection with Django."""
        (tmp_path / "requirements.txt").write_text("django\n")
        (tmp_path / "manage.py").write_text("# django manage")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert "manage.py" in info.start_command

    def test_detect_node_npm(self, tool, tmp_path):
        """Test Node.js project detection with npm."""
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "myproject",
                    "main": "index.js",
                    "scripts": {"start": "node index.js", "build": "tsc"},
                }
            )
        )
        (tmp_path / "package-lock.json").write_text("{}")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.package_manager == "npm"
        assert info.has_package_json is True
        assert info.has_lock_file is True
        assert info.entry_point == "index.js"
        assert info.build_command == "npm run build"

    def test_detect_node_yarn(self, tool, tmp_path):
        """Test Node.js project detection with yarn."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myproject"}))
        (tmp_path / "yarn.lock").write_text("")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.package_manager == "yarn"
        assert info.has_lock_file is True

    def test_detect_node_pnpm(self, tool, tmp_path):
        """Test Node.js project detection with pnpm."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myproject"}))
        (tmp_path / "pnpm-lock.yaml").write_text("")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.package_manager == "pnpm"

    def test_detect_node_nextjs(self, tool, tmp_path):
        """Test Node.js project detection with Next.js."""
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "nextapp",
                    "dependencies": {"next": "^14.0.0", "react": "^18.0.0"},
                }
            )
        )

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.uses_static_files is True
        assert info.port == 3000

    def test_detect_rust(self, tool, tmp_path):
        """Test Rust project detection."""
        (tmp_path / "Cargo.toml").write_text(
            """
[package]
name = "myapp"
version = "0.1.0"
"""
        )

        info = tool._detect_project(tmp_path)

        assert info.project_type == "rust"
        assert info.package_manager == "cargo"
        assert info.entry_point == "myapp"

    def test_detect_go(self, tool, tmp_path):
        """Test Go project detection."""
        (tmp_path / "go.mod").write_text("module myproject")
        (tmp_path / "main.go").write_text("package main")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "go"
        assert info.package_manager == "go"
        assert info.entry_point == "main.go"

    def test_detect_go_cmd_structure(self, tool, tmp_path):
        """Test Go project detection with cmd structure."""
        (tmp_path / "go.mod").write_text("module myproject")
        cmd_dir = tmp_path / "cmd"
        cmd_dir.mkdir()
        (cmd_dir / "main.go").write_text("package main")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "go"
        assert info.entry_point == "cmd/main.go"

    def test_detect_generic(self, tool, tmp_path):
        """Test generic project detection."""
        info = tool._detect_project(tmp_path)

        assert info.project_type == "generic"


class TestGenerateDockerfileTool:
    """Tests for GenerateDockerfileTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateDockerfileTool instance."""
        return GenerateDockerfileTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_generate_python_dockerfile(self, tool, tmp_path):
        """Test generating Python Dockerfile."""
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (tmp_path / "main.py").write_text("# main")

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "FROM python:" in result.output
        assert "requirements.txt" in result.output
        assert "EXPOSE" in result.output
        assert result.metadata["project_type"] == "python"

    @pytest.mark.asyncio
    async def test_generate_python_poetry_dockerfile(self, tool, tmp_path):
        """Test generating Python Dockerfile with Poetry."""
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.poetry]
name = "myproject"
"""
        )

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "poetry" in result.output.lower()
        assert result.metadata["project_type"] == "python"

    @pytest.mark.asyncio
    async def test_generate_python_dockerfile_alpine(self, tool, tmp_path):
        """Test generating Python Dockerfile with Alpine."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(alpine=True, dry_run=True)

        assert result.success
        assert "-alpine" in result.output

    @pytest.mark.asyncio
    async def test_generate_python_dockerfile_custom_version(self, tool, tmp_path):
        """Test generating Python Dockerfile with custom version."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(python_version="3.12", dry_run=True)

        assert result.success
        assert "python:3.12" in result.output

    @pytest.mark.asyncio
    async def test_generate_node_dockerfile(self, tool, tmp_path):
        """Test generating Node.js Dockerfile."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myproject", "main": "index.js"})
        )

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "FROM node:" in result.output
        assert "package*.json" in result.output
        assert result.metadata["project_type"] == "node"

    @pytest.mark.asyncio
    async def test_generate_node_dockerfile_with_build(self, tool, tmp_path):
        """Test generating Node.js Dockerfile with build step."""
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "myproject",
                    "scripts": {"build": "tsc", "start": "node dist/index.js"},
                }
            )
        )

        result = await tool.execute(multi_stage=True, dry_run=True)

        assert result.success
        assert "AS builder" in result.output
        assert "RUN npm run build" in result.output

    @pytest.mark.asyncio
    async def test_generate_node_dockerfile_yarn(self, tool, tmp_path):
        """Test generating Node.js Dockerfile with yarn."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myproject"}))
        (tmp_path / "yarn.lock").write_text("")

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "yarn" in result.output

    @pytest.mark.asyncio
    async def test_generate_rust_dockerfile(self, tool, tmp_path):
        """Test generating Rust Dockerfile."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myapp"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}")

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "rust:" in result.output
        assert "cargo build" in result.output
        assert result.metadata["project_type"] == "rust"

    @pytest.mark.asyncio
    async def test_generate_rust_dockerfile_multi_stage(self, tool, tmp_path):
        """Test generating Rust Dockerfile with multi-stage build."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myapp"')

        result = await tool.execute(multi_stage=True, dry_run=True)

        assert result.success
        assert "AS builder" in result.output
        assert "--release" in result.output
        assert "COPY --from=builder" in result.output

    @pytest.mark.asyncio
    async def test_generate_go_dockerfile(self, tool, tmp_path):
        """Test generating Go Dockerfile."""
        (tmp_path / "go.mod").write_text("module myproject")
        (tmp_path / "main.go").write_text("package main")

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "golang:" in result.output
        assert "go build" in result.output
        assert result.metadata["project_type"] == "go"

    @pytest.mark.asyncio
    async def test_generate_go_dockerfile_multi_stage(self, tool, tmp_path):
        """Test generating Go Dockerfile with multi-stage build."""
        (tmp_path / "go.mod").write_text("module myproject")

        result = await tool.execute(multi_stage=True, dry_run=True)

        assert result.success
        assert "AS builder" in result.output
        assert "CGO_ENABLED=0" in result.output
        assert "COPY --from=builder" in result.output

    @pytest.mark.asyncio
    async def test_generate_generic_dockerfile(self, tool, tmp_path):
        """Test generating generic Dockerfile."""
        result = await tool.execute(dry_run=True)

        assert result.success
        assert "FROM alpine:latest" in result.output
        assert result.metadata["project_type"] == "generic"

    @pytest.mark.asyncio
    async def test_generate_dockerfile_custom_port(self, tool, tmp_path):
        """Test generating Dockerfile with custom port."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(port=5000, dry_run=True)

        assert result.success
        assert "EXPOSE 5000" in result.output

    @pytest.mark.asyncio
    async def test_generate_dockerfile_custom_entry_point(self, tool, tmp_path):
        """Test generating Dockerfile with custom entry point."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(entry_point="server.py", dry_run=True)

        assert result.success
        assert "server.py" in result.output

    @pytest.mark.asyncio
    async def test_generate_dockerfile_write_file(self, tool, tmp_path):
        """Test actually writing Dockerfile."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute()

        assert result.success
        dockerfile_path = tmp_path / "Dockerfile"
        assert dockerfile_path.exists()
        content = dockerfile_path.read_text()
        assert "FROM python:" in content

    @pytest.mark.asyncio
    async def test_generate_dockerfile_custom_output(self, tool, tmp_path):
        """Test generating Dockerfile with custom output file."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(output_file="Dockerfile.prod")

        assert result.success
        assert (tmp_path / "Dockerfile.prod").exists()

    @pytest.mark.asyncio
    async def test_generate_dockerfile_nonexistent_path(self, tool, tmp_path):
        """Test generating Dockerfile with nonexistent path."""
        result = await tool.execute(path="/nonexistent/path")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_generate_dockerfile_override_project_type(self, tool, tmp_path):
        """Test overriding project type detection."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(project_type="go", dry_run=True)

        assert result.success
        assert "golang:" in result.output
        assert result.metadata["project_type"] == "go"


class TestGenerateDockerComposeTool:
    """Tests for GenerateDockerComposeTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateDockerComposeTool instance."""
        return GenerateDockerComposeTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_generate_compose_basic(self, tool, tmp_path):
        """Test generating basic docker-compose.yml."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "version: '3.8'" in result.output
        assert "services:" in result.output
        assert "build: ." in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_postgres(self, tool, tmp_path):
        """Test generating docker-compose.yml with PostgreSQL."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["postgres"], dry_run=True)

        assert result.success
        assert "postgres:" in result.output
        assert "postgres:15-alpine" in result.output
        assert "POSTGRES_USER" in result.output
        assert "postgres_data:" in result.output
        assert "DATABASE_URL" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_redis(self, tool, tmp_path):
        """Test generating docker-compose.yml with Redis."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["redis"], dry_run=True)

        assert result.success
        assert "redis:" in result.output
        assert "redis:7-alpine" in result.output
        assert "REDIS_URL" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_mysql(self, tool, tmp_path):
        """Test generating docker-compose.yml with MySQL."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["mysql"], dry_run=True)

        assert result.success
        assert "mysql:" in result.output
        assert "mysql:8" in result.output
        assert "MYSQL_ROOT_PASSWORD" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_mongodb(self, tool, tmp_path):
        """Test generating docker-compose.yml with MongoDB."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["mongodb"], dry_run=True)

        assert result.success
        assert "mongodb:" in result.output
        assert "mongo:7" in result.output
        assert "MONGODB_URL" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_rabbitmq(self, tool, tmp_path):
        """Test generating docker-compose.yml with RabbitMQ."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["rabbitmq"], dry_run=True)

        assert result.success
        assert "rabbitmq:" in result.output
        assert "rabbitmq:3-management" in result.output
        assert "RABBITMQ_URL" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_kafka(self, tool, tmp_path):
        """Test generating docker-compose.yml with Kafka."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["kafka"], dry_run=True)

        assert result.success
        assert "kafka:" in result.output
        assert "zookeeper:" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_elasticsearch(self, tool, tmp_path):
        """Test generating docker-compose.yml with Elasticsearch."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["elasticsearch"], dry_run=True)

        assert result.success
        assert "elasticsearch:" in result.output
        assert "ELASTICSEARCH_URL" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_with_nginx(self, tool, tmp_path):
        """Test generating docker-compose.yml with nginx."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["nginx"], dry_run=True)

        assert result.success
        assert "nginx:" in result.output
        assert "nginx:alpine" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_multiple_services(self, tool, tmp_path):
        """Test generating docker-compose.yml with multiple services."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(services=["postgres", "redis"], dry_run=True)

        assert result.success
        assert "postgres:" in result.output
        assert "redis:" in result.output
        assert "depends_on:" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_custom_app_name(self, tool, tmp_path):
        """Test generating docker-compose.yml with custom app name."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(app_name="web", dry_run=True)

        assert result.success
        assert "web:" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_custom_port(self, tool, tmp_path):
        """Test generating docker-compose.yml with custom port."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(port=5000, dry_run=True)

        assert result.success
        assert "5000:5000" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_production(self, tool, tmp_path):
        """Test generating production docker-compose.yml."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(production=True, dry_run=True)

        assert result.success
        assert "restart: always" in result.output

    @pytest.mark.asyncio
    async def test_generate_compose_write_file(self, tool, tmp_path):
        """Test actually writing docker-compose.yml."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute()

        assert result.success
        compose_path = tmp_path / "docker-compose.yml"
        assert compose_path.exists()
        content = compose_path.read_text()
        assert "version: '3.8'" in content

    @pytest.mark.asyncio
    async def test_generate_compose_custom_output(self, tool, tmp_path):
        """Test generating docker-compose with custom output file."""
        (tmp_path / "requirements.txt").write_text("flask\n")

        result = await tool.execute(output_file="docker-compose.prod.yml")

        assert result.success
        assert (tmp_path / "docker-compose.prod.yml").exists()

    @pytest.mark.asyncio
    async def test_generate_compose_node_project(self, tool, tmp_path):
        """Test generating docker-compose for Node.js project."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myapp"}))

        result = await tool.execute(dry_run=True)

        assert result.success
        assert "3000:3000" in result.output  # Node default port


class TestValidateDockerfileTool:
    """Tests for ValidateDockerfileTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a ValidateDockerfileTool instance."""
        return ValidateDockerfileTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_validate_valid_dockerfile(self, tool, tmp_path):
        """Test validating a valid Dockerfile."""
        dockerfile_content = """FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

EXPOSE 8000

HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert len(result.metadata["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_empty_dockerfile(self, tool, tmp_path):
        """Test validating empty Dockerfile."""
        result = await tool.execute(content="")

        assert not result.success
        assert "empty" in result.metadata["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_validate_missing_from(self, tool, tmp_path):
        """Test validating Dockerfile without FROM."""
        dockerfile_content = """WORKDIR /app
COPY . .
CMD ["./app"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert not result.success
        assert any("FROM" in err for err in result.metadata["errors"])

    @pytest.mark.asyncio
    async def test_validate_latest_tag_warning(self, tool, tmp_path):
        """Test warning for :latest tag."""
        dockerfile_content = """FROM python:latest
WORKDIR /app
CMD ["python"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success  # Not an error
        assert any("latest" in warn.lower() for warn in result.metadata["warnings"])

    @pytest.mark.asyncio
    async def test_validate_missing_workdir(self, tool, tmp_path):
        """Test warning for missing WORKDIR."""
        dockerfile_content = """FROM python:3.11
COPY . .
CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success  # Not an error
        assert any("WORKDIR" in warn for warn in result.metadata["warnings"])

    @pytest.mark.asyncio
    async def test_validate_missing_user(self, tool, tmp_path):
        """Test suggestion for missing USER."""
        dockerfile_content = """FROM python:3.11
WORKDIR /app
CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert any(
            "USER" in sug or "non-root" in sug for sug in result.metadata["suggestions"]
        )

    @pytest.mark.asyncio
    async def test_validate_pip_no_cache(self, tool, tmp_path):
        """Test suggestion for pip without --no-cache-dir."""
        dockerfile_content = """FROM python:3.11
WORKDIR /app
RUN pip install requests
CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert any("--no-cache-dir" in sug for sug in result.metadata["suggestions"])

    @pytest.mark.asyncio
    async def test_validate_add_vs_copy(self, tool, tmp_path):
        """Test suggestion for ADD vs COPY."""
        dockerfile_content = """FROM python:3.11
WORKDIR /app
ADD . .
CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert any(
            "COPY" in sug and "ADD" in sug for sug in result.metadata["suggestions"]
        )

    @pytest.mark.asyncio
    async def test_validate_apt_cleanup(self, tool, tmp_path):
        """Test suggestion for apt-get cleanup."""
        dockerfile_content = """FROM debian:bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y curl
CMD ["./app"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert any("apt" in sug.lower() for sug in result.metadata["suggestions"])

    @pytest.mark.asyncio
    async def test_validate_missing_healthcheck(self, tool, tmp_path):
        """Test suggestion for missing HEALTHCHECK."""
        dockerfile_content = """FROM python:3.11
WORKDIR /app
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert any("HEALTHCHECK" in sug for sug in result.metadata["suggestions"])

    @pytest.mark.asyncio
    async def test_validate_missing_expose(self, tool, tmp_path):
        """Test suggestion for missing EXPOSE."""
        dockerfile_content = """FROM python:3.11
WORKDIR /app
COPY . .
CMD ["python", "main.py"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success
        assert any("EXPOSE" in sug for sug in result.metadata["suggestions"])

    @pytest.mark.asyncio
    async def test_validate_file_path(self, tool, tmp_path):
        """Test validating Dockerfile from file path."""
        dockerfile_path = tmp_path / "Dockerfile"
        dockerfile_path.write_text(
            """FROM python:3.11
WORKDIR /app
EXPOSE 8000
CMD ["python", "main.py"]
"""
        )

        result = await tool.execute(file_path="Dockerfile")

        assert result.success
        assert "Validating:" in result.output

    @pytest.mark.asyncio
    async def test_validate_nonexistent_file(self, tool, tmp_path):
        """Test validating nonexistent Dockerfile."""
        result = await tool.execute(file_path="NonexistentDockerfile")

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_validate_multi_stage_dockerfile(self, tool, tmp_path):
        """Test validating multi-stage Dockerfile."""
        dockerfile_content = """FROM golang:1.21 AS builder
WORKDIR /app
COPY . .
RUN go build -o main .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
"""
        result = await tool.execute(content=dockerfile_content)

        assert result.success


class TestToolRegistry:
    """Tests for Docker tools in registry."""

    def test_tools_registered(self, tmp_path):
        """Test that Docker tools are registered in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default(work_dir=tmp_path)

        assert registry.get_tool("generate_dockerfile") is not None
        assert registry.get_tool("generate_docker_compose") is not None
        assert registry.get_tool("validate_dockerfile") is not None

    def test_tool_schemas(self, tmp_path):
        """Test that Docker tools have valid schemas."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default(work_dir=tmp_path)
        schemas = registry.get_schemas()

        tool_names = [s["function"]["name"] for s in schemas]
        assert "generate_dockerfile" in tool_names
        assert "generate_docker_compose" in tool_names
        assert "validate_dockerfile" in tool_names


class TestDockerProjectInfo:
    """Tests for DockerProjectInfo dataclass."""

    def test_default_values(self):
        """Test default values for DockerProjectInfo."""
        info = DockerProjectInfo(project_type="python")

        assert info.project_type == "python"
        assert info.python_version == "3.11"
        assert info.node_version == "20"
        assert info.port == 8000
        assert info.services == []

    def test_custom_values(self):
        """Test custom values for DockerProjectInfo."""
        info = DockerProjectInfo(
            project_type="node",
            node_version="18",
            port=3000,
            package_manager="yarn",
            services=["postgres", "redis"],
        )

        assert info.project_type == "node"
        assert info.node_version == "18"
        assert info.port == 3000
        assert info.package_manager == "yarn"
        assert info.services == ["postgres", "redis"]


# =============================================================================
# Docker Runtime Tools Tests
# =============================================================================

import shutil
from unittest.mock import AsyncMock, patch, MagicMock

from sindri.tools.docker import (
    DockerPsTool,
    DockerImagesTool,
    DockerLogsTool,
    DockerBuildTool,
    DockerRunTool,
    DockerStopTool,
    DockerRmTool,
    DockerComposeUpTool,
    DockerComposeDownTool,
    DOCKER_AVAILABLE,
    _run_docker,
    _run_compose,
)


# Skip marker for when Docker is not available
DOCKER_INSTALLED = shutil.which("docker") is not None
skip_no_docker = pytest.mark.skipif(
    not DOCKER_INSTALLED,
    reason="Docker not installed"
)


class TestDockerAvailability:
    """Tests for Docker availability detection."""

    def test_docker_available_detection(self):
        """Test that DOCKER_AVAILABLE is correctly detected."""
        # This just tests that the constant is a boolean
        assert isinstance(DOCKER_AVAILABLE, bool)

    @pytest.mark.asyncio
    async def test_run_docker_not_available(self):
        """Test _run_docker when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            returncode, stdout, stderr = await _run_docker("ps")
            assert returncode == -1
            assert "Docker not found" in stderr


class TestDockerPsTool:
    """Tests for DockerPsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerPsTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_containers_success(self, tool):
        """Test listing containers with mocked Docker."""
        mock_output = """CONTAINER ID   IMAGE   STATUS   PORTS   NAMES
abc123   nginx   Up 2 hours   80/tcp   web
def456   postgres   Up 2 hours   5432/tcp   db"""

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute()

        assert result.success is True
        assert "nginx" in result.output
        assert result.metadata["container_count"] == 2

    @pytest.mark.asyncio
    async def test_list_containers_with_all_flag(self, tool):
        """Test listing all containers including stopped."""
        mock_output = """CONTAINER ID   IMAGE   STATUS   PORTS   NAMES
abc123   nginx   Up 2 hours   80/tcp   web
xyz789   alpine   Exited (0) 1 day ago      old"""

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                result = await tool.execute(all=True)

        assert result.success is True
        assert result.metadata["show_all"] is True
        mock.assert_called_once()
        # Verify -a flag was passed
        call_args = mock.call_args[0]
        assert "-a" in call_args

    @pytest.mark.asyncio
    async def test_list_containers_with_filter(self, tool):
        """Test filtering containers."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(filter="name=web")

        call_args = mock.call_args[0]
        assert "--filter" in call_args
        assert "name=web" in call_args

    @pytest.mark.asyncio
    async def test_list_containers_json_format(self, tool):
        """Test JSON output format."""
        mock_json = '{"ID":"abc123","Image":"nginx","Names":"web"}\n'

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, mock_json, ""))):
                result = await tool.execute(format="json")

        assert result.success is True
        assert result.metadata["format"] == "json"


class TestDockerImagesTool:
    """Tests for DockerImagesTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerImagesTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_images_success(self, tool):
        """Test listing images with mocked Docker."""
        mock_output = """REPOSITORY   TAG   IMAGE ID   SIZE   CREATED
nginx   latest   abc123   50MB   2 weeks ago
postgres   15   def456   100MB   1 month ago"""

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute()

        assert result.success is True
        assert "nginx" in result.output
        assert result.metadata["image_count"] == 2

    @pytest.mark.asyncio
    async def test_list_images_with_filter(self, tool):
        """Test filtering images."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(filter="dangling=true")

        call_args = mock.call_args[0]
        assert "--filter" in call_args
        assert "dangling=true" in call_args


class TestDockerLogsTool:
    """Tests for DockerLogsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerLogsTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute(container="myapp")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_logs_success(self, tool):
        """Test getting container logs."""
        mock_logs = "2024-01-01 Starting app...\n2024-01-01 Ready on port 8000\n"

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, mock_logs, ""))):
                result = await tool.execute(container="myapp")

        assert result.success is True
        assert "Starting app" in result.output
        assert result.metadata["container"] == "myapp"
        assert result.metadata["line_count"] == 2

    @pytest.mark.asyncio
    async def test_get_logs_with_tail(self, tool):
        """Test getting logs with tail option."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(container="myapp", tail=50)

        call_args = mock.call_args[0]
        assert "--tail" in call_args
        assert "50" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_with_since(self, tool):
        """Test getting logs with since option."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(container="myapp", since="10m")

        call_args = mock.call_args[0]
        assert "--since" in call_args
        assert "10m" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_container_not_found(self, tool):
        """Test getting logs for non-existent container."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(1, "", "No such container"))):
                result = await tool.execute(container="nonexistent")

        assert result.success is False
        assert "nonexistent" in result.error


class TestDockerBuildTool:
    """Tests for DockerBuildTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerBuildTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute(tag="test:latest")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_build_success(self, tool, tmp_path):
        """Test successful build."""
        (tmp_path / "Dockerfile").write_text("FROM alpine:latest\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "Successfully built abc123", ""))):
                result = await tool.execute(tag="myapp:latest", path=str(tmp_path))

        assert result.success is True
        assert "myapp:latest" in result.output
        assert result.metadata["tag"] == "myapp:latest"

    @pytest.mark.asyncio
    async def test_build_with_no_cache(self, tool, tmp_path):
        """Test build with no-cache flag."""
        (tmp_path / "Dockerfile").write_text("FROM alpine\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(tag="myapp:latest", path=str(tmp_path), no_cache=True)

        call_args = mock.call_args[0]
        assert "--no-cache" in call_args

    @pytest.mark.asyncio
    async def test_build_with_target(self, tool, tmp_path):
        """Test build with multi-stage target."""
        (tmp_path / "Dockerfile").write_text("FROM alpine AS builder\nFROM alpine\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(tag="myapp:latest", path=str(tmp_path), target="builder")

        call_args = mock.call_args[0]
        assert "--target" in call_args
        assert "builder" in call_args

    @pytest.mark.asyncio
    async def test_build_with_build_args(self, tool, tmp_path):
        """Test build with build arguments."""
        (tmp_path / "Dockerfile").write_text("FROM alpine\nARG VERSION\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(
                    tag="myapp:latest",
                    path=str(tmp_path),
                    build_args={"VERSION": "1.0"}
                )

        call_args = mock.call_args[0]
        assert "--build-arg" in call_args
        assert "VERSION=1.0" in call_args

    @pytest.mark.asyncio
    async def test_build_path_not_found(self, tool):
        """Test build with non-existent path."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            result = await tool.execute(tag="test:latest", path="/nonexistent/path")

        assert result.success is False
        assert "not found" in result.error.lower()


class TestDockerRunTool:
    """Tests for DockerRunTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerRunTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute(image="nginx")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_run_success(self, tool):
        """Test successful container run."""
        container_id = "abc123def456"

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, container_id, ""))):
                result = await tool.execute(image="nginx")

        assert result.success is True
        assert container_id[:12] in result.metadata["container_id"]

    @pytest.mark.asyncio
    async def test_run_with_name(self, tool):
        """Test run with container name."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "abc123", ""))) as mock:
                result = await tool.execute(image="nginx", name="web")

        assert result.success is True
        assert result.metadata["container_name"] == "web"
        call_args = mock.call_args[0]
        assert "--name" in call_args
        assert "web" in call_args

    @pytest.mark.asyncio
    async def test_run_with_ports(self, tool):
        """Test run with port mappings."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "abc123", ""))) as mock:
                await tool.execute(image="nginx", ports=["8080:80", "443:443"])

        call_args = mock.call_args[0]
        assert "-p" in call_args
        assert "8080:80" in call_args
        assert "443:443" in call_args

    @pytest.mark.asyncio
    async def test_run_with_volumes(self, tool):
        """Test run with volume mounts."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "abc123", ""))) as mock:
                await tool.execute(image="postgres", volumes=["./data:/var/lib/postgresql/data"])

        call_args = mock.call_args[0]
        assert "-v" in call_args
        assert "./data:/var/lib/postgresql/data" in call_args

    @pytest.mark.asyncio
    async def test_run_with_env(self, tool):
        """Test run with environment variables."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "abc123", ""))) as mock:
                await tool.execute(image="postgres", env={"POSTGRES_PASSWORD": "secret"})

        call_args = mock.call_args[0]
        assert "-e" in call_args
        assert "POSTGRES_PASSWORD=secret" in call_args

    @pytest.mark.asyncio
    async def test_run_with_remove_flag(self, tool):
        """Test run with --rm flag."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "abc123", ""))) as mock:
                await tool.execute(image="alpine", command="echo hello", remove=True)

        call_args = mock.call_args[0]
        assert "--rm" in call_args


class TestDockerStopTool:
    """Tests for DockerStopTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerStopTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute(container="myapp")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_stop_success(self, tool):
        """Test successful container stop."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "myapp", ""))):
                result = await tool.execute(container="myapp")

        assert result.success is True
        assert "Stopped" in result.output
        assert result.metadata["container"] == "myapp"

    @pytest.mark.asyncio
    async def test_stop_with_timeout(self, tool):
        """Test stop with custom timeout."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(container="myapp", timeout=30)

        call_args = mock.call_args[0]
        assert "-t" in call_args
        assert "30" in call_args

    @pytest.mark.asyncio
    async def test_stop_container_not_found(self, tool):
        """Test stopping non-existent container."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(1, "", "No such container"))):
                result = await tool.execute(container="nonexistent")

        assert result.success is False


class TestDockerRmTool:
    """Tests for DockerRmTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerRmTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute(container="myapp")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rm_success(self, tool):
        """Test successful container removal."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "myapp", ""))):
                result = await tool.execute(container="myapp")

        assert result.success is True
        assert "Removed" in result.output

    @pytest.mark.asyncio
    async def test_rm_with_force(self, tool):
        """Test force removal."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(container="myapp", force=True)

        call_args = mock.call_args[0]
        assert "-f" in call_args

    @pytest.mark.asyncio
    async def test_rm_with_volumes(self, tool):
        """Test removal with associated volumes."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_docker", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(container="myapp", volumes=True)

        call_args = mock.call_args[0]
        assert "-v" in call_args
        assert result.metadata["volumes_removed"] is True


class TestDockerComposeUpTool:
    """Tests for DockerComposeUpTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerComposeUpTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_compose_file_not_found(self, tool, tmp_path):
        """Test when compose file doesn't exist."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            result = await tool.execute(path=str(tmp_path / "nonexistent.yml"))
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_compose_up_success(self, tool, tmp_path):
        """Test successful compose up."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  web:\n    image: nginx\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_compose", AsyncMock(return_value=(0, "Started", ""))):
                result = await tool.execute(path=str(compose_file))

        assert result.success is True
        assert result.metadata["detached"] is True

    @pytest.mark.asyncio
    async def test_compose_up_with_build(self, tool, tmp_path):
        """Test compose up with build flag."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  web:\n    build: .\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_compose", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(path=str(compose_file), build=True)

        call_args = mock.call_args[0]
        assert "--build" in call_args
        assert result.metadata["built"] is True

    @pytest.mark.asyncio
    async def test_compose_up_specific_services(self, tool, tmp_path):
        """Test compose up with specific services."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  web:\n    image: nginx\n  db:\n    image: postgres\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_compose", AsyncMock(return_value=(0, "", ""))) as mock:
                await tool.execute(path=str(compose_file), services=["web"])

        call_args = mock.call_args[0]
        assert "web" in call_args


class TestDockerComposeDownTool:
    """Tests for DockerComposeDownTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return DockerComposeDownTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_docker_not_available(self, tool):
        """Test behavior when Docker is not installed."""
        with patch("sindri.tools.docker.DOCKER_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_compose_down_success(self, tool, tmp_path):
        """Test successful compose down."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  web:\n    image: nginx\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_compose", AsyncMock(return_value=(0, "Stopped", ""))):
                result = await tool.execute(path=str(compose_file))

        assert result.success is True

    @pytest.mark.asyncio
    async def test_compose_down_with_volumes(self, tool, tmp_path):
        """Test compose down with volume removal."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  db:\n    image: postgres\nvolumes:\n  data:\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_compose", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(path=str(compose_file), volumes=True)

        call_args = mock.call_args[0]
        assert "-v" in call_args
        assert result.metadata["volumes_removed"] is True

    @pytest.mark.asyncio
    async def test_compose_down_with_rmi(self, tool, tmp_path):
        """Test compose down with image removal."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("version: '3'\nservices:\n  web:\n    build: .\n")

        with patch("sindri.tools.docker.DOCKER_AVAILABLE", True):
            with patch("sindri.tools.docker._run_compose", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(path=str(compose_file), rmi="local")

        call_args = mock.call_args[0]
        assert "--rmi" in call_args
        assert "local" in call_args


class TestDockerRuntimeToolsRegistry:
    """Tests for Docker runtime tools in registry."""

    def test_runtime_tools_registered(self, tmp_path):
        """Test that Docker runtime tools are registered in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default(work_dir=tmp_path)

        # Check all 9 runtime tools
        assert registry.get_tool("docker_ps") is not None
        assert registry.get_tool("docker_images") is not None
        assert registry.get_tool("docker_logs") is not None
        assert registry.get_tool("docker_build") is not None
        assert registry.get_tool("docker_run") is not None
        assert registry.get_tool("docker_stop") is not None
        assert registry.get_tool("docker_rm") is not None
        assert registry.get_tool("docker_compose_up") is not None
        assert registry.get_tool("docker_compose_down") is not None

    def test_runtime_tool_schemas(self, tmp_path):
        """Test that Docker runtime tools have valid schemas."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default(work_dir=tmp_path)
        schemas = registry.get_schemas()

        tool_names = [s["function"]["name"] for s in schemas]
        runtime_tools = [
            "docker_ps", "docker_images", "docker_logs",
            "docker_build", "docker_run", "docker_stop", "docker_rm",
            "docker_compose_up", "docker_compose_down"
        ]

        for tool_name in runtime_tools:
            assert tool_name in tool_names, f"Tool {tool_name} not in schemas"


class TestDockerAgentAssignments:
    """Tests for Docker tool assignments to agents."""

    def test_brokkr_has_docker_tools(self):
        """Test that Brokkr has all Docker runtime tools."""
        from sindri.agents.registry import get_agent

        agent = get_agent("brokkr")
        docker_tools = [
            "docker_ps", "docker_images", "docker_logs",
            "docker_build", "docker_run", "docker_stop", "docker_rm",
            "docker_compose_up", "docker_compose_down"
        ]

        for tool in docker_tools:
            assert tool in agent.tools, f"Brokkr missing tool: {tool}"

    def test_ratatoskr_has_readonly_docker_tools(self):
        """Test that Ratatoskr has read-only Docker tools."""
        from sindri.agents.registry import get_agent

        agent = get_agent("ratatoskr")
        readonly_tools = ["docker_ps", "docker_images", "docker_logs"]

        for tool in readonly_tools:
            assert tool in agent.tools, f"Ratatoskr missing tool: {tool}"

    def test_ratatoskr_no_destructive_docker_tools(self):
        """Test that Ratatoskr does NOT have destructive Docker tools."""
        from sindri.agents.registry import get_agent

        agent = get_agent("ratatoskr")
        destructive_tools = [
            "docker_build", "docker_run", "docker_stop", "docker_rm",
            "docker_compose_up", "docker_compose_down"
        ]

        for tool in destructive_tools:
            assert tool not in agent.tools, f"Ratatoskr should not have: {tool}"
