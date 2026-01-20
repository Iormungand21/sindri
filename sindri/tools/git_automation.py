"""Git automation tools for Sindri.

Phase 14: Provides AI-powered git workflow automation tools for generating
commit messages, comparing branches, assisting with conflicts, and generating
release notes.

Tools:
- GitAutoCommitTool: Generate conventional commit messages from staged changes
- GitBranchCompareTool: Compare branches and suggest merge strategy
- GitConflictAssistTool: Help resolve merge conflicts
- GitReleaseNotesTool: Generate release notes from git history
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class CommitType(str, Enum):
    """Conventional commit types."""

    FEAT = "feat"
    FIX = "fix"
    DOCS = "docs"
    STYLE = "style"
    REFACTOR = "refactor"
    PERF = "perf"
    TEST = "test"
    BUILD = "build"
    CI = "ci"
    CHORE = "chore"
    REVERT = "revert"


class MergeStrategy(str, Enum):
    """Git merge strategies."""

    MERGE = "merge"
    REBASE = "rebase"
    SQUASH = "squash"


@dataclass
class DiffAnalysis:
    """Analysis of staged changes."""

    files_changed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    file_types: dict[str, int] = field(default_factory=dict)
    detected_type: CommitType = CommitType.CHORE
    scope: str = ""
    summary: str = ""
    breaking_change: bool = False


@dataclass
class BranchCompareResult:
    """Result of branch comparison."""

    base_branch: str = ""
    compare_branch: str = ""
    commits_ahead: int = 0
    commits_behind: int = 0
    common_ancestor: str = ""
    files_changed: list[str] = field(default_factory=list)
    conflict_files: list[str] = field(default_factory=list)
    suggested_strategy: MergeStrategy = MergeStrategy.MERGE
    strategy_rationale: str = ""
    merge_complexity: str = "simple"


@dataclass
class ConflictMarker:
    """A conflict marker in a file."""

    file: str = ""
    line_start: int = 0
    line_end: int = 0
    ours: str = ""
    theirs: str = ""
    base: str = ""


@dataclass
class ConflictResolution:
    """Suggested resolution for a conflict."""

    file: str = ""
    conflicts: list[ConflictMarker] = field(default_factory=list)
    suggested_resolution: str = ""
    resolution_type: str = "manual"
    explanation: str = ""
    confidence: str = "medium"


@dataclass
class CommitInfo:
    """Information about a commit."""

    hash: str = ""
    hash_short: str = ""
    subject: str = ""
    body: str = ""
    author: str = ""
    date: datetime = field(default_factory=datetime.now)
    commit_type: str = ""
    scope: str = ""
    breaking: bool = False


@dataclass
class ReleaseNotes:
    """Generated release notes."""

    version: str = ""
    date: str = ""
    summary: str = ""
    breaking_changes: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    performance: list[str] = field(default_factory=list)
    documentation: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    contributors: list[str] = field(default_factory=list)
    commit_count: int = 0


# File patterns for detecting commit types
FILE_TYPE_PATTERNS = {
    CommitType.TEST: [r"test[s]?/", r"_test\.py$", r"\.test\.(js|ts)$", r"spec\.(js|ts)$"],
    CommitType.DOCS: [r"README", r"\.md$", r"docs/", r"\.rst$", r"CHANGELOG"],
    CommitType.CI: [r"\.github/", r"\.gitlab-ci", r"Jenkinsfile", r"\.circleci/", r"\.travis"],
    CommitType.BUILD: [r"pyproject\.toml$", r"setup\.py$", r"package\.json$", r"Cargo\.toml$", r"go\.mod$", r"Makefile$", r"Dockerfile"],
    CommitType.STYLE: [r"\.css$", r"\.scss$", r"\.less$", r"\.eslintrc", r"\.prettierrc"],
}

# Keywords in diff content for type detection
DIFF_KEYWORDS = {
    CommitType.FIX: ["fix", "bug", "issue", "error", "crash", "resolve", "patch"],
    CommitType.FEAT: ["add", "new", "feature", "implement", "create", "introduce"],
    CommitType.REFACTOR: ["refactor", "restructure", "reorganize", "clean", "simplify"],
    CommitType.PERF: ["performance", "optimize", "speed", "cache", "faster", "memory"],
}


def _check_git() -> bool:
    """Check if git is available."""
    return shutil.which("git") is not None


async def _run_git_command(
    cmd: list[str], cwd: Path, timeout: int = 30
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )
    except asyncio.TimeoutError:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def _parse_conventional_commit(message: str) -> tuple[str, str, bool]:
    """Parse a conventional commit message.

    Returns (type, scope, is_breaking).
    """
    pattern = r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?\s*:\s*"
    match = re.match(pattern, message)

    if match:
        commit_type = match.group("type")
        scope = match.group("scope") or ""
        breaking = bool(match.group("breaking"))
        return commit_type, scope, breaking

    return "", "", False


def _detect_commit_type(files: list[str], diff_content: str) -> CommitType:
    """Detect conventional commit type from changed files and diff content."""
    # Check file patterns
    for commit_type, patterns in FILE_TYPE_PATTERNS.items():
        for pattern in patterns:
            for file in files:
                if re.search(pattern, file, re.IGNORECASE):
                    return commit_type

    # Check diff content for keywords
    diff_lower = diff_content.lower()
    keyword_scores: dict[CommitType, int] = {}

    for commit_type, keywords in DIFF_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in diff_lower)
        if score > 0:
            keyword_scores[commit_type] = score

    if keyword_scores:
        return max(keyword_scores, key=keyword_scores.get)

    # Default based on change pattern
    if any(f for f in files if f.endswith((".py", ".js", ".ts", ".go", ".rs"))):
        return CommitType.FEAT

    return CommitType.CHORE


def _detect_scope(files: list[str]) -> str:
    """Detect scope from common file path prefix."""
    if not files:
        return ""

    # Extract directory components
    dirs = []
    for f in files:
        parts = Path(f).parts
        if len(parts) > 1:
            # Skip common prefixes like src/, lib/, etc.
            skip_prefixes = {"src", "lib", "app", "pkg", "internal"}
            idx = 0
            while idx < len(parts) - 1 and parts[idx] in skip_prefixes:
                idx += 1
            if idx < len(parts) - 1:
                dirs.append(parts[idx])

    if not dirs:
        return ""

    # Find most common directory
    dir_counts: dict[str, int] = {}
    for d in dirs:
        dir_counts[d] = dir_counts.get(d, 0) + 1

    if dir_counts:
        return max(dir_counts, key=dir_counts.get)

    return ""


def _generate_commit_summary(
    files: list[str], diff_content: str, commit_type: CommitType
) -> str:
    """Generate a commit message summary from the changes."""
    # Get file count and main extension
    extensions: dict[str, int] = {}
    for f in files:
        ext = Path(f).suffix or "other"
        extensions[ext] = extensions.get(ext, 0) + 1

    main_ext = max(extensions, key=extensions.get) if extensions else ""

    # Count additions vs deletions in diff
    additions = diff_content.count("\n+") - diff_content.count("\n+++")
    deletions = diff_content.count("\n-") - diff_content.count("\n---")

    # Generate description based on type
    file_count = len(files)

    if commit_type == CommitType.TEST:
        if additions > deletions:
            return f"add tests for {file_count} file(s)"
        else:
            return f"update tests in {file_count} file(s)"

    if commit_type == CommitType.DOCS:
        return f"update documentation in {file_count} file(s)"

    if commit_type == CommitType.FIX:
        return f"fix issue in {files[0] if file_count == 1 else f'{file_count} files'}"

    if commit_type == CommitType.REFACTOR:
        return f"refactor {files[0] if file_count == 1 else f'{file_count} files'}"

    if commit_type == CommitType.FEAT:
        if file_count == 1:
            return f"add {Path(files[0]).stem} functionality"
        return f"add new functionality across {file_count} files"

    # Default
    if file_count == 1:
        return f"update {files[0]}"
    return f"update {file_count} files"


class GitAutoCommitTool(Tool):
    """Generate AI-powered commit messages from staged changes."""

    name = "git_auto_commit"
    description = """Generate conventional commit messages from staged changes.

