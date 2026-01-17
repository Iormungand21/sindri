"""Architecture pattern detection for projects."""

import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import structlog

from sindri.analysis.results import ArchitectureInfo

log = structlog.get_logger()


# Common layer/component names
LAYER_PATTERNS = {
    "presentation": [
        "views",
        "templates",
        "pages",
        "components",
        "ui",
        "frontend",
        "screens",
    ],
    "api": ["api", "routes", "endpoints", "controllers", "handlers", "resources"],
    "business": ["services", "domain", "business", "use_cases", "usecases", "logic"],
    "data": ["models", "entities", "schemas", "repositories", "dao", "data"],
    "infrastructure": [
        "infrastructure",
        "infra",
        "adapters",
        "external",
        "integrations",
    ],
    "utilities": ["utils", "helpers", "common", "shared", "lib", "tools"],
    "config": ["config", "settings", "configuration"],
    "core": ["core", "kernel", "engine"],
}

# Framework detection patterns
FRAMEWORK_INDICATORS = {
    # Python web frameworks
    "flask": ["from flask", "Flask(__name__)", "@app.route"],
    "django": ["from django", "django.conf.settings", "INSTALLED_APPS"],
    "fastapi": ["from fastapi", "FastAPI()", "@app.get", "@app.post"],
    "starlette": ["from starlette", "Starlette("],
    "aiohttp": ["from aiohttp", "aiohttp.web"],
    "tornado": ["from tornado", "tornado.web"],
    # Python CLI/tools
    "click": ["import click", "from click", "@click.command"],
    "typer": ["import typer", "from typer"],
    "argparse": ["argparse.ArgumentParser"],
    # Python testing
    "pytest": ["import pytest", "from pytest", "@pytest.fixture"],
    "unittest": ["import unittest", "unittest.TestCase"],
    # Python async
    "asyncio": ["import asyncio", "async def", "await "],
    # Python ORM/DB
    "sqlalchemy": ["from sqlalchemy", "import sqlalchemy"],
    "pydantic": ["from pydantic", "BaseModel"],
    "alembic": ["from alembic", "alembic.ini"],
    # Other Python
    "celery": ["from celery", "Celery("],
    "redis": ["import redis", "from redis"],
    # JavaScript/TypeScript
    "react": ["from 'react'", "import React", "useState", "useEffect"],
    "vue": ["from 'vue'", "createApp", "defineComponent"],
    "angular": ["@angular/core", "@Component"],
    "express": ["from 'express'", "require('express')"],
    "nextjs": ["next/", "getServerSideProps", "getStaticProps"],
    "nest": ["@nestjs/", "@Controller", "@Injectable"],
}

# Project type indicators
PROJECT_TYPE_PATTERNS = {
    "cli": ["cli.py", "__main__.py", "argparse", "click.command"],
    "web_api": ["routes", "endpoints", "api/", "@app.route", "FastAPI"],
    "web_app": ["templates/", "static/", "views/", "pages/"],
    "library": ["setup.py", "pyproject.toml", "__init__.py"],
    "microservice": ["docker-compose", "Dockerfile", "kubernetes"],
    "data_pipeline": ["pipeline", "etl", "dag", "workflow"],
}


