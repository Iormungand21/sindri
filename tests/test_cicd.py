"""Tests for CI/CD integration tools."""

import pytest
import json

from sindri.tools.cicd import GenerateWorkflowTool, ValidateWorkflowTool


class TestProjectDetection:
    """Tests for project type detection."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateWorkflowTool instance."""
        return GenerateWorkflowTool(work_dir=tmp_path)

    def test_detect_python_pyproject(self, tool, tmp_path):
        """Test Python project detection with pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """
[tool.poetry]
name = "myproject"

[tool.ruff]
line-length = 88

[tool.black]
line-length = 88
"""
        )

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert info.package_manager == "poetry"
        assert info.has_linting is True
        assert info.lint_tool == "ruff"
        assert info.has_formatting is True
        assert info.format_tool == "black"

    def test_detect_python_requirements(self, tool, tmp_path):
        """Test Python project detection with requirements.txt."""
        (tmp_path / "requirements.txt").write_text("pytest\nrequests\n")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert info.package_manager == "pip"
        assert info.test_framework == "pytest"

    def test_detect_python_setup_py(self, tool, tmp_path):
        """Test Python project detection with setup.py."""
        (tmp_path / "setup.py").write_text("from setuptools import setup")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "python"
        assert info.package_manager == "pip"

    def test_detect_node_npm(self, tool, tmp_path):
        """Test Node.js project detection with npm."""
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "name": "myproject",
                    "devDependencies": {
                        "jest": "^29.0.0",
                        "eslint": "^8.0.0",
                        "prettier": "^3.0.0",
                    },
                    "scripts": {"build": "tsc"},
                }
            )
        )

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.package_manager == "npm"
        assert info.test_framework == "jest"
        assert info.has_linting is True
        assert info.lint_tool == "eslint"
        assert info.has_formatting is True
        assert info.format_tool == "prettier"
        assert info.build_command == "npm run build"

    def test_detect_node_yarn(self, tool, tmp_path):
        """Test Node.js project detection with yarn."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myproject"}))
        (tmp_path / "yarn.lock").write_text("")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.package_manager == "yarn"

    def test_detect_node_pnpm(self, tool, tmp_path):
        """Test Node.js project detection with pnpm."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myproject"}))
        (tmp_path / "pnpm-lock.yaml").write_text("")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.package_manager == "pnpm"

    def test_detect_node_vitest(self, tool, tmp_path):
        """Test Node.js project detection with vitest."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myproject", "devDependencies": {"vitest": "^1.0.0"}})
        )

        info = tool._detect_project(tmp_path)

        assert info.project_type == "node"
        assert info.test_framework == "vitest"

    def test_detect_rust(self, tool, tmp_path):
        """Test Rust project detection."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myproject"')

        info = tool._detect_project(tmp_path)

        assert info.project_type == "rust"
        assert info.package_manager == "cargo"
        assert info.test_framework == "cargo"
        assert info.has_linting is True
        assert info.lint_tool == "clippy"
        assert info.has_formatting is True
        assert info.format_tool == "rustfmt"

    def test_detect_go(self, tool, tmp_path):
        """Test Go project detection."""
        (tmp_path / "go.mod").write_text("module myproject")

        info = tool._detect_project(tmp_path)

        assert info.project_type == "go"
        assert info.package_manager == "go"
        assert info.test_framework == "go"
        assert info.has_formatting is True
        assert info.format_tool == "gofmt"

    def test_detect_generic(self, tool, tmp_path):
        """Test generic project detection."""
        info = tool._detect_project(tmp_path)

        assert info.project_type == "generic"


class TestGenerateWorkflowTool:
    """Tests for GenerateWorkflowTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateWorkflowTool instance."""
        return GenerateWorkflowTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_generate_python_test_workflow(self, tool, tmp_path):
        """Test generating Python test workflow."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'")

        result = await tool.execute(workflow_type="test", dry_run=True)

        assert result.success
        assert "pytest" in result.output
        assert "python-version" in result.output
        assert "setup-python" in result.output
        assert result.metadata["project_type"] == "python"

    @pytest.mark.asyncio
    async def test_generate_python_test_workflow_matrix(self, tool, tmp_path):
        """Test generating Python test workflow with version matrix."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        result = await tool.execute(
            workflow_type="test", python_versions=["3.10", "3.11", "3.12"], dry_run=True
        )

        assert result.success
        assert '"3.10"' in result.output
        assert '"3.11"' in result.output
        assert '"3.12"' in result.output

    @pytest.mark.asyncio
    async def test_generate_python_lint_workflow(self, tool, tmp_path):
        """Test generating Python lint workflow."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 88")

        result = await tool.execute(
            workflow_type="lint", project_type="python", dry_run=True
        )

        assert result.success
        assert "ruff" in result.output
        assert "black" in result.output
        assert "mypy" in result.output

    @pytest.mark.asyncio
    async def test_generate_python_build_workflow(self, tool, tmp_path):
        """Test generating Python build workflow."""
        result = await tool.execute(
            workflow_type="build", project_type="python", dry_run=True
        )

        assert result.success
        assert "python -m build" in result.output
        assert "upload-artifact" in result.output

    @pytest.mark.asyncio
    async def test_generate_python_full_workflow(self, tool, tmp_path):
        """Test generating Python full CI workflow."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        result = await tool.execute(workflow_type="full", dry_run=True)

        assert result.success
        assert "lint:" in result.output
        assert "test:" in result.output
        assert "build:" in result.output
        assert "needs: lint" in result.output
        assert "needs: test" in result.output

    @pytest.mark.asyncio
    async def test_generate_node_test_workflow(self, tool, tmp_path):
        """Test generating Node.js test workflow."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "test", "devDependencies": {"jest": "^29.0.0"}})
        )

        result = await tool.execute(workflow_type="test", dry_run=True)

        assert result.success
        assert "npm" in result.output
        assert "setup-node" in result.output
        assert result.metadata["project_type"] == "node"

    @pytest.mark.asyncio
    async def test_generate_node_test_workflow_matrix(self, tool, tmp_path):
        """Test generating Node.js test workflow with version matrix."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = await tool.execute(
            workflow_type="test", node_versions=["18", "20", "22"], dry_run=True
        )

        assert result.success
        assert '"18"' in result.output
        assert '"20"' in result.output
        assert '"22"' in result.output

    @pytest.mark.asyncio
    async def test_generate_node_lint_workflow(self, tool, tmp_path):
        """Test generating Node.js lint workflow."""
        result = await tool.execute(
            workflow_type="lint", project_type="node", dry_run=True
        )

        assert result.success
        assert "eslint" in result.output.lower()
        assert "prettier" in result.output.lower()

    @pytest.mark.asyncio
    async def test_generate_node_full_workflow(self, tool, tmp_path):
        """Test generating Node.js full CI workflow."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = await tool.execute(workflow_type="full", dry_run=True)

        assert result.success
        assert "lint:" in result.output
        assert "test:" in result.output
        assert "build:" in result.output

    @pytest.mark.asyncio
    async def test_generate_rust_test_workflow(self, tool, tmp_path):
        """Test generating Rust test workflow."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        result = await tool.execute(workflow_type="test", dry_run=True)

        assert result.success
        assert "cargo test" in result.output
        assert "rust-toolchain" in result.output
        assert result.metadata["project_type"] == "rust"

    @pytest.mark.asyncio
    async def test_generate_rust_lint_workflow(self, tool, tmp_path):
        """Test generating Rust lint workflow."""
        result = await tool.execute(
            workflow_type="lint", project_type="rust", dry_run=True
        )

        assert result.success
        assert "cargo fmt" in result.output
        assert "cargo clippy" in result.output

    @pytest.mark.asyncio
    async def test_generate_rust_full_workflow(self, tool, tmp_path):
        """Test generating Rust full CI workflow."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        result = await tool.execute(workflow_type="full", dry_run=True)

        assert result.success
        assert "lint:" in result.output
        assert "test:" in result.output
        assert "build:" in result.output
        assert "cargo build --release" in result.output

    @pytest.mark.asyncio
    async def test_generate_go_test_workflow(self, tool, tmp_path):
        """Test generating Go test workflow."""
        (tmp_path / "go.mod").write_text("module test")

        result = await tool.execute(workflow_type="test", dry_run=True)

        assert result.success
        assert "go test" in result.output
        assert "setup-go" in result.output
        assert result.metadata["project_type"] == "go"

    @pytest.mark.asyncio
    async def test_generate_go_lint_workflow(self, tool, tmp_path):
        """Test generating Go lint workflow."""
        result = await tool.execute(
            workflow_type="lint", project_type="go", dry_run=True
        )

        assert result.success
        assert "gofmt" in result.output
        assert "golangci-lint" in result.output

    @pytest.mark.asyncio
    async def test_generate_go_full_workflow(self, tool, tmp_path):
        """Test generating Go full CI workflow."""
        (tmp_path / "go.mod").write_text("module test")

        result = await tool.execute(workflow_type="full", dry_run=True)

        assert result.success
        assert "lint:" in result.output
        assert "test:" in result.output
        assert "build:" in result.output

    @pytest.mark.asyncio
    async def test_generate_generic_test_workflow(self, tool, tmp_path):
        """Test generating generic test workflow."""
        result = await tool.execute(workflow_type="test", dry_run=True)

        assert result.success
        assert "Add your test commands here" in result.output

    @pytest.mark.asyncio
    async def test_generate_docker_deploy_workflow(self, tool, tmp_path):
        """Test generating Docker deployment workflow."""
        result = await tool.execute(
            workflow_type="deploy", deploy_target="docker", dry_run=True
        )

        assert result.success
        assert "docker/build-push-action" in result.output
        assert "DOCKER_USERNAME" in result.output
        assert "DOCKER_PASSWORD" in result.output

    @pytest.mark.asyncio
    async def test_generate_pypi_deploy_workflow(self, tool, tmp_path):
        """Test generating PyPI deployment workflow."""
        result = await tool.execute(
            workflow_type="deploy", deploy_target="pypi", dry_run=True
        )

        assert result.success
        assert "pypi-publish" in result.output
        assert "release:" in result.output

    @pytest.mark.asyncio
    async def test_generate_npm_deploy_workflow(self, tool, tmp_path):
        """Test generating NPM deployment workflow."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = await tool.execute(
            workflow_type="deploy", deploy_target="npm", dry_run=True
        )

        assert result.success
        assert "npm publish" in result.output
        assert "NPM_TOKEN" in result.output

    @pytest.mark.asyncio
    async def test_generate_ghcr_deploy_workflow(self, tool, tmp_path):
        """Test generating GHCR deployment workflow."""
        result = await tool.execute(
            workflow_type="deploy", deploy_target="ghcr", dry_run=True
        )

        assert result.success
        assert "ghcr.io" in result.output
        assert "GITHUB_TOKEN" in result.output

    @pytest.mark.asyncio
    async def test_generate_heroku_deploy_workflow(self, tool, tmp_path):
        """Test generating Heroku deployment workflow."""
        result = await tool.execute(
            workflow_type="deploy", deploy_target="heroku", dry_run=True
        )

        assert result.success
        assert "heroku-deploy" in result.output
        assert "HEROKU_API_KEY" in result.output

    @pytest.mark.asyncio
    async def test_generate_release_workflow(self, tool, tmp_path):
        """Test generating release workflow."""
        result = await tool.execute(workflow_type="release", dry_run=True)

        assert result.success
        assert "git-cliff" in result.output
        assert "softprops/action-gh-release" in result.output

    @pytest.mark.asyncio
    async def test_generate_with_custom_branches(self, tool, tmp_path):
        """Test generating workflow with custom branches."""
        result = await tool.execute(
            workflow_type="test",
            project_type="python",
            branches=["main", "develop", "release/*"],
            dry_run=True,
        )

        assert result.success
        assert "- main" in result.output
        assert "- develop" in result.output
        assert "- release/*" in result.output

    @pytest.mark.asyncio
    async def test_generate_without_coverage(self, tool, tmp_path):
        """Test generating workflow without coverage."""
        result = await tool.execute(
            workflow_type="test",
            project_type="python",
            include_coverage=False,
            dry_run=True,
        )

        assert result.success
        assert "codecov" not in result.output

    @pytest.mark.asyncio
    async def test_generate_without_cache(self, tool, tmp_path):
        """Test generating workflow without caching."""
        result = await tool.execute(
            workflow_type="test",
            project_type="python",
            include_cache=False,
            dry_run=True,
        )

        assert result.success
        # Cache step should not be present
        assert "actions/cache" not in result.output

    @pytest.mark.asyncio
    async def test_generate_creates_file(self, tool, tmp_path):
        """Test that generate actually creates the workflow file."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        result = await tool.execute(workflow_type="test", dry_run=False)

        assert result.success
        workflow_file = tmp_path / ".github" / "workflows" / "test.yml"
        assert workflow_file.exists()
        content = workflow_file.read_text()
        assert "pytest" in content

    @pytest.mark.asyncio
    async def test_generate_creates_directory(self, tool, tmp_path):
        """Test that generate creates .github/workflows directory."""
        result = await tool.execute(
            workflow_type="test", project_type="python", dry_run=False
        )

        assert result.success
        assert (tmp_path / ".github" / "workflows").exists()

    @pytest.mark.asyncio
    async def test_generate_custom_output_file(self, tool, tmp_path):
        """Test generating workflow to custom output file."""
        result = await tool.execute(
            workflow_type="test",
            project_type="python",
            output_file="ci/custom-test.yml",
            dry_run=False,
        )

        assert result.success
        assert (tmp_path / "ci" / "custom-test.yml").exists()

    @pytest.mark.asyncio
    async def test_generate_nonexistent_path(self, tool, tmp_path):
        """Test generating workflow for nonexistent path."""
        result = await tool.execute(workflow_type="test", path="/nonexistent/path")

        assert not result.success
        assert "does not exist" in result.error


