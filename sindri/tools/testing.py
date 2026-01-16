"""Testing tools for Sindri."""

import asyncio
import re
from pathlib import Path
from typing import Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class RunTestsTool(Tool):
    """Run tests using auto-detected or specified testing framework."""

    name = "run_tests"
    description = """Run tests using the appropriate testing framework.

Auto-detects: pytest, unittest, npm test, jest, cargo test, go test.
Returns test results with pass/fail counts and failure details."""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to test file, directory, or pattern (default: current directory)"
            },
            "framework": {
                "type": "string",
                "description": "Testing framework to use (auto-detected if not specified)",
                "enum": ["pytest", "unittest", "npm", "jest", "cargo", "go"]
            },
            "pattern": {
                "type": "string",
                "description": "Test name pattern to filter (e.g., 'test_auth*' for pytest -k)"
            },
            "verbose": {
                "type": "boolean",
                "description": "Enable verbose output (default: true)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 300)"
            },
            "fail_fast": {
                "type": "boolean",
                "description": "Stop on first failure (default: false)"
            },
            "coverage": {
                "type": "boolean",
                "description": "Run with coverage reporting (default: false)"
            }
        },
        "required": []
    }

    async def execute(
        self,
        path: Optional[str] = None,
        framework: Optional[str] = None,
        pattern: Optional[str] = None,
        verbose: bool = True,
        timeout: int = 300,
        fail_fast: bool = False,
        coverage: bool = False,
        **kwargs
    ) -> ToolResult:
        """Run tests and return results."""
        try:
            # Resolve working directory
            work_dir = self.work_dir or Path.cwd()

            # Resolve test path
            if path:
                test_path = work_dir / path if not Path(path).is_absolute() else Path(path)
            else:
                test_path = work_dir

            # Auto-detect framework if not specified
            if not framework:
                framework = await self._detect_framework(work_dir)
                if not framework:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Could not auto-detect testing framework. Please specify 'framework' parameter.",
                        metadata={"detected_files": await self._list_config_files(work_dir)}
                    )

            log.info("run_tests", framework=framework, path=str(test_path), pattern=pattern)

            # Build command based on framework
            cmd = await self._build_command(
                framework=framework,
                test_path=test_path,
                work_dir=work_dir,
                pattern=pattern,
                verbose=verbose,
                fail_fast=fail_fast,
                coverage=coverage
            )

            if not cmd:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported testing framework: {framework}"
                )

            log.info("run_tests_command", command=cmd)

            # Execute tests with timeout
            try:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(work_dir)
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Tests timed out after {timeout} seconds",
                    metadata={"timeout": timeout, "framework": framework}
                )

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""
            combined_output = stdout_text + ("\n" + stderr_text if stderr_text else "")

            # Parse test results
            results = self._parse_results(framework, combined_output, process.returncode)

            # Determine success (tests passed)
            tests_passed = process.returncode == 0

            return ToolResult(
                success=tests_passed,
                output=combined_output,
                error=None if tests_passed else f"Tests failed with {results.get('failed', 'unknown')} failure(s)",
                metadata={
                    "framework": framework,
                    "returncode": process.returncode,
                    "path": str(test_path),
                    **results
                }
            )

        except Exception as e:
            log.error("run_tests_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to run tests: {str(e)}"
            )

    async def _detect_framework(self, work_dir: Path) -> Optional[str]:
        """Auto-detect testing framework based on project files."""
        # Check for Python testing
        if (work_dir / "pytest.ini").exists() or \
           (work_dir / "pyproject.toml").exists() or \
           (work_dir / "setup.py").exists() or \
           (work_dir / "conftest.py").exists():
            # Check if pytest is available
            proc = await asyncio.create_subprocess_shell(
                "python -c 'import pytest'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir)
            )
            await proc.communicate()
            if proc.returncode == 0:
                return "pytest"
            return "unittest"

        # Check for Node.js testing
        package_json = work_dir / "package.json"
        if package_json.exists():
            try:
                import json
                content = package_json.read_text()
                pkg = json.loads(content)

                # Check for jest in dependencies or devDependencies
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}

                if "jest" in all_deps:
                    return "jest"

                # Check scripts for test command
                scripts = pkg.get("scripts", {})
                if "test" in scripts:
                    test_script = scripts["test"]
                    if "jest" in test_script:
                        return "jest"
                    return "npm"
            except Exception:
                pass

        # Check for Rust
        if (work_dir / "Cargo.toml").exists():
            return "cargo"

        # Check for Go
        go_files = list(work_dir.glob("*_test.go"))
        if go_files or (work_dir / "go.mod").exists():
            return "go"

        # Check for tests directory with Python files
        tests_dir = work_dir / "tests"
        if tests_dir.exists() and list(tests_dir.glob("test_*.py")):
            return "pytest"

        return None

    async def _list_config_files(self, work_dir: Path) -> list[str]:
        """List config files that might indicate a testing framework."""
        config_patterns = [
            "pytest.ini", "pyproject.toml", "setup.py", "conftest.py",
            "package.json", "jest.config.js", "jest.config.ts",
            "Cargo.toml", "go.mod"
        ]
        found = []
        for pattern in config_patterns:
            if (work_dir / pattern).exists():
                found.append(pattern)
        return found

    async def _build_command(
        self,
        framework: str,
        test_path: Path,
        work_dir: Path,
        pattern: Optional[str],
        verbose: bool,
        fail_fast: bool,
        coverage: bool
    ) -> Optional[str]:
        """Build the test command for the specified framework."""

        if framework == "pytest":
            cmd_parts = ["python", "-m", "pytest"]

            # Add path if specific
            if test_path != work_dir:
                cmd_parts.append(str(test_path))

            if verbose:
                cmd_parts.append("-v")
            if fail_fast:
                cmd_parts.append("-x")
            if pattern:
                cmd_parts.extend(["-k", pattern])
            if coverage:
                cmd_parts.extend(["--cov", "--cov-report=term-missing"])

            # Add color output
            cmd_parts.append("--tb=short")

            return " ".join(cmd_parts)

        elif framework == "unittest":
            cmd_parts = ["python", "-m", "unittest"]

            if test_path != work_dir and test_path.exists():
                if test_path.is_file():
                    # Convert path to module notation
                    rel_path = test_path.relative_to(work_dir)
                    module = str(rel_path).replace("/", ".").replace(".py", "")
                    cmd_parts.append(module)
                else:
                    cmd_parts.extend(["discover", "-s", str(test_path)])
            else:
                cmd_parts.append("discover")

            if verbose:
                cmd_parts.append("-v")
            if fail_fast:
                cmd_parts.append("-f")
            if pattern:
                cmd_parts.extend(["-p", f"*{pattern}*"])

            return " ".join(cmd_parts)

        elif framework == "npm":
            cmd_parts = ["npm", "test"]

            if pattern:
                cmd_parts.extend(["--", pattern])

            return " ".join(cmd_parts)

        elif framework == "jest":
            cmd_parts = ["npx", "jest"]

            if test_path != work_dir:
                cmd_parts.append(str(test_path))

            if verbose:
                cmd_parts.append("--verbose")
            if fail_fast:
                cmd_parts.append("--bail")
            if pattern:
                cmd_parts.extend(["-t", pattern])
            if coverage:
                cmd_parts.append("--coverage")

            # Add color output
            cmd_parts.append("--colors")

            return " ".join(cmd_parts)

        elif framework == "cargo":
            cmd_parts = ["cargo", "test"]

            if pattern:
                cmd_parts.append(pattern)

            if verbose:
                cmd_parts.append("--verbose")
            if fail_fast:
                cmd_parts.extend(["--", "--test-threads=1"])

            # Show output
            cmd_parts.extend(["--", "--nocapture"]) if verbose else None

            return " ".join([p for p in cmd_parts if p])

        elif framework == "go":
            cmd_parts = ["go", "test"]

            if verbose:
                cmd_parts.append("-v")
            if fail_fast:
                cmd_parts.append("-failfast")
            if coverage:
                cmd_parts.append("-cover")

            # Test path
            if test_path != work_dir:
                cmd_parts.append(str(test_path))
            else:
                cmd_parts.append("./...")

            if pattern:
                cmd_parts.extend(["-run", pattern])

            return " ".join(cmd_parts)

        return None

    def _parse_results(self, framework: str, output: str, returncode: int) -> dict:
        """Parse test output to extract results summary."""
        results = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "total": 0
        }

        if framework == "pytest":
            # Match pytest summary line: "5 passed, 2 failed, 1 skipped in 0.5s"
            summary_match = re.search(
                r"(\d+)\s+passed(?:.*?(\d+)\s+failed)?(?:.*?(\d+)\s+skipped)?(?:.*?(\d+)\s+error)?",
                output,
                re.IGNORECASE
            )
            if summary_match:
                results["passed"] = int(summary_match.group(1) or 0)
                results["failed"] = int(summary_match.group(2) or 0)
                results["skipped"] = int(summary_match.group(3) or 0)
                results["errors"] = int(summary_match.group(4) or 0)

            # Also check for "X failed" at start
            failed_match = re.search(r"(\d+)\s+failed", output)
            if failed_match and results["failed"] == 0:
                results["failed"] = int(failed_match.group(1))

            # Check for collection errors
            if "error" in output.lower() and results["errors"] == 0:
                error_match = re.search(r"(\d+)\s+error", output, re.IGNORECASE)
                if error_match:
                    results["errors"] = int(error_match.group(1))

        elif framework == "unittest":
            # Match unittest summary: "Ran 5 tests in 0.001s"
            ran_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
            if ran_match:
                results["total"] = int(ran_match.group(1))

            # Check for OK or FAILED
            if "OK" in output:
                results["passed"] = results["total"]
            elif "FAILED" in output:
                # Match "failures=X, errors=Y"
                failures_match = re.search(r"failures=(\d+)", output)
                errors_match = re.search(r"errors=(\d+)", output)
                if failures_match:
                    results["failed"] = int(failures_match.group(1))
                if errors_match:
                    results["errors"] = int(errors_match.group(1))
                results["passed"] = results["total"] - results["failed"] - results["errors"]

        elif framework in ("npm", "jest"):
            # Match jest summary: "Tests: 2 failed, 5 passed, 7 total"
            tests_match = re.search(
                r"Tests:\s*(?:(\d+)\s+failed,?\s*)?(?:(\d+)\s+skipped,?\s*)?(?:(\d+)\s+passed,?\s*)?(\d+)\s+total",
                output
            )
            if tests_match:
                results["failed"] = int(tests_match.group(1) or 0)
                results["skipped"] = int(tests_match.group(2) or 0)
                results["passed"] = int(tests_match.group(3) or 0)
                results["total"] = int(tests_match.group(4) or 0)

        elif framework == "cargo":
            # Match cargo test summary: "test result: ok. 5 passed; 0 failed; 0 ignored"
            result_match = re.search(
                r"test result:.*?(\d+)\s+passed;\s*(\d+)\s+failed;\s*(\d+)\s+ignored",
                output
            )
            if result_match:
                results["passed"] = int(result_match.group(1))
                results["failed"] = int(result_match.group(2))
                results["skipped"] = int(result_match.group(3))

        elif framework == "go":
            # Count PASS and FAIL lines
            results["passed"] = len(re.findall(r"--- PASS:", output))
            results["failed"] = len(re.findall(r"--- FAIL:", output))
            results["skipped"] = len(re.findall(r"--- SKIP:", output))

            # Also check for "ok" and "FAIL" package lines
            if results["passed"] == 0 and results["failed"] == 0:
                results["passed"] = len(re.findall(r"^ok\s+", output, re.MULTILINE))
                results["failed"] = len(re.findall(r"^FAIL\s+", output, re.MULTILINE))

        # Calculate total if not set
        if results["total"] == 0:
            results["total"] = results["passed"] + results["failed"] + results["skipped"] + results["errors"]

        return results


