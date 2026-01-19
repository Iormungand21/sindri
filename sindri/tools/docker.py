"""Docker tools for Sindri.

Provides tools for generating Dockerfiles and docker-compose.yml files,
as well as runtime tools for building, running, and managing containers.
"""

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check Docker availability
DOCKER_AVAILABLE = shutil.which("docker") is not None


def _get_compose_command() -> list[str] | None:
    """Get the docker compose command (v2 plugin or v1 standalone).

    Returns:
        List of command parts, or None if compose not available.
    """
    if not DOCKER_AVAILABLE:
        return None
    # Docker Compose v2 (plugin) - preferred
    # We'll try it and fall back to v1 if needed
    return ["docker", "compose"]


async def _run_docker(
    *args: str,
    timeout: int = 300,
    input_data: str | None = None,
) -> tuple[int, str, str]:
    """Run a docker command asynchronously.

    Args:
        *args: Docker command arguments (e.g., "ps", "-a")
        timeout: Command timeout in seconds
        input_data: Optional stdin data

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    if not DOCKER_AVAILABLE:
        return (-1, "", "Docker not found. Please install Docker.")

    cmd = ["docker"] + list(args)
    log.debug("docker_command", cmd=cmd)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_data else None,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input_data.encode() if input_data else None),
            timeout=timeout,
        )

        return (proc.returncode or 0, stdout.decode(), stderr.decode())
    except asyncio.TimeoutError:
        return (-1, "", f"Docker command timed out after {timeout}s")
    except Exception as e:
        return (-1, "", f"Docker command failed: {str(e)}")


async def _run_compose(
    *args: str,
    cwd: Path | None = None,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Run a docker compose command asynchronously.

    Args:
        *args: Compose command arguments (e.g., "up", "-d")
        cwd: Working directory for the command
        timeout: Command timeout in seconds

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    compose_cmd = _get_compose_command()
    if compose_cmd is None:
        return (-1, "", "Docker Compose not found.")

    cmd = compose_cmd + list(args)
    log.debug("compose_command", cmd=cmd, cwd=str(cwd) if cwd else None)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )

        return (proc.returncode or 0, stdout.decode(), stderr.decode())
    except asyncio.TimeoutError:
        return (-1, "", f"Docker Compose command timed out after {timeout}s")
    except Exception as e:
        return (-1, "", f"Docker Compose command failed: {str(e)}")


@dataclass
class DockerProjectInfo:
    """Detected project information for Docker generation."""

    project_type: str  # python, node, rust, go, generic
    python_version: str = "3.11"
    node_version: str = "20"
    rust_version: str = "1.75"
    go_version: str = "1.21"
    package_manager: Optional[str] = None  # pip, poetry, npm, yarn, pnpm, cargo, go
    has_requirements: bool = False
    has_pyproject: bool = False
    has_package_json: bool = False
    has_lock_file: bool = False
    entry_point: Optional[str] = None  # main.py, index.js, etc.
    port: int = 8000
    build_command: Optional[str] = None
    start_command: Optional[str] = None
    uses_static_files: bool = False
    services: list[str] = field(default_factory=list)  # postgres, redis, etc.


class GenerateDockerfileTool(Tool):
    """Generate Dockerfile for projects.

    Creates optimized Dockerfiles based on project type detection,
    supporting multi-stage builds and best practices.
    """

    name = "generate_dockerfile"
    description = """Generate a Dockerfile for the project.

Automatically detects project type (Python, Node.js, Rust, Go) and generates
an optimized Dockerfile with multi-stage builds when appropriate.