class TestValidateWorkflowTool:
    """Tests for ValidateWorkflowTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a ValidateWorkflowTool instance."""
        return ValidateWorkflowTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_validate_valid_workflow(self, tool, tmp_path):
        """Test validating a valid workflow."""
        workflow = """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "Hello"
"""
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "test.yml").write_text(workflow)

        result = await tool.execute()

        assert result.success
        assert "1/1 workflows valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_missing_name_warning(self, tool, tmp_path):
        """Test warning for missing name field."""
        workflow = """
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Hello"
"""
        result = await tool.execute(content=workflow)

        assert result.success
        assert "Missing 'name'" in result.output

    @pytest.mark.asyncio
    async def test_validate_missing_on(self, tool, tmp_path):
        """Test error for missing 'on' trigger."""
        workflow = """
name: Test
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Hello"
"""
        result = await tool.execute(content=workflow)

        assert not result.success
        assert "Missing required 'on'" in result.output

    @pytest.mark.asyncio
    async def test_validate_missing_jobs(self, tool, tmp_path):
        """Test error for missing 'jobs' field."""
        workflow = """
name: Test
on: push
"""
        result = await tool.execute(content=workflow)

        assert not result.success
        assert "Missing required 'jobs'" in result.output

    @pytest.mark.asyncio
    async def test_validate_empty_jobs(self, tool, tmp_path):
        """Test error for empty jobs."""
        workflow = """
name: Test
on: push
jobs: {}
"""
        result = await tool.execute(content=workflow)

        assert not result.success
        assert "At least one job is required" in result.output

    @pytest.mark.asyncio
    async def test_validate_missing_runs_on(self, tool, tmp_path):
        """Test error for missing runs-on."""
        workflow = """
name: Test
on: push
jobs:
  test:
    steps:
      - run: echo "Hello"
"""
        result = await tool.execute(content=workflow)

        assert not result.success
        assert "missing required 'runs-on'" in result.output

    @pytest.mark.asyncio
    async def test_validate_missing_steps(self, tool, tmp_path):
        """Test error for missing steps."""
        workflow = """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
"""
        result = await tool.execute(content=workflow)

        assert not result.success
        assert "missing required 'steps'" in result.output

    @pytest.mark.asyncio
    async def test_validate_step_missing_uses_or_run(self, tool, tmp_path):
        """Test error for step without uses or run."""
        workflow = """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Invalid step
"""
        result = await tool.execute(content=workflow)

        assert not result.success
        assert "must have 'uses' or 'run'" in result.output

    @pytest.mark.asyncio
    async def test_validate_yaml_syntax_error(self, tool, tmp_path):
        """Test error for YAML syntax error."""
        workflow = """
name: Test
on: push
jobs:
  test:
    - this: is
  - invalid: yaml
  indent:
"""  # Invalid YAML - can't mix list and mapping at same level
        result = await tool.execute(content=workflow)

        # The workflow should fail validation (either YAML error or structure error)
        assert not result.success

    @pytest.mark.asyncio
    async def test_validate_deprecated_action_warning(self, tool, tmp_path):
        """Test warning for deprecated actions."""
        workflow = """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: echo "Hello"
"""
        result = await tool.execute(content=workflow)

        # Should still be valid, but with warnings
        assert result.success
        assert "actions/checkout@v4" in result.output

    @pytest.mark.asyncio
    async def test_validate_specific_file(self, tool, tmp_path):
        """Test validating a specific workflow file."""
        workflow = """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        workflow_file = tmp_path / "test.yml"
        workflow_file.write_text(workflow)

        result = await tool.execute(file_path=str(workflow_file))

        assert result.success
        assert "1/1 workflows valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_directory(self, tool, tmp_path):
        """Test validating all workflows in a directory."""
        workflow_dir = tmp_path / "workflows"
        workflow_dir.mkdir()

        valid_workflow = """