class ArchitectureDetector:
    """Detects architecture patterns in a project."""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def analyze(self) -> ArchitectureInfo:
        """Perform full architecture analysis.

        Returns:
            ArchitectureInfo with detected patterns
        """
        log.info("analyzing_architecture", project=str(self.project_path))

        result = ArchitectureInfo()

        # Find directory structure
        directories = self._find_directories()
        files = self._find_files()

        # Detect layers
        result.layer_structure = self._detect_layers(directories)

        # Detect architecture pattern
        pattern, confidence = self._detect_pattern(directories, result.layer_structure)
        result.detected_pattern = pattern
        result.confidence = confidence

        # Find component groups
        result.component_groups = self._group_components(directories, files)

        # Find key directories
        result.source_roots = self._find_source_roots(directories)
        result.test_directories = self._find_test_dirs(directories)
        result.config_files = self._find_config_files(files)

        # Detect frameworks
        result.frameworks_detected = self._detect_frameworks(files)

        # Detect project type
        result.project_type = self._detect_project_type(
            files, directories, result.frameworks_detected
        )

        log.info(
            "architecture_analysis_complete",
            pattern=result.detected_pattern,
            confidence=result.confidence,
            project_type=result.project_type,
            frameworks=result.frameworks_detected,
        )

        return result

    def _find_directories(self) -> List[str]:
        """Find all directories in the project."""
        dirs = []
        for path in self.project_path.rglob("*"):
            if path.is_dir():
                rel_path = str(path.relative_to(self.project_path))
                # Skip hidden and common non-code directories
                parts = rel_path.split(os.sep)
                if not any(
                    p.startswith(".")
                    or p in {"__pycache__", "node_modules", "venv", ".venv"}
                    for p in parts
                ):
                    dirs.append(rel_path)
        return dirs

    def _find_files(self) -> List[str]:
        """Find all files in the project."""
        files = []
        for path in self.project_path.rglob("*"):
            if path.is_file():
                rel_path = str(path.relative_to(self.project_path))
                parts = rel_path.split(os.sep)
                if not any(
                    p.startswith(".")
                    or p in {"__pycache__", "node_modules", "venv", ".venv"}
                    for p in parts
                ):
                    files.append(rel_path)
        return files

    def _detect_layers(self, directories: List[str]) -> Dict[str, List[str]]:
        """Detect layer structure from directories."""
        layers = defaultdict(list)

        for dir_path in directories:
            dir_name = Path(dir_path).name.lower()

            for layer, patterns in LAYER_PATTERNS.items():
                if dir_name in patterns or any(p in dir_path.lower() for p in patterns):
                    layers[layer].append(dir_path)
                    break

        return dict(layers)

    def _detect_pattern(
        self, directories: List[str], layer_structure: Dict[str, List[str]]
    ) -> Tuple[str, float]:
        """Detect the architecture pattern."""
        scores = {
            "layered": 0.0,
            "modular": 0.0,
            "mvc": 0.0,
            "flat": 0.0,
            "monolith": 0.0,
        }

        # Count layers present
        layer_count = len(layer_structure)
        total_layer_dirs = sum(len(dirs) for dirs in layer_structure.values())

        # Check for MVC pattern
        has_models = "data" in layer_structure or any(
            "models" in d for d in directories
        )
        has_views = "presentation" in layer_structure or any(
            "views" in d or "templates" in d for d in directories
        )
        has_controllers = "api" in layer_structure or any(
            "controllers" in d for d in directories
        )

        if has_models and has_views and has_controllers:
            scores["mvc"] = 0.8
        elif has_models and (has_views or has_controllers):
            scores["mvc"] = 0.5

        # Check for layered architecture
        if layer_count >= 3:
            scores["layered"] = 0.7 + min(layer_count * 0.05, 0.2)
        elif layer_count == 2:
            scores["layered"] = 0.5

        # Check for modular architecture (feature-based directories)
        feature_dirs = [
            d
            for d in directories
            if "/" not in d and d not in LAYER_PATTERNS.get("utilities", [])
        ]
        if len(feature_dirs) >= 3 and layer_count <= 2:
            scores["modular"] = 0.6 + min(len(feature_dirs) * 0.05, 0.3)

        # Check for flat structure
        depth_1_dirs = [d for d in directories if "/" not in d]
        if len(directories) <= 5 or len(depth_1_dirs) == len(directories):
            scores["flat"] = 0.6

        # Monolith detection
        if total_layer_dirs > 10 or len(directories) > 30:
            scores["monolith"] = 0.4

        # Find best match
        best_pattern = max(scores.keys(), key=lambda k: scores[k])
        confidence = scores[best_pattern]

        # Default to flat if no strong signal
        if confidence < 0.4:
            return "flat", 0.4

        return best_pattern, confidence

    def _group_components(
        self, directories: List[str], files: List[str]
    ) -> Dict[str, List[str]]:
        """Group related components together."""
        groups = defaultdict(list)

        # Group by top-level directory
        for dir_path in directories:
            parts = dir_path.split(os.sep)
            if len(parts) >= 1:
                top_level = parts[0]
                if top_level not in {"tests", "test", "docs", "examples"}:
                    groups[top_level].append(dir_path)

        # Filter to only include groups with multiple items
        return {k: v for k, v in groups.items() if len(v) >= 1}

    def _find_source_roots(self, directories: List[str]) -> List[str]:
        """Find source code root directories."""
        source_patterns = ["src", "lib", "source", "app"]
        roots = []

        for dir_path in directories:
            parts = dir_path.split(os.sep)
            if parts[0].lower() in source_patterns:
                roots.append(parts[0])

        # Also check for package directories (containing __init__.py)
        for dir_path in directories:
            init_path = self.project_path / dir_path / "__init__.py"
            if init_path.exists() and "/" not in dir_path:
                if dir_path.lower() not in {"tests", "test"}:
                    roots.append(dir_path)

        return list(set(roots))

    def _find_test_dirs(self, directories: List[str]) -> List[str]:
        """Find test directories."""
        test_patterns = ["tests", "test", "__tests__", "spec", "specs"]
        test_dirs = []

        for dir_path in directories:
            parts = dir_path.split(os.sep)
            if parts[0].lower() in test_patterns or parts[-1].lower() in test_patterns:
                test_dirs.append(dir_path)

        return list(set(test_dirs))

    def _find_config_files(self, files: List[str]) -> List[str]:
        """Find configuration files."""
        config_patterns = [
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "package.json",
            "tsconfig.json",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            ".env",
            ".env.example",
            "config.py",
            "config.yaml",
            "config.yml",
            "config.json",
            "settings.py",
            "settings.yaml",
            "settings.yml",
            "requirements.txt",
            "Pipfile",
            "poetry.lock",
            ".prettierrc",
            ".eslintrc",
            "ruff.toml",
            ".editorconfig",
            "tox.ini",
            "pytest.ini",
            ".coveragerc",
        ]

        found = []
        for file_path in files:
            file_name = Path(file_path).name
            if file_name in config_patterns or file_name.startswith("."):
                found.append(file_path)

        return found

    def _detect_frameworks(self, files: List[str]) -> List[str]:
        """Detect frameworks used in the project."""
        detected = set()

        # Sample some files for framework detection
        code_files = [
            f for f in files if f.endswith((".py", ".js", ".ts", ".jsx", ".tsx"))
        ][:50]

        for file_path in code_files:
            try:
                full_path = self.project_path / file_path
                content = full_path.read_text(encoding="utf-8", errors="ignore")[
                    :5000
                ]  # First 5KB

                for framework, indicators in FRAMEWORK_INDICATORS.items():
                    if any(ind in content for ind in indicators):
                        detected.add(framework)

            except Exception:
                continue

        return sorted(detected)

    def _detect_project_type(
        self, files: List[str], directories: List[str], frameworks: List[str]
    ) -> str:
        """Detect the type of project."""
        scores = defaultdict(float)

        # Check file/directory patterns
        for project_type, patterns in PROJECT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if any(pattern in f for f in files) or any(
                    pattern in d for d in directories
                ):
                    scores[project_type] += 0.3

        # Boost based on frameworks
        web_frameworks = {
            "flask",
            "django",
            "fastapi",
            "express",
            "nextjs",
            "nest",
            "react",
            "vue",
            "angular",
        }
        cli_frameworks = {"click", "typer", "argparse"}

        if any(f in frameworks for f in web_frameworks):
            if any(f in frameworks for f in {"react", "vue", "angular", "nextjs"}):
                scores["web_app"] += 0.5
            else:
                scores["web_api"] += 0.5

        if any(f in frameworks for f in cli_frameworks):
            scores["cli"] += 0.5

        # Check for library indicators
        if "setup.py" in [Path(f).name for f in files] or "pyproject.toml" in [
            Path(f).name for f in files
        ]:
            scores["library"] += 0.3

        # Default
        if not scores:
            return "unknown"

        return max(scores.keys(), key=lambda k: scores[k])