Examples:
- generate_dockerfile() - Auto-detect and generate Dockerfile
- generate_dockerfile(project_type="python") - Override detection
- generate_dockerfile(port=3000) - Specify exposed port
- generate_dockerfile(entry_point="app.py") - Specify entry point
- generate_dockerfile(multi_stage=true) - Force multi-stage build
- generate_dockerfile(dry_run=true) - Preview without creating file"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (default: Dockerfile)",
            },
            "project_type": {
                "type": "string",
                "description": "Override project type detection: 'python', 'node', 'rust', 'go', 'generic'",
                "enum": ["python", "node", "rust", "go", "generic"],
            },
            "python_version": {
                "type": "string",
                "description": "Python version (default: 3.11)",
            },
            "node_version": {
                "type": "string",
                "description": "Node.js version (default: 20)",
            },
            "port": {
                "type": "integer",
                "description": "Port to expose (default: 8000 for Python, 3000 for Node)",
            },
            "entry_point": {
                "type": "string",
                "description": "Application entry point (e.g., 'main.py', 'src/index.js')",
            },
            "multi_stage": {
                "type": "boolean",
                "description": "Use multi-stage build for smaller images (default: true for compiled languages)",
            },
            "alpine": {
                "type": "boolean",
                "description": "Use Alpine-based images for smaller size (default: false)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview Dockerfile without creating file",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        output_file: Optional[str] = None,
        project_type: Optional[str] = None,
        python_version: Optional[str] = None,
        node_version: Optional[str] = None,
        port: Optional[int] = None,
        entry_point: Optional[str] = None,
        multi_stage: Optional[bool] = None,
        alpine: bool = False,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate a Dockerfile.

        Args:
            path: Project directory path
            output_file: Output file path
            project_type: Override detected project type
            python_version: Python version to use
            node_version: Node.js version to use
            port: Port to expose
            entry_point: Application entry point
            multi_stage: Use multi-stage builds
            alpine: Use Alpine-based images
            dry_run: Preview without creating file
        """
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect project information
        info = self._detect_project(project_path)

        # Override with provided values
        if project_type:
            info.project_type = project_type
        if python_version:
            info.python_version = python_version
        if node_version:
            info.node_version = node_version
        if port:
            info.port = port
        if entry_point:
            info.entry_point = entry_point

        # Set default multi_stage based on project type
        if multi_stage is None:
            multi_stage = info.project_type in ("rust", "go")

        # Generate Dockerfile content
        dockerfile = self._generate_dockerfile(info, multi_stage, alpine)

        # Determine output file
        output_path = project_path / (output_file or "Dockerfile")

        if dry_run:
            return ToolResult(
                success=True,
                output=f"Dockerfile preview (would create {output_path}):\n\n{dockerfile}",
                metadata={
                    "dry_run": True,
                    "project_type": info.project_type,
                    "output_file": str(output_path),
                },
            )

        # Write Dockerfile
        try:
            output_path.write_text(dockerfile)
            log.info(
                "dockerfile_generated",
                project_type=info.project_type,
                output_file=str(output_path),
            )
            return ToolResult(
                success=True,
                output=f"Generated Dockerfile: {output_path}\n\n{dockerfile}",
                metadata={
                    "project_type": info.project_type,
                    "output_file": str(output_path),
                    "multi_stage": multi_stage,
                    "alpine": alpine,
                },
            )
        except Exception as e:
            log.error("dockerfile_write_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Failed to write Dockerfile: {str(e)}"
            )

    def _detect_project(self, path: Path) -> DockerProjectInfo:
        """Detect project type and configuration."""
        info = DockerProjectInfo(project_type="generic")

        # Python detection
        if (path / "pyproject.toml").exists():
            info.project_type = "python"
            info.has_pyproject = True
            pyproject = (path / "pyproject.toml").read_text()
            if "poetry" in pyproject.lower():
                info.package_manager = "poetry"
            else:
                info.package_manager = "pip"
            # Try to detect entry point
            if (path / "main.py").exists():
                info.entry_point = "main.py"
            elif (path / "app.py").exists():
                info.entry_point = "app.py"
            elif (path / "src" / "main.py").exists():
                info.entry_point = "src/main.py"
            # Detect if using uvicorn/gunicorn (web server)
            if "uvicorn" in pyproject or "fastapi" in pyproject:
                info.start_command = "uvicorn main:app --host 0.0.0.0 --port 8000"
            elif "gunicorn" in pyproject:
                info.start_command = "gunicorn -b 0.0.0.0:8000 main:app"
            elif "flask" in pyproject:
                info.start_command = "flask run --host=0.0.0.0 --port=8000"
                info.port = 5000
            elif "django" in pyproject:
                info.start_command = "python manage.py runserver 0.0.0.0:8000"

        elif (path / "requirements.txt").exists():
            info.project_type = "python"
            info.has_requirements = True
            info.package_manager = "pip"
            requirements = (path / "requirements.txt").read_text().lower()
            if (path / "main.py").exists():
                info.entry_point = "main.py"
            elif (path / "app.py").exists():
                info.entry_point = "app.py"
            if "uvicorn" in requirements or "fastapi" in requirements:
                info.start_command = "uvicorn main:app --host 0.0.0.0 --port 8000"
            elif "gunicorn" in requirements:
                info.start_command = "gunicorn -b 0.0.0.0:8000 main:app"
            elif "flask" in requirements:
                info.start_command = "flask run --host=0.0.0.0 --port=5000"
                info.port = 5000
            elif "django" in requirements:
                info.start_command = "python manage.py runserver 0.0.0.0:8000"

        # Node.js detection
        elif (path / "package.json").exists():
            info.project_type = "node"
            info.has_package_json = True
            if (path / "yarn.lock").exists():
                info.package_manager = "yarn"
                info.has_lock_file = True
            elif (path / "pnpm-lock.yaml").exists():
                info.package_manager = "pnpm"
                info.has_lock_file = True
            elif (path / "package-lock.json").exists():
                info.package_manager = "npm"
                info.has_lock_file = True
            else:
                info.package_manager = "npm"

            pkg_json = json.loads((path / "package.json").read_text())
            scripts = pkg_json.get("scripts", {})

            # Detect entry point
            if "main" in pkg_json:
                info.entry_point = pkg_json["main"]
            elif (path / "index.js").exists():
                info.entry_point = "index.js"
            elif (path / "src" / "index.js").exists():
                info.entry_point = "src/index.js"
            elif (path / "src" / "index.ts").exists():
                info.entry_point = "dist/index.js"

            # Detect build and start commands
            if "build" in scripts:
                info.build_command = f"{info.package_manager} run build"
            if "start" in scripts:
                info.start_command = f"{info.package_manager} start"
            elif info.entry_point:
                info.start_command = f"node {info.entry_point}"

            # Check for static files (Next.js, etc.)
            deps = {
                **pkg_json.get("dependencies", {}),
                **pkg_json.get("devDependencies", {}),
            }
            if "next" in deps:
                info.uses_static_files = True
                info.port = 3000
            elif "express" in deps:
                info.port = 3000
            else:
                info.port = 3000

        # Rust detection
        elif (path / "Cargo.toml").exists():
            info.project_type = "rust"
            info.package_manager = "cargo"
            cargo_toml = (path / "Cargo.toml").read_text()
            # Try to extract binary name
            if "[package]" in cargo_toml and "name" in cargo_toml:
                import re

                match = re.search(r'name\s*=\s*"([^"]+)"', cargo_toml)
                if match:
                    info.entry_point = match.group(1)

        # Go detection
        elif (path / "go.mod").exists():
            info.project_type = "go"
            info.package_manager = "go"
            if (path / "main.go").exists():
                info.entry_point = "main.go"
            elif (path / "cmd" / "main.go").exists():
                info.entry_point = "cmd/main.go"

        return info

    def _generate_dockerfile(
        self, info: DockerProjectInfo, multi_stage: bool, alpine: bool
    ) -> str:
        """Generate Dockerfile content."""
        if info.project_type == "python":
            return self._python_dockerfile(info, multi_stage, alpine)
        elif info.project_type == "node":
            return self._node_dockerfile(info, multi_stage, alpine)
        elif info.project_type == "rust":
            return self._rust_dockerfile(info, multi_stage, alpine)
        elif info.project_type == "go":
            return self._go_dockerfile(info, multi_stage, alpine)
        else:
            return self._generic_dockerfile(info)

    def _python_dockerfile(
        self, info: DockerProjectInfo, multi_stage: bool, alpine: bool
    ) -> str:
        """Generate Python Dockerfile."""
        base_image = (
            f"python:{info.python_version}-alpine"
            if alpine
            else f"python:{info.python_version}-slim"
        )

        entry_point = info.entry_point or "main.py"
        # If entry_point was explicitly set, use it for the command
        # Otherwise use detected start_command or fallback to python {entry_point}
        if info.entry_point:
            start_cmd = f"python {entry_point}"
        else:
            start_cmd = info.start_command or f"python {entry_point}"

        if info.package_manager == "poetry":
            return f"""# Python Poetry Dockerfile
FROM {base_image} AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    POETRY_HOME="/opt/poetry" \\
    POETRY_VIRTUALENVS_IN_PROJECT=true \\
    POETRY_NO_INTERACTION=1

# Install poetry
RUN pip install poetry

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --no-root --only main

# Copy application code
COPY . .

# Install the project
RUN poetry install --only main

# Expose port
EXPOSE {info.port}

# Run the application
CMD ["poetry", "run", "python", "{entry_point}"]
"""
        else:
            # pip-based
            install_cmd = (
                "pip install --no-cache-dir -r requirements.txt"
                if info.has_requirements
                else "pip install --no-cache-dir -e ."
            )

            return f"""# Python Dockerfile
FROM {base_image}

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt* pyproject.toml* ./
RUN {install_cmd}

# Copy application code
COPY . .

# Expose port
EXPOSE {info.port}

# Run the application
CMD [{", ".join(f'"{part}"' for part in start_cmd.split())}]
"""

    def _node_dockerfile(
        self, info: DockerProjectInfo, multi_stage: bool, alpine: bool
    ) -> str:
        """Generate Node.js Dockerfile."""
        base_image = (
            f"node:{info.node_version}-alpine"
            if alpine
            else f"node:{info.node_version}-slim"
        )

        if info.package_manager == "yarn":
            install_cmd = "yarn install --frozen-lockfile"
            prod_install = "yarn install --production --frozen-lockfile"
        elif info.package_manager == "pnpm":
            install_cmd = "pnpm install --frozen-lockfile"
            prod_install = "pnpm install --prod --frozen-lockfile"
        else:
            install_cmd = "npm ci"
            prod_install = "npm ci --only=production"

        start_cmd = info.start_command or f"node {info.entry_point or 'index.js'}"

        if multi_stage and info.build_command:
            return f"""# Node.js Multi-Stage Dockerfile
FROM {base_image} AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./
{"COPY yarn.lock ./" if info.package_manager == "yarn" else ""}
{"COPY pnpm-lock.yaml ./" if info.package_manager == "pnpm" else ""}

# Install all dependencies
RUN {install_cmd}

# Copy source code
COPY . .

# Build the application
RUN {info.build_command}

# Production image
FROM {base_image}

WORKDIR /app

# Copy package files
COPY package*.json ./
{"COPY yarn.lock ./" if info.package_manager == "yarn" else ""}
{"COPY pnpm-lock.yaml ./" if info.package_manager == "pnpm" else ""}

# Install production dependencies only
RUN {prod_install}

# Copy built application from builder
COPY --from=builder /app/dist ./dist

# Expose port
EXPOSE {info.port}

# Run the application
CMD [{", ".join(f'"{part}"' for part in start_cmd.split())}]
"""
        else:
            return f"""# Node.js Dockerfile
FROM {base_image}

WORKDIR /app

# Copy package files
COPY package*.json ./
{"COPY yarn.lock ./" if info.package_manager == "yarn" else ""}
{"COPY pnpm-lock.yaml ./" if info.package_manager == "pnpm" else ""}

# Install dependencies
RUN {install_cmd}

# Copy application code
COPY . .

{"# Build the application" + chr(10) + f"RUN {info.build_command}" + chr(10) if info.build_command else ""}
# Expose port
EXPOSE {info.port}

# Run the application
CMD [{", ".join(f'"{part}"' for part in start_cmd.split())}]
"""

    def _rust_dockerfile(
        self, info: DockerProjectInfo, multi_stage: bool, alpine: bool
    ) -> str:
        """Generate Rust Dockerfile."""
        binary_name = info.entry_point or "app"

        if multi_stage:
            runtime_image = "alpine:latest" if alpine else "debian:bookworm-slim"
            return f"""# Rust Multi-Stage Dockerfile
FROM rust:{info.rust_version} AS builder

WORKDIR /app

# Copy manifests
COPY Cargo.toml Cargo.lock* ./

# Create a dummy main.rs to build dependencies
RUN mkdir src && echo "fn main() {{}}" > src/main.rs

# Build dependencies (cached layer)
RUN cargo build --release && rm -rf src

# Copy actual source code
COPY . .

# Build the application
RUN touch src/main.rs && cargo build --release

# Runtime image
FROM {runtime_image}

{"RUN apk add --no-cache libgcc" if alpine else "RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*"}

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/target/release/{binary_name} .

# Expose port (if web service)
EXPOSE {info.port}

# Run the application
CMD ["./{binary_name}"]
"""
        else:
            return f"""# Rust Dockerfile
FROM rust:{info.rust_version}

WORKDIR /app

# Copy manifests
COPY Cargo.toml Cargo.lock* ./

# Copy source code
COPY . .

# Build the application
RUN cargo build --release

# Expose port (if web service)
EXPOSE {info.port}

# Run the application
CMD ["./target/release/{binary_name}"]
"""

    def _go_dockerfile(
        self, info: DockerProjectInfo, multi_stage: bool, alpine: bool
    ) -> str:
        """Generate Go Dockerfile."""
        if multi_stage:
            runtime_image = (
                "alpine:latest" if alpine else "gcr.io/distroless/base-debian12"
            )

            return f"""# Go Multi-Stage Dockerfile
FROM golang:{info.go_version} AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app/main .

# Runtime image
FROM {runtime_image}

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/main .

# Expose port
EXPOSE {info.port}

# Run the application
CMD ["./main"]
"""
        else:
            return f"""# Go Dockerfile
FROM golang:{info.go_version}

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN go build -o main .

# Expose port
EXPOSE {info.port}

# Run the application
CMD ["./main"]
"""

    def _generic_dockerfile(self, info: DockerProjectInfo) -> str:
        """Generate generic Dockerfile."""
        return f"""# Generic Dockerfile
FROM alpine:latest

WORKDIR /app

# Copy application files
COPY . .

# Add your build/install commands here
# RUN ...

# Expose port
EXPOSE {info.port}

# Run the application
# CMD ["./your-app"]
"""


class GenerateDockerComposeTool(Tool):
    """Generate docker-compose.yml for projects.

    Creates docker-compose files with common services like databases,
    caches, and message queues.
    """

    name = "generate_docker_compose"
    description = """Generate a docker-compose.yml file for the project.

Automatically detects project type and generates a compose file with
optional services (database, cache, etc.).

Examples:
- generate_docker_compose() - Auto-detect and generate
- generate_docker_compose(services=["postgres", "redis"]) - Add services
- generate_docker_compose(include_volumes=true) - Include persistent volumes
- generate_docker_compose(production=true) - Production-ready configuration
- generate_docker_compose(dry_run=true) - Preview without creating file"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (default: docker-compose.yml)",
            },
            "services": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional services: 'postgres', 'mysql', 'redis', 'mongodb', 'rabbitmq', 'kafka', 'elasticsearch', 'nginx'",
            },
            "app_name": {
                "type": "string",
                "description": "Application service name (default: 'app')",
            },
            "port": {"type": "integer", "description": "Application port to expose"},
            "include_volumes": {
                "type": "boolean",
                "description": "Include persistent volumes for services (default: true)",
            },
            "production": {
                "type": "boolean",
                "description": "Generate production-ready configuration",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without creating file",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        output_file: Optional[str] = None,
        services: Optional[list[str]] = None,
        app_name: str = "app",
        port: Optional[int] = None,
        include_volumes: bool = True,
        production: bool = False,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate docker-compose.yml.

        Args:
            path: Project directory path
            output_file: Output file path
            services: Additional services to include
            app_name: Application service name
            port: Application port to expose
            include_volumes: Include persistent volumes
            production: Generate production configuration
            dry_run: Preview without creating file
        """
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect project information
        info = self._detect_project(project_path)

        if port:
            info.port = port
        if services:
            info.services = services

        # Generate docker-compose content
        compose = self._generate_compose(info, app_name, include_volumes, production)

        # Determine output file
        output_path = project_path / (output_file or "docker-compose.yml")

        if dry_run:
            return ToolResult(
                success=True,
                output=f"docker-compose.yml preview (would create {output_path}):\n\n{compose}",
                metadata={
                    "dry_run": True,
                    "project_type": info.project_type,
                    "services": info.services,
                    "output_file": str(output_path),
                },
            )

        # Write docker-compose file
        try:
            output_path.write_text(compose)
            log.info(
                "docker_compose_generated",
                project_type=info.project_type,
                services=info.services,
                output_file=str(output_path),
            )
            return ToolResult(
                success=True,
                output=f"Generated docker-compose.yml: {output_path}\n\n{compose}",
                metadata={
                    "project_type": info.project_type,
                    "services": info.services,
                    "output_file": str(output_path),
                },
            )
        except Exception as e:
            log.error("docker_compose_write_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write docker-compose.yml: {str(e)}",
            )

    def _detect_project(self, path: Path) -> DockerProjectInfo:
        """Detect project type for docker-compose generation."""
        info = DockerProjectInfo(project_type="generic")

        # Same detection as Dockerfile
        if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
            info.project_type = "python"
            info.port = 8000
        elif (path / "package.json").exists():
            info.project_type = "node"
            info.port = 3000
        elif (path / "Cargo.toml").exists():
            info.project_type = "rust"
            info.port = 8080
        elif (path / "go.mod").exists():
            info.project_type = "go"
            info.port = 8080

        return info

    def _generate_compose(
        self,
        info: DockerProjectInfo,
        app_name: str,
        include_volumes: bool,
        production: bool,
    ) -> str:
        """Generate docker-compose.yml content."""
        services = [self._app_service(info, app_name, production)]
        volumes = []

        for service in info.services:
            svc, vol = self._get_service(service, include_volumes)
            if svc:
                services.append(svc)
            if vol:
                volumes.append(vol)

        # Build compose file
        compose_lines = ["version: '3.8'", "", "services:"]
        for svc in services:
            compose_lines.append(svc)

        if volumes and include_volumes:
            compose_lines.append("")
            compose_lines.append("volumes:")
            for vol in volumes:
                compose_lines.append(vol)

        return "\n".join(compose_lines)

    def _app_service(
        self, info: DockerProjectInfo, app_name: str, production: bool
    ) -> str:
        """Generate the main application service."""
        restart_policy = "always" if production else "unless-stopped"

        depends_on = ""
        if info.services:
            deps = [
                s
                for s in info.services
                if s in ("postgres", "mysql", "mongodb", "redis")
            ]
            if deps:
                depends_on = "\n    depends_on:\n" + "\n".join(
                    f"      - {d}" for d in deps
                )

        env_vars = self._get_env_vars(info.services)

        return f"""  {app_name}:
    build: .
    ports:
      - "{info.port}:{info.port}"
    environment:
      - PORT={info.port}{env_vars}
    restart: {restart_policy}{depends_on}
"""

    def _get_env_vars(self, services: list[str]) -> str:
        """Get environment variables for services."""
        env_vars = []

        if "postgres" in services:
            env_vars.append(
                "      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/app"
            )
        if "mysql" in services:
            env_vars.append("      - DATABASE_URL=mysql://root:root@mysql:3306/app")
        if "mongodb" in services:
            env_vars.append("      - MONGODB_URL=mongodb://mongodb:27017/app")
        if "redis" in services:
            env_vars.append("      - REDIS_URL=redis://redis:6379")
        if "rabbitmq" in services:
            env_vars.append("      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672")
        if "elasticsearch" in services:
            env_vars.append("      - ELASTICSEARCH_URL=http://elasticsearch:9200")

        if env_vars:
            return "\n" + "\n".join(env_vars)
        return ""

    def _get_service(self, service: str, include_volumes: bool) -> tuple[str, str]:
        """Get service definition and volume definition."""
        services = {
            "postgres": (
                """  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=app
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
""",
                "  postgres_data:",
            ),
            "mysql": (
                """  mysql:
    image: mysql:8
    environment:
      - MYSQL_ROOT_PASSWORD=root
      - MYSQL_DATABASE=app
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
""",
                "  mysql_data:",
            ),
            "mongodb": (
                """  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
""",
                "  mongodb_data:",
            ),
            "redis": (
                """  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
""",
                "  redis_data:",
            ),
            "rabbitmq": (
                """  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
""",
                "  rabbitmq_data:",
            ),
            "kafka": (
                """  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      - ZOOKEEPER_CLIENT_PORT=2181
    ports:
      - "2181:2181"

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    environment:
      - KAFKA_BROKER_ID=1
      - KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181
      - KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
      - KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
    ports:
      - "9092:9092"
""",
                "",
            ),
            "elasticsearch": (
                """  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
""",
                "  elasticsearch_data:",
            ),
            "nginx": (
                """  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
""",
                "",
            ),
        }

        return services.get(service, ("", ""))


class ValidateDockerfileTool(Tool):
    """Validate Dockerfile for common issues.

    Checks for best practices and potential problems in Dockerfiles.
    """

    name = "validate_dockerfile"
    description = """Validate a Dockerfile for common issues and best practices.

Examples:
- validate_dockerfile() - Validate Dockerfile in current directory
- validate_dockerfile(file_path="Dockerfile.prod") - Validate specific file
- validate_dockerfile(content="FROM python:3.11...") - Validate content directly"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to Dockerfile to validate (default: Dockerfile)",
            },
            "content": {
                "type": "string",
                "description": "Dockerfile content to validate directly",
            },
        },
        "required": [],
    }

    async def execute(
        self, file_path: Optional[str] = None, content: Optional[str] = None, **kwargs
    ) -> ToolResult:
        """Validate Dockerfile.

        Args:
            file_path: Path to Dockerfile
            content: Dockerfile content to validate directly
        """
        if content is not None:
            dockerfile_content = content
            source = "inline"
        else:
            dockerfile_path = self._resolve_path(file_path or "Dockerfile")
            if not dockerfile_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Dockerfile not found: {dockerfile_path}",
                )
            dockerfile_content = dockerfile_path.read_text()
            source = str(dockerfile_path)

        # Validate the Dockerfile
        result = self._validate(dockerfile_content, source)

        output_lines = [f"Validating: {source}"]

        if result["errors"]:
            output_lines.append("\nErrors:")
            for err in result["errors"]:
                output_lines.append(f"  - {err}")

        if result["warnings"]:
            output_lines.append("\nWarnings:")
            for warn in result["warnings"]:
                output_lines.append(f"  - {warn}")

        if result["suggestions"]:
            output_lines.append("\nSuggestions:")
            for sug in result["suggestions"]:
                output_lines.append(f"  - {sug}")

        if not result["errors"] and not result["warnings"]:
            output_lines.append("\nNo issues found!")

        return ToolResult(
            success=len(result["errors"]) == 0,
            output="\n".join(output_lines),
            metadata={
                "errors": result["errors"],
                "warnings": result["warnings"],
                "suggestions": result["suggestions"],
                "valid": len(result["errors"]) == 0,
            },
        )

    def _validate(self, content: str, source: str) -> dict:
        """Validate Dockerfile content."""
        result = {"errors": [], "warnings": [], "suggestions": []}

        stripped_content = content.strip()
        if not stripped_content:
            result["errors"].append("Dockerfile is empty")
            return result

        lines = stripped_content.split("\n")

        # Check for FROM instruction
        has_from = False
        from_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("FROM "):
                has_from = True
                from_count += 1

        if not has_from:
            result["errors"].append("Missing FROM instruction")

        # Check for common issues
        content_lower = content.lower()

        # Check for latest tag
        if (
            ":latest" in content_lower
            or "from python " in content_lower
            or "from node " in content_lower
        ):
            result["warnings"].append(
                "Using ':latest' tag or untagged base image. Consider using specific versions."
            )

        # Check for apt-get without cleanup
        if (
            "apt-get install" in content_lower
            and "rm -rf /var/lib/apt/lists" not in content_lower
        ):
            result["suggestions"].append(
                "Consider cleaning apt cache: rm -rf /var/lib/apt/lists/*"
            )

        # Check for pip install without --no-cache-dir
        if "pip install" in content_lower and "--no-cache-dir" not in content_lower:
            result["suggestions"].append(
                "Consider using pip install --no-cache-dir to reduce image size"
            )

        # Check for missing WORKDIR
        if "workdir " not in content_lower:
            result["warnings"].append("Consider adding WORKDIR instruction")

        # Check for running as root
        if "user " not in content_lower:
            result["suggestions"].append(
                "Consider adding USER instruction to run as non-root user"
            )

        # Check for COPY vs ADD
        if "add " in content_lower and "add --from" not in content_lower:
            result["suggestions"].append(
                "Prefer COPY over ADD unless you need ADD's special features (URL download, tar extraction)"
            )

        # Check for .dockerignore reference
        # Note: we can't check if .dockerignore exists, just suggest it
        result["suggestions"].append(
            "Ensure you have a .dockerignore file to exclude unnecessary files"
        )

        # Check instruction order (COPY before RUN for better caching)
        copy_indices = [
            i for i, line in enumerate(lines) if line.strip().upper().startswith("COPY")
        ]
        run_indices = [
            i for i, line in enumerate(lines) if line.strip().upper().startswith("RUN")
        ]

        if copy_indices and run_indices:
            # Check if dependencies are copied before other files
            first_copy = copy_indices[0]
            last_run = run_indices[-1] if run_indices else 0
            if first_copy > last_run and from_count == 1:
                result["suggestions"].append(
                    "Consider copying dependency files and running install before copying source code for better caching"
                )

        # Check for HEALTHCHECK
        if "healthcheck " not in content_lower:
            result["suggestions"].append(
                "Consider adding HEALTHCHECK instruction for container health monitoring"
            )

        # Check for exposed ports
        if "expose " not in content_lower:
            result["suggestions"].append(
                "Consider adding EXPOSE instruction to document the ports the container listens on"
            )

        return result


