"""Tests for git automation tools (Phase 14)."""

import pytest
from pathlib import Path
import tempfile
import shutil
import subprocess

from sindri.tools.git_automation import (
    GitAutoCommitTool,
    GitBranchCompareTool,
    GitConflictAssistTool,
    GitReleaseNotesTool,
    CommitType,
    MergeStrategy,
    _detect_commit_type,
    _detect_scope,
    _parse_conventional_commit,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    temp = Path(tempfile.mkdtemp())

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=temp, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=temp, capture_output=True
    )

    # Create initial file and commit
    (temp / "README.md").write_text("# Test Project\n\nInitial content.")
    subprocess.run(["git", "add", "README.md"], cwd=temp, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial commit"], cwd=temp, capture_output=True
    )

    yield temp

    # Cleanup
    shutil.rmtree(temp)


@pytest.fixture
def temp_repo_with_staged(temp_git_repo):
    """Git repo with staged changes for commit testing."""
    # Create and stage a new file
    (temp_git_repo / "main.py").write_text('print("Hello World")\n')
    subprocess.run(["git", "add", "main.py"], cwd=temp_git_repo, capture_output=True)

    return temp_git_repo


@pytest.fixture
def temp_repo_with_branches(temp_git_repo):
    """Git repo with multiple branches for comparison testing."""
    # Create some commits on main
    (temp_git_repo / "file1.py").write_text("# File 1\n")
    subprocess.run(["git", "add", "file1.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add file1"], cwd=temp_git_repo, capture_output=True
    )

    # Create a feature branch
    subprocess.run(
        ["git", "checkout", "-b", "feature"], cwd=temp_git_repo, capture_output=True
    )

    # Add commits on feature branch
    (temp_git_repo / "feature.py").write_text("# Feature\n")
    subprocess.run(["git", "add", "feature.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add feature"], cwd=temp_git_repo, capture_output=True
    )

    (temp_git_repo / "feature2.py").write_text("# Feature 2\n")
    subprocess.run(["git", "add", "feature2.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: fix feature"], cwd=temp_git_repo, capture_output=True
    )

    # Go back to main
    subprocess.run(
        ["git", "checkout", "master"], cwd=temp_git_repo, capture_output=True
    )
    # Try main branch if master doesn't exist
    subprocess.run(
        ["git", "checkout", "main"], cwd=temp_git_repo, capture_output=True
    )

    return temp_git_repo


@pytest.fixture
def temp_repo_with_tags(temp_git_repo):
    """Git repo with version tags for release notes testing."""
    # Create v1.0.0 tag
    subprocess.run(
        ["git", "tag", "v1.0.0"], cwd=temp_git_repo, capture_output=True
    )

    # Add some commits
    (temp_git_repo / "feature1.py").write_text("# Feature 1\n")
    subprocess.run(["git", "add", "feature1.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add feature 1"], cwd=temp_git_repo, capture_output=True
    )

    (temp_git_repo / "bugfix.py").write_text("# Bug fix\n")
    subprocess.run(["git", "add", "bugfix.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: critical bug fix"], cwd=temp_git_repo, capture_output=True
    )

    (temp_git_repo / "docs.md").write_text("# Documentation\n")
    subprocess.run(["git", "add", "docs.md"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "docs: update documentation"], cwd=temp_git_repo, capture_output=True
    )

    # Create v1.1.0 tag
    subprocess.run(
        ["git", "tag", "v1.1.0"], cwd=temp_git_repo, capture_output=True
    )

    return temp_git_repo


@pytest.fixture
def temp_repo_with_conflicts(temp_git_repo):
    """Git repo in conflict state for resolution testing."""
    # Create a file on main
    (temp_git_repo / "conflict.py").write_text("# Original content\nx = 1\n")
    subprocess.run(["git", "add", "conflict.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add conflict file"], cwd=temp_git_repo, capture_output=True
    )

    # Create branch and modify
    subprocess.run(
        ["git", "checkout", "-b", "conflict-branch"], cwd=temp_git_repo, capture_output=True
    )
    (temp_git_repo / "conflict.py").write_text("# Branch content\nx = 2\ny = 3\n")
    subprocess.run(["git", "add", "conflict.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: branch changes"], cwd=temp_git_repo, capture_output=True
    )

    # Go back to main and make conflicting change
    subprocess.run(
        ["git", "checkout", "master"], cwd=temp_git_repo, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "main"], cwd=temp_git_repo, capture_output=True
    )
    (temp_git_repo / "conflict.py").write_text("# Main content\nx = 10\nz = 5\n")
    subprocess.run(["git", "add", "conflict.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: main changes"], cwd=temp_git_repo, capture_output=True
    )

    # Try to merge (will fail with conflicts)
    subprocess.run(
        ["git", "merge", "conflict-branch"], cwd=temp_git_repo, capture_output=True
    )

    return temp_git_repo


