"""Bundle models for agent packaging.

Defines dataclasses for bundle manifest, dependencies, metadata, and test configuration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional


class BundleState(Enum):
    """State of a bundle."""

    DISCOVERED = auto()  # Found but not validated
    VALIDATED = auto()  # Passed validation
    INSTALLED = auto()  # Installed and available
    FAILED = auto()  # Failed validation or installation
    DISABLED = auto()  # Explicitly disabled


@dataclass
class AgentBundleConfig:
    """Agent configuration within a bundle.

    Attributes:
        name: Unique agent name
        role: Human-readable role description
        model: Ollama model name
        tools: List of required tool names
        can_delegate: Whether agent can delegate to others
        delegate_to: List of agents this agent can delegate to
        estimated_vram_gb: Expected VRAM usage
        priority: Task priority (0 = highest)
        max_iterations: Maximum iterations before timeout
        max_context_tokens: Maximum context window size
        temperature: LLM sampling temperature
        fallback_model: Optional fallback model if primary fails
        fallback_vram_gb: VRAM for fallback model
    """

    name: str
    role: str
    model: str
    tools: list[str] = field(default_factory=list)
    can_delegate: bool = False
    delegate_to: list[str] = field(default_factory=list)
    estimated_vram_gb: float = 8.0
    priority: int = 1
    max_iterations: int = 30
    max_context_tokens: int = 16384
    temperature: float = 0.3
    fallback_model: Optional[str] = None
    fallback_vram_gb: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "tools": self.tools,
            "can_delegate": self.can_delegate,
            "delegate_to": self.delegate_to,
            "estimated_vram_gb": self.estimated_vram_gb,
            "priority": self.priority,
            "max_iterations": self.max_iterations,
            "max_context_tokens": self.max_context_tokens,
            "temperature": self.temperature,
        }
        if self.fallback_model:
            result["fallback_model"] = self.fallback_model
        if self.fallback_vram_gb:
            result["fallback_vram_gb"] = self.fallback_vram_gb
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentBundleConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            role=data["role"],
            model=data["model"],
            tools=data.get("tools", []),
            can_delegate=data.get("can_delegate", False),
            delegate_to=data.get("delegate_to", []),
            estimated_vram_gb=data.get("estimated_vram_gb", 8.0),
            priority=data.get("priority", 1),
            max_iterations=data.get("max_iterations", 30),
            max_context_tokens=data.get("max_context_tokens", 16384),
            temperature=data.get("temperature", 0.3),
            fallback_model=data.get("fallback_model"),
            fallback_vram_gb=data.get("fallback_vram_gb"),
        )


@dataclass
class BundleDependencies:
    """Bundle dependencies specification.

    Attributes:
        tools: Required tool names (must be available)
        models: Required model names (primary + fallback)
        plugins: Plugin dependencies with version specifiers
    """

    tools: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tools": self.tools,
            "models": self.models,
            "plugins": self.plugins,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BundleDependencies":
        """Create from dictionary."""
        return cls(
            tools=data.get("tools", []),
            models=data.get("models", []),
            plugins=data.get("plugins", []),
        )


@dataclass
class TestConfig:
    """Test configuration for a bundle.

    Attributes:
        framework: Test framework (only "pytest" supported)
        path: Path to test directory relative to bundle root
        markers: Pytest markers to run
        requirements: Additional test dependencies
    """

    framework: str = "pytest"
    path: str = "tests/"
    markers: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "framework": self.framework,
            "path": self.path,
            "markers": self.markers,
            "requirements": self.requirements,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestConfig":
        """Create from dictionary."""
        return cls(
            framework=data.get("framework", "pytest"),
            path=data.get("path", "tests/"),
            markers=data.get("markers", []),
            requirements=data.get("requirements", []),
        )


@dataclass
class BundleMetadata:
    """Bundle metadata for discovery and management.

    Attributes:
        version: Semantic version string
        sindri_version: Required Sindri version (e.g., ">=0.1.0")
        author: Author name or handle
        category: Agent category (e.g., "specialist", "reviewer")
        tags: Searchable tags
        license: License identifier
        description: Brief description
        homepage: Project homepage URL
        repository: Source code repository URL
    """

    version: str = "0.1.0"
    sindri_version: str = ">=0.1.0"
    author: str = ""
    category: str = "specialist"
    tags: list[str] = field(default_factory=list)
    license: str = ""
    description: str = ""
    homepage: str = ""
    repository: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "sindri_version": self.sindri_version,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "license": self.license,
            "description": self.description,
            "homepage": self.homepage,
            "repository": self.repository,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BundleMetadata":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "0.1.0"),
            sindri_version=data.get("sindri_version", ">=0.1.0"),
            author=data.get("author", ""),
            category=data.get("category", "specialist"),
            tags=data.get("tags", []),
            license=data.get("license", ""),
            description=data.get("description", ""),
            homepage=data.get("homepage", ""),
            repository=data.get("repository", ""),
        )


@dataclass
class BundleManifest:
    """Complete agent bundle manifest.

    Parsed from sindri-agent.toml in bundle root.

    Attributes:
        schema_version: Manifest schema version for future compat
        agent: Agent configuration
        dependencies: Tool, model, and plugin dependencies
        metadata: Bundle metadata
        test_config: Optional test configuration
        prompt_file: Path to prompt file (relative to bundle)
        prompt_content: Inline prompt content (alternative to file)
    """

    schema_version: int
    agent: AgentBundleConfig
    dependencies: BundleDependencies
    metadata: BundleMetadata
    test_config: Optional[TestConfig] = None
    prompt_file: Optional[str] = None
    prompt_content: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization."""
        result: dict[str, Any] = {
            "bundle": {
                "schema_version": self.schema_version,
            },
            "agent": self.agent.to_dict(),
            "dependencies": self.dependencies.to_dict(),
            "metadata": self.metadata.to_dict(),
        }
        if self.test_config:
            result["test"] = self.test_config.to_dict()
        if self.prompt_file:
            result["prompt"] = {"file": self.prompt_file}
        elif self.prompt_content:
            result["prompt"] = {"content": self.prompt_content}
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BundleManifest":
        """Create from parsed TOML dictionary."""
        bundle = data.get("bundle", {})
        prompt = data.get("prompt", {})

        return cls(
            schema_version=bundle.get("schema_version", 1),
            agent=AgentBundleConfig.from_dict(data.get("agent", {})),
            dependencies=BundleDependencies.from_dict(data.get("dependencies", {})),
            metadata=BundleMetadata.from_dict(data.get("metadata", {})),
            test_config=(
                TestConfig.from_dict(data["test"]) if "test" in data else None
            ),
            prompt_file=prompt.get("file"),
            prompt_content=prompt.get("content"),
        )


@dataclass
class TestResult:
    """Result of running bundle tests.

    Attributes:
        passed: Whether all tests passed
        total: Total number of tests
        passed_count: Number of passing tests
        failed_count: Number of failing tests
        skipped_count: Number of skipped tests
        duration_seconds: Test execution time
        output: Raw test output
        failures: List of failure messages
    """

    passed: bool
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    failures: list[str] = field(default_factory=list)


@dataclass
class BundleInfo:
    """Information about a discovered bundle.

    Attributes:
        name: Bundle name (from agent.name)
        path: Path to bundle directory
        manifest: Parsed manifest (if valid)
        state: Current bundle state
        error: Error message if state is FAILED
        installed_at: When bundle was installed
    """

    name: str
    path: Path
    manifest: Optional[BundleManifest] = None
    state: BundleState = BundleState.DISCOVERED
    error: Optional[str] = None
    installed_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "state": self.state.name,
            "error": self.error,
            "installed_at": (
                self.installed_at.isoformat() if self.installed_at else None
            ),
            "manifest": self.manifest.to_dict() if self.manifest else None,
        }