Examples:
- git_auto_commit() - Analyze staged changes and generate commit message
- git_auto_commit(dry_run=true) - Preview message without committing
- git_auto_commit(commit=true) - Generate and execute commit
- git_auto_commit(template="angular") - Use Angular commit style
- git_auto_commit(include_body=false) - Subject line only"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository path (default: current directory)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without committing (default: true)",
            },
            "commit": {
                "type": "boolean",
                "description": "Actually create the commit (default: false)",
            },
            "template": {
                "type": "string",
                "enum": ["conventional", "angular", "emoji"],
                "description": "Commit message style (default: conventional)",
            },
            "include_body": {
                "type": "boolean",
                "description": "Include detailed body (default: true)",
            },
            "include_scope": {
                "type": "boolean",
                "description": "Auto-detect and include scope (default: true)",
            },
            "max_subject_length": {
                "type": "integer",
                "description": "Max subject line length (default: 72)",
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: text)",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize tool."""
        super().__init__(work_dir)

    async def execute(
        self,
        path: Optional[str] = None,
        dry_run: bool = True,
        commit: bool = False,
        template: str = "conventional",
        include_body: bool = True,
        include_scope: bool = True,
        max_subject_length: int = 72,
        output_format: str = "text",
        **kwargs,
    ) -> ToolResult:
        """Execute git auto commit."""
        if not _check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        log.info("git_auto_commit", path=str(repo_path), dry_run=dry_run)

        # Check for staged changes
        returncode, staged_files, stderr = await _run_git_command(
            ["git", "diff", "--cached", "--name-only"], repo_path
        )

        if returncode != 0:
            if "not a git repository" in stderr.lower():
                return ToolResult(
                    success=False, output="", error=f"Not a git repository: {repo_path}"
                )
            return ToolResult(success=False, output="", error=f"Git failed: {stderr}")

        if not staged_files:
            return ToolResult(
                success=False,
                output="",
                error="No staged changes. Use 'git add' to stage files first.",
            )

        files = [f for f in staged_files.split("\n") if f]

        # Get diff content
        _, diff_content, _ = await _run_git_command(
            ["git", "diff", "--cached"], repo_path
        )

        # Get diff stats
        _, diff_stat, _ = await _run_git_command(
            ["git", "diff", "--cached", "--stat"], repo_path
        )

        # Analyze changes
        analysis = DiffAnalysis(files_changed=files)

        # Parse stats for insertions/deletions
        stat_match = re.search(
            r"(\d+) insertion[s]?\(\+\)", diff_stat
        )
        if stat_match:
            analysis.insertions = int(stat_match.group(1))
        del_match = re.search(r"(\d+) deletion[s]?\(-\)", diff_stat)
        if del_match:
            analysis.deletions = int(del_match.group(1))

        # Detect commit type
        analysis.detected_type = _detect_commit_type(files, diff_content)

        # Detect scope
        if include_scope:
            analysis.scope = _detect_scope(files)

        # Generate summary
        analysis.summary = _generate_commit_summary(
            files, diff_content, analysis.detected_type
        )

        # Check for breaking changes
        analysis.breaking_change = "BREAKING" in diff_content.upper()

        # Build commit message
        commit_message = self._build_commit_message(
            analysis, template, include_body, include_scope, max_subject_length
        )

        # Execute commit if requested
        if commit and not dry_run:
            returncode, out, err = await _run_git_command(
                ["git", "commit", "-m", commit_message], repo_path
            )
            if returncode != 0:
                return ToolResult(
                    success=False, output="", error=f"Commit failed: {err}"
                )

            output = self._format_output(
                {
                    "status": "committed",
                    "message": commit_message,
                    "files": files,
                    "stats": {"insertions": analysis.insertions, "deletions": analysis.deletions},
                },
                output_format,
            )
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "committed": True,
                    "files_count": len(files),
                    "type": analysis.detected_type.value,
                },
            )

        # Preview only
        output = self._format_output(
            {
                "status": "preview",
                "message": commit_message,
                "files": files,
                "analysis": {
                    "type": analysis.detected_type.value,
                    "scope": analysis.scope,
                    "breaking": analysis.breaking_change,
                },
                "stats": {"insertions": analysis.insertions, "deletions": analysis.deletions},
            },
            output_format,
        )

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "committed": False,
                "files_count": len(files),
                "type": analysis.detected_type.value,
                "scope": analysis.scope,
            },
        )

    def _build_commit_message(
        self,
        analysis: DiffAnalysis,
        template: str,
        include_body: bool,
        include_scope: bool,
        max_length: int,
    ) -> str:
        """Build the commit message."""
        commit_type = analysis.detected_type.value
        scope = analysis.scope if include_scope and analysis.scope else ""
        breaking = "!" if analysis.breaking_change else ""

        # Build subject line
        if template == "emoji":
            emoji_map = {
                "feat": "\u2728",
                "fix": "\U0001F41B",
                "docs": "\U0001F4DD",
                "style": "\U0001F484",
                "refactor": "\u267B\uFE0F",
                "perf": "\u26A1",
                "test": "\U0001F9EA",
                "build": "\U0001F4E6",
                "ci": "\U0001F477",
                "chore": "\U0001F9F9",
            }
            emoji = emoji_map.get(commit_type, "\U0001F4DD")
            subject = f"{emoji} {analysis.summary}"
        else:
            if scope:
                subject = f"{commit_type}({scope}){breaking}: {analysis.summary}"
            else:
                subject = f"{commit_type}{breaking}: {analysis.summary}"

        # Truncate if needed
        if len(subject) > max_length:
            subject = subject[: max_length - 3] + "..."

        if not include_body:
            return subject

        # Build body
        body_lines = [""]

        # Add file list summary
        if len(analysis.files_changed) <= 5:
            body_lines.append("Changes:")
            for f in analysis.files_changed:
                body_lines.append(f"  - {f}")
        else:
            body_lines.append(f"Changes: {len(analysis.files_changed)} files modified")

        body_lines.append("")
        body_lines.append(
            f"Stats: +{analysis.insertions}/-{analysis.deletions} lines"
        )

        if analysis.breaking_change:
            body_lines.append("")
            body_lines.append("BREAKING CHANGE: This commit contains breaking changes.")

        return subject + "\n" + "\n".join(body_lines)

    def _format_output(self, data: dict, output_format: str) -> str:
        """Format output based on format type."""
        import json

        if output_format == "json":
            return json.dumps(data, indent=2)

        if output_format == "markdown":
            lines = []
            lines.append(f"## Commit Message ({data['status']})")
            lines.append("")
            lines.append("```")
            lines.append(data["message"])
            lines.append("```")
            lines.append("")
            lines.append(f"**Files:** {len(data['files'])}")
            if "analysis" in data:
                lines.append(f"**Type:** {data['analysis']['type']}")
                if data["analysis"]["scope"]:
                    lines.append(f"**Scope:** {data['analysis']['scope']}")
            lines.append(
                f"**Stats:** +{data['stats']['insertions']}/-{data['stats']['deletions']}"
            )
            return "\n".join(lines)

        # Text format
        lines = []
        lines.append(f"Generated Commit Message ({data['status']}):")
        lines.append("-" * 40)
        lines.append(data["message"])
        lines.append("-" * 40)
        lines.append(f"Files: {len(data['files'])}")
        lines.append(
            f"Stats: +{data['stats']['insertions']}/-{data['stats']['deletions']}"
        )
        return "\n".join(lines)


