"""Agent bundle system for Sindri.

Provides SDK for packaging agents with prompts and tests,
compatibility validation, and bundle management.
"""

from sindri.bundles.models import (
    AgentBundleConfig,
    BundleDependencies,
    BundleInfo,
    BundleManifest,
    BundleMetadata,
    BundleState,
    TestConfig,
    TestResult,
)
from sindri.bundles.loader import BundleLoader, InstallResult
from sindri.bundles.validator import BundleValidator, BundleValidationResult
from sindri.bundles.sdk import AgentSDK

__all__ = [
    # Models
    "AgentBundleConfig",
    "BundleDependencies",
    "BundleInfo",
    "BundleManifest",
    "BundleMetadata",
    "BundleState",
    "TestConfig",
    "TestResult",
    # Loader
    "BundleLoader",
    "InstallResult",
    # Validator
    "BundleValidator",
    "BundleValidationResult",
    # SDK
    "AgentSDK",
]
