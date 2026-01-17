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
