"""Tests for git integration tools."""

import pytest
from pathlib import Path
import tempfile
import shutil
import subprocess

from sindri.tools.git import GitStatusTool, GitDiffTool, GitLogTool, GitBranchTool


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
        ["git", "commit", "-m", "Initial commit"], cwd=temp, capture_output=True
    )

    # Create more files
    (temp / "main.py").write_text('print("Hello")\n')
    subprocess.run(["git", "add", "main.py"], cwd=temp, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add main.py"], cwd=temp, capture_output=True
    )

    yield temp

    # Cleanup
    shutil.rmtree(temp)


@pytest.fixture
def temp_git_repo_with_changes(temp_git_repo):
    """Git repo with uncommitted changes."""
    # Modified file
    (temp_git_repo / "main.py").write_text('print("Hello World")\n')

    # Staged file
    (temp_git_repo / "utils.py").write_text("def helper(): pass\n")
    subprocess.run(["git", "add", "utils.py"], cwd=temp_git_repo, capture_output=True)

    # Untracked file
    (temp_git_repo / "untracked.txt").write_text("Not tracked\n")

    return temp_git_repo


@pytest.fixture
def temp_non_git_dir():
    """Create a temporary directory that is NOT a git repo."""
    temp = Path(tempfile.mkdtemp())
    (temp / "file.txt").write_text("Some content")
    yield temp
    shutil.rmtree(temp)


# =============================================================================
# GitStatusTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_status_clean_repo(temp_git_repo):
    """Test git status on a clean repository."""
    tool = GitStatusTool(work_dir=temp_git_repo)
    result = await tool.execute()

    assert result.success is True
    assert (
        "clean" in result.output.lower() or "nothing to commit" in result.output.lower()
    )
    assert result.metadata.get("clean") is True


@pytest.mark.asyncio
async def test_git_status_with_changes(temp_git_repo_with_changes):
    """Test git status with various changes."""
    tool = GitStatusTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute()

    assert result.success is True
    # Should show modified, staged, and untracked
    assert "main.py" in result.output or "modified" in result.output.lower()
    assert result.metadata.get("clean") is False


@pytest.mark.asyncio
async def test_git_status_short_format(temp_git_repo_with_changes):
    """Test git status with short format."""
    tool = GitStatusTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(short=True)

    assert result.success is True
    # Short format uses status codes like M, A, ??
    output = result.output
    assert any(c in output for c in ["M", "A", "??", "modified", "staged"])


@pytest.mark.asyncio
async def test_git_status_not_a_repo(temp_non_git_dir):
    """Test git status on non-git directory."""
    tool = GitStatusTool(work_dir=temp_non_git_dir)
    result = await tool.execute()

    assert result.success is False
    assert "not a git repository" in result.error.lower()


@pytest.mark.asyncio
async def test_git_status_nonexistent_path():
    """Test git status on non-existent path."""
    tool = GitStatusTool()
    result = await tool.execute(path="/nonexistent/path/12345")

    assert result.success is False
    assert "does not exist" in result.error.lower()


@pytest.mark.asyncio
async def test_git_status_with_path(temp_git_repo):
    """Test git status with explicit path."""
    tool = GitStatusTool()
    result = await tool.execute(path=str(temp_git_repo))

    assert result.success is True


# =============================================================================
# GitDiffTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_diff_no_changes(temp_git_repo):
    """Test git diff with no changes."""
    tool = GitDiffTool(work_dir=temp_git_repo)
    result = await tool.execute()

    assert result.success is True
    assert "No changes" in result.output or result.output == ""
    assert result.metadata.get("has_changes") is False


@pytest.mark.asyncio
async def test_git_diff_unstaged_changes(temp_git_repo_with_changes):
    """Test git diff with unstaged changes."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute()

    assert result.success is True
    # Should show diff for main.py modification
    assert "main.py" in result.output or "Hello World" in result.output
    assert result.metadata.get("has_changes") is True


@pytest.mark.asyncio
async def test_git_diff_staged_changes(temp_git_repo_with_changes):
    """Test git diff with staged changes."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(staged=True)

    assert result.success is True
    # Should show staged utils.py
    assert "utils.py" in result.output or "helper" in result.output


@pytest.mark.asyncio
async def test_git_diff_specific_file(temp_git_repo_with_changes):
    """Test git diff for specific file."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(file_path="main.py")

    assert result.success is True
    if result.metadata.get("has_changes"):
        assert "Hello" in result.output


@pytest.mark.asyncio
async def test_git_diff_stat(temp_git_repo_with_changes):
    """Test git diff with stat output."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(stat=True)

    assert result.success is True
    # Stat format shows file summary