class GitBranchCompareTool(Tool):
    """Compare two branches and suggest merge strategy."""

    name = "git_branch_compare"
    description = """Compare two branches and suggest merge strategy.

Examples:
- git_branch_compare(base="main", compare="feature") - Compare branches
- git_branch_compare(base="main", compare="HEAD") - Compare current to main
- git_branch_compare(check_conflicts=true) - Also check for potential conflicts"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository path (default: current directory)",
            },
            "base": {
                "type": "string",
                "description": "Base branch (default: main)",
            },
            "compare": {
                "type": "string",
                "description": "Branch to compare (default: HEAD)",
            },
            "check_conflicts": {
                "type": "boolean",
                "description": "Simulate merge to find conflicts (default: false)",
            },
            "include_commits": {
                "type": "boolean",
                "description": "List differing commits (default: false)",
            },
            "include_files": {
                "type": "boolean",
                "description": "List changed files (default: true)",
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: text)",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize tool."""
        super().__init__(work_dir)

    async def execute(
        self,
        path: Optional[str] = None,
        base: str = "main",
        compare: str = "HEAD",
        check_conflicts: bool = False,
        include_commits: bool = False,
        include_files: bool = True,
        output_format: str = "text",
        **kwargs,
    ) -> ToolResult:
        """Execute branch comparison."""
        if not _check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        log.info("git_branch_compare", path=str(repo_path), base=base, compare=compare)

        # Check if branches exist
        for branch in [base, compare]:
            if branch != "HEAD":
                returncode, _, stderr = await _run_git_command(
                    ["git", "rev-parse", "--verify", branch], repo_path
                )
                if returncode != 0:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Branch '{branch}' does not exist",
                    )

        result = BranchCompareResult(base_branch=base, compare_branch=compare)

        # Get merge base
        returncode, merge_base, _ = await _run_git_command(
            ["git", "merge-base", base, compare], repo_path
        )
        if returncode == 0:
            result.common_ancestor = merge_base[:8]

        # Get commits ahead/behind
        returncode, ahead, _ = await _run_git_command(
            ["git", "rev-list", "--count", f"{base}..{compare}"], repo_path
        )
        if returncode == 0 and ahead.isdigit():
            result.commits_ahead = int(ahead)

        returncode, behind, _ = await _run_git_command(
            ["git", "rev-list", "--count", f"{compare}..{base}"], repo_path
        )
        if returncode == 0 and behind.isdigit():
            result.commits_behind = int(behind)

        # Get changed files
        if include_files:
            returncode, files, _ = await _run_git_command(
                ["git", "diff", "--name-only", f"{base}...{compare}"], repo_path
            )
            if returncode == 0 and files:
                result.files_changed = [f for f in files.split("\n") if f]

        # Check for conflicts
        if check_conflicts:
            result.conflict_files = await self._check_conflicts(
                repo_path, base, compare
            )

        # Determine merge strategy
        result.suggested_strategy, result.strategy_rationale = self._suggest_strategy(
            result
        )
        result.merge_complexity = self._assess_complexity(result)

        # Get commits if requested
        commits = []
        if include_commits:
            returncode, log_output, _ = await _run_git_command(
                [
                    "git",
                    "log",
                    "--oneline",
                    f"{base}..{compare}",
                    "--format=%h %s",
                ],
                repo_path,
            )
            if returncode == 0 and log_output:
                commits = [line for line in log_output.split("\n") if line]

        # Format output
        output = self._format_output(result, commits, output_format)

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "base": base,
                "compare": compare,
                "commits_ahead": result.commits_ahead,
                "commits_behind": result.commits_behind,
                "files_changed": len(result.files_changed),
                "conflicts": len(result.conflict_files),
                "strategy": result.suggested_strategy.value,
                "complexity": result.merge_complexity,
            },
        )

    async def _check_conflicts(
        self, repo_path: Path, base: str, compare: str
    ) -> list[str]:
        """Check for potential merge conflicts."""
        conflicts = []

        # Get files modified in both branches
        _, base_files, _ = await _run_git_command(
            ["git", "diff", "--name-only", f"{base}...{compare}"], repo_path
        )
        _, compare_files, _ = await _run_git_command(
            ["git", "diff", "--name-only", f"{compare}...{base}"], repo_path
        )

        if base_files and compare_files:
            base_set = set(base_files.split("\n"))
            compare_set = set(compare_files.split("\n"))
            conflicts = list(base_set & compare_set)

        return conflicts

    def _suggest_strategy(
        self, result: BranchCompareResult
    ) -> tuple[MergeStrategy, str]:
        """Suggest a merge strategy based on comparison results."""
        # If there are conflicts, suggest regular merge to preserve history
        if result.conflict_files:
            return (
                MergeStrategy.MERGE,
                f"Regular merge recommended: {len(result.conflict_files)} potential conflict(s) detected. "
                "Merge preserves full history and allows conflict resolution.",
            )

        # Few commits and no divergence -> squash for clean history
        if result.commits_ahead <= 3 and result.commits_behind == 0:
            return (
                MergeStrategy.SQUASH,
                f"Squash merge recommended: Only {result.commits_ahead} commit(s) ahead with no divergence. "
                "Squash creates a clean, single commit on the target branch.",
            )

        # Linear history possible -> rebase
        if result.commits_behind == 0:
            return (
                MergeStrategy.REBASE,
                f"Rebase recommended: {result.commits_ahead} commit(s) ahead with linear history. "
                "Rebase maintains clean linear history.",
            )

        # Complex changes -> merge
        return (
            MergeStrategy.MERGE,
            f"Regular merge recommended: {result.commits_ahead} ahead, {result.commits_behind} behind. "
            "Merge preserves the complete history of both branches.",
        )

    def _assess_complexity(self, result: BranchCompareResult) -> str:
        """Assess merge complexity."""
        if result.conflict_files:
            if len(result.conflict_files) > 5:
                return "complex"
            return "moderate"

        if result.commits_ahead > 10 or len(result.files_changed) > 20:
            return "moderate"

        return "simple"

    def _format_output(
        self, result: BranchCompareResult, commits: list[str], output_format: str
    ) -> str:
        """Format output."""
        import json

        if output_format == "json":
            data = {
                "base": result.base_branch,
                "compare": result.compare_branch,
                "common_ancestor": result.common_ancestor,
                "commits_ahead": result.commits_ahead,
                "commits_behind": result.commits_behind,
                "files_changed": result.files_changed,
                "conflict_files": result.conflict_files,
                "strategy": result.suggested_strategy.value,
                "strategy_rationale": result.strategy_rationale,
                "complexity": result.merge_complexity,
                "commits": commits,
            }
            return json.dumps(data, indent=2)

        if output_format == "markdown":
            lines = []
            lines.append(f"## Branch Comparison: {result.compare_branch} -> {result.base_branch}")
            lines.append("")
            lines.append(f"| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Commits Ahead | {result.commits_ahead} |")
            lines.append(f"| Commits Behind | {result.commits_behind} |")
            lines.append(f"| Files Changed | {len(result.files_changed)} |")
            lines.append(f"| Potential Conflicts | {len(result.conflict_files)} |")
            lines.append(f"| Complexity | {result.merge_complexity} |")
            lines.append("")
            lines.append(f"### Recommended Strategy: **{result.suggested_strategy.value}**")
            lines.append("")
            lines.append(result.strategy_rationale)
            if result.conflict_files:
                lines.append("")
                lines.append("### Potential Conflict Files")
                for f in result.conflict_files[:10]:
                    lines.append(f"- {f}")
            return "\n".join(lines)

        # Text format
        lines = []
        lines.append(f"Branch Comparison: {result.compare_branch} -> {result.base_branch}")
        lines.append("=" * 50)
        lines.append(f"Commits ahead:  {result.commits_ahead}")
        lines.append(f"Commits behind: {result.commits_behind}")
        lines.append(f"Files changed:  {len(result.files_changed)}")
        lines.append(f"Conflicts:      {len(result.conflict_files)}")
        lines.append(f"Complexity:     {result.merge_complexity}")
        lines.append("")
        lines.append(f"Recommended: {result.suggested_strategy.value.upper()}")
        lines.append(result.strategy_rationale)
        return "\n".join(lines)


