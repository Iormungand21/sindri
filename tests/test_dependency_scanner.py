"""Tests for dependency scanner tools (Phase 9.4)."""

import pytest
import pytest_asyncio
import asyncio
import json
import tempfile
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from sindri.tools.dependency_scanner import (
    Severity,
    Vulnerability,
    DependencyInfo,
    ScanResult,
    ScanDependenciesTool,
    GenerateSBOMTool,
    CheckOutdatedTool,
)
from sindri.tools.base import ToolResult


# ============================================
# Severity Enum Tests
# ============================================


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test all severity values exist."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.UNKNOWN.value == "unknown"

    def test_from_string_critical(self):
        """Test parsing critical severity."""
        assert Severity.from_string("critical") == Severity.CRITICAL
        assert Severity.from_string("CRITICAL") == Severity.CRITICAL
        assert Severity.from_string("crit") == Severity.CRITICAL

    def test_from_string_high(self):
        """Test parsing high severity."""
        assert Severity.from_string("high") == Severity.HIGH
        assert Severity.from_string("HIGH") == Severity.HIGH
        assert Severity.from_string("important") == Severity.HIGH

    def test_from_string_medium(self):
        """Test parsing medium severity."""
        assert Severity.from_string("medium") == Severity.MEDIUM
        assert Severity.from_string("moderate") == Severity.MEDIUM
        assert Severity.from_string("mod") == Severity.MEDIUM

    def test_from_string_low(self):
        """Test parsing low severity."""
        assert Severity.from_string("low") == Severity.LOW
        assert Severity.from_string("minor") == Severity.LOW

    def test_from_string_unknown(self):
        """Test parsing unknown severity."""
        assert Severity.from_string("unknown") == Severity.UNKNOWN
        assert Severity.from_string("other") == Severity.UNKNOWN
        assert Severity.from_string("") == Severity.UNKNOWN

    def test_severity_score(self):
        """Test severity scores for sorting."""
        assert Severity.CRITICAL.score == 4
        assert Severity.HIGH.score == 3
        assert Severity.MEDIUM.score == 2
        assert Severity.LOW.score == 1
        assert Severity.UNKNOWN.score == 0

    def test_severity_sorting(self):
        """Test sorting by severity."""
        severities = [Severity.LOW, Severity.CRITICAL, Severity.MEDIUM, Severity.HIGH]
        sorted_sevs = sorted(severities, key=lambda s: s.score, reverse=True)
        assert sorted_sevs == [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]


# ============================================
# Vulnerability Dataclass Tests
# ============================================


class TestVulnerability:
    """Tests for Vulnerability dataclass."""

    def test_vulnerability_basic(self):
        """Test basic vulnerability creation."""
        vuln = Vulnerability(
            id="CVE-2023-1234",
            package="requests",
            installed_version="2.25.0",
            fixed_version="2.31.0",
            severity=Severity.HIGH,
            description="Remote code execution vulnerability",
        )
        assert vuln.id == "CVE-2023-1234"
        assert vuln.package == "requests"
        assert vuln.installed_version == "2.25.0"
        assert vuln.fixed_version == "2.31.0"
        assert vuln.severity == Severity.HIGH
        assert "Remote code execution" in vuln.description

    def test_vulnerability_with_url(self):
        """Test vulnerability with URL."""
        vuln = Vulnerability(
            id="GHSA-1234",
            package="lodash",
            installed_version="4.17.0",
            fixed_version="4.17.21",
            severity=Severity.CRITICAL,
            description="Prototype pollution",
            url="https://github.com/advisories/GHSA-1234",
        )
        assert vuln.url == "https://github.com/advisories/GHSA-1234"

    def test_vulnerability_with_aliases(self):
        """Test vulnerability with aliases."""
        vuln = Vulnerability(
            id="CVE-2023-1234",
            package="example",
            installed_version="1.0.0",
            fixed_version=None,
            severity=Severity.MEDIUM,
            description="Test",
            aliases=["GHSA-5678", "OSV-2023-001"],
        )
        assert len(vuln.aliases) == 2
        assert "GHSA-5678" in vuln.aliases

    def test_vulnerability_no_fix(self):
        """Test vulnerability without fix version."""
        vuln = Vulnerability(
            id="CVE-2023-0000",
            package="unfixable",
            installed_version="1.0.0",
            fixed_version=None,
            severity=Severity.LOW,
            description="No fix available",
        )
        assert vuln.fixed_version is None