# =============================================================================
# Docker Runtime Tools
# =============================================================================


class DockerPsTool(Tool):
    """List Docker containers."""

    name = "docker_ps"
    description = """List Docker containers.

Examples:
- docker_ps() - List running containers
- docker_ps(all=true) - List all containers including stopped
- docker_ps(filter="name=myapp") - Filter by name
- docker_ps(format="json") - Output as JSON"""

    parameters = {
        "type": "object",
        "properties": {
            "all": {
                "type": "boolean",
                "description": "Show all containers (including stopped). Default: false",
            },
            "filter": {
                "type": "string",
                "description": "Filter containers (e.g., 'status=running', 'name=myapp')",
            },
            "format": {
                "type": "string",
                "description": "Output format: 'table' (default) or 'json'",
                "enum": ["table", "json"],
            },
        },
        "required": [],
    }

    async def execute(
        self,
        all: bool = False,
        filter: Optional[str] = None,
        format: str = "table",
        **kwargs,
    ) -> ToolResult:
        """List Docker containers."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        args = ["ps"]
        if all:
            args.append("-a")
        if filter:
            args.extend(["--filter", filter])

        if format == "json":
            args.extend(["--format", "json"])
        else:
            args.extend(
                [
                    "--format",
                    "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.Names}}",
                ]
            )

        returncode, stdout, stderr = await _run_docker(*args)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list containers: {stderr}",
            )

        # Count containers
        lines = [l for l in stdout.strip().split("\n") if l]
        # Subtract header line for table format
        container_count = len(lines) - 1 if format == "table" and lines else len(lines)

        return ToolResult(
            success=True,
            output=stdout if stdout.strip() else "No containers found.",
            metadata={
                "container_count": max(0, container_count),
                "format": format,
                "show_all": all,
            },
        )


class DockerImagesTool(Tool):
    """List Docker images."""

    name = "docker_images"
    description = """List Docker images.