class GitConflictAssistTool(Tool):
    """Help resolve merge conflicts with AI-powered suggestions."""

    name = "git_conflict_assist"
    description = """Help resolve merge conflicts with suggestions.

Examples:
- git_conflict_assist() - Analyze all conflicted files
- git_conflict_assist(file="src/main.py") - Analyze specific file
- git_conflict_assist(strategy="ours") - Prefer "ours" for ambiguous cases"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository path (default: current directory)",
            },
            "file": {
                "type": "string",
                "description": "Specific conflicted file to analyze (optional)",
            },
            "strategy": {
                "type": "string",
                "enum": ["ours", "theirs", "smart"],
                "description": "Default resolution strategy (default: smart)",
            },
            "show_diff3": {
                "type": "boolean",
                "description": "Show 3-way diff with base (default: false)",
            },
            "include_context": {
                "type": "boolean",
                "description": "Include surrounding code context (default: true)",
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown"],
                "description": "Output format (default: text)",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize tool."""
        super().__init__(work_dir)

    async def execute(
        self,
        path: Optional[str] = None,
        file: Optional[str] = None,
        strategy: str = "smart",
        show_diff3: bool = False,
        include_context: bool = True,
        output_format: str = "text",
        **kwargs,
    ) -> ToolResult:
        """Execute conflict analysis."""
        if not _check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        log.info("git_conflict_assist", path=str(repo_path), file=file)

        # Get conflicted files
        returncode, conflict_files, stderr = await _run_git_command(
            ["git", "diff", "--name-only", "--diff-filter=U"], repo_path
        )

        if returncode != 0:
            if "not a git repository" in stderr.lower():
                return ToolResult(
                    success=False, output="", error=f"Not a git repository: {repo_path}"
                )
            return ToolResult(success=False, output="", error=f"Git failed: {stderr}")

        if not conflict_files:
            return ToolResult(
                success=True,
                output="No merge conflicts detected.",
                metadata={"conflict_count": 0},
            )

        files_to_analyze = [f for f in conflict_files.split("\n") if f]

        # Filter to specific file if requested
        if file:
            if file in files_to_analyze:
                files_to_analyze = [file]
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File '{file}' is not in conflict or does not exist",
                )

        # Analyze each conflicted file
        resolutions: list[ConflictResolution] = []
        for conflict_file in files_to_analyze:
            resolution = await self._analyze_conflict(
                repo_path, conflict_file, strategy, show_diff3
            )
            resolutions.append(resolution)

        # Format output
        output = self._format_output(resolutions, output_format)

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "conflict_count": len(resolutions),
                "files": [r.file for r in resolutions],
            },
        )

    async def _analyze_conflict(
        self, repo_path: Path, conflict_file: str, strategy: str, show_diff3: bool
    ) -> ConflictResolution:
        """Analyze a single conflicted file."""
        resolution = ConflictResolution(file=conflict_file)

        try:
            file_path = repo_path / conflict_file
            if not file_path.exists():
                resolution.explanation = "File does not exist"
                return resolution

            content = file_path.read_text(encoding="utf-8", errors="replace")

            # Parse conflict markers
            conflicts = self._parse_conflicts(content)
            resolution.conflicts = conflicts

            if not conflicts:
                resolution.explanation = "No conflict markers found in file"
                return resolution

            # Analyze and suggest resolution
            resolution.suggested_resolution, resolution.resolution_type, resolution.confidence = (
                self._suggest_resolution(conflicts, strategy)
            )

            resolution.explanation = self._generate_explanation(conflicts, strategy)

        except Exception as e:
            resolution.explanation = f"Error analyzing file: {e}"

        return resolution

    def _parse_conflicts(self, content: str) -> list[ConflictMarker]:
        """Parse conflict markers from file content."""
        conflicts = []
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            if lines[i].startswith("<<<<<<<"):
                conflict = ConflictMarker(line_start=i + 1)
                ours_lines = []
                theirs_lines = []
                base_lines = []

                i += 1
                # Read "ours" section
                while i < len(lines) and not lines[i].startswith(("=======", "|||||||")):
                    ours_lines.append(lines[i])
                    i += 1

                # Check for diff3 base section
                if i < len(lines) and lines[i].startswith("|||||||"):
                    i += 1
                    while i < len(lines) and not lines[i].startswith("======="):
                        base_lines.append(lines[i])
                        i += 1

                # Skip separator
                if i < len(lines) and lines[i].startswith("======="):
                    i += 1

                # Read "theirs" section
                while i < len(lines) and not lines[i].startswith(">>>>>>>"):
                    theirs_lines.append(lines[i])
                    i += 1

                conflict.line_end = i + 1
                conflict.ours = "\n".join(ours_lines)
                conflict.theirs = "\n".join(theirs_lines)
                conflict.base = "\n".join(base_lines)

                conflicts.append(conflict)

            i += 1

        return conflicts

    def _suggest_resolution(
        self, conflicts: list[ConflictMarker], strategy: str
    ) -> tuple[str, str, str]:
        """Suggest resolution for conflicts."""
        resolutions = []
        resolution_type = "smart"
        confidence = "medium"

        for conflict in conflicts:
            if strategy == "ours":
                resolutions.append(conflict.ours)
                resolution_type = "ours"
                confidence = "high"
            elif strategy == "theirs":
                resolutions.append(conflict.theirs)
                resolution_type = "theirs"
                confidence = "high"
            else:
                # Smart resolution
                resolved, res_type, conf = self._smart_resolve(conflict)
                resolutions.append(resolved)
                resolution_type = res_type
                confidence = conf

        return "\n---\n".join(resolutions), resolution_type, confidence

    def _smart_resolve(self, conflict: ConflictMarker) -> tuple[str, str, str]:
        """Attempt smart resolution of a conflict."""
        ours = conflict.ours.strip()
        theirs = conflict.theirs.strip()

        # If one side is empty, use the other
        if not ours and theirs:
            return theirs, "theirs", "high"
        if not theirs and ours:
            return ours, "ours", "high"

        # If identical, use either
        if ours == theirs:
            return ours, "identical", "high"

        # Check if one is a superset (additions only)
        if ours in theirs:
            return theirs, "theirs", "medium"
        if theirs in ours:
            return ours, "ours", "medium"

        # Check for import statements (usually can be combined)
        if self._looks_like_imports(ours) and self._looks_like_imports(theirs):
            combined = self._combine_imports(ours, theirs)
            return combined, "combined", "medium"

        # Default: suggest manual resolution
        return f"OURS:\n{ours}\n\nTHEIRS:\n{theirs}", "manual", "low"

    def _looks_like_imports(self, code: str) -> bool:
        """Check if code looks like import statements."""
        lines = code.strip().split("\n")
        import_patterns = ["import ", "from ", "require(", "#include"]
        return all(
            any(line.strip().startswith(p) for p in import_patterns)
            or not line.strip()
            for line in lines
        )

    def _combine_imports(self, ours: str, theirs: str) -> str:
        """Combine import statements."""
        all_imports = set()
        for line in ours.split("\n") + theirs.split("\n"):
            if line.strip():
                all_imports.add(line.strip())
        return "\n".join(sorted(all_imports))

    def _generate_explanation(
        self, conflicts: list[ConflictMarker], strategy: str
    ) -> str:
        """Generate explanation for the resolution."""
        if len(conflicts) == 1:
            conflict = conflicts[0]
            ours_lines = len(conflict.ours.split("\n"))
            theirs_lines = len(conflict.theirs.split("\n"))

            return (
                f"Found 1 conflict (lines {conflict.line_start}-{conflict.line_end}). "
                f"Ours: {ours_lines} lines, Theirs: {theirs_lines} lines. "
                f"Strategy: {strategy}."
            )

        return (
            f"Found {len(conflicts)} conflicts. "
            f"Strategy: {strategy}. "
            "Review each suggested resolution before applying."
        )

    def _format_output(
        self, resolutions: list[ConflictResolution], output_format: str
    ) -> str:
        """Format output."""
        import json

        if output_format == "json":
            data = [
                {
                    "file": r.file,
                    "conflicts": len(r.conflicts),
                    "resolution_type": r.resolution_type,
                    "confidence": r.confidence,
                    "suggested_resolution": r.suggested_resolution,
                    "explanation": r.explanation,
                }
                for r in resolutions
            ]
            return json.dumps(data, indent=2)

        if output_format == "markdown":
            lines = []
            lines.append("## Merge Conflict Analysis")
            lines.append("")
            for r in resolutions:
                lines.append(f"### {r.file}")
                lines.append("")
                lines.append(f"- **Conflicts:** {len(r.conflicts)}")
                lines.append(f"- **Resolution Type:** {r.resolution_type}")
                lines.append(f"- **Confidence:** {r.confidence}")
                lines.append("")
                lines.append("**Explanation:**")
                lines.append(r.explanation)
                lines.append("")
                if r.suggested_resolution:
                    lines.append("**Suggested Resolution:**")
                    lines.append("```")
                    lines.append(r.suggested_resolution[:500])
                    if len(r.suggested_resolution) > 500:
                        lines.append("... (truncated)")
                    lines.append("```")
                lines.append("")
            return "\n".join(lines)

        # Text format
        lines = []
        lines.append("Merge Conflict Analysis")
        lines.append("=" * 50)
        for r in resolutions:
            lines.append(f"\nFile: {r.file}")
            lines.append(f"Conflicts: {len(r.conflicts)}")
            lines.append(f"Resolution: {r.resolution_type} (confidence: {r.confidence})")
            lines.append(f"Explanation: {r.explanation}")
            if r.suggested_resolution:
                lines.append("\nSuggested Resolution:")
                lines.append("-" * 30)
                lines.append(r.suggested_resolution[:300])
                if len(r.suggested_resolution) > 300:
                    lines.append("... (truncated)")
        return "\n".join(lines)