@pytest.mark.asyncio
async def test_git_diff_name_only(temp_git_repo_with_changes):
    """Test git diff with name-only output."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(name_only=True)

    assert result.success is True
    if result.metadata.get("has_changes"):
        assert "main.py" in result.output


@pytest.mark.asyncio
async def test_git_diff_commit_comparison(temp_git_repo):
    """Test git diff comparing with previous commit."""
    tool = GitDiffTool(work_dir=temp_git_repo)
    result = await tool.execute(commit="HEAD~1")

    assert result.success is True
    # Should show diff between HEAD~1 and working tree
    assert "main.py" in result.output


@pytest.mark.asyncio
async def test_git_diff_context_lines(temp_git_repo_with_changes):
    """Test git diff with custom context lines."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(context_lines=5)

    assert result.success is True


@pytest.mark.asyncio
async def test_git_diff_not_a_repo(temp_non_git_dir):
    """Test git diff on non-git directory."""
    tool = GitDiffTool(work_dir=temp_non_git_dir)
    result = await tool.execute()

    assert result.success is False
    assert "not a git repository" in result.error.lower()


# =============================================================================
# GitLogTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_log_basic(temp_git_repo):
    """Test basic git log."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute()

    assert result.success is True
    # Should show commits
    assert "Initial commit" in result.output or "main.py" in result.output
    assert result.metadata.get("commit_count", 0) >= 2


@pytest.mark.asyncio
async def test_git_log_limit(temp_git_repo):
    """Test git log with limit."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(limit=1)

    assert result.success is True
    assert result.metadata.get("commit_count") == 1


@pytest.mark.asyncio
async def test_git_log_oneline(temp_git_repo):
    """Test git log with oneline format."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(oneline=True)

    assert result.success is True
    # Oneline format is more compact


@pytest.mark.asyncio
async def test_git_log_with_stat(temp_git_repo):
    """Test git log with stat."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(stat=True, limit=2)

    assert result.success is True


@pytest.mark.asyncio
async def test_git_log_for_file(temp_git_repo):
    """Test git log for specific file."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(file_path="main.py")

    assert result.success is True
    # Should only show commits that touched main.py
    assert result.metadata.get("commit_count", 0) >= 1


@pytest.mark.asyncio
async def test_git_log_author_filter(temp_git_repo):
    """Test git log with author filter."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(author="Test User")

    assert result.success is True
    assert result.metadata.get("commit_count", 0) >= 2