Examples:
- docker_images() - List all images
- docker_images(filter="dangling=true") - List dangling images
- docker_images(format="json") - Output as JSON"""

    parameters = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Filter images (e.g., 'dangling=true', 'reference=myapp*')",
            },
            "format": {
                "type": "string",
                "description": "Output format: 'table' (default) or 'json'",
                "enum": ["table", "json"],
            },
        },
        "required": [],
    }

    async def execute(
        self,
        filter: Optional[str] = None,
        format: str = "table",
        **kwargs,
    ) -> ToolResult:
        """List Docker images."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        args = ["images"]
        if filter:
            args.extend(["--filter", filter])

        if format == "json":
            args.extend(["--format", "json"])
        else:
            args.extend(
                [
                    "--format",
                    "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}",
                ]
            )

        returncode, stdout, stderr = await _run_docker(*args)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list images: {stderr}",
            )

        # Count images
        lines = [l for l in stdout.strip().split("\n") if l]
        image_count = len(lines) - 1 if format == "table" and lines else len(lines)

        return ToolResult(
            success=True,
            output=stdout if stdout.strip() else "No images found.",
            metadata={
                "image_count": max(0, image_count),
                "format": format,
            },
        )


class DockerLogsTool(Tool):
    """Get logs from a Docker container."""

    name = "docker_logs"
    description = """Get logs from a Docker container.

Examples:
- docker_logs(container="myapp") - Get recent logs
- docker_logs(container="myapp", tail=50) - Get last 50 lines
- docker_logs(container="myapp", since="10m") - Logs from last 10 minutes
- docker_logs(container="myapp", timestamps=true) - Include timestamps"""

    parameters = {
        "type": "object",
        "properties": {
            "container": {
                "type": "string",
                "description": "Container name or ID",
            },
            "tail": {
                "type": "integer",
                "description": "Number of lines to show from end (default: 100)",
            },
            "since": {
                "type": "string",
                "description": "Show logs since timestamp (e.g., '10m', '1h', '2024-01-01')",
            },
            "timestamps": {
                "type": "boolean",
                "description": "Show timestamps with each log line",
            },
        },
        "required": ["container"],
    }

    async def execute(
        self,
        container: str,
        tail: int = 100,
        since: Optional[str] = None,
        timestamps: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Get container logs."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        args = ["logs", "--tail", str(tail)]
        if since:
            args.extend(["--since", since])
        if timestamps:
            args.append("--timestamps")
        args.append(container)

        returncode, stdout, stderr = await _run_docker(*args, timeout=60)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get logs for '{container}': {stderr}",
            )

        # Combine stdout and stderr (containers may log to either)
        output = stdout + stderr if stdout or stderr else "No logs available."
        lines = output.strip().split("\n") if output.strip() else []

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "container": container,
                "line_count": len(lines),
                "tail": tail,
            },
        )


