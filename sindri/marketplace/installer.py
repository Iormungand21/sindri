"""Plugin installer for the marketplace.

Handles installing plugins from various sources (git, URL, local path)
and managing plugin files in the plugin directories.
"""

import shutil
import tempfile
import zipfile
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import structlog

from sindri.marketplace.metadata import (
    PluginMetadata,
    PluginSource,
    SourceType,
    parse_manifest,
)
from sindri.marketplace.index import MarketplaceIndex, InstalledPlugin
from sindri.plugins.validator import PluginValidator, ValidationResult

log = structlog.get_logger()


@dataclass
class InstallResult:
    """Result of a plugin installation.

    Attributes:
        success: Whether installation succeeded
        plugin: Installed plugin info (if successful)
        error: Error message (if failed)
        validation: Validation result (if validation was performed)
        warnings: List of warning messages
    """
    success: bool
    plugin: Optional[InstalledPlugin] = None
    error: Optional[str] = None
    validation: Optional[ValidationResult] = None
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class UninstallResult:
    """Result of a plugin uninstallation.

    Attributes:
        success: Whether uninstallation succeeded
        name: Plugin name
        error: Error message (if failed)
    """
    success: bool
    name: str
    error: Optional[str] = None


class PluginInstaller:
    """Installs plugins from various sources.

    Supports:
    - Local file paths
    - Git repositories (requires git)
    - Direct URLs (zip/tar archives or single files)

    Example:
        installer = PluginInstaller()

        # Install from git
        result = await installer.install_from_git(
            "https://github.com/user/sindri-plugin-example.git"
        )

        # Install from local path
        result = await installer.install_from_path(Path("/path/to/plugin.py"))

        # Install from URL
        result = await installer.install_from_url(
            "https://example.com/plugin.zip"
        )

        # Uninstall
        result = await installer.uninstall("plugin_name")
    """

    def __init__(
        self,
        plugin_dir: Optional[Path] = None,
        agent_dir: Optional[Path] = None,
        index: Optional[MarketplaceIndex] = None,
        validate: bool = True,
        strict: bool = False,
    ):
        """Initialize the installer.

        Args:
            plugin_dir: Directory for tool plugins
            agent_dir: Directory for agent configs
            index: Marketplace index (created if not provided)
            validate: Whether to validate plugins before installing
            strict: Whether to treat validation warnings as errors
        """
        self.plugin_dir = plugin_dir or (Path.home() / ".sindri" / "plugins")
        self.agent_dir = agent_dir or (Path.home() / ".sindri" / "agents")
        self.index = index or MarketplaceIndex()
        self.validate = validate
        self.strict = strict

    def _ensure_dirs(self) -> None:
        """Ensure plugin directories exist."""
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.agent_dir.mkdir(parents=True, exist_ok=True)

    def _detect_source_type(self, source: str) -> tuple[SourceType, str]:
        """Detect the source type from a string.

        Args:
            source: Source string (path, URL, or git URL)

        Returns:
            Tuple of (SourceType, normalized_location)
        """
        # Check if it's a local path
        path = Path(source)
        if path.exists():
            return SourceType.LOCAL, str(path.resolve())

        # Check if it's a git URL
        if source.endswith(".git") or source.startswith("git@"):
            return SourceType.GIT, source

        # Check if it's a GitHub/GitLab shorthand
        if "/" in source and not source.startswith(("http://", "https://")):
            parts = source.split("/")
            if len(parts) == 2:
                # Assume GitHub
                return SourceType.GIT, f"https://github.com/{source}.git"

        # Parse URL
        parsed = urlparse(source)
        if parsed.scheme in ("http", "https"):
            # Check if it's a git host
            git_hosts = ["github.com", "gitlab.com", "bitbucket.org"]
            if any(host in parsed.netloc for host in git_hosts):
                if not source.endswith(".git"):
                    source = source.rstrip("/") + ".git"
                return SourceType.GIT, source
            return SourceType.URL, source

        # Default to local path
        return SourceType.LOCAL, source

    async def install(
        self,
        source: str,
        name: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> InstallResult:
        """Install a plugin from any source.

        Automatically detects the source type and delegates to the
        appropriate install method.

        Args:
            source: Plugin source (path, URL, or git URL)
            name: Optional name override
            ref: Git ref (branch/tag/commit) for git sources

        Returns:
            InstallResult with status and details
        """
        source_type, location = self._detect_source_type(source)

        if source_type == SourceType.LOCAL:
            return await self.install_from_path(Path(location), name)
        elif source_type == SourceType.GIT:
            return await self.install_from_git(location, name, ref)
        else:
            return await self.install_from_url(location, name)

    async def install_from_path(
        self,
        path: Path,
        name: Optional[str] = None,
    ) -> InstallResult:
        """Install a plugin from a local path.

        Args:
            path: Path to plugin file or directory
            name: Optional name override

        Returns:
            InstallResult
        """
        self._ensure_dirs()
        self.index.load()

        if not path.exists():
            return InstallResult(
                success=False,
                error=f"Path not found: {path}"
            )

        try:
            # Handle directory with manifest
            if path.is_dir():
                return await self._install_from_directory(path, name)

            # Handle single file
            return await self._install_single_file(path, name)

        except Exception as e:
            log.error("plugin_install_failed", error=str(e))
            return InstallResult(success=False, error=str(e))

    async def _install_single_file(
        self,
        path: Path,
        name: Optional[str] = None,
    ) -> InstallResult:
        """Install a single plugin file."""
        # Determine plugin type
        if path.suffix == ".py":
            dest_dir = self.plugin_dir
            plugin_type = "tool"
        elif path.suffix == ".toml":
            dest_dir = self.agent_dir
            plugin_type = "agent"
        else:
            return InstallResult(
                success=False,
                error=f"Unsupported file type: {path.suffix}"
            )

        # Extract metadata
        metadata = PluginMetadata.from_plugin_file(path)
        if not metadata:
            metadata = PluginMetadata(
                name=name or path.stem,
                plugin_type=plugin_type,
            )
        elif name:
            metadata.name = name

        # Check if already installed
        if self.index.exists(metadata.name):
            existing = self.index.get(metadata.name)
            return InstallResult(
                success=False,
                error=f"Plugin '{metadata.name}' is already installed at {existing.installed_path}"
            )

        # Validate if requested
        validation = None
        if self.validate:
            validation = self._validate_file(path)
            if not validation.valid:
                error_msg = "; ".join(msg for _, msg in validation.errors)
                return InstallResult(
                    success=False,
                    error=f"Validation failed: {error_msg}",
                    validation=validation,
                )
            if self.strict and validation.warnings:
                return InstallResult(
                    success=False,
                    error=f"Validation warnings (strict mode): {'; '.join(validation.warnings)}",
                    validation=validation,
                )

        # Copy file to plugin directory
        dest_path = dest_dir / path.name
        if dest_path.exists():
            dest_path = dest_dir / f"{metadata.name}{path.suffix}"

        shutil.copy2(path, dest_path)

        # Create installed plugin record
        source = PluginSource(
            type=SourceType.LOCAL,
            location=str(path.resolve()),
            installed_at=datetime.now(),
        )

        installed = InstalledPlugin(
            metadata=metadata,
            source=source,
            installed_path=dest_path,
        )

        # Add to index
        self.index.add(installed)
        self.index.save()

        log.info(
            "plugin_installed",
            name=metadata.name,
            path=str(dest_path),
            source="local",
        )

        warnings = validation.warnings if validation else []
        return InstallResult(
            success=True,
            plugin=installed,
            validation=validation,
            warnings=warnings,
        )

    async def _install_from_directory(
        self,
        path: Path,
        name: Optional[str] = None,
    ) -> InstallResult:
        """Install a plugin from a directory (with manifest)."""
        # Check for manifest
        manifest_path = path / "sindri-plugin.json"
        if manifest_path.exists():
            metadata = parse_manifest(manifest_path)
            if not metadata:
                return InstallResult(
                    success=False,
                    error="Failed to parse sindri-plugin.json manifest"
                )
        else:
            # Look for plugin files
            py_files = list(path.glob("*.py"))
            toml_files = list(path.glob("*.toml"))

            if not py_files and not toml_files:
                return InstallResult(
                    success=False,
                    error="No plugin files found in directory"
                )

            # Install each file
            results = []
            for py_file in py_files:
                if not py_file.name.startswith("_"):
                    result = await self._install_single_file(py_file)
                    results.append(result)

            for toml_file in toml_files:
                if not toml_file.name.startswith("_"):
                    result = await self._install_single_file(toml_file)
                    results.append(result)

            # Return combined result
            successes = [r for r in results if r.success]
            failures = [r for r in results if not r.success]

            if not successes:
                return InstallResult(
                    success=False,
                    error=f"All plugin files failed: {[r.error for r in failures]}"
                )

            return InstallResult(
                success=True,
                plugin=successes[0].plugin if successes else None,
                warnings=[f"Installed {len(successes)} plugins, {len(failures)} failed"],
            )

        # Install from manifest
        if name:
            metadata.name = name

        # Find entry point
        entry_point = path / metadata.to_dict().get("entry_point", f"{metadata.name}.py")
        if not entry_point.exists():
            # Try common patterns
            for pattern in [f"{metadata.name}.py", "plugin.py", "main.py"]:
                candidate = path / pattern
                if candidate.exists():
                    entry_point = candidate
                    break

        if not entry_point.exists():
            return InstallResult(
                success=False,
                error=f"Entry point not found: {entry_point}"
            )

        return await self._install_single_file(entry_point, metadata.name)

    async def install_from_git(
        self,
        url: str,
        name: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> InstallResult:
        """Install a plugin from a git repository.

        Args:
            url: Git repository URL
            name: Optional name override
            ref: Branch, tag, or commit to checkout

        Returns:
            InstallResult
        """
        import subprocess

        self._ensure_dirs()
        self.index.load()

        # Check if git is available
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return InstallResult(
                success=False,
                error="Git is not installed or not in PATH"
            )

        # Clone to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "repo"

            try:
                # Clone repository
                cmd = ["git", "clone", "--depth", "1"]
                if ref:
                    cmd.extend(["--branch", ref])
                cmd.extend([url, str(clone_path)])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    return InstallResult(
                        success=False,
                        error=f"Git clone failed: {result.stderr}"
                    )

                # Install from cloned directory
                install_result = await self._install_from_directory(clone_path, name)

                if install_result.success and install_result.plugin:
                    # Update source info with git details
                    install_result.plugin.source = PluginSource(
                        type=SourceType.GIT,
                        location=url,
                        ref=ref,
                        installed_at=datetime.now(),
                    )
                    self.index.add(install_result.plugin)
                    self.index.save()

                return install_result

            except Exception as e:
                return InstallResult(
                    success=False,
                    error=f"Git install failed: {e}"
                )

    async def install_from_url(
        self,
        url: str,
        name: Optional[str] = None,
    ) -> InstallResult:
        """Install a plugin from a URL.

        Supports single Python/TOML files or zip/tar archives.

        Args:
            url: URL to download
            name: Optional name override

        Returns:
            InstallResult
        """
        import urllib.request

        self._ensure_dirs()
        self.index.load()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            try:
                # Download file
                parsed = urlparse(url)
                filename = Path(parsed.path).name or "plugin"

                download_path = tmppath / filename
                urllib.request.urlretrieve(url, download_path)

                # Handle archives
                if download_path.suffix in (".zip", ".gz", ".tar"):
                    extract_dir = tmppath / "extracted"
                    extract_dir.mkdir()

                    if download_path.suffix == ".zip":
                        with zipfile.ZipFile(download_path, "r") as zf:
                            zf.extractall(extract_dir)
                    elif download_path.suffix in (".gz", ".tar"):
                        with tarfile.open(download_path, "r:*") as tf:
                            tf.extractall(extract_dir)

                    # Find plugin files
                    install_result = await self._install_from_directory(extract_dir, name)

                else:
                    # Single file
                    install_result = await self._install_single_file(download_path, name)

                if install_result.success and install_result.plugin:
                    # Update source info
                    install_result.plugin.source = PluginSource(
                        type=SourceType.URL,
                        location=url,
                        installed_at=datetime.now(),
                    )
                    self.index.add(install_result.plugin)
                    self.index.save()

                return install_result

            except Exception as e:
                return InstallResult(
                    success=False,
                    error=f"URL install failed: {e}"
                )

    async def uninstall(self, name: str) -> UninstallResult:
        """Uninstall a plugin.

        Args:
            name: Plugin name

        Returns:
            UninstallResult
        """
        self.index.load()

        plugin = self.index.get(name)
        if not plugin:
            return UninstallResult(
                success=False,
                name=name,
                error=f"Plugin '{name}' is not installed"
            )

        try:
            # Remove the file
            if plugin.installed_path.exists():
                plugin.installed_path.unlink()
                log.info(
                    "plugin_file_removed",
                    path=str(plugin.installed_path)
                )

            # Remove from index
            self.index.remove(name)
            self.index.save()

            return UninstallResult(success=True, name=name)

        except Exception as e:
            return UninstallResult(
                success=False,
                name=name,
                error=f"Uninstall failed: {e}"
            )

    async def update(
        self,
        name: Optional[str] = None,
    ) -> list[InstallResult]:
        """Update plugins from their sources.

        Args:
            name: Plugin name (or None for all updatable)

        Returns:
            List of InstallResults for updated plugins
        """
        self.index.load()
        results = []

        if name:
            plugins = [self.index.get(name)] if self.index.get(name) else []
        else:
            plugins = [p for p, _ in self.index.get_outdated()]

        for plugin in plugins:
            if not plugin or plugin.pinned:
                continue

            # Re-install from source
            source = plugin.source

            # First uninstall
            await self.uninstall(plugin.metadata.name)

            # Then reinstall
            if source.type == SourceType.GIT:
                result = await self.install_from_git(
                    source.location,
                    plugin.metadata.name,
                    source.ref,
                )
            elif source.type == SourceType.URL:
                result = await self.install_from_url(
                    source.location,
                    plugin.metadata.name,
                )
            else:
                result = await self.install_from_path(
                    Path(source.location),
                    plugin.metadata.name,
                )

            if result.success and result.plugin:
                result.plugin.source.updated_at = datetime.now()
                self.index.add(result.plugin)
                self.index.save()

            results.append(result)

        return results

    def _validate_file(self, path: Path) -> ValidationResult:
        """Validate a plugin file.

        Args:
            path: Path to plugin file

        Returns:
            ValidationResult
        """
        from sindri.plugins.loader import PluginLoader

        loader = PluginLoader()

        # Set up loader for this specific file
        if path.suffix == ".py":
            loader.plugin_dir = path.parent
        else:
            loader.agent_dir = path.parent

        # Discover plugins (will find our file)
        plugins = loader.discover()

        # Find our plugin
        plugin = None
        for p in plugins:
            if p.path == path or p.path.name == path.name:
                plugin = p
                break

        if not plugin:
            result = ValidationResult(valid=False)
            from sindri.plugins.validator import ValidationError
            result.add_error(
                ValidationError.SYNTAX_ERROR,
                f"Could not load plugin from {path}"
            )
            return result

        validator = PluginValidator(strict=self.strict)
        return validator.validate(plugin)