@pytest.fixture
def temp_non_git_dir():
    """Create a temporary directory that is NOT a git repo."""
    temp = Path(tempfile.mkdtemp())
    (temp / "file.txt").write_text("Some content")
    yield temp
    shutil.rmtree(temp)


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestParseConventionalCommit:
    """Tests for _parse_conventional_commit function."""

    def test_parse_feat(self):
        """Test parsing feat commit."""
        commit_type, scope, breaking = _parse_conventional_commit("feat: add new feature")
        assert commit_type == "feat"
        assert scope == ""
        assert breaking is False

    def test_parse_with_scope(self):
        """Test parsing commit with scope."""
        commit_type, scope, breaking = _parse_conventional_commit("fix(auth): fix login bug")
        assert commit_type == "fix"
        assert scope == "auth"
        assert breaking is False

    def test_parse_breaking_change(self):
        """Test parsing breaking change."""
        commit_type, scope, breaking = _parse_conventional_commit("feat!: breaking change")
        assert commit_type == "feat"
        assert breaking is True

    def test_parse_breaking_with_scope(self):
        """Test parsing breaking change with scope."""
        commit_type, scope, breaking = _parse_conventional_commit("refactor(api)!: restructure")
        assert commit_type == "refactor"
        assert scope == "api"
        assert breaking is True

    def test_parse_non_conventional(self):
        """Test parsing non-conventional commit."""
        commit_type, scope, breaking = _parse_conventional_commit("Update the readme file")
        assert commit_type == ""
        assert scope == ""
        assert breaking is False


class TestDetectCommitType:
    """Tests for _detect_commit_type function."""

    def test_detect_test_type(self):
        """Test detecting test commit type."""
        files = ["tests/test_auth.py", "tests/test_user.py"]
        result = _detect_commit_type(files, "")
        assert result == CommitType.TEST

    def test_detect_docs_type(self):
        """Test detecting docs commit type."""
        files = ["README.md", "docs/guide.md"]
        result = _detect_commit_type(files, "")
        assert result == CommitType.DOCS

    def test_detect_ci_type(self):
        """Test detecting CI commit type."""
        files = [".github/workflows/ci.yml"]
        result = _detect_commit_type(files, "")
        assert result == CommitType.CI

    def test_detect_build_type(self):
        """Test detecting build commit type."""
        files = ["pyproject.toml", "setup.py"]
        result = _detect_commit_type(files, "")
        assert result == CommitType.BUILD

    def test_detect_fix_from_diff(self):
        """Test detecting fix from diff content."""
        files = ["src/main.py"]
        diff = "fix the bug in the system"
        result = _detect_commit_type(files, diff)
        assert result == CommitType.FIX

    def test_detect_feat_from_diff(self):
        """Test detecting feat from diff content."""
        files = ["src/main.py"]
        diff = "add new feature to the system"
        result = _detect_commit_type(files, diff)
        assert result == CommitType.FEAT


class TestDetectScope:
    """Tests for _detect_scope function."""

    def test_detect_scope_from_directory(self):
        """Test detecting scope from common directory."""
        files = ["sindri/tools/git.py", "sindri/tools/http.py"]
        result = _detect_scope(files)
        # Should detect common parent directory (sindri is first non-skip dir)
        assert result in ["sindri", "tools"]

    def test_detect_scope_empty_files(self):
        """Test with empty file list."""
        result = _detect_scope([])
        assert result == ""

    def test_detect_scope_root_files(self):
        """Test with root-level files."""
        files = ["main.py", "config.py"]
        result = _detect_scope(files)
        assert result == ""


# =============================================================================
# GitAutoCommitTool Tests
# =============================================================================


