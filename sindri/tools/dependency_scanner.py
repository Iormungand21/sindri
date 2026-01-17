"""Dependency scanner tools for vulnerability detection.

Provides tools for scanning project dependencies for known vulnerabilities
using various ecosystem-specific tools (pip-audit, npm audit, cargo audit, etc.).
"""

import asyncio
import json
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


class Severity(Enum):
    """Vulnerability severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, s: str) -> "Severity":
        """Parse severity from string."""
        s = s.lower().strip()
        if s in ("critical", "crit"):
            return cls.CRITICAL
        elif s in ("high", "important"):
            return cls.HIGH
        elif s in ("medium", "moderate", "mod"):
            return cls.MEDIUM
        elif s in ("low", "minor"):
            return cls.LOW
        return cls.UNKNOWN

    @property
    def score(self) -> int:
        """Numeric score for sorting (higher = more severe)."""
        scores = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.UNKNOWN: 0,
        }
        return scores.get(self, 0)


@dataclass
class Vulnerability:
    """A detected vulnerability."""

    id: str  # CVE-XXXX-XXXX or advisory ID
    package: str
    installed_version: str
    fixed_version: Optional[str]
    severity: Severity
    description: str
    url: Optional[str] = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class DependencyInfo:
    """Information about a dependency."""

    name: str
    version: str
    latest_version: Optional[str] = None
    is_outdated: bool = False
    is_dev: bool = False
    license: Optional[str] = None


@dataclass
class ScanResult:
    """Result from dependency scanning."""

    ecosystem: str  # python, node, rust, go
    total_dependencies: int
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    dependencies: list[DependencyInfo] = field(default_factory=list)
    scan_time: datetime = field(default_factory=datetime.now)
    scanner_tool: Optional[str] = None
    error: Optional[str] = None

    @property
    def vulnerability_count(self) -> int:
        return len(self.vulnerabilities)

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.LOW)

    @property
    def outdated_count(self) -> int:
        return sum(1 for d in self.dependencies if d.is_outdated)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "ecosystem": self.ecosystem,
            "total_dependencies": self.total_dependencies,
            "vulnerability_count": self.vulnerability_count,
            "severity_breakdown": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
            },
            "outdated_count": self.outdated_count,
            "vulnerabilities": [
                {
                    "id": v.id,
                    "package": v.package,
                    "installed_version": v.installed_version,
                    "fixed_version": v.fixed_version,
                    "severity": v.severity.value,
                    "description": v.description,
                    "url": v.url,
                    "aliases": v.aliases,
                }
                for v in self.vulnerabilities
            ],
            "dependencies": [
                {
                    "name": d.name,
                    "version": d.version,
                    "latest_version": d.latest_version,
                    "is_outdated": d.is_outdated,
                    "is_dev": d.is_dev,
                    "license": d.license,
                }
                for d in self.dependencies
            ],
            "scan_time": self.scan_time.isoformat(),
            "scanner_tool": self.scanner_tool,
        }


class ScanDependenciesTool(Tool):
    """Scan project dependencies for vulnerabilities.

    Detects project type and uses appropriate scanner:
    - Python: pip-audit (or safety as fallback)
    - Node.js: npm audit
    - Rust: cargo audit
    - Go: govulncheck
    """

    name = "scan_dependencies"
    description = """Scan project dependencies for known security vulnerabilities.

Automatically detects project type and uses the appropriate vulnerability scanner.
Supports Python (pip-audit), Node.js (npm audit), Rust (cargo audit), and Go (govulncheck).

