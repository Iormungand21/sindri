"""CI/CD integration tools for Sindri.

Provides tools for generating and validating GitHub Actions workflows.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


@dataclass
class ProjectInfo:
    """Detected project information."""

    project_type: str  # python, node, rust, go, generic
    package_manager: Optional[str] = None  # pip, poetry, npm, yarn, pnpm, cargo, go
    test_framework: Optional[str] = None  # pytest, unittest, jest, vitest, cargo, go
    has_linting: bool = False
    lint_tool: Optional[str] = None  # ruff, flake8, eslint, clippy
    has_formatting: bool = False
    format_tool: Optional[str] = None  # black, prettier, rustfmt
    python_versions: list[str] = None  # for matrix testing
    node_versions: list[str] = None  # for matrix testing
    build_command: Optional[str] = None


class GenerateWorkflowTool(Tool):
    """Generate GitHub Actions workflow files.

    Creates CI/CD workflow YAML files based on project configuration
    and detected project type.
    """

    name = "generate_workflow"
    description = """Generate a GitHub Actions workflow file for CI/CD.

Automatically detects project type (Python, Node.js, Rust, Go) and generates
an appropriate workflow with test, lint, and build steps.

Examples:
- generate_workflow(workflow_type="test") - Generate test workflow
- generate_workflow(workflow_type="lint") - Generate linting workflow
- generate_workflow(workflow_type="full") - Generate full CI workflow (test + lint + build)
- generate_workflow(workflow_type="deploy", deploy_target="docker") - Generate deployment workflow
- generate_workflow(workflow_type="test", python_versions=["3.10", "3.11", "3.12"]) - Matrix testing
- generate_workflow(dry_run=true) - Preview workflow without creating file"""

    parameters = {
        "type": "object",
        "properties": {
            "workflow_type": {
                "type": "string",
                "description": "Type of workflow to generate: 'test', 'lint', 'build', 'full', 'deploy', 'release'",
                "enum": ["test", "lint", "build", "full", "deploy", "release"],
            },
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "output_file": {
                "type": "string",
                "description": "Output file path (default: .github/workflows/{workflow_type}.yml)",
            },
            "project_type": {
                "type": "string",
                "description": "Override project type detection: 'python', 'node', 'rust', 'go', 'generic'",
                "enum": ["python", "node", "rust", "go", "generic"],
            },
            "python_versions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Python versions for matrix testing (e.g., ['3.10', '3.11', '3.12'])",
            },
            "node_versions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Node.js versions for matrix testing (e.g., ['18', '20', '22'])",
            },
            "branches": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Branches to trigger on (default: ['main'])",
            },
            "deploy_target": {
                "type": "string",
                "description": "Deployment target: 'docker', 'pypi', 'npm', 'ghcr', 'heroku'",
                "enum": ["docker", "pypi", "npm", "ghcr", "heroku"],
            },
            "include_coverage": {
                "type": "boolean",
                "description": "Include test coverage reporting (default: true)",
            },
            "include_cache": {
                "type": "boolean",
                "description": "Include dependency caching (default: true)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview workflow without creating file",
            },
        },
        "required": ["workflow_type"],
    }

    async def execute(
        self,
        workflow_type: str,
        path: Optional[str] = None,
        output_file: Optional[str] = None,
        project_type: Optional[str] = None,
        python_versions: Optional[list[str]] = None,
        node_versions: Optional[list[str]] = None,
        branches: Optional[list[str]] = None,
        deploy_target: Optional[str] = None,
        include_coverage: bool = True,
        include_cache: bool = True,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate a GitHub Actions workflow file.

        Args:
            workflow_type: Type of workflow (test, lint, build, full, deploy, release)
            path: Project directory path
            output_file: Output file path
            project_type: Override detected project type
            python_versions: Python versions for matrix testing
            node_versions: Node.js versions for matrix testing
            branches: Branches to trigger on
            deploy_target: Deployment target
            include_coverage: Include coverage reporting
            include_cache: Include dependency caching
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
        if python_versions:
            info.python_versions = python_versions
        if node_versions:
            info.node_versions = node_versions

        # Set default branches
        trigger_branches = branches or ["main"]

        # Generate workflow YAML
        workflow = self._generate_workflow(
            workflow_type=workflow_type,
            info=info,
            branches=trigger_branches,
            deploy_target=deploy_target,
            include_coverage=include_coverage,
            include_cache=include_cache,
        )

        # Determine output file
        if not output_file:
            output_file = f".github/workflows/{workflow_type}.yml"

        output_path = project_path / output_file

        if dry_run:
            return ToolResult(
                success=True,
                output=f"Workflow preview (would create {output_path}):\n\n{workflow}",
                metadata={
                    "dry_run": True,
                    "project_type": info.project_type,
                    "output_file": str(output_path),
                },
            )

        # Create directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write workflow file
        try:
            output_path.write_text(workflow)
            log.info(
                "workflow_generated",
                workflow_type=workflow_type,
                project_type=info.project_type,
                output_file=str(output_path),
            )
            return ToolResult(
                success=True,
                output=f"Generated {workflow_type} workflow: {output_path}\n\n{workflow}",
                metadata={
                    "workflow_type": workflow_type,
                    "project_type": info.project_type,
                    "output_file": str(output_path),
                    "branches": trigger_branches,
                },
            )
        except Exception as e:
            log.error("workflow_write_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write workflow file: {str(e)}",
            )

    def _detect_project(self, path: Path) -> ProjectInfo:
        """Detect project type and configuration."""
        info = ProjectInfo(
            project_type="generic", python_versions=["3.11"], node_versions=["20"]
        )

        # Python detection
        if (path / "pyproject.toml").exists():
            info.project_type = "python"
            info.package_manager = (
                "poetry"
                if "poetry" in (path / "pyproject.toml").read_text().lower()
                else "pip"
            )
            info.test_framework = "pytest"  # Assume pytest
            # Check for common tools
            pyproject = (path / "pyproject.toml").read_text()
            if "ruff" in pyproject:
                info.has_linting = True
                info.lint_tool = "ruff"
            elif "flake8" in pyproject:
                info.has_linting = True
                info.lint_tool = "flake8"
            if "black" in pyproject:
                info.has_formatting = True
                info.format_tool = "black"
        elif (path / "setup.py").exists() or (path / "requirements.txt").exists():
            info.project_type = "python"
            info.package_manager = "pip"
            info.test_framework = "pytest"

        # Node.js detection
        elif (path / "package.json").exists():
            info.project_type = "node"
            if (path / "yarn.lock").exists():
                info.package_manager = "yarn"
            elif (path / "pnpm-lock.yaml").exists():
                info.package_manager = "pnpm"
            else:
                info.package_manager = "npm"
            # Check for test framework and lint tools
            pkg_json = json.loads((path / "package.json").read_text())
            scripts = pkg_json.get("scripts", {})
            deps = {
                **pkg_json.get("dependencies", {}),
                **pkg_json.get("devDependencies", {}),
            }

            if "vitest" in deps:
                info.test_framework = "vitest"
            elif "jest" in deps:
                info.test_framework = "jest"

            if "eslint" in deps:
                info.has_linting = True
                info.lint_tool = "eslint"

            if "prettier" in deps:
                info.has_formatting = True
                info.format_tool = "prettier"

            if "build" in scripts:
                info.build_command = f"{info.package_manager} run build"

        # Rust detection
        elif (path / "Cargo.toml").exists():
            info.project_type = "rust"
            info.package_manager = "cargo"
            info.test_framework = "cargo"
            info.has_linting = True
            info.lint_tool = "clippy"
            info.has_formatting = True
            info.format_tool = "rustfmt"

        # Go detection
        elif (path / "go.mod").exists():
            info.project_type = "go"
            info.package_manager = "go"
            info.test_framework = "go"
            info.has_formatting = True
            info.format_tool = "gofmt"

        return info

    def _generate_workflow(
        self,
        workflow_type: str,
        info: ProjectInfo,
        branches: list[str],
        deploy_target: Optional[str],
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate workflow YAML content."""
        if workflow_type == "test":
            return self._generate_test_workflow(
                info, branches, include_coverage, include_cache
            )
        elif workflow_type == "lint":
            return self._generate_lint_workflow(info, branches, include_cache)
        elif workflow_type == "build":
            return self._generate_build_workflow(info, branches, include_cache)
        elif workflow_type == "full":
            return self._generate_full_workflow(
                info, branches, include_coverage, include_cache
            )
        elif workflow_type == "deploy":
            return self._generate_deploy_workflow(
                info, branches, deploy_target, include_cache
            )
        elif workflow_type == "release":
            return self._generate_release_workflow(info, deploy_target)
        else:
            return self._generate_full_workflow(
                info, branches, include_coverage, include_cache
            )

    def _generate_test_workflow(
        self,
        info: ProjectInfo,
        branches: list[str],
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate test workflow."""
        branches_yaml = "\n".join(f"      - {b}" for b in branches)

        if info.project_type == "python":
            return self._python_test_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        elif info.project_type == "node":
            return self._node_test_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        elif info.project_type == "rust":
            return self._rust_test_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        elif info.project_type == "go":
            return self._go_test_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        else:
            return self._generic_test_workflow(branches_yaml)

    def _python_test_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Python test workflow."""
        versions = info.python_versions or ["3.11"]
        versions_yaml = ", ".join(f'"{v}"' for v in versions)

        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt', '**/pyproject.toml') }}
          restore-keys: |
            ${{ runner.os }}-pip-
"""

        coverage_step = ""
        if include_coverage:
            coverage_step = """
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: false
"""

        install_cmd = (
            "pip install -e .[dev]"
            if info.package_manager == "pip"
            else "poetry install"
        )
        test_cmd = (
            "pytest tests/ -v --cov --cov-report=xml"
            if include_coverage
            else "pytest tests/ -v"
        )

        if info.package_manager == "poetry":
            test_cmd = f"poetry run {test_cmd}"

        return f"""name: Tests

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [{versions_yaml}]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
{cache_step}
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          {install_cmd}

      - name: Run tests
        run: {test_cmd}
{coverage_step}"""

    def _node_test_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Node.js test workflow."""
        versions = info.node_versions or ["20"]
        versions_yaml = ", ".join(f'"{v}"' for v in versions)

        pkg_manager = info.package_manager or "npm"
        install_cmd = {
            "npm": "npm ci",
            "yarn": "yarn install --frozen-lockfile",
            "pnpm": "pnpm install --frozen-lockfile",
        }.get(pkg_manager, "npm ci")

        test_cmd = f"{pkg_manager} test"
        if include_coverage:
            test_cmd = (
                f"{pkg_manager} test -- --coverage"
                if pkg_manager == "npm"
                else f"{pkg_manager} test --coverage"
            )

        cache_config = ""
        if include_cache:
            cache_config = f"""
          cache: '{pkg_manager}'"""

        coverage_step = ""
        if include_coverage:
            coverage_step = """
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          fail_ci_if_error: false
"""

        return f"""name: Tests

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [{versions_yaml}]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js ${{{{ matrix.node-version }}}}
        uses: actions/setup-node@v4
        with:
          node-version: ${{{{ matrix.node-version }}}}{cache_config}

      - name: Install dependencies
        run: {install_cmd}

      - name: Run tests
        run: {test_cmd}
{coverage_step}"""

    def _rust_test_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Rust test workflow."""
        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache cargo
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
"""

        coverage_step = ""
        if include_coverage:
            coverage_step = """
      - name: Install coverage tool
        run: cargo install cargo-tarpaulin

      - name: Generate coverage
        run: cargo tarpaulin --out Xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./cobertura.xml
          fail_ci_if_error: false
"""

        return f"""name: Tests

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable
{cache_step}
      - name: Run tests
        run: cargo test --verbose
{coverage_step}"""

    def _go_test_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Go test workflow."""
        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache Go modules
        uses: actions/cache@v4
        with:
          path: |
            ~/go/pkg/mod
            ~/.cache/go-build
          key: ${{ runner.os }}-go-${{ hashFiles('**/go.sum') }}
"""

        coverage_flag = "-coverprofile=coverage.out" if include_coverage else ""
        coverage_step = ""
        if include_coverage:
            coverage_step = """
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.out
          fail_ci_if_error: false
"""

        return f"""name: Tests

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: stable
{cache_step}
      - name: Run tests
        run: go test -v {coverage_flag} ./...
{coverage_step}"""

    def _generic_test_workflow(self, branches_yaml: str) -> str:
        """Generate generic test workflow."""
        return f"""name: Tests

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: |
          echo "Add your test commands here"
          # Example: pytest, npm test, cargo test, etc.
"""

    def _generate_lint_workflow(
        self, info: ProjectInfo, branches: list[str], include_cache: bool
    ) -> str:
        """Generate lint workflow."""
        branches_yaml = "\n".join(f"      - {b}" for b in branches)

        if info.project_type == "python":
            return self._python_lint_workflow(info, branches_yaml, include_cache)
        elif info.project_type == "node":
            return self._node_lint_workflow(info, branches_yaml, include_cache)
        elif info.project_type == "rust":
            return self._rust_lint_workflow(info, branches_yaml, include_cache)
        elif info.project_type == "go":
            return self._go_lint_workflow(info, branches_yaml, include_cache)
        else:
            return self._generic_lint_workflow(branches_yaml)

    def _python_lint_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Python lint workflow."""
        lint_tool = info.lint_tool or "ruff"
        format_tool = info.format_tool or "black"

        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-lint
"""

        return f"""name: Lint

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
{cache_step}
      - name: Install linters
        run: |
          python -m pip install --upgrade pip
          pip install {lint_tool} {format_tool} mypy

      - name: Run {lint_tool}
        run: {lint_tool} check .

      - name: Check formatting
        run: {format_tool} --check .

      - name: Type check
        run: mypy . --ignore-missing-imports || true
"""

    def _node_lint_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Node.js lint workflow."""
        pkg_manager = info.package_manager or "npm"
        install_cmd = {
            "npm": "npm ci",
            "yarn": "yarn install --frozen-lockfile",
            "pnpm": "pnpm install --frozen-lockfile",
        }.get(pkg_manager, "npm ci")

        cache_config = ""
        if include_cache:
            cache_config = f"""
          cache: '{pkg_manager}'"""

        return f"""name: Lint

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"{cache_config}

      - name: Install dependencies
        run: {install_cmd}

      - name: Run ESLint
        run: {pkg_manager} run lint || npx eslint .

      - name: Check formatting
        run: npx prettier --check . || true
"""

    def _rust_lint_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Rust lint workflow."""
        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache cargo
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-lint-${{ hashFiles('**/Cargo.lock') }}
"""

        return f"""name: Lint

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
{cache_step}
      - name: Check formatting
        run: cargo fmt --all -- --check

      - name: Run Clippy
        run: cargo clippy --all-targets --all-features -- -D warnings
"""

    def _go_lint_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Go lint workflow."""
        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache Go modules
        uses: actions/cache@v4
        with:
          path: |
            ~/go/pkg/mod
            ~/.cache/go-build
          key: ${{ runner.os }}-go-lint-${{ hashFiles('**/go.sum') }}
"""

        return f"""name: Lint

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: stable
{cache_step}
      - name: Check formatting
        run: |
          if [ -n "$(gofmt -s -l .)" ]; then
            gofmt -s -d .
            exit 1
          fi

      - name: Run golangci-lint
        uses: golangci/golangci-lint-action@v4
        with:
          version: latest
"""

    def _generic_lint_workflow(self, branches_yaml: str) -> str:
        """Generate generic lint workflow."""
        return f"""name: Lint

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Run linters
        run: |
          echo "Add your lint commands here"
          # Example: ruff check ., npm run lint, cargo clippy, etc.
"""

    def _generate_build_workflow(
        self, info: ProjectInfo, branches: list[str], include_cache: bool
    ) -> str:
        """Generate build workflow."""
        branches_yaml = "\n".join(f"      - {b}" for b in branches)

        if info.project_type == "python":
            return self._python_build_workflow(info, branches_yaml, include_cache)
        elif info.project_type == "node":
            return self._node_build_workflow(info, branches_yaml, include_cache)
        elif info.project_type == "rust":
            return self._rust_build_workflow(info, branches_yaml, include_cache)
        elif info.project_type == "go":
            return self._go_build_workflow(info, branches_yaml, include_cache)
        else:
            return self._generic_build_workflow(branches_yaml)

    def _python_build_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Python build workflow."""
        return f"""name: Build

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: |
          python -m pip install --upgrade pip
          pip install build wheel

      - name: Build package
        run: python -m build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
"""

    def _node_build_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Node.js build workflow."""
        pkg_manager = info.package_manager or "npm"
        install_cmd = {
            "npm": "npm ci",
            "yarn": "yarn install --frozen-lockfile",
            "pnpm": "pnpm install --frozen-lockfile",
        }.get(pkg_manager, "npm ci")

        cache_config = ""
        if include_cache:
            cache_config = f"""
          cache: '{pkg_manager}'"""

        return f"""name: Build

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"{cache_config}

      - name: Install dependencies
        run: {install_cmd}

      - name: Build
        run: {pkg_manager} run build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
"""

    def _rust_build_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Rust build workflow."""
        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache cargo
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-build-${{ hashFiles('**/Cargo.lock') }}
"""

        return f"""name: Build

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable
{cache_step}
      - name: Build
        run: cargo build --release

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: release
          path: target/release/
"""

    def _go_build_workflow(
        self, info: ProjectInfo, branches_yaml: str, include_cache: bool
    ) -> str:
        """Generate Go build workflow."""
        cache_step = ""
        if include_cache:
            cache_step = """
      - name: Cache Go modules
        uses: actions/cache@v4
        with:
          path: |
            ~/go/pkg/mod
            ~/.cache/go-build
          key: ${{ runner.os }}-go-build-${{ hashFiles('**/go.sum') }}
"""

        return f"""name: Build

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: stable
{cache_step}
      - name: Build
        run: go build -v ./...

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: build
          path: ./
"""

    def _generic_build_workflow(self, branches_yaml: str) -> str:
        """Generate generic build workflow."""
        return f"""name: Build

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: |
          echo "Add your build commands here"
          # Example: python -m build, npm run build, cargo build, etc.
"""

    def _generate_full_workflow(
        self,
        info: ProjectInfo,
        branches: list[str],
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate full CI workflow with test, lint, and build."""
        branches_yaml = "\n".join(f"      - {b}" for b in branches)

        if info.project_type == "python":
            return self._python_full_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        elif info.project_type == "node":
            return self._node_full_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        elif info.project_type == "rust":
            return self._rust_full_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        elif info.project_type == "go":
            return self._go_full_workflow(
                info, branches_yaml, include_coverage, include_cache
            )
        else:
            return self._generic_full_workflow(branches_yaml)

    def _python_full_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Python full CI workflow."""
        versions = info.python_versions or ["3.11"]
        versions_yaml = ", ".join(f'"{v}"' for v in versions)
        lint_tool = info.lint_tool or "ruff"
        format_tool = info.format_tool or "black"

        install_cmd = (
            "pip install -e .[dev]"
            if info.package_manager == "pip"
            else "poetry install"
        )
        test_cmd = (
            "pytest tests/ -v --cov --cov-report=xml"
            if include_coverage
            else "pytest tests/ -v"
        )

        if info.package_manager == "poetry":
            test_cmd = f"poetry run {test_cmd}"

        coverage_step = ""
        if include_coverage:
            coverage_step = """
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.11'
        with:
          files: ./coverage.xml
          fail_ci_if_error: false
"""

        return f"""name: CI

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install linters
        run: |
          python -m pip install --upgrade pip
          pip install {lint_tool} {format_tool} mypy

      - name: Run {lint_tool}
        run: {lint_tool} check .

      - name: Check formatting
        run: {format_tool} --check .

  test:
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      matrix:
        python-version: [{versions_yaml}]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          {install_cmd}

      - name: Run tests
        run: {test_cmd}
{coverage_step}
  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Build package
        run: |
          pip install build
          python -m build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
"""

    def _node_full_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Node.js full CI workflow."""
        versions = info.node_versions or ["20"]
        versions_yaml = ", ".join(f'"{v}"' for v in versions)
        pkg_manager = info.package_manager or "npm"
        install_cmd = {
            "npm": "npm ci",
            "yarn": "yarn install --frozen-lockfile",
            "pnpm": "pnpm install --frozen-lockfile",
        }.get(pkg_manager, "npm ci")

        test_cmd = f"{pkg_manager} test"

        return f"""name: CI

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: '{pkg_manager}'

      - name: Install dependencies
        run: {install_cmd}

      - name: Run ESLint
        run: {pkg_manager} run lint || npx eslint .

      - name: Check formatting
        run: npx prettier --check . || true

  test:
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      matrix:
        node-version: [{versions_yaml}]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js ${{{{ matrix.node-version }}}}
        uses: actions/setup-node@v4
        with:
          node-version: ${{{{ matrix.node-version }}}}
          cache: '{pkg_manager}'

      - name: Install dependencies
        run: {install_cmd}

      - name: Run tests
        run: {test_cmd}

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: '{pkg_manager}'

      - name: Install dependencies
        run: {install_cmd}

      - name: Build
        run: {pkg_manager} run build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
"""

    def _rust_full_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Rust full CI workflow."""
        return f"""name: CI

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy

      - name: Check formatting
        run: cargo fmt --all -- --check

      - name: Run Clippy
        run: cargo clippy --all-targets --all-features -- -D warnings

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Cache cargo
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{{{ runner.os }}}}-cargo-${{{{ hashFiles('**/Cargo.lock') }}}}

      - name: Run tests
        run: cargo test --verbose

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Build release
        run: cargo build --release

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: release
          path: target/release/