# ============================================
# DependencyInfo Dataclass Tests
# ============================================


class TestDependencyInfo:
    """Tests for DependencyInfo dataclass."""

    def test_dependency_basic(self):
        """Test basic dependency info."""
        dep = DependencyInfo(name="requests", version="2.31.0")
        assert dep.name == "requests"
        assert dep.version == "2.31.0"
        assert dep.latest_version is None
        assert not dep.is_outdated
        assert not dep.is_dev

    def test_dependency_outdated(self):
        """Test outdated dependency."""
        dep = DependencyInfo(
            name="requests",
            version="2.25.0",
            latest_version="2.31.0",
            is_outdated=True,
        )
        assert dep.is_outdated
        assert dep.latest_version == "2.31.0"

    def test_dependency_dev(self):
        """Test dev dependency."""
        dep = DependencyInfo(
            name="pytest",
            version="7.0.0",
            is_dev=True,
        )
        assert dep.is_dev

    def test_dependency_with_license(self):
        """Test dependency with license."""
        dep = DependencyInfo(
            name="requests",
            version="2.31.0",
            license="Apache-2.0",
        )
        assert dep.license == "Apache-2.0"


# ============================================
# ScanResult Dataclass Tests
# ============================================


class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_scan_result_empty(self):
        """Test empty scan result."""
        result = ScanResult(ecosystem="python", total_dependencies=0)
        assert result.ecosystem == "python"
        assert result.total_dependencies == 0
        assert result.vulnerability_count == 0
        assert result.critical_count == 0
        assert result.high_count == 0
        assert result.medium_count == 0
        assert result.low_count == 0

    def test_scan_result_with_vulnerabilities(self):
        """Test scan result with vulnerabilities."""
        result = ScanResult(
            ecosystem="node",
            total_dependencies=50,
            vulnerabilities=[
                Vulnerability("CVE-1", "pkg1", "1.0", "1.1", Severity.CRITICAL, "Critical"),
                Vulnerability("CVE-2", "pkg2", "2.0", "2.1", Severity.HIGH, "High"),
                Vulnerability("CVE-3", "pkg3", "3.0", "3.1", Severity.MEDIUM, "Medium"),
                Vulnerability("CVE-4", "pkg4", "4.0", "4.1", Severity.LOW, "Low"),
                Vulnerability("CVE-5", "pkg5", "5.0", "5.1", Severity.LOW, "Low2"),
            ]
        )
        assert result.vulnerability_count == 5
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.low_count == 2

    def test_scan_result_outdated_count(self):
        """Test outdated count."""
        result = ScanResult(
            ecosystem="python",
            total_dependencies=10,
            dependencies=[
                DependencyInfo("pkg1", "1.0", "2.0", is_outdated=True),
                DependencyInfo("pkg2", "2.0", "2.0", is_outdated=False),
                DependencyInfo("pkg3", "1.0", "3.0", is_outdated=True),
            ]
        )
        assert result.outdated_count == 2

    def test_scan_result_to_dict(self):
        """Test to_dict serialization."""
        result = ScanResult(
            ecosystem="python",
            total_dependencies=10,
            vulnerabilities=[
                Vulnerability("CVE-1", "pkg1", "1.0", "1.1", Severity.HIGH, "Test"),
            ],
            scanner_tool="pip-audit",
        )
        data = result.to_dict()

        assert data["ecosystem"] == "python"
        assert data["total_dependencies"] == 10
        assert data["vulnerability_count"] == 1
        assert data["severity_breakdown"]["high"] == 1
        assert len(data["vulnerabilities"]) == 1
        assert data["scanner_tool"] == "pip-audit"


# ============================================
# ScanDependenciesTool Tests
# ============================================