name: Test1
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Hello"
"""
        invalid_workflow = """
name: Test2
on: push
jobs: {}
"""
        (workflow_dir / "valid.yml").write_text(valid_workflow)
        (workflow_dir / "invalid.yml").write_text(invalid_workflow)

        result = await tool.execute(path=str(workflow_dir))

        assert not result.success
        assert "1/2 workflows valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_nonexistent_file(self, tool, tmp_path):
        """Test validating nonexistent file."""
        result = await tool.execute(file_path="/nonexistent/workflow.yml")

        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_validate_nonexistent_directory(self, tool, tmp_path):
        """Test validating nonexistent directory."""
        result = await tool.execute(path="/nonexistent/workflows")

        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_validate_empty_directory(self, tool, tmp_path):
        """Test validating empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = await tool.execute(path=str(empty_dir))

        assert not result.success
        assert "No workflow files found" in result.error

    @pytest.mark.asyncio
    async def test_validate_multiple_valid_workflows(self, tool, tmp_path):
        """Test validating multiple valid workflows."""
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)

        for i in range(3):
            workflow = f"""
name: Test{i}
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Hello {i}"
"""
            (workflow_dir / f"test{i}.yml").write_text(workflow)

        result = await tool.execute()

        assert result.success
        assert "3/3 workflows valid" in result.output

    @pytest.mark.asyncio
    async def test_validate_yaml_extension(self, tool, tmp_path):
        """Test validating .yaml files (not just .yml)."""
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)

        workflow = """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Hello"
"""
        (workflow_dir / "test.yaml").write_text(workflow)

        result = await tool.execute()

        assert result.success
        assert "1/1 workflows valid" in result.output