"""

    def _go_full_workflow(
        self,
        info: ProjectInfo,
        branches_yaml: str,
        include_coverage: bool,
        include_cache: bool,
    ) -> str:
        """Generate Go full CI workflow."""
        return f"""name: CI

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: stable

      - name: Check formatting
        run: |
          if [ -n "$(gofmt -s -l .)" ]; then
            gofmt -s -d .
            exit 1
          fi

      - name: Run golangci-lint
        uses: golangci/golangci-lint-action@v4
        with:
          version: latest

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: stable

      - name: Run tests
        run: go test -v ./...

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: stable

      - name: Build
        run: go build -v ./...
"""

    def _generic_full_workflow(self, branches_yaml: str) -> str:
        """Generate generic full CI workflow."""
        return f"""name: CI

on:
  push:
    branches:
{branches_yaml}
  pull_request:
    branches:
{branches_yaml}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run linters
        run: |
          echo "Add your lint commands here"

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: |
          echo "Add your test commands here"

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: |
          echo "Add your build commands here"
"""

    def _generate_deploy_workflow(
        self,
        info: ProjectInfo,
        branches: list[str],
        deploy_target: Optional[str],
        include_cache: bool,
    ) -> str:
        """Generate deployment workflow."""
        if deploy_target == "docker":
            return self._docker_deploy_workflow(info, branches)
        elif deploy_target == "pypi":
            return self._pypi_deploy_workflow(info)
        elif deploy_target == "npm":
            return self._npm_deploy_workflow(info)
        elif deploy_target == "ghcr":
            return self._ghcr_deploy_workflow(info, branches)
        elif deploy_target == "heroku":
            return self._heroku_deploy_workflow(info, branches)
        else:
            return self._docker_deploy_workflow(info, branches)

    def _docker_deploy_workflow(self, info: ProjectInfo, branches: list[str]) -> str:
        """Generate Docker deployment workflow."""
        branches_yaml = "\n".join(f"      - {b}" for b in branches)

        return f"""name: Deploy

