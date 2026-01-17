"""Tool registry for Sindri."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult
from sindri.tools.filesystem import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ListDirectoryTool,
    ReadTreeTool,
)
from sindri.tools.shell import ShellTool
from sindri.tools.planning import ProposePlanTool
from sindri.tools.search import SearchCodeTool, FindSymbolTool
from sindri.tools.git import GitStatusTool, GitDiffTool, GitLogTool, GitBranchTool
from sindri.tools.http import HttpRequestTool, HttpGetTool, HttpPostTool
from sindri.tools.testing import RunTestsTool, CheckSyntaxTool
from sindri.tools.formatting import FormatCodeTool, LintCodeTool
from sindri.tools.refactoring import (
    RenameSymbolTool,
    ExtractFunctionTool,
    InlineVariableTool,
    MoveFileTool,
    BatchRenameTool,
    SplitFileTool,
    MergeFilesTool,
)
from sindri.tools.sql import ExecuteQueryTool, DescribeSchemaTool, ExplainQueryTool
from sindri.tools.cicd import GenerateWorkflowTool, ValidateWorkflowTool
from sindri.tools.dependency_scanner import (
    ScanDependenciesTool,
    GenerateSBOMTool,
    CheckOutdatedTool,
)
from sindri.tools.docker import (
    GenerateDockerfileTool,
    GenerateDockerComposeTool,
    ValidateDockerfileTool,
)
from sindri.tools.api_spec import GenerateApiSpecTool, ValidateApiSpecTool
from sindri.tools.ast_refactoring import (
    ASTParserTool,
    FindReferencesTool,
    ASTSymbolInfoTool,
    ASTRefactorRenameTool,
)
from sindri.core.errors import (
    ErrorCategory,
    classify_error,
    classify_error_message,
)

log = structlog.get_logger()


@dataclass
class ToolRetryConfig:
    """Configuration for tool execution retry behavior."""

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 5.0
    exponential_base: float = 2.0


class ToolRegistry:
    """Manages available tools with retry support."""

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        retry_config: Optional[ToolRetryConfig] = None,
    ):
        """Initialize registry with optional working directory and retry config.

        Args:
            work_dir: Working directory for file operations. None = current directory.
            retry_config: Retry configuration for transient failures.
        """
        self._tools: dict[str, Tool] = {}
        self.work_dir = work_dir
        self.retry_config = retry_config or ToolRetryConfig()

    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool
        log.info(
            "tool_registered",
            name=tool.name,
            work_dir=str(self.work_dir) if self.work_dir else None,
        )

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """Get all tool schemas for Ollama."""
        return [tool.get_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict | str) -> ToolResult:
        """Execute a tool by name with automatic retry for transient errors.

        Args:
            name: Tool name to execute
            arguments: Tool arguments (dict or JSON string)

        Returns:
            ToolResult with execution result and error classification
        """
        tool = self.get_tool(name)
        if not tool:
            log.error("tool_not_found", name=name)
            return ToolResult(
                success=False,
                output="",
                error=f"Tool not found: {name}",
                error_category=ErrorCategory.FATAL,
                suggestion="Check tool name spelling or available tools",
            )

        # Parse arguments if they're a JSON string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as e:
                log.error("tool_args_parse_error", name=name, error=str(e))
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to parse tool arguments: {str(e)}",
                    error_category=ErrorCategory.FATAL,
                    suggestion="Check JSON syntax in arguments",
                )

        log.info("tool_execute", name=name, args=arguments)

        # Execute with retry for transient errors
        last_result: Optional[ToolResult] = None
        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                result = await tool.execute(**arguments)

                if result.success:
                    # Success - return with retry count
                    result.retries_attempted = attempt
                    return result

                # Tool returned failure - classify and maybe retry
                classified = classify_error_message(result.error or "Unknown error")
                result.error_category = classified.category
                result.suggestion = classified.suggestion
                result.retries_attempted = attempt

                if not classified.retryable:
                    # Fatal error - don't retry
                    return result

                # Transient error - retry if not exhausted
                last_result = result
                if attempt < self.retry_config.max_attempts - 1:
                    delay = min(
                        self.retry_config.base_delay
                        * (self.retry_config.exponential_base**attempt),
                        self.retry_config.max_delay,
                    )
                    log.warning(
                        "tool_retry",
                        tool=name,
                        attempt=attempt + 1,
                        max_attempts=self.retry_config.max_attempts,
                        delay=delay,
                        error=result.error,
                    )
                    await asyncio.sleep(delay)

            except Exception as e:
                # Exception during execution - classify
                classified = classify_error(e)
                last_exception = e

                if not classified.retryable:
                    # Fatal exception - return immediately
                    log.error(
                        "tool_execution_error",
                        name=name,
                        error=str(e),
                        category=classified.category.value,
                    )
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Tool execution failed: {str(e)}",
                        error_category=classified.category,
                        suggestion=classified.suggestion,
                        retries_attempted=attempt,
                    )

                # Transient exception - retry if not exhausted
                if attempt < self.retry_config.max_attempts - 1:
                    delay = min(
                        self.retry_config.base_delay
                        * (self.retry_config.exponential_base**attempt),
                        self.retry_config.max_delay,
                    )
                    log.warning(
                        "tool_retry_exception",
                        tool=name,
                        attempt=attempt + 1,
                        max_attempts=self.retry_config.max_attempts,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        # Exhausted retries
        if last_result:
            log.error(
                "tool_retry_exhausted",
                tool=name,
                attempts=self.retry_config.max_attempts,
                error=last_result.error,
            )
            return last_result
        elif last_exception:
            classified = classify_error(last_exception)
            log.error(
                "tool_retry_exhausted",
                tool=name,
                attempts=self.retry_config.max_attempts,
                error=str(last_exception),
            )
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution failed after {self.retry_config.max_attempts} attempts: {str(last_exception)}",
                error_category=classified.category,
                suggestion=classified.suggestion,
                retries_attempted=self.retry_config.max_attempts - 1,
            )
        else:
            # Should never happen
            return ToolResult(
                success=False,
                output="",
                error="Tool execution failed unexpectedly",
                error_category=ErrorCategory.FATAL,
                retries_attempted=self.retry_config.max_attempts - 1,
            )

    @classmethod
    def default(cls, work_dir: Optional[Path] = None) -> "ToolRegistry":
        """Create a registry with default tools.

        Args:
            work_dir: Working directory for file operations. None = current directory.

        Returns:
            ToolRegistry with default filesystem and shell tools registered.
        """
        registry = cls(work_dir=work_dir)
        registry.register(ReadFileTool(work_dir=work_dir))
        registry.register(WriteFileTool(work_dir=work_dir))
        registry.register(EditFileTool(work_dir=work_dir))
        registry.register(ListDirectoryTool(work_dir=work_dir))
        registry.register(ReadTreeTool(work_dir=work_dir))
        registry.register(ShellTool(work_dir=work_dir))
        registry.register(ProposePlanTool(work_dir=work_dir))
        registry.register(SearchCodeTool(work_dir=work_dir))
        registry.register(FindSymbolTool(work_dir=work_dir))
        registry.register(GitStatusTool(work_dir=work_dir))
        registry.register(GitDiffTool(work_dir=work_dir))
        registry.register(GitLogTool(work_dir=work_dir))
        registry.register(GitBranchTool(work_dir=work_dir))
        registry.register(HttpRequestTool(work_dir=work_dir))
        registry.register(HttpGetTool(work_dir=work_dir))
        registry.register(HttpPostTool(work_dir=work_dir))
        registry.register(RunTestsTool(work_dir=work_dir))
        registry.register(CheckSyntaxTool(work_dir=work_dir))
        registry.register(FormatCodeTool(work_dir=work_dir))
        registry.register(LintCodeTool(work_dir=work_dir))
        registry.register(RenameSymbolTool(work_dir=work_dir))
        registry.register(ExtractFunctionTool(work_dir=work_dir))
        registry.register(InlineVariableTool(work_dir=work_dir))
        registry.register(MoveFileTool(work_dir=work_dir))
        registry.register(BatchRenameTool(work_dir=work_dir))
        registry.register(SplitFileTool(work_dir=work_dir))
        registry.register(MergeFilesTool(work_dir=work_dir))
        registry.register(ExecuteQueryTool(work_dir=work_dir))
        registry.register(DescribeSchemaTool(work_dir=work_dir))
        registry.register(ExplainQueryTool(work_dir=work_dir))
        registry.register(GenerateWorkflowTool(work_dir=work_dir))
        registry.register(ValidateWorkflowTool(work_dir=work_dir))
        registry.register(ScanDependenciesTool(work_dir=work_dir))
        registry.register(GenerateSBOMTool(work_dir=work_dir))
        registry.register(CheckOutdatedTool(work_dir=work_dir))
        registry.register(GenerateDockerfileTool(work_dir=work_dir))
        registry.register(GenerateDockerComposeTool(work_dir=work_dir))
        registry.register(ValidateDockerfileTool(work_dir=work_dir))
        registry.register(GenerateApiSpecTool(work_dir=work_dir))
        registry.register(ValidateApiSpecTool(work_dir=work_dir))
        # AST-based refactoring tools (requires tree-sitter)
        registry.register(ASTParserTool(work_dir=work_dir))
        registry.register(FindReferencesTool(work_dir=work_dir))
        registry.register(ASTSymbolInfoTool(work_dir=work_dir))
        registry.register(ASTRefactorRenameTool(work_dir=work_dir))
        return registry