class TestToolIntegration:
    """Integration tests for CI/CD tools."""

    @pytest.fixture
    def generate_tool(self, tmp_path):
        """Create a GenerateWorkflowTool instance."""
        return GenerateWorkflowTool(work_dir=tmp_path)

    @pytest.fixture
    def validate_tool(self, tmp_path):
        """Create a ValidateWorkflowTool instance."""
        return ValidateWorkflowTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_generate_then_validate(self, generate_tool, validate_tool, tmp_path):
        """Test generating a workflow and then validating it."""
        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        # Generate workflow
        gen_result = await generate_tool.execute(workflow_type="test")
        assert gen_result.success

        # Validate the generated workflow
        val_result = await validate_tool.execute()
        assert val_result.success
        assert "1/1 workflows valid" in val_result.output

    @pytest.mark.asyncio
    async def test_generate_full_then_validate(
        self, generate_tool, validate_tool, tmp_path
    ):
        """Test generating a full CI workflow and validating it."""
        # Create a Node.js project
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        # Generate full CI workflow
        gen_result = await generate_tool.execute(workflow_type="full")
        assert gen_result.success

        # Validate the generated workflow
        val_result = await validate_tool.execute()
        assert val_result.success

    @pytest.mark.asyncio
    async def test_generate_all_types(self, generate_tool, validate_tool, tmp_path):
        """Test generating all workflow types for all project types."""
        project_types = ["python", "node", "rust", "go", "generic"]
        workflow_types = ["test", "lint", "build", "full"]

        for project_type in project_types:
            for workflow_type in workflow_types:
                result = await generate_tool.execute(
                    workflow_type=workflow_type,
                    project_type=project_type,
                    output_file=f".github/workflows/{project_type}-{workflow_type}.yml",
                )
                assert (
                    result.success
                ), f"Failed for {project_type}/{workflow_type}: {result.error}"

        # Validate all generated workflows
        val_result = await validate_tool.execute()
        assert val_result.success
        assert (
            f"{len(project_types) * len(workflow_types)}/{len(project_types) * len(workflow_types)} workflows valid"
            in val_result.output
        )