class DockerBuildTool(Tool):
    """Build a Docker image from a Dockerfile."""

    name = "docker_build"
    description = """Build a Docker image from a Dockerfile.

Examples:
- docker_build(tag="myapp:latest") - Build with tag
- docker_build(tag="myapp:v1", path="./docker") - Build from different context
- docker_build(tag="myapp:latest", no_cache=true) - Build without cache
- docker_build(tag="myapp:latest", target="builder") - Multi-stage target
- docker_build(tag="myapp:latest", build_args={"VERSION": "1.0"}) - With build args"""

    parameters = {
        "type": "object",
        "properties": {
            "tag": {
                "type": "string",
                "description": "Image tag (e.g., 'myapp:latest')",
            },
            "path": {
                "type": "string",
                "description": "Build context path (default: current directory)",
            },
            "dockerfile": {
                "type": "string",
                "description": "Path to Dockerfile (default: Dockerfile in context)",
            },
            "build_args": {
                "type": "object",
                "description": "Build arguments as key-value pairs",
            },
            "no_cache": {
                "type": "boolean",
                "description": "Build without using cache",
            },
            "target": {
                "type": "string",
                "description": "Target build stage for multi-stage builds",
            },
            "platform": {
                "type": "string",
                "description": "Target platform (e.g., 'linux/amd64', 'linux/arm64')",
            },
        },
        "required": ["tag"],
    }

    async def execute(
        self,
        tag: str,
        path: Optional[str] = None,
        dockerfile: Optional[str] = None,
        build_args: Optional[dict] = None,
        no_cache: bool = False,
        target: Optional[str] = None,
        platform: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Build a Docker image."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        build_path = self._resolve_path(path or ".")
        if not build_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Build context path not found: {build_path}",
            )

        args = ["build", "-t", tag]

        if dockerfile:
            dockerfile_path = self._resolve_path(dockerfile)
            args.extend(["-f", str(dockerfile_path)])

        if no_cache:
            args.append("--no-cache")

        if target:
            args.extend(["--target", target])

        if platform:
            args.extend(["--platform", platform])

        if build_args:
            for key, value in build_args.items():
                args.extend(["--build-arg", f"{key}={value}"])

        args.append(str(build_path))

        log.info("docker_build_started", tag=tag, path=str(build_path))

        # Build can take a long time
        returncode, stdout, stderr = await _run_docker(*args, timeout=600)

        if returncode != 0:
            log.error("docker_build_failed", tag=tag, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Build failed: {stderr}",
            )

        log.info("docker_build_completed", tag=tag)
        return ToolResult(
            success=True,
            output=f"Successfully built image: {tag}\n\n{stdout}",
            metadata={
                "tag": tag,
                "path": str(build_path),
                "no_cache": no_cache,
                "target": target,
            },
        )


