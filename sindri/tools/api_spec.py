"""API Spec Generator tools for Sindri.

Generates OpenAPI 3.0 specifications from route definitions in various web frameworks.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


@dataclass
class RouteInfo:
    """Information about a single API route."""

    path: str
    method: str
    handler: str
    summary: Optional[str] = None
    description: Optional[str] = None
    parameters: list = field(default_factory=list)
    request_body: Optional[dict] = None
    responses: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    file: Optional[str] = None
    line: Optional[int] = None


@dataclass
class FrameworkInfo:
    """Detected web framework information."""

    framework: str  # flask, fastapi, express, django, gin, echo, actix, generic
    language: str  # python, javascript, typescript, go, rust
    version: Optional[str] = None
    entry_point: Optional[str] = None  # Main application file


class GenerateApiSpecTool(Tool):
    """Generate OpenAPI specification from route definitions.

    Scans source code for route definitions and generates an OpenAPI 3.0 spec.
    """

    name = "generate_api_spec"
    description = """Generate an OpenAPI 3.0 specification from route definitions.

Automatically detects the web framework and extracts route information:
- Flask (@app.route, Blueprint routes)
- FastAPI (@app.get, @router.post, etc.)
- Express.js (app.get, router.post, etc.)
- Django (urlpatterns, path(), re_path())
- Go (Gin, Echo frameworks)