Examples:
- scan_dependencies() - Scan current directory
- scan_dependencies(path="/path/to/project") - Scan specific project
- scan_dependencies(min_severity="high") - Only report high and critical vulnerabilities
- scan_dependencies(include_dev=true) - Include dev dependencies
- scan_dependencies(format="json") - Output as JSON
- scan_dependencies(check_outdated=true) - Also check for outdated packages"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "ecosystem": {
                "type": "string",
                "description": "Override ecosystem detection: 'python', 'node', 'rust', 'go'",
                "enum": ["python", "node", "rust", "go"],
            },
            "min_severity": {
                "type": "string",
                "description": "Minimum severity to report: 'low', 'medium', 'high', 'critical'",
                "enum": ["low", "medium", "high", "critical"],
            },
            "include_dev": {
                "type": "boolean",
                "description": "Include development dependencies (default: true)",
            },
            "check_outdated": {
                "type": "boolean",
                "description": "Also check for outdated dependencies (default: false)",
            },
            "format": {
                "type": "string",
                "description": "Output format: 'text', 'json', 'sarif'",
                "enum": ["text", "json", "sarif"],
            },
            "fix": {
                "type": "boolean",
                "description": "Attempt to automatically fix vulnerabilities (default: false)",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        ecosystem: Optional[str] = None,
        min_severity: str = "low",
        include_dev: bool = True,
        check_outdated: bool = False,
        format: str = "text",
        fix: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Execute dependency scan.

        Args:
            path: Project directory path
            ecosystem: Override ecosystem detection
            min_severity: Minimum severity level to report
            include_dev: Include dev dependencies
            check_outdated: Check for outdated packages
            format: Output format (text, json, sarif)
            fix: Attempt automatic fixes
        """
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect ecosystem if not specified
        if not ecosystem:
            ecosystem = self._detect_ecosystem(project_path)
            if not ecosystem:
                return ToolResult(
                    success=False,
                    output="",
                    error="Could not detect project ecosystem. No package.json, requirements.txt, Cargo.toml, or go.mod found.",
                )

        log.info(
            "scanning_dependencies",
            path=str(project_path),
            ecosystem=ecosystem,
            min_severity=min_severity,
        )

        # Run appropriate scanner
        try:
            if ecosystem == "python":
                result = await self._scan_python(
                    project_path, include_dev, check_outdated, fix
                )
            elif ecosystem == "node":
                result = await self._scan_node(
                    project_path, include_dev, check_outdated, fix
                )
            elif ecosystem == "rust":
                result = await self._scan_rust(project_path, check_outdated, fix)
            elif ecosystem == "go":
                result = await self._scan_go(project_path, check_outdated)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported ecosystem: {ecosystem}",
                )

            if result.error:
                return ToolResult(success=False, output="", error=result.error)

            # Filter by severity
            min_sev = Severity.from_string(min_severity)
            result.vulnerabilities = [
                v for v in result.vulnerabilities if v.severity.score >= min_sev.score
            ]

            # Format output
            if format == "json":
                output = json.dumps(result.to_dict(), indent=2)
            elif format == "sarif":
                output = self._to_sarif(result)
            else:
                output = self._format_text(result)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "ecosystem": ecosystem,
                    "vulnerability_count": result.vulnerability_count,
                    "critical": result.critical_count,
                    "high": result.high_count,
                    "medium": result.medium_count,
                    "low": result.low_count,
                    "outdated": result.outdated_count,
                },
            )

        except Exception as e:
            log.error("scan_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Scan failed: {str(e)}")

    def _detect_ecosystem(self, path: Path) -> Optional[str]:
        """Detect project ecosystem from files."""
        if (path / "package.json").exists():
            return "node"
        elif (
            (path / "requirements.txt").exists()
            or (path / "pyproject.toml").exists()
            or (path / "setup.py").exists()
            or (path / "Pipfile").exists()
        ):
            return "python"
        elif (path / "Cargo.toml").exists():
            return "rust"
        elif (path / "go.mod").exists():
            return "go"
        return None

    async def _scan_python(
        self, path: Path, include_dev: bool, check_outdated: bool, fix: bool
    ) -> ScanResult:
        """Scan Python project for vulnerabilities."""
        result = ScanResult(ecosystem="python", total_dependencies=0)

        # Try pip-audit first (preferred)
        if shutil.which("pip-audit"):
            result.scanner_tool = "pip-audit"
            return await self._run_pip_audit(path, include_dev, check_outdated, fix)

        # Fall back to safety
        if shutil.which("safety"):
            result.scanner_tool = "safety"
            return await self._run_safety(path, check_outdated)

        # No scanner available, try using pip to at least list packages
        result.error = (
            "No Python vulnerability scanner found. Install with: pip install pip-audit"
        )
        return result

    async def _run_pip_audit(
        self, path: Path, include_dev: bool, check_outdated: bool, fix: bool
    ) -> ScanResult:
        """Run pip-audit scanner."""
        result = ScanResult(
            ecosystem="python", total_dependencies=0, scanner_tool="pip-audit"
        )

        cmd = ["pip-audit", "--format", "json"]

        # Check for requirements file
        req_file = None
        for filename in [
            "requirements.txt",
            "requirements-dev.txt",
            "requirements/base.txt",
        ]:
            if (path / filename).exists():
                req_file = path / filename
                break

        if req_file:
            cmd.extend(["-r", str(req_file)])

        if fix:
            cmd.append("--fix")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stdout:
                try:
                    data = json.loads(stdout.decode())

                    # Handle pip-audit JSON format
                    if isinstance(data, dict):
                        dependencies = data.get("dependencies", [])
                    else:
                        dependencies = data

                    result.total_dependencies = len(dependencies)

                    for dep in dependencies:
                        # Each dependency may have vulnerabilities
                        vulns = dep.get("vulns", [])
                        for vuln in vulns:
                            result.vulnerabilities.append(
                                Vulnerability(
                                    id=vuln.get("id", "UNKNOWN"),
                                    package=dep.get("name", "unknown"),
                                    installed_version=dep.get("version", "unknown"),
                                    fixed_version=(
                                        vuln.get("fix_versions", [None])[0]
                                        if vuln.get("fix_versions")
                                        else None
                                    ),
                                    severity=Severity.from_string(
                                        vuln.get("severity", "unknown")
                                    ),
                                    description=vuln.get(
                                        "description", "No description available"
                                    ),
                                    url=vuln.get("url"),
                                    aliases=vuln.get("aliases", []),
                                )
                            )

                        # Track dependency info
                        result.dependencies.append(
                            DependencyInfo(
                                name=dep.get("name", "unknown"),
                                version=dep.get("version", "unknown"),
                            )
                        )

                except json.JSONDecodeError:
                    # If JSON parsing fails, try to extract info from text
                    result.error = (
                        f"Failed to parse pip-audit output: {stdout.decode()[:200]}"
                    )

        except Exception as e:
            result.error = f"pip-audit failed: {str(e)}"

        # Check for outdated packages if requested
        if check_outdated and not result.error:
            await self._check_python_outdated(path, result)

        return result

    async def _run_safety(self, path: Path, check_outdated: bool) -> ScanResult:
        """Run safety scanner (fallback)."""
        result = ScanResult(
            ecosystem="python", total_dependencies=0, scanner_tool="safety"
        )

        cmd = ["safety", "check", "--json"]

        # Check for requirements file
        req_file = None
        for filename in ["requirements.txt", "requirements-dev.txt"]:
            if (path / filename).exists():
                req_file = path / filename
                cmd.extend(["-r", str(req_file)])
                break

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stdout:
                try:
                    data = json.loads(stdout.decode())
                    vulns = (
                        data
                        if isinstance(data, list)
                        else data.get("vulnerabilities", [])
                    )

                    for vuln in vulns:
                        result.vulnerabilities.append(
                            Vulnerability(
                                id=vuln.get(
                                    "vulnerability_id", vuln.get("CVE", "UNKNOWN")
                                ),
                                package=vuln.get("package_name", "unknown"),
                                installed_version=vuln.get(
                                    "analyzed_version", "unknown"
                                ),
                                fixed_version=vuln.get("more_info_path"),
                                severity=Severity.from_string(
                                    vuln.get("severity", "unknown")
                                ),
                                description=vuln.get("advisory", "No description"),
                            )
                        )

                except json.JSONDecodeError:
                    pass

        except Exception as e:
            result.error = f"safety check failed: {str(e)}"

        return result

    async def _check_python_outdated(self, path: Path, result: ScanResult) -> None:
        """Check for outdated Python packages."""
        try:
            process = await asyncio.create_subprocess_exec(
                "pip",
                "list",
                "--outdated",
                "--format",
                "json",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if stdout:
                outdated = json.loads(stdout.decode())
                for pkg in outdated:
                    # Update existing dependency info
                    for dep in result.dependencies:
                        if dep.name.lower() == pkg.get("name", "").lower():
                            dep.latest_version = pkg.get("latest_version")
                            dep.is_outdated = True
                            break
                    else:
                        # Add new entry if not found
                        result.dependencies.append(
                            DependencyInfo(
                                name=pkg.get("name", "unknown"),
                                version=pkg.get("version", "unknown"),
                                latest_version=pkg.get("latest_version"),
                                is_outdated=True,
                            )
                        )

        except Exception:
            pass  # Outdated check is optional, don't fail on error

    async def _scan_node(
        self, path: Path, include_dev: bool, check_outdated: bool, fix: bool
    ) -> ScanResult:
        """Scan Node.js project for vulnerabilities."""
        result = ScanResult(
            ecosystem="node", total_dependencies=0, scanner_tool="npm audit"
        )

        if not shutil.which("npm"):
            result.error = "npm not found. Please install Node.js."
            return result

        # Build npm audit command
        cmd = ["npm", "audit", "--json"]

        if not include_dev:
            cmd.append("--omit=dev")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stdout:
                try:
                    data = json.loads(stdout.decode())

                    # npm audit v7+ format
                    vulnerabilities = data.get("vulnerabilities", {})
                    metadata = data.get("metadata", {})

                    result.total_dependencies = metadata.get("dependencies", {}).get(
                        "total", 0
                    )

                    for pkg_name, vuln_data in vulnerabilities.items():
                        severity = vuln_data.get("severity", "unknown")
                        via = vuln_data.get("via", [])

                        # Extract vulnerability details
                        for v in via:
                            if isinstance(v, dict):
                                result.vulnerabilities.append(
                                    Vulnerability(
                                        id=str(
                                            v.get("source", v.get("url", "UNKNOWN"))
                                        ),
                                        package=pkg_name,
                                        installed_version=vuln_data.get(
                                            "range", "unknown"
                                        ),
                                        fixed_version=(
                                            vuln_data.get("fixAvailable", {}).get(
                                                "version"
                                            )
                                            if isinstance(
                                                vuln_data.get("fixAvailable"), dict
                                            )
                                            else None
                                        ),
                                        severity=Severity.from_string(
                                            v.get("severity", severity)
                                        ),
                                        description=v.get("title", "No description"),
                                        url=v.get("url"),
                                    )
                                )

                except json.JSONDecodeError:
                    result.error = "Failed to parse npm audit output"

            # Attempt fix if requested
            if fix and result.vulnerability_count > 0:
                fix_process = await asyncio.create_subprocess_exec(
                    "npm",
                    "audit",
                    "fix",
                    cwd=str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await fix_process.communicate()

        except Exception as e:
            result.error = f"npm audit failed: {str(e)}"

        # Check for outdated packages
        if check_outdated and not result.error:
            await self._check_node_outdated(path, result)

        return result

    async def _check_node_outdated(self, path: Path, result: ScanResult) -> None:
        """Check for outdated Node.js packages."""
        try:
            process = await asyncio.create_subprocess_exec(
                "npm",
                "outdated",
                "--json",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if stdout:
                try:
                    outdated = json.loads(stdout.decode())
                    for name, info in outdated.items():
                        result.dependencies.append(
                            DependencyInfo(
                                name=name,
                                version=info.get("current", "unknown"),
                                latest_version=info.get("latest"),
                                is_outdated=True,
                            )
                        )
                except json.JSONDecodeError:
                    pass

        except Exception:
            pass

    async def _scan_rust(
        self, path: Path, check_outdated: bool, fix: bool
    ) -> ScanResult:
        """Scan Rust project for vulnerabilities."""
        result = ScanResult(
            ecosystem="rust", total_dependencies=0, scanner_tool="cargo audit"
        )

        if not shutil.which("cargo"):
            result.error = "cargo not found. Please install Rust."
            return result

        # Check if cargo-audit is installed
        audit_check = await asyncio.create_subprocess_exec(
            "cargo",
            "audit",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await audit_check.communicate()

        if audit_check.returncode != 0:
            result.error = (
                "cargo-audit not installed. Install with: cargo install cargo-audit"
            )
            return result

        cmd = ["cargo", "audit", "--json"]

        if fix:
            cmd.append("--fix")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stdout:
                try:
                    data = json.loads(stdout.decode())

                    # Parse cargo audit JSON output
                    vulns = data.get("vulnerabilities", {}).get("list", [])

                    for vuln in vulns:
                        advisory = vuln.get("advisory", {})
                        package = vuln.get("package", {})

                        result.vulnerabilities.append(
                            Vulnerability(
                                id=advisory.get("id", "UNKNOWN"),
                                package=package.get("name", "unknown"),
                                installed_version=package.get("version", "unknown"),
                                fixed_version=(
                                    advisory.get("patched_versions", [None])[0]
                                    if advisory.get("patched_versions")
                                    else None
                                ),
                                severity=Severity.from_string(
                                    advisory.get("severity", "unknown")
                                ),
                                description=advisory.get(
                                    "title",
                                    advisory.get("description", "No description"),
                                ),
                                url=advisory.get("url"),
                                aliases=advisory.get("aliases", []),
                            )
                        )

                except json.JSONDecodeError:
                    pass

        except Exception as e:
            result.error = f"cargo audit failed: {str(e)}"

        return result

    async def _scan_go(self, path: Path, check_outdated: bool) -> ScanResult:
        """Scan Go project for vulnerabilities."""
        result = ScanResult(
            ecosystem="go", total_dependencies=0, scanner_tool="govulncheck"
        )

        if not shutil.which("go"):
            result.error = "go not found. Please install Go."
            return result

        # Check if govulncheck is available
        govuln = shutil.which("govulncheck")
        if not govuln:
            result.error = "govulncheck not installed. Install with: go install golang.org/x/vuln/cmd/govulncheck@latest"
            return result

        try:
            process = await asyncio.create_subprocess_exec(
                "govulncheck",
                "-json",
                "./...",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stdout:
                # govulncheck outputs newline-delimited JSON
                for line in stdout.decode().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)

                        # Parse vulnerability entries
                        if data.get("vulnerability"):
                            vuln = data["vulnerability"]
                            osv = vuln.get("osv", {})

                            result.vulnerabilities.append(
                                Vulnerability(
                                    id=osv.get("id", "UNKNOWN"),
                                    package=vuln.get("module", {}).get(
                                        "path", "unknown"
                                    ),
                                    installed_version=vuln.get("module", {}).get(
                                        "version", "unknown"
                                    ),
                                    fixed_version=osv.get("affected", [{}])[0]
                                    .get("ranges", [{}])[0]
                                    .get("events", [{}])[-1]
                                    .get("fixed"),
                                    severity=Severity.from_string(
                                        osv.get("severity", "unknown")
                                    ),
                                    description=osv.get(
                                        "summary", osv.get("details", "No description")
                                    ),
                                    url=f"https://pkg.go.dev/vuln/{osv.get('id', '')}",
                                    aliases=osv.get("aliases", []),
                                )
                            )

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            result.error = f"govulncheck failed: {str(e)}"

        return result

    def _format_text(self, result: ScanResult) -> str:
        """Format scan result as human-readable text."""
        lines = []

        lines.append(f"Dependency Scan Results ({result.ecosystem})")
        lines.append("=" * 50)
        lines.append(f"Scanner: {result.scanner_tool or 'unknown'}")
        lines.append(f"Total Dependencies: {result.total_dependencies}")
        lines.append(f"Vulnerabilities Found: {result.vulnerability_count}")

        if result.vulnerability_count > 0:
            lines.append("")
            lines.append("Severity Breakdown:")
            lines.append(f"  Critical: {result.critical_count}")
            lines.append(f"  High: {result.high_count}")
            lines.append(f"  Medium: {result.medium_count}")
            lines.append(f"  Low: {result.low_count}")

            lines.append("")
            lines.append("Vulnerabilities:")
            lines.append("-" * 50)

            # Sort by severity
            sorted_vulns = sorted(
                result.vulnerabilities, key=lambda v: v.severity.score, reverse=True
            )

            for vuln in sorted_vulns:
                severity_badge = f"[{vuln.severity.value.upper()}]"
                lines.append(f"\n{severity_badge} {vuln.id}")
                lines.append(f"  Package: {vuln.package} ({vuln.installed_version})")
                if vuln.fixed_version:
                    lines.append(f"  Fix: Upgrade to {vuln.fixed_version}")
                lines.append(f"  {vuln.description[:100]}...")
                if vuln.url:
                    lines.append(f"  More info: {vuln.url}")

        if result.outdated_count > 0:
            lines.append("")
            lines.append(f"Outdated Packages: {result.outdated_count}")
            lines.append("-" * 50)

            for dep in result.dependencies:
                if dep.is_outdated:
                    lines.append(f"  {dep.name}: {dep.version} -> {dep.latest_version}")

        if result.vulnerability_count == 0:
            lines.append("")
            lines.append("No vulnerabilities found!")

        return "\n".join(lines)

    def _to_sarif(self, result: ScanResult) -> str:
        """Convert result to SARIF format (for GitHub Security tab)."""
        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": f"sindri-{result.scanner_tool or 'scanner'}",
                            "version": "1.0.0",
                            "rules": [],
                        }
                    },
                    "results": [],
                }
            ],
        }

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        results = sarif["runs"][0]["results"]

        for vuln in result.vulnerabilities:
            # Add rule
            rules.append(
                {
                    "id": vuln.id,
                    "name": f"Vulnerable dependency: {vuln.package}",
                    "shortDescription": {"text": vuln.description[:100]},
                    "fullDescription": {"text": vuln.description},
                    "helpUri": vuln.url,
                    "defaultConfiguration": {
                        "level": "error" if vuln.severity.score >= 3 else "warning"
                    },
                }
            )

            # Add result
            results.append(
                {
                    "ruleId": vuln.id,
                    "level": "error" if vuln.severity.score >= 3 else "warning",
                    "message": {
                        "text": f"{vuln.package} {vuln.installed_version} has vulnerability {vuln.id}"
                    },
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": self._get_manifest_file(result.ecosystem)
                                }
                            }
                        }
                    ],
                }
            )

        return json.dumps(sarif, indent=2)

    def _get_manifest_file(self, ecosystem: str) -> str:
        """Get the manifest file name for an ecosystem."""
        manifest_map = {
            "python": "requirements.txt",
            "node": "package.json",
            "rust": "Cargo.toml",
            "go": "go.mod",
        }
        return manifest_map.get(ecosystem, "unknown")


class GenerateSBOMTool(Tool):
    """Generate Software Bill of Materials (SBOM).

    Creates an SBOM in CycloneDX or SPDX format listing all dependencies.
    """

    name = "generate_sbom"
    description = """Generate a Software Bill of Materials (SBOM) for a project.

Lists all project dependencies with versions, licenses, and metadata.
Supports CycloneDX and SPDX formats.

Examples:
- generate_sbom() - Generate SBOM for current directory
- generate_sbom(format="cyclonedx") - CycloneDX format (default)
- generate_sbom(format="spdx") - SPDX format
- generate_sbom(output="sbom.json") - Save to file"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to project directory"},
            "format": {
                "type": "string",
                "description": "SBOM format: 'cyclonedx' or 'spdx'",
                "enum": ["cyclonedx", "spdx"],
            },
            "output": {"type": "string", "description": "Output file path (optional)"},
            "include_dev": {
                "type": "boolean",
                "description": "Include development dependencies",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        format: str = "cyclonedx",
        output: Optional[str] = None,
        include_dev: bool = True,
        **kwargs,
    ) -> ToolResult:
        """Generate SBOM.

        Args:
            path: Project directory path
            format: Output format (cyclonedx or spdx)
            output: Output file path
            include_dev: Include dev dependencies
        """
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect ecosystem
        ecosystem = self._detect_ecosystem(project_path)
        if not ecosystem:
            return ToolResult(
                success=False, output="", error="Could not detect project ecosystem"
            )

        try:
            # Gather dependencies
            deps = await self._gather_dependencies(project_path, ecosystem, include_dev)

            # Generate SBOM
            if format == "cyclonedx":
                sbom = self._generate_cyclonedx(deps, ecosystem)
            else:
                sbom = self._generate_spdx(deps, ecosystem)

            sbom_json = json.dumps(sbom, indent=2)

            # Write to file if specified
            if output:
                output_path = self._resolve_path(output)
                output_path.write_text(sbom_json)

            return ToolResult(
                success=True,
                output=sbom_json,
                metadata={
                    "format": format,
                    "ecosystem": ecosystem,
                    "dependency_count": len(deps),
                    "output_file": output,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"SBOM generation failed: {str(e)}"
            )

    def _detect_ecosystem(self, path: Path) -> Optional[str]:
        """Detect project ecosystem."""
        if (path / "package.json").exists():
            return "node"
        elif (path / "requirements.txt").exists() or (path / "pyproject.toml").exists():
            return "python"
        elif (path / "Cargo.toml").exists():
            return "rust"
        elif (path / "go.mod").exists():
            return "go"
        return None

    async def _gather_dependencies(
        self, path: Path, ecosystem: str, include_dev: bool
    ) -> list[DependencyInfo]:
        """Gather dependencies for a project."""
        deps = []

        if ecosystem == "python":
            deps = await self._gather_python_deps(path, include_dev)
        elif ecosystem == "node":
            deps = await self._gather_node_deps(path, include_dev)
        elif ecosystem == "rust":
            deps = await self._gather_rust_deps(path)
        elif ecosystem == "go":
            deps = await self._gather_go_deps(path)

        return deps

    async def _gather_python_deps(
        self, path: Path, include_dev: bool
    ) -> list[DependencyInfo]:
        """Gather Python dependencies."""
        deps = []

        try:
            process = await asyncio.create_subprocess_exec(
                "pip",
                "list",
                "--format",
                "json",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if stdout:
                packages = json.loads(stdout.decode())
                for pkg in packages:
                    deps.append(
                        DependencyInfo(
                            name=pkg.get("name", "unknown"),
                            version=pkg.get("version", "unknown"),
                        )
                    )

        except Exception:
            pass

        return deps

    async def _gather_node_deps(
        self, path: Path, include_dev: bool
    ) -> list[DependencyInfo]:
        """Gather Node.js dependencies."""
        deps = []

        try:
            pkg_json = path / "package.json"
            if pkg_json.exists():
                data = json.loads(pkg_json.read_text())

                for name, version in data.get("dependencies", {}).items():
                    deps.append(
                        DependencyInfo(
                            name=name,
                            version=version.lstrip("^~"),
                            is_dev=False,
                        )
                    )

                if include_dev:
                    for name, version in data.get("devDependencies", {}).items():
                        deps.append(
                            DependencyInfo(
                                name=name,
                                version=version.lstrip("^~"),
                                is_dev=True,
                            )
                        )

        except Exception:
            pass

        return deps

    async def _gather_rust_deps(self, path: Path) -> list[DependencyInfo]:
        """Gather Rust dependencies."""
        deps = []

        try:
            process = await asyncio.create_subprocess_exec(
                "cargo",
                "tree",
                "--format",
                "{p} {l}",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if stdout:
                for line in stdout.decode().split("\n"):
                    match = re.match(r"(\S+)\s+v?(\S+)(?:\s+\((.+)\))?", line)
                    if match:
                        deps.append(
                            DependencyInfo(
                                name=match.group(1),
                                version=match.group(2),
                                license=(
                                    match.group(3) if match.lastindex >= 3 else None
                                ),
                            )
                        )

        except Exception:
            pass

        return deps

    async def _gather_go_deps(self, path: Path) -> list[DependencyInfo]:
        """Gather Go dependencies."""
        deps = []

        try:
            process = await asyncio.create_subprocess_exec(
                "go",
                "list",
                "-m",
                "-json",
                "all",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if stdout:
                # go list outputs newline-delimited JSON
                for line in stdout.decode().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        mod = json.loads(line)
                        deps.append(
                            DependencyInfo(
                                name=mod.get("Path", "unknown"),
                                version=mod.get("Version", "unknown"),
                            )
                        )
                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass

        return deps

    def _generate_cyclonedx(self, deps: list[DependencyInfo], ecosystem: str) -> dict:
        """Generate CycloneDX SBOM."""
        import uuid

        components = []
        for dep in deps:
            components.append(
                {
                    "type": "library",
                    "name": dep.name,
                    "version": dep.version,
                    "purl": self._get_purl(dep, ecosystem),
                }
            )

        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "tools": [
                    {
                        "vendor": "Sindri",
                        "name": "dependency-scanner",
                        "version": "1.0.0",
                    }
                ],
            },
            "components": components,
        }

    def _generate_spdx(self, deps: list[DependencyInfo], ecosystem: str) -> dict:
        """Generate SPDX SBOM."""
        import uuid

        packages = []
        for dep in deps:
            packages.append(
                {
                    "SPDXID": f"SPDXRef-{dep.name.replace('/', '-')}",
                    "name": dep.name,
                    "versionInfo": dep.version,
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE_MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": self._get_purl(dep, ecosystem),
                        }
                    ],
                }
            )

        return {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "sindri-sbom",
            "documentNamespace": f"https://sindri.local/sbom/{uuid.uuid4()}",
            "creationInfo": {
                "created": datetime.now().isoformat(),
                "creators": ["Tool: sindri-dependency-scanner-1.0.0"],
            },
            "packages": packages,
        }

    def _get_purl(self, dep: DependencyInfo, ecosystem: str) -> str:
        """Get Package URL (purl) for a dependency."""
        purl_type_map = {
            "python": "pypi",
            "node": "npm",
            "rust": "cargo",
            "go": "golang",
        }
        purl_type = purl_type_map.get(ecosystem, "generic")
        return f"pkg:{purl_type}/{dep.name}@{dep.version}"