on:
  push:
    branches:
{branches_yaml}
    tags:
      - 'v*'

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{{{ secrets.DOCKER_USERNAME }}}}
          password: ${{{{ secrets.DOCKER_PASSWORD }}}}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{{{ secrets.DOCKER_USERNAME }}}}/${{{{ github.event.repository.name }}}}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{{{version}}}}
            type=sha,prefix=

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to: type=gha,mode=max
"""

    def _pypi_deploy_workflow(self, info: ProjectInfo) -> str:
        """Generate PyPI deployment workflow."""
        return """name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write  # For trusted publishing

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: |
          python -m pip install --upgrade pip
          pip install build

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
"""

    def _npm_deploy_workflow(self, info: ProjectInfo) -> str:
        """Generate NPM deployment workflow."""
        pkg_manager = info.package_manager or "npm"

        return f"""name: Publish to NPM

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"
          cache: '{pkg_manager}'

      - name: Install dependencies
        run: {pkg_manager} ci

      - name: Build
        run: {pkg_manager} run build

      - name: Publish
        run: {pkg_manager} publish
        env:
          NODE_AUTH_TOKEN: ${{{{ secrets.NPM_TOKEN }}}}
"""

    def _ghcr_deploy_workflow(self, info: ProjectInfo, branches: list[str]) -> str:
        """Generate GitHub Container Registry deployment workflow."""
        branches_yaml = "\n".join(f"      - {b}" for b in branches)

        return f"""name: Deploy to GHCR

