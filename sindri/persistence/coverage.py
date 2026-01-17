"""Code coverage data storage and parsing for Sindri.

Phase 9: Coverage Visualization - parse coverage.xml (Cobertura) and lcov.info formats,
store in SQLite, and expose via API for Web UI visualization.
"""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import structlog

log = structlog.get_logger()


@dataclass
class LineCoverage:
    """Coverage information for a single line."""

    line_number: int
    hits: int  # Number of times line was executed

    @property
    def is_covered(self) -> bool:
        """Check if line was covered (executed at least once)."""
        return self.hits > 0


@dataclass
class FileCoverage:
    """Coverage information for a single file."""

    filename: str  # Relative path
    lines_valid: int  # Total coverable lines
    lines_covered: int  # Lines that were executed
    line_rate: float  # 0.0 - 1.0
    branches_valid: int = 0
    branches_covered: int = 0
    branch_rate: float = 0.0
    lines: list[LineCoverage] = field(default_factory=list)

    @property
    def covered_lines(self) -> list[int]:
        """Get list of covered line numbers."""
        return [ln.line_number for ln in self.lines if ln.is_covered]

    @property
    def uncovered_lines(self) -> list[int]:
        """Get list of uncovered line numbers."""
        return [ln.line_number for ln in self.lines if not ln.is_covered]

    @property
    def line_percentage(self) -> float:
        """Get line coverage as percentage."""
        return self.line_rate * 100

    @property
    def branch_percentage(self) -> float:
        """Get branch coverage as percentage."""
        return self.branch_rate * 100

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "filename": self.filename,
            "lines_valid": self.lines_valid,
            "lines_covered": self.lines_covered,
            "line_rate": self.line_rate,
            "branches_valid": self.branches_valid,
            "branches_covered": self.branches_covered,
            "branch_rate": self.branch_rate,
            "covered_lines": self.covered_lines,
            "uncovered_lines": self.uncovered_lines,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileCoverage":
        """Deserialize from dictionary."""
        # Reconstruct lines from covered/uncovered lists
        lines = []
        for ln in data.get("covered_lines", []):
            lines.append(LineCoverage(line_number=ln, hits=1))
        for ln in data.get("uncovered_lines", []):
            lines.append(LineCoverage(line_number=ln, hits=0))
        lines.sort(key=lambda x: x.line_number)

        return cls(
            filename=data["filename"],
            lines_valid=data["lines_valid"],
            lines_covered=data["lines_covered"],
            line_rate=data["line_rate"],
            branches_valid=data.get("branches_valid", 0),
            branches_covered=data.get("branches_covered", 0),
            branch_rate=data.get("branch_rate", 0.0),
            lines=lines,
        )


@dataclass
class PackageCoverage:
    """Coverage information for a package/directory."""

    name: str
    line_rate: float
    branch_rate: float = 0.0
    files: list[FileCoverage] = field(default_factory=list)

    @property
    def lines_valid(self) -> int:
        """Total coverable lines in package."""
        return sum(f.lines_valid for f in self.files)

    @property
    def lines_covered(self) -> int:
        """Total covered lines in package."""
        return sum(f.lines_covered for f in self.files)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "line_rate": self.line_rate,
            "branch_rate": self.branch_rate,
            "lines_valid": self.lines_valid,
            "lines_covered": self.lines_covered,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackageCoverage":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            line_rate=data["line_rate"],
            branch_rate=data.get("branch_rate", 0.0),
            files=[FileCoverage.from_dict(f) for f in data.get("files", [])],
        )


