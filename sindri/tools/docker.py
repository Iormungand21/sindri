"""Docker file generation tools for Sindri.

Provides tools for generating Dockerfiles and docker-compose.yml files
based on project detection.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


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
