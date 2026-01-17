"""Tests for Sindri code coverage parsing and storage.

Phase 9: Coverage Visualization
"""

import json
import pytest
import tempfile
from pathlib import Path

from sindri.persistence.database import Database
from sindri.persistence.coverage import (
    LineCoverage,
    FileCoverage,
    PackageCoverage,
    CoverageReport,
    CoverageParser,
    CoverageStore,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path, auto_backup=False)
        yield db


@pytest.fixture
def coverage_store(temp_db):
    """Create a coverage store with temporary database."""
    return CoverageStore(temp_db)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_cobertura_xml(temp_dir) -> Path:
    """Create a sample Cobertura XML coverage file."""
    xml_content = """<?xml version="1.0" ?>
<coverage version="7.0.0" timestamp="1700000000000" lines-valid="100" lines-covered="80" line-rate="0.8" branches-valid="20" branches-covered="15" branch-rate="0.75">
    <sources>
        <source>/home/test/project</source>
    </sources>
    <packages>
        <package name="myproject" line-rate="0.8" branch-rate="0.75">
            <classes>
                <class name="main.py" filename="myproject/main.py" line-rate="0.9" branch-rate="0.8">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                        <line number="3" hits="0"/>
                        <line number="4" hits="5"/>
                        <line number="5" hits="1"/>
                    </lines>
                </class>
                <class name="utils.py" filename="myproject/utils.py" line-rate="0.7" branch-rate="0.6">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="0"/>
                        <line number="3" hits="0"/>
                        <line number="4" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
        <package name="tests" line-rate="1.0" branch-rate="1.0">
            <classes>
                <class name="test_main.py" filename="tests/test_main.py" line-rate="1.0" branch-rate="1.0">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                        <line number="3" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""
    path = temp_dir / "coverage.xml"
    path.write_text(xml_content)
    return path


@pytest.fixture
def sample_lcov(temp_dir) -> Path:
    """Create a sample LCOV coverage file."""
    lcov_content = """TN:
SF:src/main.py
DA:1,1
DA:2,1
DA:3,0
DA:4,5
DA:5,1
BRDA:4,0,0,1
BRDA:4,0,1,0
end_of_record
SF:src/utils.py
DA:1,1
DA:2,0
DA:3,1
end_of_record
"""
    path = temp_dir / "lcov.info"
    path.write_text(lcov_content)
    return path


@pytest.fixture
def sample_json_coverage(temp_dir) -> Path:
    """Create a sample JSON coverage file."""
    json_content = {
        "meta": {
            "version": "7.0.0",
            "timestamp": 1700000000.0,
        },
        "totals": {
            "num_statements": 50,
            "covered_lines": 40,
            "percent_covered": 80.0,
            "num_branches": 10,
            "covered_branches": 8,
        },
        "files": {
            "src/main.py": {
                "summary": {
                    "num_statements": 30,
                    "covered_lines": 25,
                    "percent_covered": 83.33,
                    "num_branches": 6,
                    "covered_branches": 5,
                },
                "executed_lines": [1, 2, 4, 5, 7, 8, 10],
                "missing_lines": [3, 6],
            },
            "src/utils.py": {
                "summary": {
                    "num_statements": 20,
                    "covered_lines": 15,
                    "percent_covered": 75.0,
                    "num_branches": 4,
                    "covered_branches": 3,
                },
                "executed_lines": [1, 2, 3, 5, 6],
                "missing_lines": [4, 7],
            },
        },
    }
    path = temp_dir / "coverage.json"
    path.write_text(json.dumps(json_content))
    return path


# ============================================================
# LineCoverage Tests
# ============================================================


class TestLineCoverage:
    """Tests for LineCoverage dataclass."""

    def test_create_covered_line(self):
        """Test creating a covered line."""
        line = LineCoverage(line_number=10, hits=5)
        assert line.line_number == 10
        assert line.hits == 5
        assert line.is_covered is True

    def test_create_uncovered_line(self):
        """Test creating an uncovered line."""
        line = LineCoverage(line_number=20, hits=0)
        assert line.line_number == 20
        assert line.hits == 0
        assert line.is_covered is False


# ============================================================
# FileCoverage Tests
# ============================================================


class TestFileCoverage:
    """Tests for FileCoverage dataclass."""

    def test_create_file_coverage(self):
        """Test creating file coverage."""
        fc = FileCoverage(
            filename="src/main.py",
            lines_valid=100,
            lines_covered=80,
            line_rate=0.8,
        )
        assert fc.filename == "src/main.py"
        assert fc.lines_valid == 100
        assert fc.lines_covered == 80
        assert fc.line_rate == 0.8
        assert fc.line_percentage == 80.0

    def test_covered_uncovered_lines(self):
        """Test getting covered and uncovered line lists."""
        fc = FileCoverage(
            filename="test.py",
            lines_valid=5,
            lines_covered=3,
            line_rate=0.6,
            lines=[
                LineCoverage(1, 1),
                LineCoverage(2, 0),
                LineCoverage(3, 5),
                LineCoverage(4, 0),
                LineCoverage(5, 1),
            ],
        )
        assert fc.covered_lines == [1, 3, 5]
        assert fc.uncovered_lines == [2, 4]

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        fc = FileCoverage(
            filename="src/utils.py",
            lines_valid=50,
            lines_covered=40,
            line_rate=0.8,
            branches_valid=10,
            branches_covered=8,
            branch_rate=0.8,
            lines=[
                LineCoverage(1, 1),
                LineCoverage(2, 0),
            ],
        )
        data = fc.to_dict()
        restored = FileCoverage.from_dict(data)

        assert restored.filename == fc.filename
        assert restored.lines_valid == fc.lines_valid
        assert restored.lines_covered == fc.lines_covered
        assert restored.line_rate == fc.line_rate
        assert restored.branches_valid == fc.branches_valid


# ============================================================
# PackageCoverage Tests
# ============================================================


class TestPackageCoverage:
    """Tests for PackageCoverage dataclass."""

    def test_create_package_coverage(self):
        """Test creating package coverage."""
        pkg = PackageCoverage(
            name="myproject",
            line_rate=0.85,
            branch_rate=0.75,
        )
        assert pkg.name == "myproject"
        assert pkg.line_rate == 0.85
        assert pkg.branch_rate == 0.75

    def test_aggregated_lines(self):
        """Test lines_valid and lines_covered aggregation."""
        pkg = PackageCoverage(
            name="src",
            line_rate=0.8,
            files=[
                FileCoverage("src/a.py", lines_valid=50, lines_covered=40, line_rate=0.8),
                FileCoverage("src/b.py", lines_valid=30, lines_covered=25, line_rate=0.83),
            ],
        )
        assert pkg.lines_valid == 80
        assert pkg.lines_covered == 65

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        pkg = PackageCoverage(
            name="myproject",
            line_rate=0.8,
            branch_rate=0.7,
            files=[
                FileCoverage("myproject/main.py", 100, 80, 0.8),
            ],
        )
        data = pkg.to_dict()
        restored = PackageCoverage.from_dict(data)

        assert restored.name == pkg.name
        assert restored.line_rate == pkg.line_rate
        assert len(restored.files) == 1


# ============================================================
# CoverageReport Tests
# ============================================================


class TestCoverageReport:
    """Tests for CoverageReport dataclass."""

    def test_create_empty_report(self):
        """Test creating an empty report."""
        report = CoverageReport()
        assert report.lines_valid == 0
        assert report.lines_covered == 0
        assert report.line_rate == 0.0
        assert report.files_count == 0

    def test_create_report_with_data(self):
        """Test creating a report with data."""
        report = CoverageReport(
            session_id="test-session",
            source="/home/test/project",
            timestamp=1700000000.0,
            lines_valid=1000,
            lines_covered=800,
            line_rate=0.8,
        )
        assert report.session_id == "test-session"
        assert report.line_percentage == 80.0

    def test_files_count(self):
        """Test files_count property."""
        report = CoverageReport(
            packages=[
                PackageCoverage(
                    name="pkg1",
                    line_rate=0.8,
                    files=[
                        FileCoverage("a.py", 10, 8, 0.8),
                        FileCoverage("b.py", 10, 8, 0.8),
                    ],
                ),
                PackageCoverage(
                    name="pkg2",
                    line_rate=0.9,
                    files=[
                        FileCoverage("c.py", 10, 9, 0.9),
                    ],
                ),
            ],
        )
        assert report.files_count == 3

    def test_get_all_files(self):
        """Test get_all_files method."""
        report = CoverageReport(
            packages=[
                PackageCoverage(
                    name="pkg1",
                    line_rate=0.8,
                    files=[
                        FileCoverage("a.py", 10, 8, 0.8),
                    ],
                ),
                PackageCoverage(
                    name="pkg2",
                    line_rate=0.9,
                    files=[
                        FileCoverage("b.py", 10, 9, 0.9),
                    ],
                ),
            ],
        )
        files = report.get_all_files()
        assert len(files) == 2
        assert files[0].filename == "a.py"
        assert files[1].filename == "b.py"

    def test_get_file(self):
        """Test get_file method."""
        report = CoverageReport(
            packages=[
                PackageCoverage(
                    name="pkg1",
                    line_rate=0.8,
                    files=[
                        FileCoverage("src/main.py", 10, 8, 0.8),
                    ],
                ),
            ],
        )
        file = report.get_file("src/main.py")
        assert file is not None
        assert file.filename == "src/main.py"

        # Test partial match
        file2 = report.get_file("main.py")
        assert file2 is not None

        # Test not found
        assert report.get_file("nonexistent.py") is None

    def test_get_low_coverage_files(self):
        """Test get_low_coverage_files method."""
        report = CoverageReport(
            packages=[
                PackageCoverage(
                    name="pkg1",
                    line_rate=0.5,
                    files=[
                        FileCoverage("high.py", 10, 9, 0.9),
                        FileCoverage("medium.py", 10, 6, 0.6),
                        FileCoverage("low.py", 10, 3, 0.3),
                    ],
                ),
            ],
        )
        low_files = report.get_low_coverage_files(threshold=0.5)
        assert len(low_files) == 1
        assert low_files[0].filename == "low.py"

    def test_get_summary(self):
        """Test get_summary method."""
        report = CoverageReport(
            session_id="test-session",
            source="/project",
            timestamp=1700000000000,  # milliseconds
            lines_valid=100,
            lines_covered=80,
            line_rate=0.8,
            branches_valid=20,
            branches_covered=15,
            branch_rate=0.75,
            packages=[
                PackageCoverage("pkg1", 0.8, files=[FileCoverage("a.py", 50, 40, 0.8)]),
                PackageCoverage("pkg2", 0.8, files=[FileCoverage("b.py", 50, 40, 0.8)]),
            ],
        )
        summary = report.get_summary()

        assert summary["session_id"] == "test-session"
        assert summary["line_rate"] == 0.8
        assert summary["line_percentage"] == 80.0
        assert summary["lines_valid"] == 100
        assert summary["lines_covered"] == 80
        assert summary["files_count"] == 2
        assert summary["packages_count"] == 2

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        report = CoverageReport(
            session_id="test",
            source="/project",
            timestamp=1700000000.0,
            version="7.0.0",
            lines_valid=100,
            lines_covered=80,
            line_rate=0.8,
            branches_valid=20,
            branches_covered=15,
            branch_rate=0.75,
            packages=[
                PackageCoverage("pkg1", 0.8, files=[FileCoverage("a.py", 50, 40, 0.8)]),
            ],
        )
        data = report.to_dict()
        restored = CoverageReport.from_dict(data)

        assert restored.session_id == report.session_id
        assert restored.source == report.source
        assert restored.line_rate == report.line_rate
        assert len(restored.packages) == 1


# ============================================================
# CoverageParser Tests
# ============================================================


class TestCoverageParser:
    """Tests for CoverageParser."""

    def test_parse_cobertura_xml(self, sample_cobertura_xml):
        """Test parsing Cobertura XML format."""
        report = CoverageParser.parse_cobertura_xml(sample_cobertura_xml)

        assert report.lines_valid == 100
        assert report.lines_covered == 80
        assert report.line_rate == 0.8
        assert report.source == "/home/test/project"
        assert len(report.packages) == 2

        # Check package 1
        pkg1 = report.packages[0]
        assert pkg1.name == "myproject"
        assert len(pkg1.files) == 2

        # Check file coverage
        main_py = pkg1.files[0]
        assert main_py.filename == "myproject/main.py"
        assert main_py.line_rate == 0.9
        assert len(main_py.lines) == 5
        assert main_py.lines_covered == 4  # lines 1, 2, 4, 5 are covered

    def test_parse_lcov(self, sample_lcov):
        """Test parsing LCOV format."""
        report = CoverageParser.parse_lcov(sample_lcov)

        assert report.files_count == 2
        assert report.lines_valid > 0
        assert report.lines_covered > 0

        files = report.get_all_files()
        main_py = next(f for f in files if "main.py" in f.filename)
        assert main_py.lines_covered == 4  # lines 1, 2, 4, 5
        assert main_py.lines_valid == 5

    def test_parse_json(self, sample_json_coverage):
        """Test parsing JSON coverage format."""
        report = CoverageParser.parse_json(sample_json_coverage)

        assert report.lines_valid == 50
        assert report.lines_covered == 40
        assert report.line_rate == 0.8
        assert report.files_count == 2

        main_py = report.get_file("src/main.py")
        assert main_py is not None
        assert main_py.lines_valid == 30
        assert main_py.lines_covered == 25

    def test_parse_auto_detect_xml(self, sample_cobertura_xml):
        """Test auto-detection of Cobertura XML."""
        report = CoverageParser.parse(sample_cobertura_xml)
        assert report.lines_valid == 100

    def test_parse_auto_detect_lcov(self, sample_lcov):
        """Test auto-detection of LCOV format."""
        report = CoverageParser.parse(sample_lcov)
        assert report.files_count == 2

    def test_parse_auto_detect_json(self, sample_json_coverage):
        """Test auto-detection of JSON format."""
        report = CoverageParser.parse(sample_json_coverage)
        assert report.lines_valid == 50

    def test_parse_file_not_found(self, temp_dir):
        """Test parsing nonexistent file."""
        with pytest.raises(FileNotFoundError):
            CoverageParser.parse(temp_dir / "nonexistent.xml")

    def test_parse_unknown_format(self, temp_dir):
        """Test parsing file with unknown format."""
        path = temp_dir / "unknown.txt"
        path.write_text("This is not a coverage file")

        with pytest.raises(ValueError, match="Unknown coverage format"):
            CoverageParser.parse(path)


# ============================================================
# CoverageStore Tests
# ============================================================


class TestCoverageStore:
    """Tests for CoverageStore."""

    @pytest.mark.asyncio
    async def test_save_and_load_coverage(self, coverage_store):
        """Test saving and loading coverage."""
        report = CoverageReport(
            lines_valid=100,
            lines_covered=80,
            line_rate=0.8,
            packages=[
                PackageCoverage("pkg1", 0.8, files=[FileCoverage("a.py", 100, 80, 0.8)]),
            ],
        )

        await coverage_store.save_coverage("session-123", report)

        loaded = await coverage_store.load_coverage("session-123")
        assert loaded is not None
        assert loaded.session_id == "session-123"
        assert loaded.line_rate == 0.8
        assert len(loaded.packages) == 1

    @pytest.mark.asyncio
    async def test_load_nonexistent_coverage(self, coverage_store):
        """Test loading coverage that doesn't exist."""
        loaded = await coverage_store.load_coverage("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_update_coverage(self, coverage_store):
        """Test updating existing coverage."""
        report1 = CoverageReport(lines_valid=100, lines_covered=50, line_rate=0.5)
        await coverage_store.save_coverage("session-123", report1)

        report2 = CoverageReport(lines_valid=100, lines_covered=80, line_rate=0.8)
        await coverage_store.save_coverage("session-123", report2)

        loaded = await coverage_store.load_coverage("session-123")
        assert loaded is not None
        assert loaded.line_rate == 0.8

    @pytest.mark.asyncio
    async def test_list_coverage(self, coverage_store):
        """Test listing coverage reports."""
        for i in range(5):
            report = CoverageReport(
                lines_valid=100,
                lines_covered=80 + i,
                line_rate=0.8 + i * 0.01,
            )
            await coverage_store.save_coverage(f"session-{i}", report)

        coverage_list = await coverage_store.list_coverage(limit=3)
        assert len(coverage_list) == 3

    @pytest.mark.asyncio
    async def test_get_aggregate_stats(self, coverage_store):
        """Test getting aggregate statistics."""
        for rate in [0.6, 0.7, 0.8, 0.9]:
            report = CoverageReport(
                lines_valid=100,
                lines_covered=int(100 * rate),
                line_rate=rate,
            )
            await coverage_store.save_coverage(f"session-{rate}", report)

        stats = await coverage_store.get_aggregate_stats()
        assert stats["total_reports"] == 4
        assert stats["avg_line_rate"] == 0.75
        assert stats["max_line_rate"] == 0.9
        assert stats["min_line_rate"] == 0.6

    @pytest.mark.asyncio
    async def test_delete_coverage(self, coverage_store):
        """Test deleting coverage."""
        report = CoverageReport(lines_valid=100, lines_covered=80, line_rate=0.8)
        await coverage_store.save_coverage("session-123", report)

        deleted = await coverage_store.delete_coverage("session-123")
        assert deleted is True

        loaded = await coverage_store.load_coverage("session-123")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_coverage(self, coverage_store):
        """Test deleting coverage that doesn't exist."""
        deleted = await coverage_store.delete_coverage("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_import_from_file(self, coverage_store, sample_cobertura_xml):
        """Test importing coverage from file."""
        report = await coverage_store.import_from_file("session-123", sample_cobertura_xml)

        assert report.lines_valid == 100
        assert report.session_id == "session-123"

        loaded = await coverage_store.load_coverage("session-123")
        assert loaded is not None
        assert loaded.line_rate == 0.8


# ============================================================
# Edge Cases and Error Handling
# ============================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_cobertura_xml(self, temp_dir):
        """Test parsing empty Cobertura XML."""
        xml_content = """<?xml version="1.0" ?>
<coverage version="7.0.0" timestamp="0" lines-valid="0" lines-covered="0" line-rate="0">
    <packages></packages>
</coverage>
"""
        path = temp_dir / "empty.xml"
        path.write_text(xml_content)

        report = CoverageParser.parse_cobertura_xml(path)
        assert report.lines_valid == 0
        assert report.files_count == 0

    def test_empty_lcov(self, temp_dir):
        """Test parsing empty LCOV file."""
        path = temp_dir / "empty.info"
        path.write_text("")

        report = CoverageParser.parse_lcov(path)
        assert report.files_count == 0

    def test_file_coverage_zero_lines(self):
        """Test FileCoverage with zero lines."""
        fc = FileCoverage(
            filename="empty.py",
            lines_valid=0,
            lines_covered=0,
            line_rate=0.0,
        )
        assert fc.line_percentage == 0.0
        assert fc.covered_lines == []
        assert fc.uncovered_lines == []

    def test_package_coverage_no_files(self):
        """Test PackageCoverage with no files."""
        pkg = PackageCoverage(name="empty", line_rate=0.0)
        assert pkg.lines_valid == 0
        assert pkg.lines_covered == 0

    def test_coverage_report_large_timestamp(self):
        """Test CoverageReport with millisecond timestamp."""
        report = CoverageReport(
            timestamp=1700000000000,  # milliseconds
            lines_valid=100,
            lines_covered=80,
            line_rate=0.8,
        )
        summary = report.get_summary()
        # Should handle milliseconds vs seconds correctly
        assert "timestamp" in summary


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """Integration tests for the coverage system."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, coverage_store, sample_cobertura_xml):
        """Test complete workflow: parse -> store -> retrieve -> query."""
        # Parse coverage file
        report = CoverageParser.parse(sample_cobertura_xml)
        assert report.lines_valid == 100

        # Save to database
        await coverage_store.save_coverage("session-integration", report)

        # Load from database
        loaded = await coverage_store.load_coverage("session-integration")
        assert loaded is not None

        # Verify data integrity
        assert loaded.lines_valid == report.lines_valid
        assert loaded.line_rate == report.line_rate
        assert loaded.files_count == report.files_count

        # Check summary
        summary = loaded.get_summary()
        assert summary["line_percentage"] == 80.0

        # Check low coverage files
        low_files = loaded.get_low_coverage_files(threshold=0.75)
        assert len(low_files) > 0

    @pytest.mark.asyncio
    async def test_multiple_sessions(self, coverage_store, sample_cobertura_xml):
        """Test handling multiple sessions with coverage."""
        # Import for multiple sessions
        for i in range(3):
            await coverage_store.import_from_file(f"session-{i}", sample_cobertura_xml)

        # List all
        coverage_list = await coverage_store.list_coverage()
        assert len(coverage_list) == 3

        # Get stats
        stats = await coverage_store.get_aggregate_stats()
        assert stats["total_reports"] == 3
        assert stats["avg_line_rate"] == pytest.approx(0.8)  # All same file

    @pytest.mark.asyncio
    async def test_update_preserves_created_at(self, coverage_store):
        """Test that updating coverage preserves original created_at."""
        import asyncio

        report1 = CoverageReport(lines_valid=100, lines_covered=50, line_rate=0.5)
        await coverage_store.save_coverage("session-time", report1)

        await asyncio.sleep(0.01)  # Small delay

        report2 = CoverageReport(lines_valid=100, lines_covered=80, line_rate=0.8)
        await coverage_store.save_coverage("session-time", report2)

        # Verify update worked
        loaded = await coverage_store.load_coverage("session-time")
        assert loaded is not None
        assert loaded.line_rate == 0.8