on:
  push:
    branches:
{branches_yaml}
    tags:
      - 'v*'

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{{{ github.repository }}}}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{{{version}}}}
            type=sha,prefix=

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to: type=gha,mode=max
"""

    def _heroku_deploy_workflow(self, info: ProjectInfo, branches: list[str]) -> str:
        """Generate Heroku deployment workflow."""
        return """name: Deploy to Heroku

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Heroku
        uses: akhileshns/heroku-deploy@v3.13.15
        with:
          heroku_api_key: ${{ secrets.HEROKU_API_KEY }}
          heroku_app_name: ${{ secrets.HEROKU_APP_NAME }}
          heroku_email: ${{ secrets.HEROKU_EMAIL }}
"""

    def _generate_release_workflow(
        self, info: ProjectInfo, deploy_target: Optional[str]
    ) -> str:
        """Generate release workflow with changelog generation."""
        publish_step = ""
        if deploy_target == "pypi":
            publish_step = """
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Build and publish to PyPI
        run: |
          pip install build
          python -m build
        # Add PyPI publish step here
"""
        elif deploy_target == "npm":
            publish_step = """
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"

      - name: Publish to NPM
        run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
"""

        return f"""name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate changelog
        id: changelog
        uses: orhun/git-cliff-action@v3
        with:
          config: cliff.toml
          args: --latest --strip header
        env:
          OUTPUT: CHANGELOG.md

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          body: ${{{{ steps.changelog.outputs.content }}}}
          draft: false
          prerelease: ${{{{ contains(github.ref, '-') }}}}
{publish_step}"""


class ValidateWorkflowTool(Tool):
    """Validate GitHub Actions workflow files.

    Checks workflow YAML for syntax errors and common issues.
    """

    name = "validate_workflow"
    description = """Validate a GitHub Actions workflow file for syntax and common errors.