@pytest.mark.asyncio
async def test_git_log_grep_filter(temp_git_repo):
    """Test git log with grep filter."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(grep="Initial")

    assert result.success is True
    # Should find "Initial commit"


@pytest.mark.asyncio
async def test_git_log_not_a_repo(temp_non_git_dir):
    """Test git log on non-git directory."""
    tool = GitLogTool(work_dir=temp_non_git_dir)
    result = await tool.execute()

    assert result.success is False
    assert "not a git repository" in result.error.lower()


@pytest.mark.asyncio
async def test_git_log_nonexistent_path():
    """Test git log on non-existent path."""
    tool = GitLogTool()
    result = await tool.execute(path="/nonexistent/path/12345")

    assert result.success is False
    assert "does not exist" in result.error.lower()


# =============================================================================
# GitBranchTool Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_branch_list(temp_git_repo):
    """Test listing branches."""
    tool = GitBranchTool(work_dir=temp_git_repo)
    result = await tool.execute()

    assert result.success is True
    # Should show at least master/main branch
    assert "master" in result.output or "main" in result.output
    assert result.metadata.get("branch_count", 0) >= 1


@pytest.mark.asyncio
async def test_git_branch_current(temp_git_repo):
    """Test getting current branch."""
    tool = GitBranchTool(work_dir=temp_git_repo)
    result = await tool.execute(current=True)

    assert result.success is True
    # Should return just the branch name
    assert result.output.strip() in ["master", "main"]
    assert result.metadata.get("current_branch") in ["master", "main"]


@pytest.mark.asyncio
async def test_git_branch_verbose(temp_git_repo):
    """Test verbose branch listing."""
    tool = GitBranchTool(work_dir=temp_git_repo)
    result = await tool.execute(verbose=True)

    assert result.success is True
    # Verbose shows commit hash and message


@pytest.mark.asyncio
async def test_git_branch_not_a_repo(temp_non_git_dir):
    """Test git branch on non-git directory."""
    tool = GitBranchTool(work_dir=temp_non_git_dir)
    result = await tool.execute()

    assert result.success is False
    assert "not a git repository" in result.error.lower()


@pytest.mark.asyncio
async def test_git_branch_with_multiple_branches(temp_git_repo):
    """Test branch listing with multiple branches."""
    # Create a new branch
    subprocess.run(["git", "branch", "feature"], cwd=temp_git_repo, capture_output=True)

    tool = GitBranchTool(work_dir=temp_git_repo)
    result = await tool.execute()

    assert result.success is True
    assert "feature" in result.output
    assert result.metadata.get("branch_count", 0) >= 2


# =============================================================================
# Tool Registry Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_tools_in_registry():
    """Test that git tools are properly registered."""
    from sindri.tools.registry import ToolRegistry

    registry = ToolRegistry.default()

    assert registry.get_tool("git_status") is not None
    assert registry.get_tool("git_diff") is not None
    assert registry.get_tool("git_log") is not None
    assert registry.get_tool("git_branch") is not None


@pytest.mark.asyncio
async def test_git_status_schema():
    """Test GitStatusTool schema format."""
    tool = GitStatusTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "git_status"
    assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_git_diff_schema():
    """Test GitDiffTool schema format."""
    tool = GitDiffTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "git_diff"
    assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_git_log_schema():
    """Test GitLogTool schema format."""
    tool = GitLogTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "git_log"
    assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_git_branch_schema():
    """Test GitBranchTool schema format."""
    tool = GitBranchTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "git_branch"
    assert "parameters" in schema["function"]


# =============================================================================
# Agent Integration Tests
# =============================================================================


def test_agents_have_git_tools():
    """Test that appropriate agents have git tools."""
    from sindri.agents.registry import AGENTS

    # Brokkr should have all git tools
    assert "git_status" in AGENTS["brokkr"].tools
    assert "git_diff" in AGENTS["brokkr"].tools
    assert "git_log" in AGENTS["brokkr"].tools
    assert "git_branch" in AGENTS["brokkr"].tools

    # Huginn should have main git tools
    assert "git_status" in AGENTS["huginn"].tools
    assert "git_diff" in AGENTS["huginn"].tools
    assert "git_log" in AGENTS["huginn"].tools

    # Mimir should have review-relevant git tools
    assert "git_diff" in AGENTS["mimir"].tools
    assert "git_log" in AGENTS["mimir"].tools

    # Odin should have planning-relevant git tools
    assert "git_status" in AGENTS["odin"].tools
    assert "git_log" in AGENTS["odin"].tools


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.asyncio
async def test_git_diff_branch_comparison(temp_git_repo):
    """Test git diff comparing two branches."""
    # Create a feature branch with changes
    subprocess.run(
        ["git", "checkout", "-b", "feature"], cwd=temp_git_repo, capture_output=True
    )
    (temp_git_repo / "feature.py").write_text("# Feature code\n")
    subprocess.run(["git", "add", "feature.py"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add feature"], cwd=temp_git_repo, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "master"],
        cwd=temp_git_repo,
        capture_output=True,
        check=False,  # May fail if default branch is main
    )
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=temp_git_repo,
        capture_output=True,
        check=False,  # May fail if default branch is master
    )

    tool = GitDiffTool(work_dir=temp_git_repo)
    # Compare current branch with feature
    result = await tool.execute(commit="feature")

    assert result.success is True


@pytest.mark.asyncio
async def test_git_log_since_date(temp_git_repo):
    """Test git log with since date filter."""
    tool = GitLogTool(work_dir=temp_git_repo)
    result = await tool.execute(since="1 year ago")

    assert result.success is True
    # Should find recent commits
    assert result.metadata.get("commit_count", 0) >= 2


@pytest.mark.asyncio
async def test_git_tools_work_dir_resolution(temp_git_repo):
    """Test that work_dir is properly used."""
    # Create subdirectory
    subdir = temp_git_repo / "subdir"
    subdir.mkdir()

    tool = GitStatusTool(work_dir=subdir)
    result = await tool.execute()

    # Should work - git finds repo in parent
    assert result.success is True


@pytest.mark.asyncio
async def test_git_status_metadata_parsing(temp_git_repo_with_changes):
    """Test that status metadata is correctly parsed."""
    tool = GitStatusTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute(short=True)

    assert result.success is True
    metadata = result.metadata

    # Should have parsed metadata
    assert "modified" in metadata
    assert "staged" in metadata
    assert "untracked" in metadata
    assert metadata["clean"] is False


@pytest.mark.asyncio
async def test_git_diff_metadata_parsing(temp_git_repo_with_changes):
    """Test that diff metadata is correctly parsed."""
    tool = GitDiffTool(work_dir=temp_git_repo_with_changes)
    result = await tool.execute()

    assert result.success is True
    metadata = result.metadata

    assert "files_changed" in metadata
    assert "insertions" in metadata
    assert "deletions" in metadata
    assert metadata["has_changes"] is True