class CheckOutdatedTool(Tool):
    """Check for outdated dependencies.

    Lists packages that have newer versions available.
    """

    name = "check_outdated"
    description = """Check for outdated dependencies in a project.

Lists all packages that have newer versions available.

Examples:
- check_outdated() - Check current directory
- check_outdated(path="/project") - Check specific project
- check_outdated(include_dev=false) - Exclude dev dependencies"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to project directory"},
            "include_dev": {
                "type": "boolean",
                "description": "Include development dependencies",
            },
        },
        "required": [],
    }

    async def execute(
        self, path: Optional[str] = None, include_dev: bool = True, **kwargs
    ) -> ToolResult:
        """Check for outdated dependencies."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect ecosystem
        ecosystem = self._detect_ecosystem(project_path)
        if not ecosystem:
            return ToolResult(
                success=False, output="", error="Could not detect project ecosystem"
            )

        try:
            outdated = await self._check_outdated(project_path, ecosystem, include_dev)

            if not outdated:
                return ToolResult(
                    success=True,
                    output="All dependencies are up to date!",
                    metadata={"outdated_count": 0, "ecosystem": ecosystem},
                )

            # Format output
            lines = [f"Outdated Dependencies ({ecosystem})", "=" * 40]

            for dep in outdated:
                lines.append(f"  {dep.name}: {dep.version} -> {dep.latest_version}")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                metadata={
                    "outdated_count": len(outdated),
                    "ecosystem": ecosystem,
                    "packages": [
                        {
                            "name": d.name,
                            "current": d.version,
                            "latest": d.latest_version,
                        }
                        for d in outdated
                    ],
                },
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Check failed: {str(e)}")

    def _detect_ecosystem(self, path: Path) -> Optional[str]:
        """Detect project ecosystem."""
        if (path / "package.json").exists():
            return "node"
        elif (path / "requirements.txt").exists() or (path / "pyproject.toml").exists():
            return "python"
        elif (path / "Cargo.toml").exists():
            return "rust"
        elif (path / "go.mod").exists():
            return "go"
        return None

    async def _check_outdated(
        self, path: Path, ecosystem: str, include_dev: bool
    ) -> list[DependencyInfo]:
        """Check for outdated packages."""
        outdated = []

        if ecosystem == "python":
            try:
                process = await asyncio.create_subprocess_exec(
                    "pip",
                    "list",
                    "--outdated",
                    "--format",
                    "json",
                    cwd=str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()

                if stdout:
                    for pkg in json.loads(stdout.decode()):
                        outdated.append(
                            DependencyInfo(
                                name=pkg.get("name"),
                                version=pkg.get("version"),
                                latest_version=pkg.get("latest_version"),
                                is_outdated=True,
                            )
                        )
            except Exception:
                pass

        elif ecosystem == "node":
            try:
                process = await asyncio.create_subprocess_exec(
                    "npm",
                    "outdated",
                    "--json",
                    cwd=str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()

                if stdout:
                    try:
                        data = json.loads(stdout.decode())
                        for name, info in data.items():
                            outdated.append(
                                DependencyInfo(
                                    name=name,
                                    version=info.get("current", "unknown"),
                                    latest_version=info.get("latest"),
                                    is_outdated=True,
                                )
                            )
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        elif ecosystem == "rust":
            # cargo outdated requires cargo-outdated to be installed
            try:
                process = await asyncio.create_subprocess_exec(
                    "cargo",
                    "outdated",
                    "--format",
                    "json",
                    cwd=str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()

                if stdout:
                    try:
                        data = json.loads(stdout.decode())
                        for dep in data.get("dependencies", []):
                            if dep.get("project") != dep.get("latest"):
                                outdated.append(
                                    DependencyInfo(
                                        name=dep.get("name"),
                                        version=dep.get("project"),
                                        latest_version=dep.get("latest"),
                                        is_outdated=True,
                                    )
                                )
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        elif ecosystem == "go":
            try:
                process = await asyncio.create_subprocess_exec(
                    "go",
                    "list",
                    "-u",
                    "-m",
                    "-json",
                    "all",
                    cwd=str(path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()

                if stdout:
                    for line in stdout.decode().split("\n"):
                        if not line.strip():
                            continue
                        try:
                            mod = json.loads(line)
                            if mod.get("Update"):
                                outdated.append(
                                    DependencyInfo(
                                        name=mod.get("Path"),
                                        version=mod.get("Version"),
                                        latest_version=mod.get("Update", {}).get(
                                            "Version"
                                        ),
                                        is_outdated=True,
                                    )
                                )
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

        return outdated
