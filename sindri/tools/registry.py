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
from sindri.tools.sql import (
    ExecuteQueryTool,
    DescribeSchemaTool,
    ExplainQueryTool,
    SqlGenerateTool,
    DbSeedTool,
)
from sindri.tools.sql_advanced import (
    SqlOptimizeTool,
    DbSchemaDiffTool,
    DbAnalyzeIndexesTool,
    DbBackupTool,
    DbVisualizeSchemaTool,
)
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
    # Docker runtime tools
    DockerPsTool,
    DockerImagesTool,
    DockerLogsTool,
    DockerBuildTool,
    DockerRunTool,
    DockerStopTool,
    DockerRmTool,
    DockerComposeUpTool,
    DockerComposeDownTool,
)
from sindri.tools.aws import (
    AwsS3ListTool,
    AwsS3UploadTool,
    AwsS3DownloadTool,
    AwsLogsQueryTool,
    AwsEc2ListTool,
    AwsLambdaInvokeTool,
)
from sindri.tools.kubernetes import (
    K8sApplyTool,
    K8sGetPodsTool,
    K8sLogsTool,
    K8sGetServicesTool,
    K8sDescribeTool,
    K8sDeleteTool,
)
from sindri.tools.api_spec import GenerateApiSpecTool, ValidateApiSpecTool
from sindri.tools.ast_refactoring import (
    ASTParserTool,
    FindReferencesTool,
    ASTSymbolInfoTool,
    ASTRefactorRenameTool,
)
from sindri.tools.iac import (
    GenerateTerraformTool,
    GeneratePulumiTool,
    ValidateTerraformTool,
)
from sindri.tools.migrations import (
    GenerateMigrationTool,
    MigrationStatusTool,
    RunMigrationsTool,
    RollbackMigrationTool,
    ValidateMigrationsTool,
)
from sindri.tools.diagrams import (
    GenerateMermaidTool,
    GeneratePlantUMLTool,
    GenerateD2Tool,
    DiagramFromCodeTool,
    GenerateSequenceDiagramTool,
    GenerateERDiagramTool,
)
from sindri.tools.latex import (
    GenerateLatexTool,
    FormatEquationsTool,
    GenerateTikzTool,
    ManageBibliographyTool,
    CreateBeamerTool,
    LatexToPdfTool,
)
from sindri.tools.openscad import (
    GenerateSCADTool,
    RenderPreviewTool,
    ExportSTLTool,
    ValidateSCADTool,
    ParametrizeTool,
    OptimizePrintabilityTool,
)
from sindri.tools.dataviz import (
    AnalyzeDataTool,
    SuggestVisualizationTool,
    GenerateD3Tool,
    GenerateMatplotlibTool,
    GeneratePlotlyTool,
    CreateDashboardTool,
    ExportInteractiveTool,
)
from sindri.tools.text_regex import (
    RegexGenerateTool,
    RegexExplainTool,
    RegexTestTool,
    TextTransformTool,
    TextExtractTool,
)
from sindri.tools.compression import (
    ArchiveCreateTool,
    ArchiveExtractTool,
    ArchiveListTool,
    CompressFileTool,
    DecompressFileTool,
)
from sindri.tools.crypto import (
    HashFileTool,
    HashTextTool,
    EncodeBase64Tool,
    EncodeUrlTool,
    JwtDecodeTool,
    JwtGenerateTool,
    UuidGenerateTool,
    EncryptFileTool,
    DecryptFileTool,
)
from sindri.tools.system import (
    ProcessListTool,
    ProcessKillTool,
    SystemInfoTool,
    DiskUsageTool,
    MemoryUsageTool,
    EnvGetTool,
)
from sindri.tools.images import (
    ImageResizeTool,
    ImageCropTool,
    ImageConvertTool,
    ImageRotateTool,
    ImageThumbnailTool,
    ImageInfoTool,
)
from sindri.tools.documents import (
    PdfExtractTextTool,
    PdfToMarkdownTool,
    PdfMergeTool,
    PdfSplitTool,
    OcrImageTool,
    SpreadsheetReadTool,
    SpreadsheetWriteTool,
)
from sindri.tools.vision_documents import (
    DocumentDescribeTool,
    DocumentExtractStructuredTool,
    DocumentSummarizeTool,
)
from sindri.tools.network import (
    HttpTraceTool,
    DnsLookupTool,
    CurlGenerateTool,
    SslAnalyzeTool,
    PortCheckTool,
    PingHostTool,
)
from sindri.tools.media import (
    AudioTranscribeTool,
    VideoExtractAudioTool,
    VideoTranscribeTool,
    VideoGenerateSubtitlesTool,
    AudioConvertTool,
    VideoConvertTool,
    VideoTrimTool,
    VideoThumbnailTool,
    VideoConcatTool,
    TtsGenerateTool,
    VideoAddSubtitlesTool,
)
from sindri.tools.profiling import (
    ProfilePythonTool,
    ProfileTimeTool,
    MemoryAnalyzeTool,
    DetectMemoryLeaksTool,
    BenchmarkFunctionTool,
    FlameGraphTool,
    ComplexityAnalyzeTool,
)
from sindri.tools.browser import (
    BrowserNavigateTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserScreenshotTool,
    BrowserExtractTool,
    BrowserExecuteJsTool,
    BrowserPdfTool,
    BrowserCloseTool,
)
from sindri.tools.scraping import WebScrapeTool
from sindri.tools.services import (
    ServiceStatusTool,
    ServiceStartTool,
    ServiceStopTool,
    ServiceRestartTool,
    ServiceEnableTool,
    ServiceDisableTool,
    ServiceLogsTool,
    ServiceListTool,
)
from sindri.tools.self_management import (
    SindriVersionTool,
    SindriUpdateTool,
    SindriConfigGetTool,
    SindriConfigSetTool,
    OllamaListTool,
    OllamaPullTool,
    OllamaRemoveTool,
    OllamaStatusTool,
    VramStatusTool,
)
from sindri.tools.scheduling import (
    CronListTool,
    CronAddTool,
    CronRemoveTool,
    TimerListTool,
    TimerCreateTool,
    TimerRemoveTool,
    AtScheduleTool,
    AtListTool,
    AtRemoveTool,
)
from sindri.tools.bash_tools import (
    BashGenerateTool,
    BashExplainTool,
    BashValidateTool,
    SystemdGenerateTool,
    BashLintTool,
)
from sindri.tools.math import (
    MathEvaluateTool,
    MathSolveTool,
    StatsAnalyzeTool,
    PlotGenerateTool,
    UnitConvertTool,
    MatrixOperationsTool,
)
from sindri.tools.music import (
    GenerateMIDITool,
    GenerateABCTool,
    HarmonizeTool,
    ArrangeTool,
    AnalyzeMusicTool,
    ExportAudioTool,
)
from sindri.tools.game_level import (
    GenerateTilemapTool,
    GenerateDungeonTool,
    BalanceDifficultyTool,
    GenerateDialogueTool,
    GenerateItemStatsTool,
    GenerateGDScriptTool,
    GenerateUnityScriptTool,
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
        registry.register(SqlGenerateTool(work_dir=work_dir))
        registry.register(DbSeedTool(work_dir=work_dir))
        # Advanced SQL tools (Fafnir agent)
        registry.register(SqlOptimizeTool(work_dir=work_dir))
        registry.register(DbSchemaDiffTool(work_dir=work_dir))
        registry.register(DbAnalyzeIndexesTool(work_dir=work_dir))
        registry.register(DbBackupTool(work_dir=work_dir))
        registry.register(DbVisualizeSchemaTool(work_dir=work_dir))
        registry.register(GenerateWorkflowTool(work_dir=work_dir))
        registry.register(ValidateWorkflowTool(work_dir=work_dir))
        registry.register(ScanDependenciesTool(work_dir=work_dir))
        registry.register(GenerateSBOMTool(work_dir=work_dir))
        registry.register(CheckOutdatedTool(work_dir=work_dir))
        registry.register(GenerateDockerfileTool(work_dir=work_dir))
        registry.register(GenerateDockerComposeTool(work_dir=work_dir))
        registry.register(ValidateDockerfileTool(work_dir=work_dir))
        # Docker runtime tools
        registry.register(DockerPsTool(work_dir=work_dir))
        registry.register(DockerImagesTool(work_dir=work_dir))
        registry.register(DockerLogsTool(work_dir=work_dir))
        registry.register(DockerBuildTool(work_dir=work_dir))
        registry.register(DockerRunTool(work_dir=work_dir))
        registry.register(DockerStopTool(work_dir=work_dir))
        registry.register(DockerRmTool(work_dir=work_dir))
        registry.register(DockerComposeUpTool(work_dir=work_dir))
        registry.register(DockerComposeDownTool(work_dir=work_dir))
        registry.register(GenerateApiSpecTool(work_dir=work_dir))
        registry.register(ValidateApiSpecTool(work_dir=work_dir))
        # AST-based refactoring tools (requires tree-sitter)
        registry.register(ASTParserTool(work_dir=work_dir))
        registry.register(FindReferencesTool(work_dir=work_dir))
        registry.register(ASTSymbolInfoTool(work_dir=work_dir))
        registry.register(ASTRefactorRenameTool(work_dir=work_dir))
        # Infrastructure as Code tools
        registry.register(GenerateTerraformTool(work_dir=work_dir))
        registry.register(GeneratePulumiTool(work_dir=work_dir))
        registry.register(ValidateTerraformTool(work_dir=work_dir))
        # Database Migration tools
        registry.register(GenerateMigrationTool(work_dir=work_dir))
        registry.register(MigrationStatusTool(work_dir=work_dir))
        registry.register(RunMigrationsTool(work_dir=work_dir))
        registry.register(RollbackMigrationTool(work_dir=work_dir))
        registry.register(ValidateMigrationsTool(work_dir=work_dir))
        # Diagram generation tools
        registry.register(GenerateMermaidTool(work_dir=work_dir))
        registry.register(GeneratePlantUMLTool(work_dir=work_dir))
        registry.register(GenerateD2Tool(work_dir=work_dir))
        registry.register(DiagramFromCodeTool(work_dir=work_dir))
        registry.register(GenerateSequenceDiagramTool(work_dir=work_dir))
        registry.register(GenerateERDiagramTool(work_dir=work_dir))
        # LaTeX generation tools
        registry.register(GenerateLatexTool(work_dir=work_dir))
        registry.register(FormatEquationsTool(work_dir=work_dir))
        registry.register(GenerateTikzTool(work_dir=work_dir))
        registry.register(ManageBibliographyTool(work_dir=work_dir))
        registry.register(CreateBeamerTool(work_dir=work_dir))
        registry.register(LatexToPdfTool(work_dir=work_dir))
        # OpenSCAD 3D modeling tools
        registry.register(GenerateSCADTool(work_dir=work_dir))
        registry.register(RenderPreviewTool(work_dir=work_dir))
        registry.register(ExportSTLTool(work_dir=work_dir))
        registry.register(ValidateSCADTool(work_dir=work_dir))
        registry.register(ParametrizeTool(work_dir=work_dir))
        registry.register(OptimizePrintabilityTool(work_dir=work_dir))
        # Data visualization tools
        registry.register(AnalyzeDataTool(work_dir=work_dir))
        registry.register(SuggestVisualizationTool(work_dir=work_dir))
        registry.register(GenerateD3Tool(work_dir=work_dir))
        registry.register(GenerateMatplotlibTool(work_dir=work_dir))
        registry.register(GeneratePlotlyTool(work_dir=work_dir))
        registry.register(CreateDashboardTool(work_dir=work_dir))
        registry.register(ExportInteractiveTool(work_dir=work_dir))
        # Text and regex tools
        registry.register(RegexGenerateTool(work_dir=work_dir))
        registry.register(RegexExplainTool(work_dir=work_dir))
        registry.register(RegexTestTool(work_dir=work_dir))
        registry.register(TextTransformTool(work_dir=work_dir))
        registry.register(TextExtractTool(work_dir=work_dir))
        # Compression and archive tools
        registry.register(ArchiveCreateTool(work_dir=work_dir))
        registry.register(ArchiveExtractTool(work_dir=work_dir))
        registry.register(ArchiveListTool(work_dir=work_dir))
        registry.register(CompressFileTool(work_dir=work_dir))
        registry.register(DecompressFileTool(work_dir=work_dir))
        # Crypto and encoding tools
        registry.register(HashFileTool(work_dir=work_dir))
        registry.register(HashTextTool(work_dir=work_dir))
        registry.register(EncodeBase64Tool(work_dir=work_dir))
        registry.register(EncodeUrlTool(work_dir=work_dir))
        registry.register(JwtDecodeTool(work_dir=work_dir))
        registry.register(JwtGenerateTool(work_dir=work_dir))
        registry.register(UuidGenerateTool(work_dir=work_dir))
        registry.register(EncryptFileTool(work_dir=work_dir))
        registry.register(DecryptFileTool(work_dir=work_dir))
        # System and process tools
        registry.register(ProcessListTool(work_dir=work_dir))
        registry.register(ProcessKillTool(work_dir=work_dir))
        registry.register(SystemInfoTool(work_dir=work_dir))
        registry.register(DiskUsageTool(work_dir=work_dir))
        registry.register(MemoryUsageTool(work_dir=work_dir))
        registry.register(EnvGetTool(work_dir=work_dir))
        # Image manipulation tools
        registry.register(ImageResizeTool(work_dir=work_dir))
        registry.register(ImageCropTool(work_dir=work_dir))
        registry.register(ImageConvertTool(work_dir=work_dir))
        registry.register(ImageRotateTool(work_dir=work_dir))
        registry.register(ImageThumbnailTool(work_dir=work_dir))
        registry.register(ImageInfoTool(work_dir=work_dir))
        # Document processing tools
        registry.register(PdfExtractTextTool(work_dir=work_dir))
        registry.register(PdfToMarkdownTool(work_dir=work_dir))
        registry.register(PdfMergeTool(work_dir=work_dir))
        registry.register(PdfSplitTool(work_dir=work_dir))
        registry.register(OcrImageTool(work_dir=work_dir))
        registry.register(SpreadsheetReadTool(work_dir=work_dir))
        registry.register(SpreadsheetWriteTool(work_dir=work_dir))
        # Vision-based document tools
        registry.register(DocumentDescribeTool(work_dir=work_dir))
        registry.register(DocumentExtractStructuredTool(work_dir=work_dir))
        registry.register(DocumentSummarizeTool(work_dir=work_dir))
        # Network and HTTP diagnostic tools
        registry.register(HttpTraceTool(work_dir=work_dir))
        registry.register(DnsLookupTool(work_dir=work_dir))
        registry.register(CurlGenerateTool(work_dir=work_dir))
        registry.register(SslAnalyzeTool(work_dir=work_dir))
        registry.register(PortCheckTool(work_dir=work_dir))
        registry.register(PingHostTool(work_dir=work_dir))
        # Video and audio processing tools
        registry.register(AudioTranscribeTool(work_dir=work_dir))
        registry.register(VideoExtractAudioTool(work_dir=work_dir))
        registry.register(VideoTranscribeTool(work_dir=work_dir))
        registry.register(VideoGenerateSubtitlesTool(work_dir=work_dir))
        registry.register(AudioConvertTool(work_dir=work_dir))
        registry.register(VideoConvertTool(work_dir=work_dir))
        registry.register(VideoTrimTool(work_dir=work_dir))
        registry.register(VideoThumbnailTool(work_dir=work_dir))
        registry.register(VideoConcatTool(work_dir=work_dir))
        registry.register(TtsGenerateTool(work_dir=work_dir))
        registry.register(VideoAddSubtitlesTool(work_dir=work_dir))
        # Profiling tools
        registry.register(ProfilePythonTool(work_dir=work_dir))
        registry.register(ProfileTimeTool(work_dir=work_dir))
        registry.register(MemoryAnalyzeTool(work_dir=work_dir))
        registry.register(DetectMemoryLeaksTool(work_dir=work_dir))
        registry.register(BenchmarkFunctionTool(work_dir=work_dir))
        registry.register(FlameGraphTool(work_dir=work_dir))
        registry.register(ComplexityAnalyzeTool(work_dir=work_dir))
        # Browser automation tools
        registry.register(BrowserNavigateTool(work_dir=work_dir))
        registry.register(BrowserClickTool(work_dir=work_dir))
        registry.register(BrowserTypeTool(work_dir=work_dir))
        registry.register(BrowserScreenshotTool(work_dir=work_dir))
        registry.register(BrowserExtractTool(work_dir=work_dir))
        registry.register(BrowserExecuteJsTool(work_dir=work_dir))
        registry.register(BrowserPdfTool(work_dir=work_dir))
        registry.register(BrowserCloseTool(work_dir=work_dir))
        # Web scraping tool
        registry.register(WebScrapeTool(work_dir=work_dir))
        # Service management tools
        registry.register(ServiceStatusTool(work_dir=work_dir))
        registry.register(ServiceStartTool(work_dir=work_dir))
        registry.register(ServiceStopTool(work_dir=work_dir))
        registry.register(ServiceRestartTool(work_dir=work_dir))
        registry.register(ServiceEnableTool(work_dir=work_dir))
        registry.register(ServiceDisableTool(work_dir=work_dir))
        registry.register(ServiceLogsTool(work_dir=work_dir))
        registry.register(ServiceListTool(work_dir=work_dir))
        # Self-management tools
        registry.register(SindriVersionTool(work_dir=work_dir))
        registry.register(SindriUpdateTool(work_dir=work_dir))
        registry.register(SindriConfigGetTool(work_dir=work_dir))
        registry.register(SindriConfigSetTool(work_dir=work_dir))
        registry.register(OllamaListTool(work_dir=work_dir))
        registry.register(OllamaPullTool(work_dir=work_dir))
        registry.register(OllamaRemoveTool(work_dir=work_dir))
        registry.register(OllamaStatusTool(work_dir=work_dir))
        registry.register(VramStatusTool(work_dir=work_dir))
        # Scheduling tools
        registry.register(CronListTool(work_dir=work_dir))
        registry.register(CronAddTool(work_dir=work_dir))
        registry.register(CronRemoveTool(work_dir=work_dir))
        registry.register(TimerListTool(work_dir=work_dir))
        registry.register(TimerCreateTool(work_dir=work_dir))
        registry.register(TimerRemoveTool(work_dir=work_dir))
        registry.register(AtScheduleTool(work_dir=work_dir))
        registry.register(AtListTool(work_dir=work_dir))
        registry.register(AtRemoveTool(work_dir=work_dir))
        # Bash scripting tools
        registry.register(BashGenerateTool(work_dir=work_dir))
        registry.register(BashExplainTool(work_dir=work_dir))
        registry.register(BashValidateTool(work_dir=work_dir))
        registry.register(SystemdGenerateTool(work_dir=work_dir))
        registry.register(BashLintTool(work_dir=work_dir))
        # Math and scientific tools (Phase 12)
        registry.register(MathEvaluateTool(work_dir=work_dir))
        registry.register(MathSolveTool(work_dir=work_dir))
        registry.register(StatsAnalyzeTool(work_dir=work_dir))
        registry.register(PlotGenerateTool(work_dir=work_dir))
        registry.register(UnitConvertTool(work_dir=work_dir))
        registry.register(MatrixOperationsTool(work_dir=work_dir))
        # AWS tools (Phase 12)
        registry.register(AwsS3ListTool(work_dir=work_dir))
        registry.register(AwsS3UploadTool(work_dir=work_dir))
        registry.register(AwsS3DownloadTool(work_dir=work_dir))
        registry.register(AwsLogsQueryTool(work_dir=work_dir))
        registry.register(AwsEc2ListTool(work_dir=work_dir))
        registry.register(AwsLambdaInvokeTool(work_dir=work_dir))
        # Kubernetes tools (Phase 12)
        registry.register(K8sApplyTool(work_dir=work_dir))
        registry.register(K8sGetPodsTool(work_dir=work_dir))
        registry.register(K8sLogsTool(work_dir=work_dir))
        registry.register(K8sGetServicesTool(work_dir=work_dir))
        registry.register(K8sDescribeTool(work_dir=work_dir))
        registry.register(K8sDeleteTool(work_dir=work_dir))
        # Music composition tools (Phase 11 - Bragi agent)
        registry.register(GenerateMIDITool(work_dir=work_dir))
        registry.register(GenerateABCTool(work_dir=work_dir))
        registry.register(HarmonizeTool(work_dir=work_dir))
        registry.register(ArrangeTool(work_dir=work_dir))
        registry.register(AnalyzeMusicTool(work_dir=work_dir))
        registry.register(ExportAudioTool(work_dir=work_dir))
        # Game level design tools (Phase 11 - Nidhogr Game agent)
        registry.register(GenerateTilemapTool(work_dir=work_dir))
        registry.register(GenerateDungeonTool(work_dir=work_dir))
        registry.register(BalanceDifficultyTool(work_dir=work_dir))
        registry.register(GenerateDialogueTool(work_dir=work_dir))
        registry.register(GenerateItemStatsTool(work_dir=work_dir))
        registry.register(GenerateGDScriptTool(work_dir=work_dir))
        registry.register(GenerateUnityScriptTool(work_dir=work_dir))
        return registry