class DockerRunTool(Tool):
    """Run a Docker container."""

    name = "docker_run"
    description = """Run a Docker container.

Examples:
- docker_run(image="nginx") - Run nginx in detached mode
- docker_run(image="nginx", name="web", ports=["8080:80"]) - With name and port mapping
- docker_run(image="postgres", env={"POSTGRES_PASSWORD": "secret"}) - With env vars
- docker_run(image="myapp", volumes=["./data:/data"]) - With volume mount
- docker_run(image="alpine", command="echo hello", detach=false, remove=true) - Run and remove"""

    parameters = {
        "type": "object",
        "properties": {
            "image": {
                "type": "string",
                "description": "Image name or ID to run",
            },
            "name": {
                "type": "string",
                "description": "Container name",
            },
            "detach": {
                "type": "boolean",
                "description": "Run container in background (default: true)",
            },
            "ports": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Port mappings (e.g., ['8080:80', '443:443'])",
            },
            "volumes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Volume mounts (e.g., ['./data:/data', 'myvolume:/app/data'])",
            },
            "env": {
                "type": "object",
                "description": "Environment variables as key-value pairs",
            },
            "network": {
                "type": "string",
                "description": "Network mode or network name (e.g., 'host', 'bridge', 'mynetwork')",
            },
            "command": {
                "type": "string",
                "description": "Override container CMD",
            },
            "remove": {
                "type": "boolean",
                "description": "Automatically remove container when it exits (--rm)",
            },
            "privileged": {
                "type": "boolean",
                "description": "Run with extended privileges (use with caution)",
            },
        },
        "required": ["image"],
    }

    async def execute(
        self,
        image: str,
        name: Optional[str] = None,
        detach: bool = True,
        ports: Optional[list[str]] = None,
        volumes: Optional[list[str]] = None,
        env: Optional[dict] = None,
        network: Optional[str] = None,
        command: Optional[str] = None,
        remove: bool = False,
        privileged: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Run a Docker container."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        args = ["run"]

        if detach:
            args.append("-d")

        if name:
            args.extend(["--name", name])

        if remove:
            args.append("--rm")

        if privileged:
            log.warning("docker_run_privileged", image=image, name=name)
            args.append("--privileged")

        if ports:
            for port in ports:
                args.extend(["-p", port])

        if volumes:
            for vol in volumes:
                args.extend(["-v", vol])

        if env:
            for key, value in env.items():
                args.extend(["-e", f"{key}={value}"])

        if network:
            args.extend(["--network", network])

        args.append(image)

        if command:
            args.extend(command.split())

        log.info("docker_run_started", image=image, name=name)

        returncode, stdout, stderr = await _run_docker(*args, timeout=120)

        if returncode != 0:
            log.error("docker_run_failed", image=image, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to run container: {stderr}",
            )

        container_id = stdout.strip()[:12] if stdout.strip() else None
        container_name = name or container_id

        log.info("docker_run_completed", image=image, container=container_name)

        return ToolResult(
            success=True,
            output=f"Container started: {container_name}\nID: {stdout.strip()}" if detach else stdout,
            metadata={
                "container_id": stdout.strip(),
                "container_name": container_name,
                "image": image,
                "detached": detach,
            },
        )


class DockerStopTool(Tool):
    """Stop a running Docker container."""

    name = "docker_stop"
    description = """Stop a running Docker container.

Examples:
- docker_stop(container="myapp") - Stop container
- docker_stop(container="abc123") - Stop by ID
- docker_stop(container="myapp", timeout=30) - Wait 30s before killing"""

    parameters = {
        "type": "object",
        "properties": {
            "container": {
                "type": "string",
                "description": "Container name or ID",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds to wait before killing (default: 10)",
            },
        },
        "required": ["container"],
    }

    async def execute(
        self,
        container: str,
        timeout: int = 10,
        **kwargs,
    ) -> ToolResult:
        """Stop a Docker container."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        args = ["stop", "-t", str(timeout), container]

        log.info("docker_stop", container=container)

        returncode, stdout, stderr = await _run_docker(*args, timeout=timeout + 30)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to stop container '{container}': {stderr}",
            )

        return ToolResult(
            success=True,
            output=f"Stopped container: {container}",
            metadata={
                "container": container,
                "timeout": timeout,
            },
        )


class DockerRmTool(Tool):
    """Remove a Docker container."""

    name = "docker_rm"
    description = """Remove a Docker container.

Examples:
- docker_rm(container="myapp") - Remove stopped container
- docker_rm(container="myapp", force=true) - Force remove running container
- docker_rm(container="myapp", volumes=true) - Also remove associated volumes"""

    parameters = {
        "type": "object",
        "properties": {
            "container": {
                "type": "string",
                "description": "Container name or ID",
            },
            "force": {
                "type": "boolean",
                "description": "Force remove a running container",
            },
            "volumes": {
                "type": "boolean",
                "description": "Remove associated anonymous volumes",
            },
        },
        "required": ["container"],
    }

    async def execute(
        self,
        container: str,
        force: bool = False,
        volumes: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Remove a Docker container."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        args = ["rm"]
        if force:
            args.append("-f")
        if volumes:
            args.append("-v")
        args.append(container)

        log.info("docker_rm", container=container, force=force)

        returncode, stdout, stderr = await _run_docker(*args)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to remove container '{container}': {stderr}",
            )

        return ToolResult(
            success=True,
            output=f"Removed container: {container}",
            metadata={
                "container": container,
                "force": force,
                "volumes_removed": volumes,
            },
        )


class DockerComposeUpTool(Tool):
    """Start services defined in docker-compose.yml."""

    name = "docker_compose_up"
    description = """Start services defined in docker-compose.yml.

Examples:
- docker_compose_up() - Start all services in detached mode
- docker_compose_up(path="./docker/docker-compose.yml") - Use specific file
- docker_compose_up(services=["web", "db"]) - Start specific services
- docker_compose_up(build=true) - Build images before starting
- docker_compose_up(force_recreate=true) - Recreate containers"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to docker-compose.yml (default: ./docker-compose.yml)",
            },
            "services": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific services to start (default: all)",
            },
            "detach": {
                "type": "boolean",
                "description": "Run in background (default: true)",
            },
            "build": {
                "type": "boolean",
                "description": "Build images before starting",
            },
            "force_recreate": {
                "type": "boolean",
                "description": "Recreate containers even if unchanged",
            },
            "remove_orphans": {
                "type": "boolean",
                "description": "Remove containers for services not in the compose file",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        services: Optional[list[str]] = None,
        detach: bool = True,
        build: bool = False,
        force_recreate: bool = False,
        remove_orphans: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Start docker compose services."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        compose_file = self._resolve_path(path or "docker-compose.yml")
        if not compose_file.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Compose file not found: {compose_file}",
            )

        args = ["-f", str(compose_file), "up"]

        if detach:
            args.append("-d")
        if build:
            args.append("--build")
        if force_recreate:
            args.append("--force-recreate")
        if remove_orphans:
            args.append("--remove-orphans")

        if services:
            args.extend(services)

        log.info("docker_compose_up", file=str(compose_file), services=services)

        returncode, stdout, stderr = await _run_compose(
            *args, cwd=compose_file.parent, timeout=300
        )

        if returncode != 0:
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to start services: {stderr}",
            )

        return ToolResult(
            success=True,
            output=f"Services started from {compose_file}\n\n{stdout}",
            metadata={
                "compose_file": str(compose_file),
                "services": services or "all",
                "detached": detach,
                "built": build,
            },
        )


