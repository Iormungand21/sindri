"""Bundle loader for agent bundles.

Handles discovery, parsing, and installation of agent bundles.
"""

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
import toml

from sindri.bundles.models import (
    BundleInfo,
    BundleManifest,
    BundleState,
)

log = structlog.get_logger()

MANIFEST_FILENAME = "sindri-agent.toml"


@dataclass
class InstallResult:
    """Result of bundle installation.

    Attributes:
        success: Whether installation succeeded
        bundle: Bundle info (if successful)
        error: Error message (if failed)
        installed_path: Path where bundle was installed
    """

    success: bool
    bundle: Optional[BundleInfo] = None
    error: Optional[str] = None
    installed_path: Optional[Path] = None


class BundleLoader:
    """Discovers and loads agent bundles.

    Bundles are directories containing:
    - sindri-agent.toml (manifest)
    - prompt.txt or inline prompt
    - Optional tests/ directory
    - Optional tools/ directory

    Example:
        loader = BundleLoader()
        bundles = loader.discover()
        for bundle in bundles:
            print(f"{bundle.name}: {bundle.state}")
    """

    def __init__(self, bundles_dir: Optional[Path] = None):
        """Initialize the bundle loader.

        Args:
            bundles_dir: Directory containing installed bundles.
                        Defaults to ~/.sindri/bundles/
        """
        self.bundles_dir = bundles_dir or Path.home() / ".sindri" / "bundles"

    def ensure_directory(self) -> None:
        """Ensure bundles directory exists."""
        self.bundles_dir.mkdir(parents=True, exist_ok=True)

    def discover(self) -> list[BundleInfo]:
        """Discover all bundles in the bundles directory.

        Returns:
            List of BundleInfo for each discovered bundle
        """
        self.ensure_directory()
        bundles = []

        for path in self.bundles_dir.iterdir():
            if not path.is_dir():
                continue

            manifest_path = path / MANIFEST_FILENAME
            if not manifest_path.exists():
                continue

            bundle = self._load_bundle(path)
            bundles.append(bundle)

        log.info("bundles_discovered", count=len(bundles))
        return bundles

    def load(self, bundle_path: Path) -> BundleInfo:
        """Load a bundle from a path.

        Args:
            bundle_path: Path to bundle directory

        Returns:
            BundleInfo with parsed manifest or error
        """
        return self._load_bundle(bundle_path)

    def _load_bundle(self, path: Path) -> BundleInfo:
        """Load and parse a bundle.

        Args:
            path: Path to bundle directory

        Returns:
            BundleInfo with manifest or error
        """
        manifest_path = path / MANIFEST_FILENAME

        if not manifest_path.exists():
            return BundleInfo(
                name=path.name,
                path=path,
                state=BundleState.FAILED,
                error=f"Manifest not found: {MANIFEST_FILENAME}",
            )

        try:
            manifest_data = toml.load(manifest_path)
            manifest = BundleManifest.from_dict(manifest_data)

            # Load prompt from file if specified
            if manifest.prompt_file and not manifest.prompt_content:
                prompt_path = path / manifest.prompt_file
                if prompt_path.exists():
                    manifest.prompt_content = prompt_path.read_text()
                else:
                    return BundleInfo(
                        name=manifest.agent.name,
                        path=path,
                        state=BundleState.FAILED,
                        error=f"Prompt file not found: {manifest.prompt_file}",
                    )

            return BundleInfo(
                name=manifest.agent.name,
                path=path,
                manifest=manifest,
                state=BundleState.DISCOVERED,
            )

        except toml.TomlDecodeError as e:
            return BundleInfo(
                name=path.name,
                path=path,
                state=BundleState.FAILED,
                error=f"Invalid TOML: {e}",
            )
        except KeyError as e:
            return BundleInfo(
                name=path.name,
                path=path,
                state=BundleState.FAILED,
                error=f"Missing required field: {e}",
            )
        except Exception as e:
            return BundleInfo(
                name=path.name,
                path=path,
                state=BundleState.FAILED,
                error=f"Failed to load bundle: {e}",
            )

    def install(self, source_path: Path, force: bool = False) -> InstallResult:
        """Install a bundle from source path.

        Copies the bundle directory to bundles_dir.

        Args:
            source_path: Path to bundle directory to install
            force: Overwrite if bundle already exists

        Returns:
            InstallResult with success status
        """
        self.ensure_directory()

        if not source_path.is_dir():
            return InstallResult(
                success=False,
                error=f"Source is not a directory: {source_path}",
            )

        manifest_path = source_path / MANIFEST_FILENAME
        if not manifest_path.exists():
            return InstallResult(
                success=False,
                error=f"Manifest not found: {MANIFEST_FILENAME}",
            )

        # Load and validate manifest
        bundle = self._load_bundle(source_path)
        if bundle.state == BundleState.FAILED:
            return InstallResult(
                success=False,
                error=bundle.error,
            )

        # Determine target path
        target_path = self.bundles_dir / bundle.name

        if target_path.exists():
            if not force:
                return InstallResult(
                    success=False,
                    error=f"Bundle already exists: {bundle.name}. Use --force to overwrite.",
                )
            shutil.rmtree(target_path)

        # Copy bundle
        try:
            shutil.copytree(source_path, target_path)

            # Reload from installed location
            installed_bundle = self._load_bundle(target_path)
            installed_bundle.state = BundleState.INSTALLED
            installed_bundle.installed_at = datetime.now()

            log.info(
                "bundle_installed",
                name=bundle.name,
                path=str(target_path),
            )

            return InstallResult(
                success=True,
                bundle=installed_bundle,
                installed_path=target_path,
            )

        except Exception as e:
            return InstallResult(
                success=False,
                error=f"Failed to copy bundle: {e}",
            )

    def uninstall(self, name: str) -> InstallResult:
        """Uninstall a bundle by name.

        Args:
            name: Bundle name to uninstall

        Returns:
            InstallResult with success status
        """
        target_path = self.bundles_dir / name

        if not target_path.exists():
            return InstallResult(
                success=False,
                error=f"Bundle not found: {name}",
            )

        try:
            shutil.rmtree(target_path)

            log.info("bundle_uninstalled", name=name)

            return InstallResult(
                success=True,
                installed_path=target_path,
            )

        except Exception as e:
            return InstallResult(
                success=False,
                error=f"Failed to uninstall bundle: {e}",
            )

    def get_bundle(self, name: str) -> Optional[BundleInfo]:
        """Get a bundle by name.

        Args:
            name: Bundle name

        Returns:
            BundleInfo or None if not found
        """
        target_path = self.bundles_dir / name

        if not target_path.exists():
            return None

        bundle = self._load_bundle(target_path)
        if bundle.state != BundleState.FAILED:
            bundle.state = BundleState.INSTALLED
        return bundle

    def get_prompt(self, bundle: BundleInfo) -> Optional[str]:
        """Get the system prompt for a bundle.

        Args:
            bundle: BundleInfo to get prompt for

        Returns:
            System prompt string or None
        """
        if not bundle.manifest:
            return None

        # Return inline content if available
        if bundle.manifest.prompt_content:
            return bundle.manifest.prompt_content

        # Load from file
        if bundle.manifest.prompt_file:
            prompt_path = bundle.path / bundle.manifest.prompt_file
            if prompt_path.exists():
                return prompt_path.read_text()

        return None