Examples:
- validate_workflow(file_path=".github/workflows/ci.yml") - Validate specific file
- validate_workflow(path=".github/workflows") - Validate all workflows in directory
- validate_workflow(content="...") - Validate workflow YAML content directly"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to workflow file to validate",
            },
            "path": {
                "type": "string",
                "description": "Directory containing workflow files to validate",
            },
            "content": {
                "type": "string",
                "description": "Workflow YAML content to validate directly",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        file_path: Optional[str] = None,
        path: Optional[str] = None,
        content: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Validate workflow file(s).

        Args:
            file_path: Path to specific workflow file
            path: Directory containing workflow files
            content: Workflow YAML content string
        """
        try:
            import yaml
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="PyYAML is not installed. Install with: pip install pyyaml",
            )

        results = []
        errors = []

        if content:
            # Validate content directly
            result = self._validate_content(content, "inline", yaml)
            results.append(result)
            if not result["valid"]:
                errors.extend(result["errors"])

        elif file_path:
            # Validate single file
            resolved = self._resolve_path(file_path)
            if not resolved.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Workflow file not found: {resolved}",
                )

            content = resolved.read_text()
            result = self._validate_content(content, str(resolved), yaml)
            results.append(result)
            if not result["valid"]:
                errors.extend(result["errors"])

        elif path:
            # Validate all workflows in directory
            workflow_dir = self._resolve_path(path)
            if not workflow_dir.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Workflow directory not found: {workflow_dir}",
                )

            for workflow_file in workflow_dir.glob("*.yml"):
                content = workflow_file.read_text()
                result = self._validate_content(content, str(workflow_file), yaml)
                results.append(result)
                if not result["valid"]:
                    errors.extend(result["errors"])

            for workflow_file in workflow_dir.glob("*.yaml"):
                content = workflow_file.read_text()
                result = self._validate_content(content, str(workflow_file), yaml)
                results.append(result)
                if not result["valid"]:
                    errors.extend(result["errors"])

            if not results:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No workflow files found in: {workflow_dir}",
                )

        else:
            # Default: validate all workflows in .github/workflows
            workflow_dir = self._resolve_path(".github/workflows")
            if not workflow_dir.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error="No .github/workflows directory found",
                )

            for workflow_file in workflow_dir.glob("*.yml"):
                content = workflow_file.read_text()
                result = self._validate_content(content, str(workflow_file), yaml)
                results.append(result)
                if not result["valid"]:
                    errors.extend(result["errors"])

            for workflow_file in workflow_dir.glob("*.yaml"):
                content = workflow_file.read_text()
                result = self._validate_content(content, str(workflow_file), yaml)
                results.append(result)
                if not result["valid"]:
                    errors.extend(result["errors"])

        # Build output
        output_lines = []
        for result in results:
            status = "✓" if result["valid"] else "✗"
            output_lines.append(f"{status} {result['file']}")
            if result["warnings"]:
                for warning in result["warnings"]:
                    output_lines.append(f"  ⚠ {warning}")
            if result["errors"]:
                for error in result["errors"]:
                    output_lines.append(f"  ✗ {error}")

        valid_count = sum(1 for r in results if r["valid"])
        total_count = len(results)

        output_lines.append(f"\n{valid_count}/{total_count} workflows valid")

        return ToolResult(
            success=len(errors) == 0,
            output="\n".join(output_lines),
            metadata={
                "valid_count": valid_count,
                "total_count": total_count,
                "errors": errors,
            },
        )

    def _validate_content(self, content: str, file_name: str, yaml_module) -> dict:
        """Validate workflow YAML content."""
        result = {"file": file_name, "valid": True, "errors": [], "warnings": []}

        # Check YAML syntax
        try:
            workflow = yaml_module.safe_load(content)
        except yaml_module.YAMLError as e:
            result["valid"] = False
            result["errors"].append(f"YAML syntax error: {str(e)}")
            return result

        if not isinstance(workflow, dict):
            result["valid"] = False
            result["errors"].append("Workflow must be a YAML mapping")
            return result

        # Check required fields
        if "name" not in workflow:
            result["warnings"].append("Missing 'name' field (recommended)")

        # 'on' key gets parsed as True in YAML (boolean), so check for both
        if "on" not in workflow and True not in workflow:
            result["valid"] = False
            result["errors"].append("Missing required 'on' trigger field")

        if "jobs" not in workflow:
            result["valid"] = False
            result["errors"].append("Missing required 'jobs' field")
            return result

        jobs = workflow.get("jobs", {})
        if not isinstance(jobs, dict):
            result["valid"] = False
            result["errors"].append("'jobs' must be a mapping")
            return result

        if len(jobs) == 0:
            result["valid"] = False
            result["errors"].append("At least one job is required")
            return result

        # Validate each job
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                result["valid"] = False
                result["errors"].append(f"Job '{job_name}' must be a mapping")
                continue

            if "runs-on" not in job:
                result["valid"] = False
                result["errors"].append(
                    f"Job '{job_name}' missing required 'runs-on' field"
                )

            if "steps" not in job:
                result["valid"] = False
                result["errors"].append(
                    f"Job '{job_name}' missing required 'steps' field"
                )
                continue

            steps = job.get("steps", [])
            if not isinstance(steps, list):
                result["valid"] = False
                result["errors"].append(f"Job '{job_name}' steps must be a list")
                continue

            if len(steps) == 0:
                result["warnings"].append(f"Job '{job_name}' has no steps")

            # Validate steps
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    result["valid"] = False
                    result["errors"].append(
                        f"Job '{job_name}' step {i+1} must be a mapping"
                    )
                    continue

                # Step must have 'uses' or 'run'
                if "uses" not in step and "run" not in step:
                    result["valid"] = False
                    result["errors"].append(
                        f"Job '{job_name}' step {i+1} must have 'uses' or 'run'"
                    )

        # Check for common issues
        content_lower = content.lower()

        # Deprecated actions
        deprecated_actions = [
            ("actions/checkout@v2", "actions/checkout@v4"),
            ("actions/checkout@v3", "actions/checkout@v4"),
            ("actions/setup-python@v2", "actions/setup-python@v5"),
            ("actions/setup-python@v3", "actions/setup-python@v5"),
            ("actions/setup-python@v4", "actions/setup-python@v5"),
            ("actions/setup-node@v2", "actions/setup-node@v4"),
            ("actions/setup-node@v3", "actions/setup-node@v4"),
            ("actions/cache@v2", "actions/cache@v4"),
            ("actions/cache@v3", "actions/cache@v4"),
            ("actions/upload-artifact@v2", "actions/upload-artifact@v4"),
            ("actions/upload-artifact@v3", "actions/upload-artifact@v4"),
        ]

        for old_action, new_action in deprecated_actions:
            if old_action.lower() in content_lower:
                result["warnings"].append(
                    f"Consider updating '{old_action}' to '{new_action}'"
                )

        # Check for hardcoded secrets
        if re.search(
            r'(password|secret|token|key)\s*[:=]\s*["\'][^$]', content, re.IGNORECASE
        ):
            result["warnings"].append(
                "Possible hardcoded secret detected - use ${{ secrets.* }} instead"
            )

        return result