class GitReleaseNotesTool(Tool):
    """Generate release notes from git history."""

    name = "git_release_notes"
    description = """Generate release notes from git commit history.

Examples:
- git_release_notes(from_tag="v1.0.0", to_tag="v1.1.0") - Between tags
- git_release_notes(from_ref="HEAD~50") - Last 50 commits
- git_release_notes(from_tag="v1.0.0", to_tag="HEAD") - Since last release
- git_release_notes(version="2.0.0") - Label with version number"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository path (default: current directory)",
            },
            "from_ref": {
                "type": "string",
                "description": "Starting reference (tag, commit, or HEAD~n)",
            },
            "to_ref": {
                "type": "string",
                "description": "Ending reference (default: HEAD)",
            },
            "from_tag": {
                "type": "string",
                "description": "Starting tag (alternative to from_ref)",
            },
            "to_tag": {
                "type": "string",
                "description": "Ending tag (alternative to to_ref)",
            },
            "version": {
                "type": "string",
                "description": "Version label for release notes",
            },
            "include_contributors": {
                "type": "boolean",
                "description": "Include list of contributors (default: true)",
            },
            "include_commit_links": {
                "type": "boolean",
                "description": "Include commit hashes (default: true)",
            },
            "group_by_scope": {
                "type": "boolean",
                "description": "Group by conventional commit scope (default: false)",
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "json", "markdown", "keepachangelog"],
                "description": "Output format (default: markdown)",
            },
        },
        "required": [],
    }

    def __init__(self, work_dir: Optional[Path] = None):
        """Initialize tool."""
        super().__init__(work_dir)

    async def execute(
        self,
        path: Optional[str] = None,
        from_ref: Optional[str] = None,
        to_ref: str = "HEAD",
        from_tag: Optional[str] = None,
        to_tag: Optional[str] = None,
        version: Optional[str] = None,
        include_contributors: bool = True,
        include_commit_links: bool = True,
        group_by_scope: bool = False,
        output_format: str = "markdown",
        **kwargs,
    ) -> ToolResult:
        """Execute release notes generation."""
        if not _check_git():
            return ToolResult(
                success=False, output="", error="Git is not installed or not in PATH"
            )

        repo_path = self._resolve_path(path or ".")
        if not repo_path.exists():
            return ToolResult(
                success=False, output="", error=f"Path does not exist: {repo_path}"
            )

        # Determine references
        start_ref = from_tag or from_ref
        end_ref = to_tag or to_ref

        if not start_ref:
            # Default to last tag or HEAD~20
            returncode, last_tag, _ = await _run_git_command(
                ["git", "describe", "--tags", "--abbrev=0", "HEAD^"], repo_path
            )
            if returncode == 0 and last_tag:
                start_ref = last_tag
            else:
                start_ref = "HEAD~20"

        log.info(
            "git_release_notes",
            path=str(repo_path),
            from_ref=start_ref,
            to_ref=end_ref,
        )

        # Get commits
        commits = await self._get_commits(repo_path, start_ref, end_ref)

        if not commits:
            return ToolResult(
                success=True,
                output="No commits found in the specified range.",
                metadata={"commit_count": 0},
            )

        # Build release notes
        notes = ReleaseNotes(
            version=version or "Unreleased",
            date=datetime.now().strftime("%Y-%m-%d"),
            commit_count=len(commits),
        )

        # Categorize commits
        for commit in commits:
            commit_type, scope, breaking = _parse_conventional_commit(commit.subject)
            commit.commit_type = commit_type
            commit.scope = scope
            commit.breaking = breaking

            # Check for breaking change in body
            if "BREAKING CHANGE" in commit.body.upper():
                commit.breaking = True

            entry = commit.subject
            if include_commit_links:
                entry = f"{commit.subject} ({commit.hash_short})"

            if commit.breaking:
                notes.breaking_changes.append(entry)
            elif commit_type == "feat":
                notes.features.append(entry)
            elif commit_type == "fix":
                notes.fixes.append(entry)
            elif commit_type == "perf":
                notes.performance.append(entry)
            elif commit_type == "docs":
                notes.documentation.append(entry)
            else:
                notes.other.append(entry)

        # Get contributors
        if include_contributors:
            notes.contributors = await self._get_contributors(
                repo_path, start_ref, end_ref
            )

        # Generate summary
        notes.summary = self._generate_summary(notes)

        # Format output
        output = self._format_output(notes, output_format, group_by_scope, commits)

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "version": notes.version,
                "commit_count": notes.commit_count,
                "features": len(notes.features),
                "fixes": len(notes.fixes),
                "breaking_changes": len(notes.breaking_changes),
                "contributors": len(notes.contributors),
            },
        )

    async def _get_commits(
        self, repo_path: Path, from_ref: str, to_ref: str
    ) -> list[CommitInfo]:
        """Get commits in range."""
        commits = []

        returncode, output, stderr = await _run_git_command(
            [
                "git",
                "log",
                "--format=%H|%h|%s|%b|%an|%aI",
                "--no-merges",
                f"{from_ref}..{to_ref}",
            ],
            repo_path,
        )

        if returncode != 0:
            log.warning("git_log_failed", error=stderr)
            return commits

        for line in output.split("\n"):
            if not line or "|" not in line:
                continue

            parts = line.split("|", 5)
            if len(parts) < 6:
                continue

            hash_full, hash_short, subject, body, author, date_str = parts

            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                date = datetime.now()

            commits.append(
                CommitInfo(
                    hash=hash_full,
                    hash_short=hash_short,
                    subject=subject,
                    body=body,
                    author=author,
                    date=date,
                )
            )

        return commits

    async def _get_contributors(
        self, repo_path: Path, from_ref: str, to_ref: str
    ) -> list[str]:
        """Get contributors in range."""
        returncode, output, _ = await _run_git_command(
            ["git", "shortlog", "-sne", f"{from_ref}..{to_ref}"], repo_path
        )

        if returncode != 0:
            return []

        contributors = []
        for line in output.split("\n"):
            if line.strip():
                # Format: "  42\tName <email>"
                match = re.match(r"\s*\d+\t(.+)", line)
                if match:
                    contributors.append(match.group(1))

        return contributors

    def _generate_summary(self, notes: ReleaseNotes) -> str:
        """Generate release summary."""
        parts = []

        if notes.breaking_changes:
            parts.append(f"{len(notes.breaking_changes)} breaking change(s)")
        if notes.features:
            parts.append(f"{len(notes.features)} new feature(s)")
        if notes.fixes:
            parts.append(f"{len(notes.fixes)} bug fix(es)")
        if notes.performance:
            parts.append(f"{len(notes.performance)} performance improvement(s)")

        if parts:
            return f"This release includes {', '.join(parts)}."
        return f"This release includes {notes.commit_count} commit(s)."

    def _format_output(
        self,
        notes: ReleaseNotes,
        output_format: str,
        group_by_scope: bool,
        commits: list[CommitInfo],
    ) -> str:
        """Format release notes."""
        import json

        if output_format == "json":
            data = {
                "version": notes.version,
                "date": notes.date,
                "summary": notes.summary,
                "breaking_changes": notes.breaking_changes,
                "features": notes.features,
                "fixes": notes.fixes,
                "performance": notes.performance,
                "documentation": notes.documentation,
                "other": notes.other,
                "contributors": notes.contributors,
                "commit_count": notes.commit_count,
            }
            return json.dumps(data, indent=2)

        if output_format == "keepachangelog":
            return self._format_keepachangelog(notes)

        if output_format == "markdown":
            return self._format_markdown(notes)

        # Text format
        return self._format_text(notes)

    def _format_markdown(self, notes: ReleaseNotes) -> str:
        """Format as markdown."""
        lines = []
        lines.append(f"# {notes.version}")
        lines.append("")
        lines.append(f"**Release Date:** {notes.date}")
        lines.append("")
        lines.append(notes.summary)
        lines.append("")

        if notes.breaking_changes:
            lines.append("## Breaking Changes")
            lines.append("")
            for item in notes.breaking_changes:
                lines.append(f"- {item}")
            lines.append("")

        if notes.features:
            lines.append("## Features")
            lines.append("")
            for item in notes.features:
                lines.append(f"- {item}")
            lines.append("")

        if notes.fixes:
            lines.append("## Bug Fixes")
            lines.append("")
            for item in notes.fixes:
                lines.append(f"- {item}")
            lines.append("")

        if notes.performance:
            lines.append("## Performance")
            lines.append("")
            for item in notes.performance:
                lines.append(f"- {item}")
            lines.append("")

        if notes.documentation:
            lines.append("## Documentation")
            lines.append("")
            for item in notes.documentation:
                lines.append(f"- {item}")
            lines.append("")

        if notes.other:
            lines.append("## Other Changes")
            lines.append("")
            for item in notes.other[:10]:  # Limit to 10
                lines.append(f"- {item}")
            if len(notes.other) > 10:
                lines.append(f"- ... and {len(notes.other) - 10} more")
            lines.append("")

        if notes.contributors:
            lines.append("## Contributors")
            lines.append("")
            for contrib in notes.contributors:
                lines.append(f"- {contrib}")
            lines.append("")

        return "\n".join(lines)

    def _format_keepachangelog(self, notes: ReleaseNotes) -> str:
        """Format according to Keep a Changelog spec."""
        lines = []
        lines.append(f"## [{notes.version}] - {notes.date}")
        lines.append("")

        if notes.breaking_changes:
            lines.append("### Changed")
            lines.append("")
            for item in notes.breaking_changes:
                lines.append(f"- **BREAKING:** {item}")
            lines.append("")

        if notes.features:
            lines.append("### Added")
            lines.append("")
            for item in notes.features:
                lines.append(f"- {item}")
            lines.append("")

        if notes.fixes:
            lines.append("### Fixed")
            lines.append("")
            for item in notes.fixes:
                lines.append(f"- {item}")
            lines.append("")

        if notes.performance or notes.other:
            lines.append("### Changed")
            lines.append("")
            for item in notes.performance + notes.other:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)

    def _format_text(self, notes: ReleaseNotes) -> str:
        """Format as plain text."""
        lines = []
        lines.append(f"Release Notes: {notes.version}")
        lines.append("=" * 50)
        lines.append(f"Date: {notes.date}")
        lines.append("")
        lines.append(notes.summary)
        lines.append("")

        if notes.breaking_changes:
            lines.append("BREAKING CHANGES:")
            for item in notes.breaking_changes:
                lines.append(f"  * {item}")
            lines.append("")

        if notes.features:
            lines.append("NEW FEATURES:")
            for item in notes.features:
                lines.append(f"  * {item}")
            lines.append("")

        if notes.fixes:
            lines.append("BUG FIXES:")
            for item in notes.fixes:
                lines.append(f"  * {item}")
            lines.append("")

        lines.append(f"Total commits: {notes.commit_count}")
        lines.append(f"Contributors: {len(notes.contributors)}")

        return "\n".join(lines)