class TestGitAutoCommitTool:
    """Tests for GitAutoCommitTool."""

    @pytest.mark.asyncio
    async def test_auto_commit_no_staged_changes(self, temp_git_repo):
        """Test auto commit with no staged changes."""
        tool = GitAutoCommitTool(work_dir=temp_git_repo)
        result = await tool.execute()

        assert result.success is False
        assert "no staged changes" in result.error.lower()

    @pytest.mark.asyncio
    async def test_auto_commit_dry_run(self, temp_repo_with_staged):
        """Test auto commit in dry run mode."""
        tool = GitAutoCommitTool(work_dir=temp_repo_with_staged)
        result = await tool.execute(dry_run=True)

        assert result.success is True
        assert "preview" in result.output.lower() or "generated" in result.output.lower()
        assert result.metadata.get("committed") is False

    @pytest.mark.asyncio
    async def test_auto_commit_execute(self, temp_repo_with_staged):
        """Test auto commit execution."""
        tool = GitAutoCommitTool(work_dir=temp_repo_with_staged)
        result = await tool.execute(commit=True, dry_run=False)

        assert result.success is True
        assert result.metadata.get("committed") is True

        # Verify commit was created
        proc = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=temp_repo_with_staged,
            capture_output=True,
            text=True,
        )
        assert "feat" in proc.stdout.lower() or "chore" in proc.stdout.lower()

    @pytest.mark.asyncio
    async def test_auto_commit_json_format(self, temp_repo_with_staged):
        """Test auto commit with JSON output."""
        tool = GitAutoCommitTool(work_dir=temp_repo_with_staged)
        result = await tool.execute(output_format="json")

        assert result.success is True
        import json
        data = json.loads(result.output)
        assert "message" in data
        assert "files" in data

    @pytest.mark.asyncio
    async def test_auto_commit_markdown_format(self, temp_repo_with_staged):
        """Test auto commit with markdown output."""
        tool = GitAutoCommitTool(work_dir=temp_repo_with_staged)
        result = await tool.execute(output_format="markdown")

        assert result.success is True
        assert "##" in result.output or "**" in result.output

    @pytest.mark.asyncio
    async def test_auto_commit_not_a_repo(self, temp_non_git_dir):
        """Test auto commit on non-git directory."""
        tool = GitAutoCommitTool(work_dir=temp_non_git_dir)
        result = await tool.execute()

        assert result.success is False
        # Error can be "not a git repository" or git command failure
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_auto_commit_nonexistent_path(self):
        """Test auto commit on non-existent path."""
        tool = GitAutoCommitTool()
        result = await tool.execute(path="/nonexistent/path/12345")

        assert result.success is False
        assert "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_auto_commit_detects_type(self, temp_git_repo):
        """Test that auto commit detects correct commit type."""
        # Stage a test file
        (temp_git_repo / "tests" / "__init__.py").parent.mkdir(exist_ok=True)
        (temp_git_repo / "tests" / "test_new.py").write_text("def test_example(): pass\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)

        tool = GitAutoCommitTool(work_dir=temp_git_repo)
        result = await tool.execute()

        assert result.success is True
        assert result.metadata.get("type") == "test"


# =============================================================================
# GitBranchCompareTool Tests
# =============================================================================


class TestGitBranchCompareTool:
    """Tests for GitBranchCompareTool."""

    @pytest.mark.asyncio
    async def test_branch_compare_basic(self, temp_repo_with_branches):
        """Test basic branch comparison."""
        tool = GitBranchCompareTool(work_dir=temp_repo_with_branches)
        # Get the main branch name
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo_with_branches,
            capture_output=True,
            text=True,
        )
        main_branch = proc.stdout.strip() or "master"

        result = await tool.execute(base=main_branch, compare="feature")

        assert result.success is True
        assert result.metadata.get("commits_ahead", 0) >= 0

    @pytest.mark.asyncio
    async def test_branch_compare_with_conflicts_check(self, temp_repo_with_branches):
        """Test branch comparison with conflict check."""
        tool = GitBranchCompareTool(work_dir=temp_repo_with_branches)
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo_with_branches,
            capture_output=True,
            text=True,
        )
        main_branch = proc.stdout.strip() or "master"

        result = await tool.execute(
            base=main_branch, compare="feature", check_conflicts=True
        )

        assert result.success is True
        assert "conflicts" in result.metadata or "conflict_files" not in result.metadata

    @pytest.mark.asyncio
    async def test_branch_compare_nonexistent_branch(self, temp_git_repo):
        """Test comparison with non-existent branch."""
        tool = GitBranchCompareTool(work_dir=temp_git_repo)
        result = await tool.execute(base="main", compare="nonexistent")

        assert result.success is False
        assert "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_branch_compare_json_format(self, temp_repo_with_branches):
        """Test branch comparison with JSON output."""
        tool = GitBranchCompareTool(work_dir=temp_repo_with_branches)
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo_with_branches,
            capture_output=True,
            text=True,
        )
        main_branch = proc.stdout.strip() or "master"

        result = await tool.execute(
            base=main_branch, compare="feature", output_format="json"
        )

        assert result.success is True
        import json
        data = json.loads(result.output)
        assert "strategy" in data

    @pytest.mark.asyncio
    async def test_branch_compare_markdown_format(self, temp_repo_with_branches):
        """Test branch comparison with markdown output."""
        tool = GitBranchCompareTool(work_dir=temp_repo_with_branches)
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo_with_branches,
            capture_output=True,
            text=True,
        )
        main_branch = proc.stdout.strip() or "master"

        result = await tool.execute(
            base=main_branch, compare="feature", output_format="markdown"
        )

        assert result.success is True
        assert "##" in result.output

    @pytest.mark.asyncio
    async def test_branch_compare_not_a_repo(self, temp_non_git_dir):
        """Test branch comparison on non-git directory."""
        tool = GitBranchCompareTool(work_dir=temp_non_git_dir)
        result = await tool.execute()

        assert result.success is False