Examples:
- generate_api_spec() - Generate spec for current directory
- generate_api_spec(path="src/api") - Generate spec from specific directory
- generate_api_spec(title="My API", version="2.0.0") - Custom metadata
- generate_api_spec(output="openapi.yaml", format="yaml") - Output to YAML file
- generate_api_spec(dry_run=true) - Preview without creating file"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "output": {
                "type": "string",
                "description": "Output file path (default: openapi.json)",
            },
            "format": {
                "type": "string",
                "description": "Output format: 'json' or 'yaml'",
                "enum": ["json", "yaml"],
            },
            "title": {
                "type": "string",
                "description": "API title (default: auto-detected from project)",
            },
            "version": {
                "type": "string",
                "description": "API version (default: '1.0.0')",
            },
            "description": {"type": "string", "description": "API description"},
            "servers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Server URLs (e.g., ['http://localhost:8000', 'https://api.example.com'])",
            },
            "framework": {
                "type": "string",
                "description": "Override framework detection: 'flask', 'fastapi', 'express', 'django', 'gin', 'echo'",
                "enum": ["flask", "fastapi", "express", "django", "gin", "echo"],
            },
            "include_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File patterns to include (e.g., ['*.py', 'routes/*.js'])",
            },
            "exclude_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File patterns to exclude (e.g., ['test_*.py', '*_test.go'])",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview spec without creating file",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        output: Optional[str] = None,
        format: str = "json",
        title: Optional[str] = None,
        version: str = "1.0.0",
        description: Optional[str] = None,
        servers: Optional[list[str]] = None,
        framework: Optional[str] = None,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate an OpenAPI specification from route definitions.

        Args:
            path: Project directory path
            output: Output file path
            format: Output format (json or yaml)
            title: API title
            version: API version
            description: API description
            servers: Server URLs
            framework: Override detected framework
            include_patterns: File patterns to include
            exclude_patterns: File patterns to exclude
            dry_run: Preview without creating file
        """
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect framework
        if framework:
            fw_info = FrameworkInfo(
                framework=framework,
                language=self._get_language_for_framework(framework),
            )
        else:
            fw_info = self._detect_framework(project_path)

        if fw_info.framework == "generic":
            return ToolResult(
                success=False,
                output="",
                error="Could not detect web framework. Use --framework to specify manually.",
                metadata={"detected": None},
            )

        # Extract routes based on framework
        routes = self._extract_routes(
            project_path, fw_info, include_patterns, exclude_patterns
        )

        if not routes:
            return ToolResult(
                success=False,
                output="",
                error=f"No routes found for {fw_info.framework} framework in {project_path}",
                metadata={"framework": fw_info.framework},
            )

        # Detect title from project if not provided
        if not title:
            title = self._detect_project_name(project_path) or "API"

        # Generate OpenAPI spec
        spec = self._generate_openapi_spec(
            routes=routes,
            title=title,
            version=version,
            description=description,
            servers=servers,
            framework_info=fw_info,
        )

        # Format output
        if format == "yaml":
            try:
                import yaml

                output_content = yaml.dump(
                    spec, default_flow_style=False, sort_keys=False, allow_unicode=True
                )
            except ImportError:
                return ToolResult(
                    success=False,
                    output="",
                    error="PyYAML is not installed. Install with: pip install pyyaml",
                )
        else:
            output_content = json.dumps(spec, indent=2)

        # Determine output file
        if not output:
            output = f"openapi.{format if format == 'yaml' else 'json'}"

        output_path = project_path / output

        if dry_run:
            return ToolResult(
                success=True,
                output=f"OpenAPI spec preview (would create {output_path}):\n\n{output_content}",
                metadata={
                    "dry_run": True,
                    "framework": fw_info.framework,
                    "routes_count": len(routes),
                    "output_file": str(output_path),
                },
            )

        # Write spec file
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output_content)
            log.info(
                "api_spec_generated",
                framework=fw_info.framework,
                routes=len(routes),
                output=str(output_path),
            )
            return ToolResult(
                success=True,
                output=f"Generated OpenAPI spec: {output_path}\n\nFramework: {fw_info.framework}\nRoutes: {len(routes)}\n\n{output_content}",
                metadata={
                    "framework": fw_info.framework,
                    "language": fw_info.language,
                    "routes_count": len(routes),
                    "output_file": str(output_path),
                },
            )
        except Exception as e:
            log.error("api_spec_write_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write OpenAPI spec: {str(e)}",
            )

    def _get_language_for_framework(self, framework: str) -> str:
        """Get the programming language for a framework."""
        language_map = {
            "flask": "python",
            "fastapi": "python",
            "django": "python",
            "express": "javascript",
            "gin": "go",
            "echo": "go",
            "actix": "rust",
        }
        return language_map.get(framework, "unknown")

    def _detect_framework(self, path: Path) -> FrameworkInfo:
        """Detect the web framework used in the project."""
        # Python frameworks
        pyproject = path / "pyproject.toml"
        requirements = path / "requirements.txt"
        setup_py = path / "setup.py"

        python_deps = ""
        if pyproject.exists():
            python_deps = pyproject.read_text().lower()
        if requirements.exists():
            python_deps += requirements.read_text().lower()
        if setup_py.exists():
            python_deps += setup_py.read_text().lower()

        if "fastapi" in python_deps:
            return FrameworkInfo(framework="fastapi", language="python")
        if "flask" in python_deps:
            return FrameworkInfo(framework="flask", language="python")
        if "django" in python_deps:
            return FrameworkInfo(framework="django", language="python")

        # Node.js frameworks
        package_json = path / "package.json"
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                if "express" in deps:
                    lang = "typescript" if "typescript" in deps else "javascript"
                    return FrameworkInfo(framework="express", language=lang)
                if "fastify" in deps:
                    lang = "typescript" if "typescript" in deps else "javascript"
                    return FrameworkInfo(
                        framework="express", language=lang
                    )  # Treat fastify similarly
            except json.JSONDecodeError:
                pass

        # Go frameworks
        go_mod = path / "go.mod"
        if go_mod.exists():
            go_deps = go_mod.read_text().lower()
            if "gin-gonic/gin" in go_deps:
                return FrameworkInfo(framework="gin", language="go")
            if "labstack/echo" in go_deps:
                return FrameworkInfo(framework="echo", language="go")

        # Rust frameworks
        cargo_toml = path / "Cargo.toml"
        if cargo_toml.exists():
            rust_deps = cargo_toml.read_text().lower()
            if "actix-web" in rust_deps:
                return FrameworkInfo(framework="actix", language="rust")

        # Scan source files for framework patterns
        return self._detect_framework_from_source(path)

    def _detect_framework_from_source(self, path: Path) -> FrameworkInfo:
        """Detect framework by scanning source files for patterns."""
        # Python patterns
        py_files = list(path.rglob("*.py"))
        for py_file in py_files[:50]:  # Limit search
            try:
                content = py_file.read_text()
                if "from fastapi import" in content or "import fastapi" in content:
                    return FrameworkInfo(
                        framework="fastapi", language="python", entry_point=str(py_file)
                    )
                if "from flask import" in content or "import flask" in content:
                    return FrameworkInfo(
                        framework="flask", language="python", entry_point=str(py_file)
                    )
                if "from django" in content:
                    return FrameworkInfo(framework="django", language="python")
            except (UnicodeDecodeError, IOError):
                continue

        # JavaScript patterns
        js_files = list(path.rglob("*.js")) + list(path.rglob("*.ts"))
        for js_file in js_files[:50]:
            try:
                content = js_file.read_text()
                if "require('express')" in content or "from 'express'" in content:
                    lang = "typescript" if js_file.suffix == ".ts" else "javascript"
                    return FrameworkInfo(
                        framework="express", language=lang, entry_point=str(js_file)
                    )
            except (UnicodeDecodeError, IOError):
                continue

        # Go patterns
        go_files = list(path.rglob("*.go"))
        for go_file in go_files[:50]:
            try:
                content = go_file.read_text()
                if '"github.com/gin-gonic/gin"' in content:
                    return FrameworkInfo(
                        framework="gin", language="go", entry_point=str(go_file)
                    )
                if '"github.com/labstack/echo' in content:
                    return FrameworkInfo(
                        framework="echo", language="go", entry_point=str(go_file)
                    )
            except (UnicodeDecodeError, IOError):
                continue

        return FrameworkInfo(framework="generic", language="unknown")

    def _detect_project_name(self, path: Path) -> Optional[str]:
        """Detect project name from configuration files."""
        # Python
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1).replace("-", " ").replace("_", " ").title()

        # Node.js
        package_json = path / "package.json"
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                name = pkg.get("name", "")
                if name:
                    return name.replace("-", " ").replace("_", " ").title()
            except json.JSONDecodeError:
                pass

        # Go
        go_mod = path / "go.mod"
        if go_mod.exists():
            content = go_mod.read_text()
            match = re.search(r"module\s+([^\s]+)", content)
            if match:
                name = match.group(1).split("/")[-1]
                return name.replace("-", " ").replace("_", " ").title()

        # Rust
        cargo_toml = path / "Cargo.toml"
        if cargo_toml.exists():
            content = cargo_toml.read_text()
            match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1).replace("-", " ").replace("_", " ").title()

        return None

    def _extract_routes(
        self,
        path: Path,
        fw_info: FrameworkInfo,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes based on framework."""
        if fw_info.framework == "fastapi":
            return self._extract_fastapi_routes(
                path, include_patterns, exclude_patterns
            )
        elif fw_info.framework == "flask":
            return self._extract_flask_routes(path, include_patterns, exclude_patterns)
        elif fw_info.framework == "django":
            return self._extract_django_routes(path, include_patterns, exclude_patterns)
        elif fw_info.framework == "express":
            return self._extract_express_routes(
                path, include_patterns, exclude_patterns
            )
        elif fw_info.framework == "gin":
            return self._extract_gin_routes(path, include_patterns, exclude_patterns)
        elif fw_info.framework == "echo":
            return self._extract_echo_routes(path, include_patterns, exclude_patterns)
        else:
            return []

    def _get_files(
        self,
        path: Path,
        extensions: list[str],
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[Path]:
        """Get files matching criteria."""
        files = []
        for ext in extensions:
            files.extend(path.rglob(f"*{ext}"))

        # Filter by patterns
        exclude_patterns = exclude_patterns or [
            "test_*",
            "*_test*",
            "tests/*",
            "test/*",
            "__pycache__/*",
            "node_modules/*",
            "vendor/*",
        ]

        result = []
        for f in files:
            rel_path = str(f.relative_to(path))

            # Check exclude patterns
            excluded = False
            for pattern in exclude_patterns:
                if self._match_pattern(rel_path, pattern):
                    excluded = True
                    break

            if excluded:
                continue

            # Check include patterns (if specified)
            if include_patterns:
                included = False
                for pattern in include_patterns:
                    if self._match_pattern(rel_path, pattern):
                        included = True
                        break
                if not included:
                    continue

            result.append(f)

        return result

    def _match_pattern(self, path: str, pattern: str) -> bool:
        """Simple glob-style pattern matching."""
        import fnmatch

        return fnmatch.fnmatch(path, pattern)

    def _extract_fastapi_routes(
        self,
        path: Path,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes from FastAPI application."""
        routes = []
        files = self._get_files(path, [".py"], include_patterns, exclude_patterns)

        # FastAPI decorator patterns
        re.compile(
            r'@(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']'
            r'(?:.*?(?:summary\s*=\s*["\']([^"\']+)["\'])|)'
            r'(?:.*?(?:description\s*=\s*["\']([^"\']+)["\'])|)'
            r"(?:.*?(?:tags\s*=\s*\[([^\]]+)\])|)",
            re.DOTALL,
        )

        for file in files:
            try:
                content = file.read_text()
                for line_num, line in enumerate(content.split("\n"), 1):
                    # Simple single-line matching for common cases
                    match = re.search(
                        r'@(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']',
                        line,
                    )
                    if match:
                        method = match.group(1).upper()
                        route_path = match.group(2)

                        # Extract path parameters
                        params = self._extract_path_params(route_path)

                        # Try to get function name and docstring
                        summary = None
                        handler = None
                        remaining_lines = content.split("\n")[line_num:]
                        for next_line in remaining_lines[:5]:
                            fn_match = re.search(r"(?:async\s+)?def\s+(\w+)", next_line)
                            if fn_match:
                                handler = fn_match.group(1)
                                break

                        routes.append(
                            RouteInfo(
                                path=route_path,
                                method=method,
                                handler=handler or "handler",
                                summary=summary,
                                parameters=params,
                                file=str(file.relative_to(path)),
                                line=line_num,
                            )
                        )
            except (UnicodeDecodeError, IOError):
                continue

        return routes

    def _extract_flask_routes(
        self,
        path: Path,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes from Flask application."""
        routes = []
        files = self._get_files(path, [".py"], include_patterns, exclude_patterns)

        for file in files:
            try:
                content = file.read_text()
                for line_num, line in enumerate(content.split("\n"), 1):
                    # Flask @app.route or @blueprint.route
                    match = re.search(
                        r'@(?:app|[\w_]+)\.route\s*\(\s*["\']([^"\']+)["\']'
                        r"(?:.*?methods\s*=\s*\[([^\]]+)\])?",
                        line,
                    )
                    if match:
                        route_path = match.group(1)
                        methods_str = match.group(2)

                        if methods_str:
                            methods = [
                                m.strip().strip("\"'").upper()
                                for m in methods_str.split(",")
                            ]
                        else:
                            methods = ["GET"]

                        params = self._extract_path_params(route_path)

                        # Get function name
                        handler = None
                        remaining_lines = content.split("\n")[line_num:]
                        for next_line in remaining_lines[:5]:
                            fn_match = re.search(r"def\s+(\w+)", next_line)
                            if fn_match:
                                handler = fn_match.group(1)
                                break

                        for method in methods:
                            routes.append(
                                RouteInfo(
                                    path=route_path,
                                    method=method,
                                    handler=handler or "handler",
                                    parameters=params,
                                    file=str(file.relative_to(path)),
                                    line=line_num,
                                )
                            )
            except (UnicodeDecodeError, IOError):
                continue

        return routes

    def _extract_django_routes(
        self,
        path: Path,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes from Django application."""
        routes = []
        files = self._get_files(path, [".py"], include_patterns, exclude_patterns)

        for file in files:
            if "urls" not in file.name:
                continue

            try:
                content = file.read_text()
                for line_num, line in enumerate(content.split("\n"), 1):
                    # Django path() function
                    match = re.search(r'path\s*\(\s*["\']([^"\']*)["\']', line)
                    if match:
                        route_path = "/" + match.group(1)
                        params = self._extract_django_path_params(route_path)

                        # Get view name
                        view_match = re.search(r",\s*([\w.]+)", line)
                        handler = view_match.group(1) if view_match else "view"

                        # Django doesn't specify methods in urls.py, assume GET
                        routes.append(
                            RouteInfo(
                                path=route_path,
                                method="GET",
                                handler=handler,
                                parameters=params,
                                file=str(file.relative_to(path)),
                                line=line_num,
                            )
                        )
            except (UnicodeDecodeError, IOError):
                continue

        return routes

    def _extract_express_routes(
        self,
        path: Path,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes from Express.js application."""
        routes = []
        files = self._get_files(
            path, [".js", ".ts"], include_patterns, exclude_patterns
        )

        for file in files:
            try:
                content = file.read_text()
                for line_num, line in enumerate(content.split("\n"), 1):
                    # Express app.get, router.post, etc.
                    match = re.search(
                        r'(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']',
                        line,
                    )
                    if match:
                        method = match.group(1).upper()
                        route_path = match.group(2)
                        params = self._extract_express_path_params(route_path)

                        routes.append(
                            RouteInfo(
                                path=route_path,
                                method=method,
                                handler="handler",
                                parameters=params,
                                file=str(file.relative_to(path)),
                                line=line_num,
                            )
                        )
            except (UnicodeDecodeError, IOError):
                continue

        return routes

    def _extract_gin_routes(
        self,
        path: Path,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes from Gin (Go) application."""
        routes = []
        files = self._get_files(path, [".go"], include_patterns, exclude_patterns)

        for file in files:
            try:
                content = file.read_text()
                for line_num, line in enumerate(content.split("\n"), 1):
                    # Gin router.GET, group.POST, etc.
                    match = re.search(
                        r'\.(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*\(\s*"([^"]+)"',
                        line,
                    )
                    if match:
                        method_match = re.search(
                            r"\.(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)", line
                        )
                        method = method_match.group(1) if method_match else "GET"
                        route_path = match.group(1)
                        params = self._extract_gin_path_params(route_path)

                        routes.append(
                            RouteInfo(
                                path=route_path,
                                method=method,
                                handler="handler",
                                parameters=params,
                                file=str(file.relative_to(path)),
                                line=line_num,
                            )
                        )
            except (UnicodeDecodeError, IOError):
                continue

        return routes

    def _extract_echo_routes(
        self,
        path: Path,
        include_patterns: Optional[list[str]],
        exclude_patterns: Optional[list[str]],
    ) -> list[RouteInfo]:
        """Extract routes from Echo (Go) application."""
        routes = []
        files = self._get_files(path, [".go"], include_patterns, exclude_patterns)

        for file in files:
            try:
                content = file.read_text()
                for line_num, line in enumerate(content.split("\n"), 1):
                    # Echo e.GET, g.POST, etc.
                    match = re.search(
                        r'\.(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*\(\s*"([^"]+)"',
                        line,
                    )
                    if match:
                        method_match = re.search(
                            r"\.(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)", line
                        )
                        method = method_match.group(1) if method_match else "GET"
                        route_path = match.group(1)
                        params = self._extract_echo_path_params(route_path)

                        routes.append(
                            RouteInfo(
                                path=route_path,
                                method=method,
                                handler="handler",
                                parameters=params,
                                file=str(file.relative_to(path)),
                                line=line_num,
                            )
                        )
            except (UnicodeDecodeError, IOError):
                continue

        return routes

    def _extract_path_params(self, path: str) -> list[dict]:
        """Extract path parameters from FastAPI/Flask style path ({param} or <param>)."""
        params = []
        # FastAPI style: {param} or {param:type}
        for match in re.finditer(r"\{(\w+)(?::(\w+))?\}", path):
            param_name = match.group(1)
            param_type = match.group(2) or "string"
            params.append(
                {
                    "name": param_name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": self._convert_type(param_type)},
                }
            )
        # Flask style: <param> or <type:param>
        for match in re.finditer(r"<(?:(\w+):)?(\w+)>", path):
            param_type = match.group(1) or "string"
            param_name = match.group(2)
            params.append(
                {
                    "name": param_name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": self._convert_type(param_type)},
                }
            )
        return params

    def _extract_django_path_params(self, path: str) -> list[dict]:
        """Extract path parameters from Django style path (<type:param>)."""
        params = []
        for match in re.finditer(r"<(?:(\w+):)?(\w+)>", path):
            param_type = match.group(1) or "str"
            param_name = match.group(2)
            params.append(
                {
                    "name": param_name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": self._convert_django_type(param_type)},
                }
            )
        return params

    def _extract_express_path_params(self, path: str) -> list[dict]:
        """Extract path parameters from Express style path (:param)."""
        params = []
        for match in re.finditer(r":(\w+)", path):
            param_name = match.group(1)
            params.append(
                {
                    "name": param_name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            )
        return params

    def _extract_gin_path_params(self, path: str) -> list[dict]:
        """Extract path parameters from Gin style path (:param)."""
        return self._extract_express_path_params(path)  # Same syntax

    def _extract_echo_path_params(self, path: str) -> list[dict]:
        """Extract path parameters from Echo style path (:param)."""
        return self._extract_express_path_params(path)  # Same syntax

    def _convert_type(self, type_str: str) -> str:
        """Convert framework type to OpenAPI type."""
        type_map = {
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "str": "string",
            "string": "string",
            "bool": "boolean",
            "boolean": "boolean",
            "path": "string",
            "uuid": "string",
        }
        return type_map.get(type_str.lower(), "string")

    def _convert_django_type(self, type_str: str) -> str:
        """Convert Django type to OpenAPI type."""
        type_map = {
            "int": "integer",
            "str": "string",
            "slug": "string",
            "uuid": "string",
            "path": "string",
        }
        return type_map.get(type_str.lower(), "string")

    def _convert_path_to_openapi(self, path: str, framework: str) -> str:
        """Convert framework-specific path to OpenAPI format."""
        # Flask/Django <param> -> {param}
        path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", path)
        # Express/Gin/Echo :param -> {param}
        path = re.sub(r":(\w+)", r"{\1}", path)
        return path

    def _generate_openapi_spec(
        self,
        routes: list[RouteInfo],
        title: str,
        version: str,
        description: Optional[str],
        servers: Optional[list[str]],
        framework_info: FrameworkInfo,
    ) -> dict:
        """Generate OpenAPI 3.0 specification."""
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": title,
                "version": version,
            },
            "paths": {},
        }

        if description:
            spec["info"]["description"] = description

        if servers:
            spec["servers"] = [{"url": url} for url in servers]
        else:
            spec["servers"] = [
                {
                    "url": "http://localhost:8000",
                    "description": "Local development server",
                }
            ]

        # Group routes by path
        paths = {}
        for route in routes:
            openapi_path = self._convert_path_to_openapi(
                route.path, framework_info.framework
            )

            if openapi_path not in paths:
                paths[openapi_path] = {}

            method_lower = route.method.lower()
            operation = {
                "operationId": (
                    f"{route.handler}_{method_lower}"
                    if route.handler
                    else f"operation_{method_lower}"
                ),
                "responses": {"200": {"description": "Successful response"}},
            }

            if route.summary:
                operation["summary"] = route.summary
            if route.description:
                operation["description"] = route.description
            if route.parameters:
                operation["parameters"] = route.parameters
            if route.tags:
                operation["tags"] = route.tags

            # Add request body for POST/PUT/PATCH
            if method_lower in ["post", "put", "patch"]:
                operation["requestBody"] = {
                    "content": {"application/json": {"schema": {"type": "object"}}}
                }

            paths[openapi_path][method_lower] = operation

        spec["paths"] = paths

        # Add tags based on file paths
        tag_set = set()
        for route in routes:
            if route.file:
                # Use directory or file name as tag
                parts = route.file.replace("\\", "/").split("/")
                if len(parts) > 1:
                    tag_set.add(parts[-2])  # Parent directory
                else:
                    tag_set.add(
                        parts[0]
                        .replace(".py", "")
                        .replace(".js", "")
                        .replace(".ts", "")
                        .replace(".go", "")
                    )

        if tag_set:
            spec["tags"] = [{"name": tag} for tag in sorted(tag_set)]

        return spec


class ValidateApiSpecTool(Tool):
    """Validate an OpenAPI specification file.

    Checks for syntax errors, missing required fields, and common issues.
    """

    name = "validate_api_spec"
    description = """Validate an OpenAPI specification file for errors and best practices.

Checks for:
- Valid JSON/YAML syntax
- Required OpenAPI fields (openapi, info, paths)
- Valid HTTP methods and status codes
- Path parameter definitions
- Reference consistency ($ref)

Examples:
- validate_api_spec(file_path="openapi.json") - Validate specific file
- validate_api_spec(content="...") - Validate content directly"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to OpenAPI spec file to validate",
            },
            "content": {
                "type": "string",
                "description": "OpenAPI spec content to validate directly",
            },
        },
        "required": [],
    }

    async def execute(
        self, file_path: Optional[str] = None, content: Optional[str] = None, **kwargs
    ) -> ToolResult:
        """Validate an OpenAPI specification.

        Args:
            file_path: Path to OpenAPI spec file
            content: OpenAPI spec content string
        """
        if not file_path and not content:
            return ToolResult(
                success=False,
                output="",
                error="Either file_path or content must be provided",
            )

        spec_content = content
        source_name = "inline"

        if file_path:
            resolved = self._resolve_path(file_path)
            if not resolved.exists():
                return ToolResult(
                    success=False, output="", error=f"File not found: {resolved}"
                )
            spec_content = resolved.read_text()
            source_name = str(resolved)

        # Parse content
        spec = None
        parse_error = None

        # Try JSON first
        try:
            spec = json.loads(spec_content)
        except json.JSONDecodeError:
            # Try YAML
            try:
                import yaml

                spec = yaml.safe_load(spec_content)
            except ImportError:
                parse_error = "Content is not valid JSON. Install PyYAML to parse YAML: pip install pyyaml"
            except yaml.YAMLError as e:
                parse_error = f"Invalid JSON/YAML syntax: {str(e)}"

        if parse_error:
            return ToolResult(success=False, output="", error=parse_error)

        if not isinstance(spec, dict):
            return ToolResult(
                success=False,
                output="",
                error="OpenAPI spec must be a JSON/YAML object",
            )

        # Validate structure
        errors = []
        warnings = []

        # Check required fields
        if "openapi" not in spec:
            errors.append("Missing required field: 'openapi'")
        elif not str(spec["openapi"]).startswith("3."):
            warnings.append(
                f"OpenAPI version {spec['openapi']} may not be fully supported"
            )

        if "info" not in spec:
            errors.append("Missing required field: 'info'")
        elif isinstance(spec["info"], dict):
            if "title" not in spec["info"]:
                errors.append("Missing required field: 'info.title'")
            if "version" not in spec["info"]:
                errors.append("Missing required field: 'info.version'")

        if "paths" not in spec:
            errors.append("Missing required field: 'paths'")
        elif isinstance(spec["paths"], dict):
            # Validate paths
            valid_methods = {
                "get",
                "post",
                "put",
                "delete",
                "patch",
                "options",
                "head",
                "trace",
            }

            for path, path_item in spec["paths"].items():
                if not path.startswith("/"):
                    warnings.append(f"Path '{path}' should start with '/'")

                if not isinstance(path_item, dict):
                    errors.append(f"Path '{path}' must be an object")
                    continue

                for method, operation in path_item.items():
                    if method.lower() not in valid_methods and not method.startswith(
                        "x-"
                    ):
                        errors.append(
                            f"Invalid HTTP method '{method}' in path '{path}'"
                        )
                        continue

                    if method.lower() in valid_methods:
                        if not isinstance(operation, dict):
                            errors.append(
                                f"Operation {method} in '{path}' must be an object"
                            )
                            continue

                        if "responses" not in operation:
                            warnings.append(
                                f"Missing 'responses' in {method.upper()} {path}"
                            )

                        # Validate parameters
                        params = operation.get("parameters", [])
                        if isinstance(params, list):
                            for param in params:
                                if isinstance(param, dict):
                                    if "name" not in param:
                                        errors.append(
                                            f"Parameter missing 'name' in {method.upper()} {path}"
                                        )
                                    if "in" not in param:
                                        errors.append(
                                            f"Parameter missing 'in' in {method.upper()} {path}"
                                        )

                # Check path parameters are defined
                path_params = re.findall(r"\{(\w+)\}", path)
                for param_name in path_params:
                    found = False
                    for method, operation in path_item.items():
                        if method.lower() not in valid_methods:
                            continue
                        if isinstance(operation, dict):
                            for param in operation.get("parameters", []):
                                if (
                                    isinstance(param, dict)
                                    and param.get("name") == param_name
                                    and param.get("in") == "path"
                                ):
                                    found = True
                                    break
                    if not found:
                        warnings.append(
                            f"Path parameter '{param_name}' in '{path}' not defined in parameters"
                        )

        # Build output
        output_lines = [f"Validating: {source_name}"]
        output_lines.append("")

        if errors:
            output_lines.append("Errors:")
            for error in errors:
                output_lines.append(f"  ✗ {error}")

        if warnings:
            output_lines.append("Warnings:")
            for warning in warnings:
                output_lines.append(f"  ⚠ {warning}")

        if not errors and not warnings:
            output_lines.append("✓ OpenAPI spec is valid")

        output_lines.append("")
        output_lines.append(f"Errors: {len(errors)}, Warnings: {len(warnings)}")

        return ToolResult(
            success=len(errors) == 0,
            output="\n".join(output_lines),
            metadata={"errors": errors, "warnings": warnings, "source": source_name},
        )