class TestScanDependenciesTool:
    """Tests for ScanDependenciesTool."""

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = ScanDependenciesTool()
        assert tool.name == "scan_dependencies"
        assert "vulnerability" in tool.description.lower()
        assert "python" in tool.description.lower()
        assert "node" in tool.description.lower()

    def test_tool_parameters(self):
        """Test tool parameters schema."""
        tool = ScanDependenciesTool()
        params = tool.parameters["properties"]
        assert "path" in params
        assert "ecosystem" in params
        assert "min_severity" in params
        assert "format" in params

    @pytest.mark.asyncio
    async def test_detect_python_ecosystem(self):
        """Test Python ecosystem detection."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create requirements.txt
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\n")

            ecosystem = tool._detect_ecosystem(Path(tmpdir))
            assert ecosystem == "python"

    @pytest.mark.asyncio
    async def test_detect_node_ecosystem(self):
        """Test Node.js ecosystem detection."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create package.json
            (Path(tmpdir) / "package.json").write_text('{"name": "test"}')

            ecosystem = tool._detect_ecosystem(Path(tmpdir))
            assert ecosystem == "node"

    @pytest.mark.asyncio
    async def test_detect_rust_ecosystem(self):
        """Test Rust ecosystem detection."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Cargo.toml
            (Path(tmpdir) / "Cargo.toml").write_text('[package]\nname = "test"')

            ecosystem = tool._detect_ecosystem(Path(tmpdir))
            assert ecosystem == "rust"

    @pytest.mark.asyncio
    async def test_detect_go_ecosystem(self):
        """Test Go ecosystem detection."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create go.mod
            (Path(tmpdir) / "go.mod").write_text("module example.com/test")

            ecosystem = tool._detect_ecosystem(Path(tmpdir))
            assert ecosystem == "go"

    @pytest.mark.asyncio
    async def test_detect_no_ecosystem(self):
        """Test no ecosystem detected."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            ecosystem = tool._detect_ecosystem(Path(tmpdir))
            assert ecosystem is None

    @pytest.mark.asyncio
    async def test_execute_nonexistent_path(self):
        """Test execution with nonexistent path."""
        tool = ScanDependenciesTool()
        result = await tool.execute(path="/nonexistent/path")
        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_ecosystem(self):
        """Test execution when no ecosystem detected."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute(path=tmpdir)
            assert not result.success
            assert "Could not detect" in result.error

    @pytest.mark.asyncio
    async def test_format_text_no_vulnerabilities(self):
        """Test text formatting with no vulnerabilities."""
        tool = ScanDependenciesTool()
        result = ScanResult(
            ecosystem="python",
            total_dependencies=10,
            scanner_tool="pip-audit",
        )
        output = tool._format_text(result)
        assert "Dependency Scan Results" in output
        assert "python" in output
        assert "Vulnerabilities Found: 0" in output
        assert "No vulnerabilities found" in output

    @pytest.mark.asyncio
    async def test_format_text_with_vulnerabilities(self):
        """Test text formatting with vulnerabilities."""
        tool = ScanDependenciesTool()
        result = ScanResult(
            ecosystem="python",
            total_dependencies=10,
            vulnerabilities=[
                Vulnerability("CVE-2023-1234", "requests", "2.25.0", "2.31.0", Severity.HIGH, "Test vulnerability"),
            ],
            scanner_tool="pip-audit",
        )
        output = tool._format_text(result)
        assert "CVE-2023-1234" in output
        assert "[HIGH]" in output
        assert "requests" in output
        assert "Upgrade to 2.31.0" in output

    @pytest.mark.asyncio
    async def test_to_sarif_format(self):
        """Test SARIF output format."""
        tool = ScanDependenciesTool()
        result = ScanResult(
            ecosystem="python",
            total_dependencies=10,
            vulnerabilities=[
                Vulnerability("CVE-2023-1234", "requests", "2.25.0", "2.31.0", Severity.HIGH, "Test"),
            ],
        )
        sarif = tool._to_sarif(result)
        data = json.loads(sarif)

        assert data["version"] == "2.1.0"
        assert "runs" in data
        assert len(data["runs"]) == 1
        assert len(data["runs"][0]["results"]) == 1

    @pytest.mark.asyncio
    async def test_severity_filtering(self):
        """Test severity filtering."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\n")

            # Mock the scan to return vulnerabilities
            with patch.object(tool, '_scan_python', new_callable=AsyncMock) as mock_scan:
                mock_scan.return_value = ScanResult(
                    ecosystem="python",
                    total_dependencies=1,
                    vulnerabilities=[
                        Vulnerability("CVE-1", "pkg1", "1.0", "1.1", Severity.CRITICAL, "Critical"),
                        Vulnerability("CVE-2", "pkg2", "1.0", "1.1", Severity.HIGH, "High"),
                        Vulnerability("CVE-3", "pkg3", "1.0", "1.1", Severity.MEDIUM, "Medium"),
                        Vulnerability("CVE-4", "pkg4", "1.0", "1.1", Severity.LOW, "Low"),
                    ]
                )

                # Filter to high and above
                result = await tool.execute(path=tmpdir, min_severity="high")
                assert result.success
                assert result.metadata["vulnerability_count"] == 2  # Only critical and high

    @pytest.mark.asyncio
    async def test_pip_audit_mock(self):
        """Test pip-audit execution with mock."""
        tool = ScanDependenciesTool()

        pip_audit_output = json.dumps({
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.25.0",
                    "vulns": [
                        {
                            "id": "PYSEC-2023-001",
                            "severity": "high",
                            "description": "Test vulnerability",
                            "fix_versions": ["2.31.0"],
                        }
                    ]
                }
            ]
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('shutil.which', return_value="/usr/bin/pip-audit"):
                with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
                    mock_process = AsyncMock()
                    mock_process.communicate = AsyncMock(return_value=(pip_audit_output.encode(), b""))
                    mock_process.returncode = 0
                    mock_exec.return_value = mock_process

                    result = await tool._run_pip_audit(Path(tmpdir), True, False, False)
                    assert result.ecosystem == "python"
                    assert result.scanner_tool == "pip-audit"


# ============================================
# GenerateSBOMTool Tests
# ============================================


class TestGenerateSBOMTool:
    """Tests for GenerateSBOMTool."""

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = GenerateSBOMTool()
        assert tool.name == "generate_sbom"
        assert "SBOM" in tool.description
        assert "CycloneDX" in tool.description
        assert "SPDX" in tool.description

    @pytest.mark.asyncio
    async def test_execute_nonexistent_path(self):
        """Test execution with nonexistent path."""
        tool = GenerateSBOMTool()
        result = await tool.execute(path="/nonexistent/path")
        assert not result.success

    @pytest.mark.asyncio
    async def test_cyclonedx_format(self):
        """Test CycloneDX SBOM generation."""
        tool = GenerateSBOMTool()

        deps = [
            DependencyInfo("requests", "2.31.0"),
            DependencyInfo("click", "8.0.0"),
        ]

        sbom = tool._generate_cyclonedx(deps, "python")
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.4"
        assert len(sbom["components"]) == 2
        assert sbom["components"][0]["name"] == "requests"
        assert "purl" in sbom["components"][0]

    @pytest.mark.asyncio
    async def test_spdx_format(self):
        """Test SPDX SBOM generation."""
        tool = GenerateSBOMTool()

        deps = [
            DependencyInfo("requests", "2.31.0"),
        ]

        sbom = tool._generate_spdx(deps, "python")
        assert sbom["spdxVersion"] == "SPDX-2.3"
        assert len(sbom["packages"]) == 1
        assert sbom["packages"][0]["name"] == "requests"

    @pytest.mark.asyncio
    async def test_purl_generation(self):
        """Test Package URL generation."""
        tool = GenerateSBOMTool()

        dep = DependencyInfo("requests", "2.31.0")

        purl_python = tool._get_purl(dep, "python")
        assert purl_python == "pkg:pypi/requests@2.31.0"

        purl_node = tool._get_purl(dep, "node")
        assert purl_node == "pkg:npm/requests@2.31.0"

        purl_rust = tool._get_purl(dep, "rust")
        assert purl_rust == "pkg:cargo/requests@2.31.0"

        purl_go = tool._get_purl(dep, "go")
        assert purl_go == "pkg:golang/requests@2.31.0"

    @pytest.mark.asyncio
    async def test_gather_python_deps_mock(self):
        """Test gathering Python dependencies."""
        tool = GenerateSBOMTool()

        pip_list_output = json.dumps([
            {"name": "requests", "version": "2.31.0"},
            {"name": "click", "version": "8.0.0"},
        ])

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(pip_list_output.encode(), b""))
            mock_exec.return_value = mock_process

            with tempfile.TemporaryDirectory() as tmpdir:
                deps = await tool._gather_python_deps(Path(tmpdir), True)
                assert len(deps) == 2
                assert deps[0].name == "requests"

    @pytest.mark.asyncio
    async def test_gather_node_deps(self):
        """Test gathering Node.js dependencies."""
        tool = GenerateSBOMTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            package_json = {
                "name": "test",
                "dependencies": {
                    "express": "^4.18.0",
                    "lodash": "^4.17.21",
                },
                "devDependencies": {
                    "jest": "^29.0.0",
                }
            }
            (Path(tmpdir) / "package.json").write_text(json.dumps(package_json))

            deps = await tool._gather_node_deps(Path(tmpdir), True)
            assert len(deps) == 3

            deps_no_dev = await tool._gather_node_deps(Path(tmpdir), False)
            assert len(deps_no_dev) == 2

    @pytest.mark.asyncio
    async def test_sbom_output_to_file(self):
        """Test SBOM output to file."""
        tool = GenerateSBOMTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create requirements.txt
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\n")

            output_file = Path(tmpdir) / "sbom.json"

            # Mock pip list
            with patch.object(tool, '_gather_dependencies', new_callable=AsyncMock) as mock_gather:
                mock_gather.return_value = [DependencyInfo("requests", "2.31.0")]

                result = await tool.execute(
                    path=tmpdir,
                    format="cyclonedx",
                    output=str(output_file),
                )

                assert result.success
                assert output_file.exists()

                # Verify file content
                sbom_data = json.loads(output_file.read_text())
                assert sbom_data["bomFormat"] == "CycloneDX"


# ============================================
# CheckOutdatedTool Tests
# ============================================


class TestCheckOutdatedTool:
    """Tests for CheckOutdatedTool."""

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = CheckOutdatedTool()
        assert tool.name == "check_outdated"
        assert "outdated" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_execute_nonexistent_path(self):
        """Test execution with nonexistent path."""
        tool = CheckOutdatedTool()
        result = await tool.execute(path="/nonexistent/path")
        assert not result.success

    @pytest.mark.asyncio
    async def test_all_up_to_date(self):
        """Test when all packages are up to date."""
        tool = CheckOutdatedTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\n")

            with patch.object(tool, '_check_outdated', new_callable=AsyncMock) as mock_check:
                mock_check.return_value = []

                result = await tool.execute(path=tmpdir)
                assert result.success
                assert "up to date" in result.output.lower()
                assert result.metadata["outdated_count"] == 0

    @pytest.mark.asyncio
    async def test_outdated_packages(self):
        """Test when packages are outdated."""
        tool = CheckOutdatedTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.25.0\n")

            with patch.object(tool, '_check_outdated', new_callable=AsyncMock) as mock_check:
                mock_check.return_value = [
                    DependencyInfo("requests", "2.25.0", "2.31.0", is_outdated=True),
                ]

                result = await tool.execute(path=tmpdir)
                assert result.success
                assert result.metadata["outdated_count"] == 1
                assert "requests" in result.output

    @pytest.mark.asyncio
    async def test_python_outdated_mock(self):
        """Test Python outdated check with mock."""
        tool = CheckOutdatedTool()

        pip_outdated_output = json.dumps([
            {"name": "requests", "version": "2.25.0", "latest_version": "2.31.0"},
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.25.0\n")

            with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(return_value=(pip_outdated_output.encode(), b""))
                mock_exec.return_value = mock_process

                outdated = await tool._check_outdated(Path(tmpdir), "python", True)
                assert len(outdated) == 1
                assert outdated[0].name == "requests"
                assert outdated[0].is_outdated


# ============================================
# Integration Tests
# ============================================


class TestDependencyScannerIntegration:
    """Integration tests for dependency scanner."""

    @pytest.mark.asyncio
    async def test_full_scan_workflow(self):
        """Test complete scan workflow."""
        scan_tool = ScanDependenciesTool()
        sbom_tool = GenerateSBOMTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Python project
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\nclick==8.0.0\n")

            # Mock the scan
            with patch.object(scan_tool, '_scan_python', new_callable=AsyncMock) as mock_scan:
                mock_scan.return_value = ScanResult(
                    ecosystem="python",
                    total_dependencies=2,
                    vulnerabilities=[],
                    scanner_tool="pip-audit",
                )

                # Run scan
                scan_result = await scan_tool.execute(path=tmpdir)
                assert scan_result.success
                assert scan_result.metadata["ecosystem"] == "python"

            # Mock SBOM generation
            with patch.object(sbom_tool, '_gather_dependencies', new_callable=AsyncMock) as mock_gather:
                mock_gather.return_value = [
                    DependencyInfo("requests", "2.31.0"),
                    DependencyInfo("click", "8.0.0"),
                ]

                # Generate SBOM
                sbom_result = await sbom_tool.execute(path=tmpdir, format="cyclonedx")
                assert sbom_result.success
                assert sbom_result.metadata["dependency_count"] == 2

    @pytest.mark.asyncio
    async def test_json_output_format(self):
        """Test JSON output format."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\n")

            with patch.object(tool, '_scan_python', new_callable=AsyncMock) as mock_scan:
                mock_scan.return_value = ScanResult(
                    ecosystem="python",
                    total_dependencies=1,
                    vulnerabilities=[
                        Vulnerability("CVE-1", "requests", "2.25.0", "2.31.0", Severity.HIGH, "Test"),
                    ],
                    scanner_tool="pip-audit",
                )

                result = await tool.execute(path=tmpdir, format="json")
                assert result.success

                # Should be valid JSON
                data = json.loads(result.output)
                assert data["ecosystem"] == "python"
                assert len(data["vulnerabilities"]) == 1