class DockerComposeDownTool(Tool):
    """Stop and remove services defined in docker-compose.yml."""

    name = "docker_compose_down"
    description = """Stop and remove services defined in docker-compose.yml.

Examples:
- docker_compose_down() - Stop all services
- docker_compose_down(path="./docker/docker-compose.yml") - Use specific file
- docker_compose_down(volumes=true) - Also remove named volumes
- docker_compose_down(rmi="all") - Also remove all images"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to docker-compose.yml (default: ./docker-compose.yml)",
            },
            "volumes": {
                "type": "boolean",
                "description": "Remove named volumes declared in the volumes section",
            },
            "rmi": {
                "type": "string",
                "description": "Remove images: 'all' or 'local' (locally built only)",
                "enum": ["all", "local"],
            },
            "timeout": {
                "type": "integer",
                "description": "Shutdown timeout in seconds (default: 10)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        volumes: bool = False,
        rmi: Optional[str] = None,
        timeout: int = 10,
        **kwargs,
    ) -> ToolResult:
        """Stop and remove docker compose services."""
        if not DOCKER_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Docker not found. Please install Docker.",
                suggestion="Install Docker: https://docs.docker.com/engine/install/",
            )

        compose_file = self._resolve_path(path or "docker-compose.yml")
        if not compose_file.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Compose file not found: {compose_file}",
            )

        args = ["-f", str(compose_file), "down", "-t", str(timeout)]

        if volumes:
            args.append("-v")
        if rmi:
            args.extend(["--rmi", rmi])

        log.info("docker_compose_down", file=str(compose_file))

        returncode, stdout, stderr = await _run_compose(
            *args, cwd=compose_file.parent, timeout=timeout + 60
        )

        if returncode != 0:
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Failed to stop services: {stderr}",
            )

        return ToolResult(
            success=True,
            output=f"Services stopped from {compose_file}\n\n{stdout}",
            metadata={
                "compose_file": str(compose_file),
                "volumes_removed": volumes,
                "images_removed": rmi,
            },
        )
