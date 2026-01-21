"""Environment snapshot capture for Reproducible Sessions."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from sindri.config import SindriConfig
from sindri.llm.client import OllamaClient
from sindri.persistence.snapshots import (
    EnvironmentSnapshot,
    InferenceParams,
    ModelMetadata,
)

log = structlog.get_logger()


class SnapshotCapture:
    """Captures environment snapshot at session creation."""

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        config: Optional[SindriConfig] = None,
    ):
        """Initialize snapshot capture.

        Args:
            ollama_client: Ollama client for model metadata. Creates default if None.
            config: Sindri configuration. Creates default if None.
        """
        self.client = ollama_client
        self.config = config or SindriConfig()

    async def capture(
        self,
        model: str,
        inference_params: Optional[InferenceParams] = None,
    ) -> EnvironmentSnapshot:
        """Capture full environment snapshot.

        Args:
            model: Model name to capture metadata for
            inference_params: Optional inference parameters to record

        Returns:
            EnvironmentSnapshot with all captured data
        """
        # Get Sindri version
        sindri_version = self._get_sindri_version()
        git_commit = self._get_git_commit()

        # Get Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        # Get Ollama info
        ollama_host = self.config.ollama_host
        ollama_version = await self._get_ollama_version()

        # Get model metadata
        model_metadata = await self._get_model_metadata(model)

        # Serialize config
        config_snapshot = self._get_config_snapshot()

        snapshot = EnvironmentSnapshot(
            sindri_version=sindri_version,
            sindri_git_commit=git_commit,
            python_version=python_version,
            ollama_version=ollama_version,
            ollama_host=ollama_host,
            model_metadata=model_metadata,
            inference_params=inference_params or InferenceParams(),
            config_snapshot=config_snapshot,
            captured_at=datetime.now(),
        )

        log.info(
            "environment_snapshot_captured",
            sindri_version=sindri_version,
            python_version=python_version,
            model=model,
            model_digest=model_metadata.digest[:12] if model_metadata.digest else None,
        )

        return snapshot

    def _get_sindri_version(self) -> str:
        """Get Sindri package version."""
        try:
            from sindri import __version__

            return __version__
        except (ImportError, AttributeError):
            return "unknown"

    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash if in a git repo."""
        try:
            # Try to find sindri package location for git info
            import sindri
            package_dir = Path(sindri.__file__).parent.parent

            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=package_dir,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        return None

    async def _get_ollama_version(self) -> Optional[str]:
        """Get Ollama server version via /api/version."""
        if not self.client:
            return None

        try:
            # Use the underlying httpx client for the version endpoint
            async with self.client._async_client._client as client:
                response = await client.get(f"{self.client.host}/api/version")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("version")
        except Exception as e:
            log.debug("ollama_version_fetch_failed", error=str(e))

        return None

    async def _get_model_metadata(self, model: str) -> ModelMetadata:
        """Get model metadata from Ollama /api/show endpoint.

        Args:
            model: Model name to get metadata for

        Returns:
            ModelMetadata with available information
        """
        if not self.client:
            return ModelMetadata(name=model)

        try:
            # Use ollama library's show method
            response = await self.client._async_client.show(model)

            details = response.get("details", {})
            model_info = response.get("modelinfo", response.get("model_info", {}))

            # Extract quantization from file type or details
            quantization = details.get("quantization_level", "")
            if not quantization and model_info:
                # Try to extract from file_type field
                file_type = model_info.get("general.file_type", "")
                if file_type:
                    quantization = str(file_type)

            # Get digest - may be in different locations
            digest = ""
            if "digest" in response:
                digest = response["digest"]
            elif model_info and "general.quantization_version" in model_info:
                digest = str(model_info["general.quantization_version"])

            return ModelMetadata(
                name=model,
                digest=digest,
                family=details.get("family", "unknown"),
                parameter_size=details.get("parameter_size", "unknown"),
                quantization_level=quantization or "unknown",
                format=details.get("format", "unknown"),
                modified_at=response.get("modified_at"),
                raw_response=response,
            )

        except Exception as e:
            log.warning(
                "model_metadata_fetch_failed",
                model=model,
                error=str(e),
            )
            return ModelMetadata(name=model)

    def _get_config_snapshot(self) -> dict:
        """Get serialized config snapshot.

        Returns:
            Dictionary of config values
        """
        try:
            return self.config.model_dump(mode="json")
        except Exception:
            # Fallback for older Pydantic versions
            return self.config.dict()


async def capture_snapshot_for_session(
    model: str,
    ollama_client: Optional[OllamaClient] = None,
    config: Optional[SindriConfig] = None,
    inference_params: Optional[InferenceParams] = None,
) -> EnvironmentSnapshot:
    """Convenience function to capture a snapshot.

    Args:
        model: Model name
        ollama_client: Optional Ollama client
        config: Optional config
        inference_params: Optional inference parameters

    Returns:
        EnvironmentSnapshot
    """
    capture = SnapshotCapture(ollama_client, config)
    return await capture.capture(model, inference_params)