@dataclass
class CoverageReport:
    """Complete coverage report."""

    session_id: Optional[str] = None
    source: str = ""  # Source directory/file the coverage was generated from
    timestamp: float = 0.0
    version: str = ""  # Coverage tool version

    # Overall metrics
    lines_valid: int = 0
    lines_covered: int = 0
    line_rate: float = 0.0
    branches_valid: int = 0
    branches_covered: int = 0
    branch_rate: float = 0.0

    # Package breakdown
    packages: list[PackageCoverage] = field(default_factory=list)

    @property
    def files_count(self) -> int:
        """Total number of files with coverage."""
        return sum(len(p.files) for p in self.packages)

    @property
    def line_percentage(self) -> float:
        """Line coverage as percentage."""
        return self.line_rate * 100

    @property
    def branch_percentage(self) -> float:
        """Branch coverage as percentage."""
        return self.branch_rate * 100

    def get_all_files(self) -> list[FileCoverage]:
        """Get flat list of all file coverage."""
        files = []
        for pkg in self.packages:
            files.extend(pkg.files)
        return files

    def get_file(self, filename: str) -> Optional[FileCoverage]:
        """Get coverage for a specific file."""
        for pkg in self.packages:
            for f in pkg.files:
                if f.filename == filename or f.filename.endswith(filename):
                    return f
        return None

    def get_low_coverage_files(self, threshold: float = 0.5) -> list[FileCoverage]:
        """Get files with coverage below threshold."""
        return [f for f in self.get_all_files() if f.line_rate < threshold]

    def get_summary(self) -> dict[str, Any]:
        """Get coverage summary for API response."""
        return {
            "session_id": self.session_id,
            "source": self.source,
            "timestamp": datetime.fromtimestamp(self.timestamp / 1000).isoformat()
            if self.timestamp > 1e10
            else datetime.fromtimestamp(self.timestamp).isoformat(),
            "line_rate": round(self.line_rate, 4),
            "line_percentage": round(self.line_percentage, 2),
            "lines_valid": self.lines_valid,
            "lines_covered": self.lines_covered,
            "branch_rate": round(self.branch_rate, 4),
            "branch_percentage": round(self.branch_percentage, 2),
            "branches_valid": self.branches_valid,
            "branches_covered": self.branches_covered,
            "files_count": self.files_count,
            "packages_count": len(self.packages),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_id": self.session_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "version": self.version,
            "lines_valid": self.lines_valid,
            "lines_covered": self.lines_covered,
            "line_rate": self.line_rate,
            "branches_valid": self.branches_valid,
            "branches_covered": self.branches_covered,
            "branch_rate": self.branch_rate,
            "packages": [p.to_dict() for p in self.packages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CoverageReport":
        """Deserialize from dictionary."""
        return cls(
            session_id=data.get("session_id"),
            source=data.get("source", ""),
            timestamp=data.get("timestamp", 0.0),
            version=data.get("version", ""),
            lines_valid=data.get("lines_valid", 0),
            lines_covered=data.get("lines_covered", 0),
            line_rate=data.get("line_rate", 0.0),
            branches_valid=data.get("branches_valid", 0),
            branches_covered=data.get("branches_covered", 0),
            branch_rate=data.get("branch_rate", 0.0),
            packages=[PackageCoverage.from_dict(p) for p in data.get("packages", [])],
        )


class CoverageParser:
    """Parser for various coverage report formats."""

    @staticmethod
    def parse_cobertura_xml(xml_path: Path) -> CoverageReport:
        """Parse Cobertura XML format (coverage.xml from pytest-cov).

        Args:
            xml_path: Path to coverage.xml file

        Returns:
            CoverageReport with parsed data
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Parse root attributes
        report = CoverageReport(
            version=root.get("version", ""),
            timestamp=float(root.get("timestamp", "0")),
            lines_valid=int(root.get("lines-valid", "0")),
            lines_covered=int(root.get("lines-covered", "0")),
            line_rate=float(root.get("line-rate", "0")),
            branches_valid=int(root.get("branches-valid", "0")),
            branches_covered=int(root.get("branches-covered", "0")),
            branch_rate=float(root.get("branch-rate", "0")),
        )

        # Parse sources
        sources = root.find("sources")
        if sources is not None:
            source_elements = sources.findall("source")
            if source_elements:
                report.source = source_elements[0].text or ""

        # Parse packages
        packages_elem = root.find("packages")
        if packages_elem is not None:
            for pkg_elem in packages_elem.findall("package"):
                pkg = PackageCoverage(
                    name=pkg_elem.get("name", ""),
                    line_rate=float(pkg_elem.get("line-rate", "0")),
                    branch_rate=float(pkg_elem.get("branch-rate", "0")),
                )

                # Parse classes (files) in package
                classes_elem = pkg_elem.find("classes")
                if classes_elem is not None:
                    for class_elem in classes_elem.findall("class"):
                        file_cov = FileCoverage(
                            filename=class_elem.get("filename", ""),
                            lines_valid=0,
                            lines_covered=0,
                            line_rate=float(class_elem.get("line-rate", "0")),
                            branch_rate=float(class_elem.get("branch-rate", "0")),
                        )

                        # Parse lines
                        lines_elem = class_elem.find("lines")
                        if lines_elem is not None:
                            for line_elem in lines_elem.findall("line"):
                                line_num = int(line_elem.get("number", "0"))
                                hits = int(line_elem.get("hits", "0"))
                                file_cov.lines.append(
                                    LineCoverage(line_number=line_num, hits=hits)
                                )
                                file_cov.lines_valid += 1
                                if hits > 0:
                                    file_cov.lines_covered += 1

                        pkg.files.append(file_cov)

                report.packages.append(pkg)

        log.info(
            "coverage_parsed",
            format="cobertura",
            files=report.files_count,
            line_rate=report.line_rate,
        )
        return report

    @staticmethod
    def parse_lcov(lcov_path: Path) -> CoverageReport:
        """Parse LCOV format (lcov.info).

        Args:
            lcov_path: Path to lcov.info file

        Returns:
            CoverageReport with parsed data
        """
        report = CoverageReport()
        current_file: Optional[FileCoverage] = None
        package_map: dict[str, PackageCoverage] = {}

        with open(lcov_path) as f:
            for line in f:
                line = line.strip()

                if line.startswith("SF:"):
                    # Source file
                    filename = line[3:]
                    current_file = FileCoverage(
                        filename=filename,
                        lines_valid=0,
                        lines_covered=0,
                        line_rate=0.0,
                    )

                elif line.startswith("DA:"):
                    # Line data: DA:line_number,hit_count
                    if current_file:
                        parts = line[3:].split(",")
                        if len(parts) >= 2:
                            line_num = int(parts[0])
                            hits = int(parts[1])
                            current_file.lines.append(
                                LineCoverage(line_number=line_num, hits=hits)
                            )
                            current_file.lines_valid += 1
                            if hits > 0:
                                current_file.lines_covered += 1

                elif line.startswith("BRDA:"):
                    # Branch data
                    if current_file:
                        parts = line[5:].split(",")
                        if len(parts) >= 4:
                            taken = parts[3]
                            current_file.branches_valid += 1
                            if taken != "-" and int(taken) > 0:
                                current_file.branches_covered += 1

                elif line == "end_of_record" and current_file:
                    # Finalize file
                    if current_file.lines_valid > 0:
                        current_file.line_rate = (
                            current_file.lines_covered / current_file.lines_valid
                        )
                    if current_file.branches_valid > 0:
                        current_file.branch_rate = (
                            current_file.branches_covered / current_file.branches_valid
                        )

                    # Group by package (directory)
                    pkg_name = str(Path(current_file.filename).parent)
                    if pkg_name not in package_map:
                        package_map[pkg_name] = PackageCoverage(
                            name=pkg_name, line_rate=0.0
                        )
                    package_map[pkg_name].files.append(current_file)

                    # Update totals
                    report.lines_valid += current_file.lines_valid
                    report.lines_covered += current_file.lines_covered
                    report.branches_valid += current_file.branches_valid
                    report.branches_covered += current_file.branches_covered

                    current_file = None

        # Finalize packages and report
        for pkg in package_map.values():
            if pkg.lines_valid > 0:
                pkg.line_rate = pkg.lines_covered / pkg.lines_valid
            report.packages.append(pkg)

        if report.lines_valid > 0:
            report.line_rate = report.lines_covered / report.lines_valid
        if report.branches_valid > 0:
            report.branch_rate = report.branches_covered / report.branches_valid

        log.info(
            "coverage_parsed",
            format="lcov",
            files=report.files_count,
            line_rate=report.line_rate,
        )
        return report

    @staticmethod
    def parse_json(json_path: Path) -> CoverageReport:
        """Parse JSON coverage format (coverage.json from coverage.py).

        Args:
            json_path: Path to coverage.json file

        Returns:
            CoverageReport with parsed data
        """
        with open(json_path) as f:
            data = json.load(f)

        report = CoverageReport()

        # Parse meta info
        meta = data.get("meta", {})
        report.version = meta.get("version", "")
        report.timestamp = meta.get("timestamp", 0.0)

        # Parse totals
        totals = data.get("totals", {})
        report.lines_valid = totals.get("num_statements", 0)
        report.lines_covered = totals.get("covered_lines", 0)
        report.line_rate = totals.get("percent_covered", 0.0) / 100.0
        report.branches_valid = totals.get("num_branches", 0)
        report.branches_covered = totals.get("covered_branches", 0)
        if report.branches_valid > 0:
            report.branch_rate = report.branches_covered / report.branches_valid

        # Parse files
        files_data = data.get("files", {})
        package_map: dict[str, PackageCoverage] = {}

        for filename, file_data in files_data.items():
            summary = file_data.get("summary", {})
            file_cov = FileCoverage(
                filename=filename,
                lines_valid=summary.get("num_statements", 0),
                lines_covered=summary.get("covered_lines", 0),
                line_rate=summary.get("percent_covered", 0.0) / 100.0,
                branches_valid=summary.get("num_branches", 0),
                branches_covered=summary.get("covered_branches", 0),
            )

            if file_cov.branches_valid > 0:
                file_cov.branch_rate = (
                    file_cov.branches_covered / file_cov.branches_valid
                )

            # Parse executed/missing lines
            executed = file_data.get("executed_lines", [])
            missing = file_data.get("missing_lines", [])
            for ln in executed:
                file_cov.lines.append(LineCoverage(line_number=ln, hits=1))
            for ln in missing:
                file_cov.lines.append(LineCoverage(line_number=ln, hits=0))
            file_cov.lines.sort(key=lambda x: x.line_number)

            # Group by package
            pkg_name = str(Path(filename).parent)
            if pkg_name not in package_map:
                package_map[pkg_name] = PackageCoverage(name=pkg_name, line_rate=0.0)
            package_map[pkg_name].files.append(file_cov)

        # Finalize packages
        for pkg in package_map.values():
            if pkg.lines_valid > 0:
                pkg.line_rate = pkg.lines_covered / pkg.lines_valid
            report.packages.append(pkg)

        log.info(
            "coverage_parsed",
            format="json",
            files=report.files_count,
            line_rate=report.line_rate,
        )
        return report

    @classmethod
    def parse(cls, path: Path) -> CoverageReport:
        """Auto-detect format and parse coverage file.

        Args:
            path: Path to coverage file

        Returns:
            CoverageReport with parsed data

        Raises:
            ValueError: If format cannot be determined
        """
        if not path.exists():
            raise FileNotFoundError(f"Coverage file not found: {path}")

        suffix = path.suffix.lower()
        name = path.name.lower()

        if suffix == ".xml" or name == "coverage.xml":
            return cls.parse_cobertura_xml(path)
        elif suffix == ".info" or name.endswith("lcov.info"):
            return cls.parse_lcov(path)
        elif suffix == ".json" or name == "coverage.json":
            return cls.parse_json(path)
        else:
            # Try to detect from content
            content = path.read_text()[:1000]
            if content.strip().startswith("<?xml") or "<coverage" in content:
                return cls.parse_cobertura_xml(path)
            elif content.startswith("TN:") or "SF:" in content:
                return cls.parse_lcov(path)
            elif content.strip().startswith("{"):
                return cls.parse_json(path)
            else:
                raise ValueError(f"Unknown coverage format: {path}")


class CoverageStore:
    """Storage backend for coverage data using SQLite."""

    def __init__(self, database=None):
        """Initialize the coverage store.

        Args:
            database: Database instance. If None, creates a new one.
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_table(self):
        """Ensure coverage table exists."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_coverage (
                    session_id TEXT PRIMARY KEY,
                    coverage_json TEXT NOT NULL,
                    line_rate REAL,
                    branch_rate REAL,
                    files_covered INTEGER,
                    lines_valid INTEGER,
                    lines_covered INTEGER,
                    source_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_coverage_line_rate
                ON session_coverage(line_rate)
            """
            )
            await conn.commit()

    async def save_coverage(
        self, session_id: str, coverage: CoverageReport, source_path: Optional[str] = None
    ):
        """Save coverage report to database.

        Args:
            session_id: Session ID to associate coverage with
            coverage: The CoverageReport to save
            source_path: Optional path where coverage was loaded from
        """
        await self._ensure_table()

        coverage.session_id = session_id
        coverage_json = json.dumps(coverage.to_dict())

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO session_coverage
                (session_id, coverage_json, line_rate, branch_rate, files_covered,
                 lines_valid, lines_covered, source_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT created_at FROM session_coverage WHERE session_id = ?),
                    CURRENT_TIMESTAMP
                ), CURRENT_TIMESTAMP)
                """,
                (
                    session_id,
                    coverage_json,
                    coverage.line_rate,
                    coverage.branch_rate,
                    coverage.files_count,
                    coverage.lines_valid,
                    coverage.lines_covered,
                    source_path,
                    session_id,
                ),
            )
            await conn.commit()

        log.info(
            "coverage_saved",
            session_id=session_id,
            line_rate=coverage.line_rate,
            files=coverage.files_count,
        )

    async def load_coverage(self, session_id: str) -> Optional[CoverageReport]:
        """Load coverage report from database.

        Args:
            session_id: Session ID to load coverage for

        Returns:
            CoverageReport if found, None otherwise
        """
        await self._ensure_table()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT coverage_json FROM session_coverage WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                data = json.loads(row[0])
                return CoverageReport.from_dict(data)

    async def list_coverage(self, limit: int = 20) -> list[dict]:
        """List recent coverage summaries.

        Args:
            limit: Maximum number of results

        Returns:
            List of coverage summary dictionaries
        """
        await self._ensure_table()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT sc.session_id, sc.line_rate, sc.branch_rate, sc.files_covered,
                       sc.lines_valid, sc.lines_covered, sc.created_at,
                       s.task, s.status
                FROM session_coverage sc
                LEFT JOIN sessions s ON sc.session_id = s.id
                ORDER BY sc.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                results = []
                async for row in cursor:
                    results.append(
                        {
                            "session_id": row[0],
                            "line_rate": row[1],
                            "line_percentage": round(row[1] * 100, 2) if row[1] else 0.0,
                            "branch_rate": row[2],
                            "files_covered": row[3],
                            "lines_valid": row[4],
                            "lines_covered": row[5],
                            "created_at": row[6],
                            "task": row[7] or "Unknown",
                            "status": row[8] or "Unknown",
                        }
                    )
                return results

    async def get_aggregate_stats(self) -> dict:
        """Get aggregate coverage statistics.

        Returns:
            Dictionary with aggregate stats
        """
        await self._ensure_table()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT
                    COUNT(*) as total_reports,
                    AVG(line_rate) as avg_line_rate,
                    MAX(line_rate) as max_line_rate,
                    MIN(line_rate) as min_line_rate,
                    SUM(files_covered) as total_files,
                    SUM(lines_valid) as total_lines,
                    SUM(lines_covered) as total_covered
                FROM session_coverage
                """
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "total_reports": row[0] or 0,
                        "avg_line_rate": row[1] or 0.0,
                        "avg_line_percentage": round((row[1] or 0.0) * 100, 2),
                        "max_line_rate": row[2] or 0.0,
                        "min_line_rate": row[3] or 0.0,
                        "total_files": row[4] or 0,
                        "total_lines": row[5] or 0,
                        "total_covered": row[6] or 0,
                    }
                return {
                    "total_reports": 0,
                    "avg_line_rate": 0.0,
                    "avg_line_percentage": 0.0,
                    "max_line_rate": 0.0,
                    "min_line_rate": 0.0,
                    "total_files": 0,
                    "total_lines": 0,
                    "total_covered": 0,
                }

    async def delete_coverage(self, session_id: str) -> bool:
        """Delete coverage for a session.

        Args:
            session_id: Session ID to delete coverage for

        Returns:
            True if deleted, False if not found
        """
        await self._ensure_table()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM session_coverage WHERE session_id = ?", (session_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def import_from_file(
        self, session_id: str, coverage_path: Path
    ) -> CoverageReport:
        """Import coverage from a file and save to database.

        Args:
            session_id: Session ID to associate coverage with
            coverage_path: Path to coverage file

        Returns:
            The parsed and saved CoverageReport
        """
        coverage = CoverageParser.parse(coverage_path)
        await self.save_coverage(session_id, coverage, str(coverage_path))
        return coverage
