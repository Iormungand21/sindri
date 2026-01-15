"""Data models for codebase analysis results."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Set
import json


@dataclass
class ModuleInfo:
    """Information about a module/file in the project."""
    path: str
    language: str
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    lines_of_code: int = 0


@dataclass
class DependencyInfo:
    """Dependency analysis results."""

    # Import relationships
    internal_dependencies: Dict[str, List[str]] = field(default_factory=dict)  # module -> imports
    external_packages: Set[str] = field(default_factory=set)  # third-party packages

    # Circular dependencies
    circular_dependencies: List[List[str]] = field(default_factory=list)  # cycles found

    # Dependency metrics
    most_imported: List[tuple] = field(default_factory=list)  # (module, import_count)
    orphan_modules: List[str] = field(default_factory=list)  # modules with no imports/exports

    # Entry points
    entry_points: List[str] = field(default_factory=list)  # main.py, cli.py, etc.

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "internal_dependencies": self.internal_dependencies,
            "external_packages": list(self.external_packages),
            "circular_dependencies": self.circular_dependencies,
            "most_imported": self.most_imported,
            "orphan_modules": self.orphan_modules,
            "entry_points": self.entry_points,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyInfo":
        """Create from dictionary."""
        return cls(
            internal_dependencies=data.get("internal_dependencies", {}),
            external_packages=set(data.get("external_packages", [])),
            circular_dependencies=data.get("circular_dependencies", []),
            most_imported=[tuple(x) for x in data.get("most_imported", [])],
            orphan_modules=data.get("orphan_modules", []),
            entry_points=data.get("entry_points", []),
        )

    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = ["## Dependency Analysis"]

        if self.entry_points:
            lines.append(f"\nEntry points: {', '.join(self.entry_points)}")

        if self.circular_dependencies:
            lines.append(f"\nCircular dependencies found: {len(self.circular_dependencies)}")
            for cycle in self.circular_dependencies[:3]:
                lines.append(f"  - {' -> '.join(cycle)}")

        if self.most_imported:
            lines.append("\nMost imported modules:")
            for mod, count in self.most_imported[:5]:
                lines.append(f"  - {mod}: {count} imports")

        if self.external_packages:
            lines.append(f"\nExternal packages: {len(self.external_packages)}")

        return "\n".join(lines)


@dataclass
class ArchitectureInfo:
    """Architecture detection results."""

    # Detected pattern
    detected_pattern: str = "unknown"  # mvc, layered, flat, modular, microservices
    confidence: float = 0.0

    # Structure analysis
    layer_structure: Dict[str, List[str]] = field(default_factory=dict)  # layer -> modules
    component_groups: Dict[str, List[str]] = field(default_factory=dict)  # group -> modules

    # Key directories
    source_roots: List[str] = field(default_factory=list)  # src/, lib/, etc.
    test_directories: List[str] = field(default_factory=list)  # tests/, test/, etc.
    config_files: List[str] = field(default_factory=list)  # config files found

    # Project type indicators
    project_type: str = "unknown"  # cli, web, library, etc.
    frameworks_detected: List[str] = field(default_factory=list)  # flask, django, etc.

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "detected_pattern": self.detected_pattern,
            "confidence": self.confidence,
            "layer_structure": self.layer_structure,
            "component_groups": self.component_groups,
            "source_roots": self.source_roots,
            "test_directories": self.test_directories,
            "config_files": self.config_files,
            "project_type": self.project_type,
            "frameworks_detected": self.frameworks_detected,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArchitectureInfo":
        """Create from dictionary."""
        return cls(
            detected_pattern=data.get("detected_pattern", "unknown"),
            confidence=data.get("confidence", 0.0),
            layer_structure=data.get("layer_structure", {}),
            component_groups=data.get("component_groups", {}),
            source_roots=data.get("source_roots", []),
            test_directories=data.get("test_directories", []),
            config_files=data.get("config_files", []),
            project_type=data.get("project_type", "unknown"),
            frameworks_detected=data.get("frameworks_detected", []),
        )

    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = ["## Architecture Analysis"]

        lines.append(f"\nDetected pattern: {self.detected_pattern} ({self.confidence:.0%} confidence)")
        lines.append(f"Project type: {self.project_type}")

        if self.frameworks_detected:
            lines.append(f"Frameworks: {', '.join(self.frameworks_detected)}")

        if self.layer_structure:
            lines.append("\nLayer structure:")
            for layer, modules in self.layer_structure.items():
                lines.append(f"  - {layer}: {len(modules)} modules")

        if self.source_roots:
            lines.append(f"\nSource roots: {', '.join(self.source_roots)}")

        if self.test_directories:
            lines.append(f"Test directories: {', '.join(self.test_directories)}")

        return "\n".join(lines)


@dataclass
class StyleInfo:
    """Style and convention analysis results."""

    # Coding conventions detected
    naming_conventions: Dict[str, str] = field(default_factory=dict)  # type -> convention
    indentation: str = "unknown"  # spaces, tabs
    indent_size: int = 4

    # Documentation style
    docstring_style: str = "unknown"  # google, numpy, sphinx, none
    has_type_hints: bool = False

    # Formatting tools detected
    formatter: Optional[str] = None  # black, prettier, etc.
    linter: Optional[str] = None  # ruff, eslint, etc.

    # Config files found
    formatting_configs: List[str] = field(default_factory=list)

    # Common patterns observed
    async_style: bool = False  # uses async/await
    test_framework: Optional[str] = None  # pytest, unittest, jest, etc.

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "naming_conventions": self.naming_conventions,
            "indentation": self.indentation,
            "indent_size": self.indent_size,
            "docstring_style": self.docstring_style,
            "has_type_hints": self.has_type_hints,
            "formatter": self.formatter,
            "linter": self.linter,
            "formatting_configs": self.formatting_configs,
            "async_style": self.async_style,
            "test_framework": self.test_framework,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StyleInfo":
        """Create from dictionary."""
        return cls(
            naming_conventions=data.get("naming_conventions", {}),
            indentation=data.get("indentation", "unknown"),
            indent_size=data.get("indent_size", 4),
            docstring_style=data.get("docstring_style", "unknown"),
            has_type_hints=data.get("has_type_hints", False),
            formatter=data.get("formatter"),
            linter=data.get("linter"),
            formatting_configs=data.get("formatting_configs", []),
            async_style=data.get("async_style", False),
            test_framework=data.get("test_framework"),
        )

    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = ["## Style Analysis"]

        lines.append(f"\nIndentation: {self.indent_size} {self.indentation}")

        if self.formatter:
            lines.append(f"Formatter: {self.formatter}")
        if self.linter:
            lines.append(f"Linter: {self.linter}")

        if self.docstring_style != "unknown":
            lines.append(f"Docstring style: {self.docstring_style}")

        if self.has_type_hints:
            lines.append("Type hints: Yes")

        if self.async_style:
            lines.append("Async/await: Yes")

        if self.test_framework:
            lines.append(f"Test framework: {self.test_framework}")

        if self.naming_conventions:
            lines.append("\nNaming conventions:")
            for item_type, convention in self.naming_conventions.items():
                lines.append(f"  - {item_type}: {convention}")

        return "\n".join(lines)


@dataclass
class CodebaseAnalysis:
    """Complete codebase analysis results."""

    # Core analysis results
    dependencies: DependencyInfo = field(default_factory=DependencyInfo)
    architecture: ArchitectureInfo = field(default_factory=ArchitectureInfo)
    style: StyleInfo = field(default_factory=StyleInfo)

    # Project metadata
    project_path: str = ""
    project_id: str = ""
    primary_language: str = "unknown"

    # File statistics
    total_files: int = 0
    total_lines: int = 0
    files_by_language: Dict[str, int] = field(default_factory=dict)

    # Analysis metadata
    analyzed_at: Optional[datetime] = None
    analysis_version: str = "1.0"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "dependencies": self.dependencies.to_dict(),
            "architecture": self.architecture.to_dict(),
            "style": self.style.to_dict(),
            "project_path": self.project_path,
            "project_id": self.project_id,
            "primary_language": self.primary_language,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "files_by_language": self.files_by_language,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
            "analysis_version": self.analysis_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodebaseAnalysis":
        """Create from dictionary."""
        return cls(
            dependencies=DependencyInfo.from_dict(data.get("dependencies", {})),
            architecture=ArchitectureInfo.from_dict(data.get("architecture", {})),
            style=StyleInfo.from_dict(data.get("style", {})),
            project_path=data.get("project_path", ""),
            project_id=data.get("project_id", ""),
            primary_language=data.get("primary_language", "unknown"),
            total_files=data.get("total_files", 0),
            total_lines=data.get("total_lines", 0),
            files_by_language=data.get("files_by_language", {}),
            analyzed_at=datetime.fromisoformat(data["analyzed_at"]) if data.get("analyzed_at") else None,
            analysis_version=data.get("analysis_version", "1.0"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "CodebaseAnalysis":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def format_summary(self) -> str:
        """Format a complete human-readable summary."""
        lines = [
            f"# Codebase Analysis: {self.project_id or self.project_path}",
            f"\nPrimary language: {self.primary_language}",
            f"Total files: {self.total_files}",
            f"Total lines: {self.total_lines:,}",
        ]

        if self.files_by_language:
            lines.append("\nFiles by language:")
            for lang, count in sorted(self.files_by_language.items(), key=lambda x: -x[1]):
                lines.append(f"  - {lang}: {count}")

        lines.append("\n" + self.dependencies.format_summary())
        lines.append("\n" + self.architecture.format_summary())
        lines.append("\n" + self.style.format_summary())

        return "\n".join(lines)

    def format_context(self) -> str:
        """Format analysis for agent context injection."""
        parts = []

        # Architecture summary for agents
        parts.append(f"Project: {self.primary_language} {self.architecture.project_type}")
        parts.append(f"Architecture: {self.architecture.detected_pattern}")

        if self.architecture.frameworks_detected:
            parts.append(f"Frameworks: {', '.join(self.architecture.frameworks_detected)}")

        if self.dependencies.entry_points:
            parts.append(f"Entry points: {', '.join(self.dependencies.entry_points)}")

        # Style guidance for code generation
        if self.style.has_type_hints:
            parts.append("Style: Use type hints")
        if self.style.docstring_style != "unknown":
            parts.append(f"Docstrings: {self.style.docstring_style} style")
        if self.style.async_style:
            parts.append("Uses async/await patterns")
        if self.style.formatter:
            parts.append(f"Formatter: {self.style.formatter}")

        # Key layers/modules
        if self.architecture.layer_structure:
            layers = ", ".join(self.architecture.layer_structure.keys())
            parts.append(f"Layers: {layers}")

        return "\n".join(parts)