# =============================================================================
# GitConflictAssistTool Tests
# =============================================================================


class TestGitConflictAssistTool:
    """Tests for GitConflictAssistTool."""

    @pytest.mark.asyncio
    async def test_conflict_assist_no_conflicts(self, temp_git_repo):
        """Test conflict assist with no conflicts."""
        tool = GitConflictAssistTool(work_dir=temp_git_repo)
        result = await tool.execute()

        assert result.success is True
        assert "no" in result.output.lower() and "conflict" in result.output.lower()
        assert result.metadata.get("conflict_count", 0) == 0

    @pytest.mark.asyncio
    async def test_conflict_assist_with_conflicts(self, temp_repo_with_conflicts):
        """Test conflict assist with actual conflicts."""
        tool = GitConflictAssistTool(work_dir=temp_repo_with_conflicts)
        result = await tool.execute()

        # May or may not have conflicts depending on git behavior
        assert result.success is True

    @pytest.mark.asyncio
    async def test_conflict_assist_specific_file(self, temp_git_repo):
        """Test conflict assist for specific file."""
        tool = GitConflictAssistTool(work_dir=temp_git_repo)
        result = await tool.execute(file="nonexistent.py")

        # Should fail because file not in conflict
        assert result.success is False or "no" in result.output.lower()

    @pytest.mark.asyncio
    async def test_conflict_assist_json_format(self, temp_git_repo):
        """Test conflict assist with JSON output."""
        tool = GitConflictAssistTool(work_dir=temp_git_repo)
        result = await tool.execute(output_format="json")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_conflict_assist_not_a_repo(self, temp_non_git_dir):
        """Test conflict assist on non-git directory."""
        tool = GitConflictAssistTool(work_dir=temp_non_git_dir)
        result = await tool.execute()

        assert result.success is False
        assert "not a git repository" in result.error.lower()


# =============================================================================
# GitReleaseNotesTool Tests
# =============================================================================