# ============================================
# Error Handling Tests
# ============================================


class TestDependencyScannerErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_scanner_not_found_python(self):
        """Test when no Python scanner is available."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("requests==2.31.0\n")

            with patch('shutil.which', return_value=None):
                result = await tool._scan_python(Path(tmpdir), True, False, False)
                assert result.error is not None
                assert "pip-audit" in result.error

    @pytest.mark.asyncio
    async def test_scanner_not_found_node(self):
        """Test when npm is not available."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package.json").write_text('{"name": "test"}')

            with patch('shutil.which', return_value=None):
                result = await tool._scan_node(Path(tmpdir), True, False, False)
                assert result.error is not None
                assert "npm" in result.error

    @pytest.mark.asyncio
    async def test_scanner_not_found_rust(self):
        """Test when cargo is not available."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "Cargo.toml").write_text('[package]\nname = "test"')

            with patch('shutil.which', return_value=None):
                result = await tool._scan_rust(Path(tmpdir), False, False)
                assert result.error is not None
                assert "cargo" in result.error.lower()

    @pytest.mark.asyncio
    async def test_scanner_not_found_go(self):
        """Test when go is not available."""
        tool = ScanDependenciesTool()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "go.mod").write_text("module example.com/test")

            with patch('shutil.which', return_value=None):
                result = await tool._scan_go(Path(tmpdir), False)
                assert result.error is not None
                assert "go" in result.error.lower()


# ============================================
# Manifest File Detection Tests
# ============================================


class TestManifestFileDetection:
    """Tests for manifest file detection."""

    def test_get_manifest_file_python(self):
        """Test manifest file for Python."""
        tool = ScanDependenciesTool()
        assert tool._get_manifest_file("python") == "requirements.txt"

    def test_get_manifest_file_node(self):
        """Test manifest file for Node.js."""
        tool = ScanDependenciesTool()
        assert tool._get_manifest_file("node") == "package.json"

    def test_get_manifest_file_rust(self):
        """Test manifest file for Rust."""
        tool = ScanDependenciesTool()
        assert tool._get_manifest_file("rust") == "Cargo.toml"

    def test_get_manifest_file_go(self):
        """Test manifest file for Go."""
        tool = ScanDependenciesTool()
        assert tool._get_manifest_file("go") == "go.mod"

    def test_get_manifest_file_unknown(self):
        """Test manifest file for unknown ecosystem."""
        tool = ScanDependenciesTool()
        assert tool._get_manifest_file("unknown") == "unknown"