class TestEdgeCases:
    """Edge case tests for CI/CD tools."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateWorkflowTool instance."""
        return GenerateWorkflowTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_python_poetry_workflow(self, tool, tmp_path):
        """Test Python workflow uses poetry commands when detected."""
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.poetry]
name = "test"
version = "1.0.0"
"""
        )

        result = await tool.execute(workflow_type="test", dry_run=True)

        assert result.success
        assert "poetry" in result.output

    @pytest.mark.asyncio
    async def test_empty_python_versions(self, tool, tmp_path):
        """Test handling empty python_versions list."""
        result = await tool.execute(
            workflow_type="test",
            project_type="python",
            python_versions=[],  # Empty list
            dry_run=True,
        )

        # Should still work with defaults
        assert result.success

    @pytest.mark.asyncio
    async def test_special_characters_in_branch(self, tool, tmp_path):
        """Test branches with special characters."""
        result = await tool.execute(
            workflow_type="test",
            project_type="python",
            branches=["main", "feature/*", "release/**"],
            dry_run=True,
        )

        assert result.success
        assert "feature/*" in result.output
        assert "release/**" in result.output

    @pytest.mark.asyncio
    async def test_workflow_with_coverage_flag(self, tool, tmp_path):
        """Test that coverage flag works correctly."""
        # With coverage
        result_with = await tool.execute(
            workflow_type="test",
            project_type="python",
            include_coverage=True,
            dry_run=True,
        )

        # Without coverage
        result_without = await tool.execute(
            workflow_type="test",
            project_type="python",
            include_coverage=False,
            dry_run=True,
        )

        assert result_with.success
        assert result_without.success
        assert "codecov" in result_with.output
        assert "codecov" not in result_without.output