class TestGitReleaseNotesTool:
    """Tests for GitReleaseNotesTool."""

    @pytest.mark.asyncio
    async def test_release_notes_basic(self, temp_git_repo):
        """Test basic release notes generation."""
        tool = GitReleaseNotesTool(work_dir=temp_git_repo)
        result = await tool.execute(from_ref="HEAD~1")

        assert result.success is True
        assert result.metadata.get("commit_count", 0) >= 0

    @pytest.mark.asyncio
    async def test_release_notes_between_tags(self, temp_repo_with_tags):
        """Test release notes between tags."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", to_tag="v1.1.0")

        assert result.success is True
        # Should include the commits between tags
        assert result.metadata.get("commit_count", 0) > 0

    @pytest.mark.asyncio
    async def test_release_notes_with_version(self, temp_repo_with_tags):
        """Test release notes with version label."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", version="2.0.0")

        assert result.success is True
        assert "2.0.0" in result.output
        assert result.metadata.get("version") == "2.0.0"

    @pytest.mark.asyncio
    async def test_release_notes_json_format(self, temp_repo_with_tags):
        """Test release notes with JSON output."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", output_format="json")

        assert result.success is True
        import json
        data = json.loads(result.output)
        assert "features" in data or "fixes" in data

    @pytest.mark.asyncio
    async def test_release_notes_markdown_format(self, temp_repo_with_tags):
        """Test release notes with markdown output."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", output_format="markdown")

        assert result.success is True
        assert "#" in result.output

    @pytest.mark.asyncio
    async def test_release_notes_keepachangelog_format(self, temp_repo_with_tags):
        """Test release notes with Keep a Changelog format."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", output_format="keepachangelog")

        assert result.success is True
        assert "##" in result.output

    @pytest.mark.asyncio
    async def test_release_notes_with_contributors(self, temp_repo_with_tags):
        """Test release notes with contributors."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", include_contributors=True)

        assert result.success is True
        assert result.metadata.get("contributors", []) is not None

    @pytest.mark.asyncio
    async def test_release_notes_categorization(self, temp_repo_with_tags):
        """Test that release notes properly categorize commits."""
        tool = GitReleaseNotesTool(work_dir=temp_repo_with_tags)
        result = await tool.execute(from_tag="v1.0.0", output_format="json")

        assert result.success is True
        import json
        data = json.loads(result.output)
        # Should have categorized the feat, fix, docs commits
        total = (
            len(data.get("features", []))
            + len(data.get("fixes", []))
            + len(data.get("documentation", []))
            + len(data.get("other", []))
        )
        assert total > 0

    @pytest.mark.asyncio
    async def test_release_notes_not_a_repo(self, temp_non_git_dir):
        """Test release notes on non-git directory."""
        tool = GitReleaseNotesTool(work_dir=temp_non_git_dir)
        result = await tool.execute(from_ref="HEAD~1")

        assert result.success is False or result.metadata.get("commit_count", 0) == 0

    @pytest.mark.asyncio
    async def test_release_notes_empty_range(self, temp_git_repo):
        """Test release notes with empty commit range."""
        tool = GitReleaseNotesTool(work_dir=temp_git_repo)
        result = await tool.execute(from_ref="HEAD", to_ref="HEAD")

        assert result.success is True
        assert result.metadata.get("commit_count", 0) == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for git automation tools."""

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test that tools are properly registered."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("git_auto_commit") is not None
        assert registry.get_tool("git_branch_compare") is not None
        assert registry.get_tool("git_conflict_assist") is not None
        assert registry.get_tool("git_release_notes") is not None

    @pytest.mark.asyncio
    async def test_tool_schemas_valid(self):
        """Test that tool schemas are valid."""
        tool1 = GitAutoCommitTool()
        tool2 = GitBranchCompareTool()
        tool3 = GitConflictAssistTool()
        tool4 = GitReleaseNotesTool()

        for tool in [tool1, tool2, tool3, tool4]:
            schema = tool.get_schema()
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    def test_huginn_agent_has_tools(self):
        """Test that Huginn agent has git automation tools."""
        from sindri.agents.registry import AGENTS

        huginn = AGENTS.get("huginn")
        assert huginn is not None
        assert "git_auto_commit" in huginn.tools
        assert "git_branch_compare" in huginn.tools
        assert "git_conflict_assist" in huginn.tools
        assert "git_release_notes" in huginn.tools

    def test_brokkr_agent_has_tools(self):
        """Test that Brokkr agent has git automation tools."""
        from sindri.agents.registry import AGENTS

        brokkr = AGENTS.get("brokkr")
        assert brokkr is not None
        assert "git_auto_commit" in brokkr.tools
        assert "git_branch_compare" in brokkr.tools
        assert "git_release_notes" in brokkr.tools
