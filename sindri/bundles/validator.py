"""Bundle validator for agent bundles.

Validates bundle structure, dependencies, and optionally runs tests.
"""

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Set

import structlog

from sindri.bundles.loader import BundleLoader, MANIFEST_FILENAME
from sindri.bundles.models import (
    BundleInfo,
    BundleManifest,
    BundleState,
    TestConfig,
    TestResult,
)

log = structlog.get_logger()


class ValidationError(Enum):
    """Types of validation errors."""

    MANIFEST_MISSING = auto()
    MANIFEST_INVALID = auto()
    PROMPT_MISSING = auto()
    TOOL_NOT_FOUND = auto()
    MODEL_NOT_FOUND = auto()
    PLUGIN_NOT_FOUND = auto()
    TEST_FAILED = auto()
    VERSION_INCOMPATIBLE = auto()
    NAME_CONFLICT = auto()


@dataclass
class BundleValidationResult:
    """Result of bundle validation.

    Attributes:
        valid: Whether bundle passed validation
        errors: List of (error_type, message) tuples
        warnings: List of warning messages
        test_result: Result of running tests (if run)
    """

    valid: bool = True
    errors: list[tuple[ValidationError, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    test_result: Optional[TestResult] = None

    def add_error(self, error_type: ValidationError, message: str) -> None:
        """Add an error."""
        self.errors.append((error_type, message))
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning."""
        self.warnings.append(message)


class BundleValidator:
    """Validates agent bundles for correctness and compatibility.

    Performs:
    - Manifest structure validation
    - Prompt file existence check
    - Tool dependency validation
    - Model availability check (optional)
    - Test execution (optional)

    Example:
        validator = BundleValidator(
            existing_tools={"read_file", "write_file"},
            available_models={"qwen2.5-coder:7b"}
        )
        result = await validator.validate(Path("./my_bundle"))
    """

    def __init__(
        self,
        existing_tools: Optional[Set[str]] = None,
        existing_agents: Optional[Set[str]] = None,
        available_models: Optional[Set[str]] = None,
        sindri_version: Optional[str] = None,
    ):
        """Initialize the validator.

        Args:
            existing_tools: Set of available tool names
            existing_agents: Set of existing agent names (for conflict detection)
            available_models: Set of available Ollama models
            sindri_version: Current Sindri version for compatibility check
        """
        self.existing_tools = existing_tools or set()
        self.existing_agents = existing_agents or set()
        self.available_models = available_models or set()
        self.sindri_version = sindri_version or "0.1.0"
        self.loader = BundleLoader()

    async def validate(
        self,
        bundle_path: Path,
        run_tests: bool = False,
    ) -> BundleValidationResult:
        """Validate a bundle completely.

        Args:
            bundle_path: Path to bundle directory
            run_tests: Whether to run bundle tests

        Returns:
            BundleValidationResult with errors and warnings
        """
        result = BundleValidationResult()

        # Check manifest exists
        manifest_path = bundle_path / MANIFEST_FILENAME
        if not manifest_path.exists():
            result.add_error(
                ValidationError.MANIFEST_MISSING,
                f"Manifest not found: {MANIFEST_FILENAME}",
            )
            return result

        # Load bundle
        bundle = self.loader.load(bundle_path)
        if bundle.state == BundleState.FAILED:
            result.add_error(
                ValidationError.MANIFEST_INVALID,
                bundle.error or "Failed to parse manifest",
            )
            return result

        manifest = bundle.manifest
        if not manifest:
            result.add_error(
                ValidationError.MANIFEST_INVALID,
                "Manifest is empty",
            )
            return result

        # Validate manifest structure
        self._validate_manifest(manifest, bundle_path, result)

        # Validate dependencies
        self._validate_dependencies(manifest, result)

        # Check for name conflicts
        self._validate_name_conflicts(manifest, result)

        # Run tests if requested and bundle has tests
        if run_tests and manifest.test_config:
            test_result = await self.run_tests(bundle_path, manifest.test_config)
            result.test_result = test_result
            if not test_result.passed:
                result.add_error(
                    ValidationError.TEST_FAILED,
                    f"Tests failed: {test_result.failed_count}/{test_result.total}",
                )

        log.info(
            "bundle_validated",
            name=manifest.agent.name,
            valid=result.valid,
            errors=len(result.errors),
            warnings=len(result.warnings),
        )

        return result

    def _validate_manifest(
        self,
        manifest: BundleManifest,
        bundle_path: Path,
        result: BundleValidationResult,
    ) -> None:
        """Validate manifest structure."""
        # Check required agent fields
        if not manifest.agent.name:
            result.add_error(
                ValidationError.MANIFEST_INVALID,
                "Agent name is required",
            )

        if not manifest.agent.role:
            result.add_error(
                ValidationError.MANIFEST_INVALID,
                "Agent role is required",
            )

        if not manifest.agent.model:
            result.add_error(
                ValidationError.MANIFEST_INVALID,
                "Agent model is required",
            )

        # Check prompt exists
        if manifest.prompt_file:
            prompt_path = bundle_path / manifest.prompt_file
            if not prompt_path.exists():
                result.add_error(
                    ValidationError.PROMPT_MISSING,
                    f"Prompt file not found: {manifest.prompt_file}",
                )
        elif not manifest.prompt_content:
            result.add_warning("No system prompt defined (prompt.file or prompt.content)")

        # Validate VRAM
        if manifest.agent.estimated_vram_gb <= 0:
            result.add_warning("estimated_vram_gb should be positive")
        elif manifest.agent.estimated_vram_gb > 24:
            result.add_warning(
                f"estimated_vram_gb={manifest.agent.estimated_vram_gb} may exceed available GPU memory"
            )

        # Validate iterations
        if manifest.agent.max_iterations <= 0:
            result.add_warning("max_iterations should be positive")
        elif manifest.agent.max_iterations > 100:
            result.add_warning(
                f"max_iterations={manifest.agent.max_iterations} is unusually high"
            )

        # Validate delegation
        if manifest.agent.delegate_to and not manifest.agent.can_delegate:
            result.add_warning(
                "delegate_to specified but can_delegate is false"
            )

    def _validate_dependencies(
        self,
        manifest: BundleManifest,
        result: BundleValidationResult,
    ) -> None:
        """Validate tool, model, and plugin dependencies."""
        # Check tools
        for tool in manifest.agent.tools:
            if self.existing_tools and tool not in self.existing_tools:
                if tool not in manifest.dependencies.tools:
                    result.add_warning(
                        f"Tool '{tool}' not in existing tools. "
                        "Ensure it's available or provided by a plugin."
                    )

        for tool in manifest.dependencies.tools:
            if self.existing_tools and tool not in self.existing_tools:
                result.add_warning(
                    f"Dependency tool '{tool}' not found in existing tools"
                )

        # Check models
        model = manifest.agent.model
        if self.available_models and model not in self.available_models:
            result.add_warning(
                f"Model '{model}' not in available models. "
                "Ensure it's installed in Ollama."
            )

        if manifest.agent.fallback_model:
            if (
                self.available_models
                and manifest.agent.fallback_model not in self.available_models
            ):
                result.add_warning(
                    f"Fallback model '{manifest.agent.fallback_model}' not available"
                )

        # Check all models in dependencies.models
        for dep_model in manifest.dependencies.models:
            if self.available_models and dep_model not in self.available_models:
                result.add_warning(
                    f"Dependency model '{dep_model}' not in available models. "
                    "Ensure it's installed in Ollama."
                )

        # Check plugin dependencies
        for plugin_spec in manifest.dependencies.plugins:
            # Plugin specs can include version like "my-plugin>=1.0"
            # Extract just the plugin name for checking
            plugin_name = plugin_spec.split(">=")[0].split("<=")[0].split("==")[0].split(">")[0].split("<")[0].strip()
            result.add_warning(
                f"Plugin dependency '{plugin_spec}' declared. "
                "Ensure plugin is installed before using this bundle."
            )

        # Check version compatibility
        self._check_version_compatibility(manifest.metadata.sindri_version, result)

    def _validate_name_conflicts(
        self,
        manifest: BundleManifest,
        result: BundleValidationResult,
    ) -> None:
        """Check for agent name conflicts."""
        if manifest.agent.name in self.existing_agents:
            result.add_error(
                ValidationError.NAME_CONFLICT,
                f"Agent name '{manifest.agent.name}' conflicts with existing agent",
            )

    def _check_version_compatibility(
        self,
        version_spec: str,
        result: BundleValidationResult,
    ) -> None:
        """Check if current Sindri version satisfies requirement."""
        try:
            from packaging import version
            from packaging.specifiers import SpecifierSet

            spec = SpecifierSet(version_spec)
            current = version.parse(self.sindri_version)

            if current not in spec:
                result.add_error(
                    ValidationError.VERSION_INCOMPATIBLE,
                    f"Sindri {self.sindri_version} does not satisfy {version_spec}",
                )
        except ImportError:
            # packaging not available, skip check
            pass
        except Exception as e:
            result.add_warning(f"Could not check version compatibility: {e}")

    async def run_tests(
        self,
        bundle_path: Path,
        config: TestConfig,
    ) -> TestResult:
        """Run tests for a bundle.

        Args:
            bundle_path: Path to bundle directory
            config: Test configuration

        Returns:
            TestResult with pass/fail status
        """
        test_path = bundle_path / config.path

        if not test_path.exists():
            return TestResult(
                passed=True,
                output="No tests found",
            )

        if config.framework != "pytest":
            return TestResult(
                passed=False,
                output=f"Unsupported test framework: {config.framework}",
                failures=[f"Only pytest is supported, got {config.framework}"],
            )

        # Build pytest command
        cmd = [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short"]

        # Add markers if specified
        for marker in config.markers:
            cmd.extend(["-m", marker])

        try:
            # Run pytest
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(bundle_path),
            )

            stdout, _ = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")

            # Parse results from output
            passed = proc.returncode == 0
            total, passed_count, failed_count, skipped_count = self._parse_pytest_output(
                output
            )

            failures = []
            if not passed:
                # Extract failure messages
                failures = self._extract_failures(output)

            return TestResult(
                passed=passed,
                total=total,
                passed_count=passed_count,
                failed_count=failed_count,
                skipped_count=skipped_count,
                output=output,
                failures=failures,
            )

        except Exception as e:
            return TestResult(
                passed=False,
                output=str(e),
                failures=[f"Failed to run tests: {e}"],
            )

    def _parse_pytest_output(self, output: str) -> tuple[int, int, int, int]:
        """Parse pytest output for test counts.

        Returns:
            Tuple of (total, passed, failed, skipped)
        """
        import re

        # Look for summary line like "5 passed, 2 failed, 1 skipped"
        pattern = r"(\d+) passed|(\d+) failed|(\d+) skipped|(\d+) error"
        matches = re.findall(pattern, output)

        passed = 0
        failed = 0
        skipped = 0

        for match in matches:
            if match[0]:
                passed = int(match[0])
            if match[1]:
                failed = int(match[1])
            if match[2]:
                skipped = int(match[2])
            if match[3]:
                failed += int(match[3])  # Count errors as failures

        total = passed + failed + skipped
        return total, passed, failed, skipped

    def _extract_failures(self, output: str) -> list[str]:
        """Extract failure messages from pytest output."""
        failures = []
        in_failure = False
        current_failure = []

        for line in output.split("\n"):
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                if current_failure:
                    failures.append("\n".join(current_failure))
                current_failure = [line]
                in_failure = True
            elif in_failure:
                if line.startswith("=") and "passed" in line:
                    if current_failure:
                        failures.append("\n".join(current_failure))
                    break
                current_failure.append(line)

        if current_failure and current_failure not in failures:
            failures.append("\n".join(current_failure))

        return failures[:5]  # Limit to first 5 failures