class CheckSyntaxTool(Tool):
    """Check code syntax without executing."""

    name = "check_syntax"
    description = """Check code syntax for errors without executing.

Supports: Python (ast/py_compile), JavaScript/TypeScript (node --check/tsc),
Rust (cargo check), Go (go build)."""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file or directory to check"
            },
            "language": {
                "type": "string",
                "description": "Language to check (auto-detected from extension if not specified)",
                "enum": ["python", "javascript", "typescript", "rust", "go"]
            }
        },
        "required": ["path"]
    }

    # File extension to language mapping
    EXTENSION_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go"
    }

    async def execute(
        self,
        path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """Check syntax of the specified file(s)."""
        try:
            work_dir = self.work_dir or Path.cwd()
            file_path = work_dir / path if not Path(path).is_absolute() else Path(path)

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path does not exist: {file_path}"
                )

            # Auto-detect language from extension
            if not language and file_path.is_file():
                ext = file_path.suffix.lower()
                language = self.EXTENSION_MAP.get(ext)
                if not language:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Could not detect language for extension: {ext}. Please specify 'language' parameter."
                    )
            elif not language:
                return ToolResult(
                    success=False,
                    output="",
                    error="Cannot auto-detect language for directory. Please specify 'language' parameter."
                )

            log.info("check_syntax", path=str(file_path), language=language)

            # Check syntax based on language
            if language == "python":
                return await self._check_python(file_path)
            elif language == "javascript":
                return await self._check_javascript(file_path)
            elif language == "typescript":
                return await self._check_typescript(file_path, work_dir)
            elif language == "rust":
                return await self._check_rust(work_dir)
            elif language == "go":
                return await self._check_go(file_path, work_dir)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported language: {language}"
                )

        except Exception as e:
            log.error("check_syntax_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to check syntax: {str(e)}"
            )

    async def _check_python(self, file_path: Path) -> ToolResult:
        """Check Python syntax using ast module."""
        import ast

        errors = []
        checked_files = []

        if file_path.is_file():
            files = [file_path]
        else:
            files = list(file_path.rglob("*.py"))

        for f in files:
            try:
                source = f.read_text()
                ast.parse(source, filename=str(f))
                checked_files.append(str(f))
            except SyntaxError as e:
                errors.append({
                    "file": str(f),
                    "line": e.lineno,
                    "column": e.offset,
                    "message": e.msg
                })

        if errors:
            error_msgs = [
                f"{e['file']}:{e['line']}:{e['column']}: {e['message']}"
                for e in errors
            ]
            return ToolResult(
                success=False,
                output="\n".join(error_msgs),
                error=f"Syntax errors found in {len(errors)} location(s)",
                metadata={"errors": errors, "checked_files": len(checked_files)}
            )

        return ToolResult(
            success=True,
            output=f"Syntax OK: {len(checked_files)} file(s) checked",
            metadata={"checked_files": checked_files}
        )

    async def _check_javascript(self, file_path: Path) -> ToolResult:
        """Check JavaScript syntax using node --check."""
        if file_path.is_dir():
            # Check all JS files in directory
            files = list(file_path.rglob("*.js")) + list(file_path.rglob("*.mjs"))
            errors = []
            for f in files:
                proc = await asyncio.create_subprocess_shell(
                    f"node --check {f}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    errors.append(f"{f}: {stderr.decode()}")

            if errors:
                return ToolResult(
                    success=False,
                    output="\n".join(errors),
                    error=f"Syntax errors in {len(errors)} file(s)"
                )
            return ToolResult(
                success=True,
                output=f"Syntax OK: {len(files)} file(s) checked"
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                f"node --check {file_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    output=stderr.decode(),
                    error="Syntax error found"
                )
            return ToolResult(
                success=True,
                output=f"Syntax OK: {file_path}"
            )

    async def _check_typescript(self, file_path: Path, work_dir: Path) -> ToolResult:
        """Check TypeScript syntax using tsc --noEmit."""
        cmd = f"npx tsc --noEmit"
        if file_path.is_file():
            cmd += f" {file_path}"

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir)
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()

        if proc.returncode != 0:
            # Count errors
            error_count = len(re.findall(r"error TS\d+:", output))
            return ToolResult(
                success=False,
                output=output,
                error=f"TypeScript errors: {error_count}",
                metadata={"error_count": error_count}
            )
        return ToolResult(
            success=True,
            output="TypeScript syntax OK"
        )

    async def _check_rust(self, work_dir: Path) -> ToolResult:
        """Check Rust syntax using cargo check."""
        proc = await asyncio.create_subprocess_shell(
            "cargo check --message-format=short",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir)
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()

        if proc.returncode != 0:
            error_count = len(re.findall(r"^error", output, re.MULTILINE))
            return ToolResult(
                success=False,
                output=output,
                error=f"Rust compilation errors: {error_count}",
                metadata={"error_count": error_count}
            )
        return ToolResult(
            success=True,
            output="Rust syntax OK"
        )

    async def _check_go(self, file_path: Path, work_dir: Path) -> ToolResult:
        """Check Go syntax using go build."""
        if file_path.is_file():
            cmd = f"go build -o /dev/null {file_path}"
        else:
            cmd = "go build -o /dev/null ./..."

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir)
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=output,
                error="Go compilation errors"
            )
        return ToolResult(
            success=True,
            output="Go syntax OK"
        )
