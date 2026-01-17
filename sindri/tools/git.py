"""Git integration tools for Sindri."""

import asyncio
import shutil
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class GitStatusTool(Tool):
    """Get the current git repository status.

    Shows modified, staged, untracked files and branch information.
    """

    name = "git_status"
    description = """Get git repository status showing modified, staged, and untracked files.

Examples:
- git_status() - Get status of current directory
- git_status(path="/path/to/repo") - Get status of specific repository
- git_status(short=true) - Get compact status output"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to git repository (default: current directory)",
            },
            "short": {
                "type": "boolean",
                "description": "Use short format output (default: false)",
            },
            "show_branch": {
                "type": "boolean",
                "description": "Show branch info in short format (default: true)",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize git status tool."""
        super().__init__(work_dir)
        self._git_available: Optional[bool] = None

    def _check_git(self) -> bool:
        """Check if git is available."""
        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
        return self._git_available

    async def execute(
        self,
        path: Optional[str] = None,
        short: bool = False,
        show_branch: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Execute git status command.

        Args:
            path: Path to git repository
            short: Use short format output
            show_branch: Show branch info in short format
        """
        if not self._check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        # Resolve repository path
        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        # Build command
        cmd = ["git", "-C", str(repo_path), "status"]
        if short:
            cmd.append("-s")
            if show_branch:
                cmd.append("-b")

        log.info("git_status_execute", path=str(repo_path), short=short)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                # Check if not a git repository
                if "not a git repository" in errors.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Not a git repository: {repo_path}",
                    )
                return ToolResult(
                    success=False, output="", error=f"Git status failed: {errors}"
                )

            # Parse status for metadata
            metadata = self._parse_status(output, short)

            return ToolResult(
                success=True,
                output=output if output else "Working tree clean",
                metadata=metadata,
            )

        except Exception as e:
            log.error("git_status_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Git status failed: {str(e)}"
            )

    def _parse_status(self, output: str, short: bool) -> dict:
        """Parse git status output for metadata."""
        metadata = {
            "modified": 0,
            "staged": 0,
            "untracked": 0,
            "deleted": 0,
            "renamed": 0,
            "clean": False,
        }

        if not output or "nothing to commit" in output.lower():
            metadata["clean"] = True
            return metadata

        lines = output.strip().split("\n")

        if short:
            for line in lines:
                if not line or line.startswith("##"):
                    continue
                if len(line) >= 2:
                    index_status = line[0]
                    worktree_status = line[1]

                    # Staged changes (index)
                    if index_status in "MADRC":
                        metadata["staged"] += 1
                    if index_status == "D":
                        metadata["deleted"] += 1
                    if index_status == "R":
                        metadata["renamed"] += 1

                    # Unstaged changes (worktree)
                    if worktree_status == "M":
                        metadata["modified"] += 1
                    if worktree_status == "D":
                        metadata["deleted"] += 1

                    # Untracked
                    if line.startswith("??"):
                        metadata["untracked"] += 1
        else:
            # Long format parsing
            for line in lines:
                lower_line = line.lower()
                if "modified:" in lower_line:
                    metadata["modified"] += 1
                elif "deleted:" in lower_line:
                    metadata["deleted"] += 1
                elif "new file:" in lower_line:
                    metadata["staged"] += 1
                elif "renamed:" in lower_line:
                    metadata["renamed"] += 1
            # Count untracked files section
            if "untracked files:" in output.lower():
                untracked_section = output.lower().split("untracked files:")[1]
                metadata["untracked"] = len(
                    [
                        line
                        for line in untracked_section.split("\n")
                        if line.strip()
                        and not line.strip().startswith("(")
                        and not line.strip().startswith("nothing")
                    ]
                )

        return metadata


class GitDiffTool(Tool):
    """Show changes between commits, commit and working tree, etc.

    Displays file differences in unified diff format.
    """

    name = "git_diff"
    description = """Show git diff of changes in the repository.

Examples:
- git_diff() - Show unstaged changes
- git_diff(staged=true) - Show staged changes
- git_diff(file_path="src/main.py") - Show changes in specific file
- git_diff(commit="HEAD~1") - Show changes since previous commit
- git_diff(commit1="main", commit2="feature") - Compare branches"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to git repository (default: current directory)",
            },
            "file_path": {
                "type": "string",
                "description": "Specific file to diff (optional)",
            },
            "staged": {
                "type": "boolean",
                "description": "Show staged changes (--cached) instead of unstaged",
            },
            "commit": {
                "type": "string",
                "description": "Compare working tree with this commit (e.g., HEAD~1, abc123)",
            },
            "commit1": {
                "type": "string",
                "description": "First commit/branch for comparison",
            },
            "commit2": {
                "type": "string",
                "description": "Second commit/branch for comparison",
            },
            "stat": {
                "type": "boolean",
                "description": "Show diffstat instead of full diff",
            },
            "name_only": {
                "type": "boolean",
                "description": "Show only names of changed files",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of context lines (default: 3)",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize git diff tool."""
        super().__init__(work_dir)
        self._git_available: Optional[bool] = None

    def _check_git(self) -> bool:
        """Check if git is available."""
        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
        return self._git_available

    async def execute(
        self,
        path: Optional[str] = None,
        file_path: Optional[str] = None,
        staged: bool = False,
        commit: Optional[str] = None,
        commit1: Optional[str] = None,
        commit2: Optional[str] = None,
        stat: bool = False,
        name_only: bool = False,
        context_lines: int = 3,
        **kwargs,
    ) -> ToolResult:
        """Execute git diff command.

        Args:
            path: Path to git repository
            file_path: Specific file to diff
            staged: Show staged changes
            commit: Compare with this commit
            commit1: First commit for comparison
            commit2: Second commit for comparison
            stat: Show diffstat
            name_only: Show only file names
            context_lines: Number of context lines
        """
        if not self._check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        # Resolve repository path
        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        # Build command
        cmd = ["git", "-C", str(repo_path), "diff"]

        # Output format options
        if stat:
            cmd.append("--stat")
        elif name_only:
            cmd.append("--name-only")
        else:
            # -U must have number directly attached (e.g., -U3)
            cmd.append(f"-U{context_lines}")

        # Staged changes
        if staged:
            cmd.append("--cached")

        # Commit comparison
        if commit1 and commit2:
            cmd.extend([commit1, commit2])
        elif commit:
            cmd.append(commit)

        # Specific file
        if file_path:
            cmd.extend(["--", file_path])

        log.info(
            "git_diff_execute",
            path=str(repo_path),
            staged=staged,
            commit=commit,
            file_path=file_path,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                if "not a git repository" in errors.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Not a git repository: {repo_path}",
                    )
                return ToolResult(
                    success=False, output="", error=f"Git diff failed: {errors}"
                )

            # Parse diff for metadata
            metadata = self._parse_diff(output, stat, name_only)

            return ToolResult(
                success=True,
                output=output if output else "No changes",
                metadata=metadata,
            )

        except Exception as e:
            log.error("git_diff_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Git diff failed: {str(e)}"
            )

    def _parse_diff(self, output: str, stat: bool, name_only: bool) -> dict:
        """Parse git diff output for metadata."""
        metadata = {
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "has_changes": bool(output.strip()),
        }

        if not output.strip():
            return metadata

        lines = output.strip().split("\n")

        if name_only:
            metadata["files_changed"] = len([ln for ln in lines if ln.strip()])
            metadata["changed_files"] = [ln.strip() for ln in lines if ln.strip()]
        elif stat:
            # Parse stat line like "3 files changed, 10 insertions(+), 5 deletions(-)"
            for line in lines:
                if "file" in line.lower() and "changed" in line.lower():
                    parts = line.split(",")
                    for part in parts:
                        part = part.strip().lower()
                        if "file" in part:
                            try:
                                metadata["files_changed"] = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "insertion" in part:
                            try:
                                metadata["insertions"] = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
                        elif "deletion" in part:
                            try:
                                metadata["deletions"] = int(part.split()[0])
                            except (ValueError, IndexError):
                                pass
        else:
            # Full diff - count +/- lines
            for line in lines:
                if line.startswith("diff --git"):
                    metadata["files_changed"] += 1
                elif line.startswith("+") and not line.startswith("+++"):
                    metadata["insertions"] += 1
                elif line.startswith("-") and not line.startswith("---"):
                    metadata["deletions"] += 1

        return metadata


class GitLogTool(Tool):
    """Show commit history.

    Displays commit logs with various formatting options.
    """

    name = "git_log"
    description = """Show git commit history.

Examples:
- git_log() - Show recent commits (default: 10)
- git_log(limit=5) - Show last 5 commits
- git_log(file_path="src/main.py") - Show commits for specific file
- git_log(oneline=true) - Compact one-line format
- git_log(author="john") - Filter by author
- git_log(since="2024-01-01") - Commits since date
- git_log(grep="fix") - Filter by commit message"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to git repository (default: current directory)",
            },
            "file_path": {
                "type": "string",
                "description": "Show commits for specific file",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of commits to show (default: 10)",
            },
            "oneline": {
                "type": "boolean",
                "description": "Use one-line format (hash + subject)",
            },
            "stat": {
                "type": "boolean",
                "description": "Include diffstat with each commit",
            },
            "author": {
                "type": "string",
                "description": "Filter by author name or email",
            },
            "since": {
                "type": "string",
                "description": "Show commits after date (e.g., '2024-01-01', '1 week ago')",
            },
            "until": {"type": "string", "description": "Show commits before date"},
            "grep": {
                "type": "string",
                "description": "Filter commits by message pattern",
            },
            "branch": {
                "type": "string",
                "description": "Show commits from specific branch",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize git log tool."""
        super().__init__(work_dir)
        self._git_available: Optional[bool] = None

    def _check_git(self) -> bool:
        """Check if git is available."""
        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
        return self._git_available

    async def execute(
        self,
        path: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 10,
        oneline: bool = False,
        stat: bool = False,
        author: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        grep: Optional[str] = None,
        branch: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Execute git log command.

        Args:
            path: Path to git repository
            file_path: Show commits for specific file
            limit: Maximum commits to show
            oneline: Use one-line format
            stat: Include diffstat
            author: Filter by author
            since: Show commits after date
            until: Show commits before date
            grep: Filter by message pattern
            branch: Show commits from branch
        """
        if not self._check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        # Resolve repository path
        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        # Build command
        cmd = ["git", "-C", str(repo_path), "log"]

        # Limit
        cmd.extend(["-n", str(limit)])

        # Format options
        if oneline:
            cmd.append("--oneline")
        else:
            # Use a readable format
            cmd.extend(["--format=%h %s (%an, %ar)"])

        if stat:
            cmd.append("--stat")

        # Filters
        if author:
            cmd.extend(["--author", author])

        if since:
            cmd.extend(["--since", since])

        if until:
            cmd.extend(["--until", until])

        if grep:
            cmd.extend(["--grep", grep])

        # Branch
        if branch:
            cmd.append(branch)

        # Specific file
        if file_path:
            cmd.extend(["--", file_path])

        log.info(
            "git_log_execute", path=str(repo_path), limit=limit, file_path=file_path
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                if "not a git repository" in errors.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Not a git repository: {repo_path}",
                    )
                if "does not have any commits" in errors.lower():
                    return ToolResult(
                        success=True,
                        output="No commits yet",
                        metadata={"commit_count": 0},
                    )
                return ToolResult(
                    success=False, output="", error=f"Git log failed: {errors}"
                )

            # Count commits
            commit_count = (
                len([line for line in output.split("\n") if line.strip()])
                if output
                else 0
            )

            return ToolResult(
                success=True,
                output=output if output else "No commits found",
                metadata={"commit_count": commit_count},
            )

        except Exception as e:
            log.error("git_log_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Git log failed: {str(e)}"
            )


class GitBranchTool(Tool):
    """List, create, or manage git branches.

    Shows branch information and current branch.
    """

    name = "git_branch"
    description = """List git branches or get current branch.

Examples:
- git_branch() - List all local branches
- git_branch(all=true) - List local and remote branches
- git_branch(current=true) - Show only current branch name"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to git repository (default: current directory)",
            },
            "all": {
                "type": "boolean",
                "description": "Show remote branches too (default: false)",
            },
            "current": {
                "type": "boolean",
                "description": "Show only current branch name",
            },
            "verbose": {
                "type": "boolean",
                "description": "Show commit info with branches",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize git branch tool."""
        super().__init__(work_dir)
        self._git_available: Optional[bool] = None

    def _check_git(self) -> bool:
        """Check if git is available."""
        if self._git_available is None:
            self._git_available = shutil.which("git") is not None
        return self._git_available

    async def execute(
        self,
        path: Optional[str] = None,
        all: bool = False,
        current: bool = False,
        verbose: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Execute git branch command.

        Args:
            path: Path to git repository
            all: Show remote branches
            current: Show only current branch
            verbose: Show verbose output
        """
        if not self._check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        # Resolve repository path
        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        # Build command
        if current:
            cmd = ["git", "-C", str(repo_path), "branch", "--show-current"]
        else:
            cmd = ["git", "-C", str(repo_path), "branch"]
            if all:
                cmd.append("-a")
            if verbose:
                cmd.append("-v")

        log.info("git_branch_execute", path=str(repo_path), current=current)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                if "not a git repository" in errors.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Not a git repository: {repo_path}",
                    )
                return ToolResult(
                    success=False, output="", error=f"Git branch failed: {errors}"
                )

            # Parse branches
            metadata = {"current_branch": None, "branch_count": 0}
            if output:
                branches = output.split("\n")
                metadata["branch_count"] = len(branches)
                for branch in branches:
                    if branch.strip().startswith("*"):
                        metadata["current_branch"] = branch.strip()[2:].split()[0]
                        break
                if current:
                    metadata["current_branch"] = output.strip()

            return ToolResult(
                success=True,
                output=output if output else "No branches",
                metadata=metadata,
            )

        except Exception as e:
            log.error("git_branch_failed", error=str(e))
            return ToolResult(
                success=False, output="", error=f"Git branch failed: {str(e)}"
            )
