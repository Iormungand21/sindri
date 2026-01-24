"""Tests for agent bundle system."""

import pytest
import tempfile
from pathlib import Path

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
from sindri.bundles.loader import BundleLoader, InstallResult, MANIFEST_FILENAME
from sindri.bundles.validator import BundleValidator, BundleValidationResult, ValidationError
from sindri.bundles.sdk import AgentSDK


class TestBundleModels:
    """Tests for bundle model dataclasses."""

    def test_agent_bundle_config_defaults(self):
        """Test AgentBundleConfig with default values."""
        config = AgentBundleConfig(
            name="test",
            role="Test agent",
            model="qwen2.5-coder:7b",
        )
        assert config.name == "test"
        assert config.tools == []
        assert config.can_delegate is False
        assert config.estimated_vram_gb == 8.0
        assert config.max_iterations == 30

    def test_agent_bundle_config_to_dict(self):
        """Test AgentBundleConfig serialization."""
        config = AgentBundleConfig(
            name="test",
            role="Test agent",
            model="qwen2.5-coder:7b",
            tools=["read_file"],
            fallback_model="qwen2.5:3b",
        )
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["tools"] == ["read_file"]
        assert d["fallback_model"] == "qwen2.5:3b"

    def test_agent_bundle_config_from_dict(self):
        """Test AgentBundleConfig deserialization."""
        data = {
            "name": "test",
            "role": "Test agent",
            "model": "qwen2.5-coder:7b",
            "tools": ["read_file", "write_file"],
            "can_delegate": True,
        }
        config = AgentBundleConfig.from_dict(data)
        assert config.name == "test"
        assert config.tools == ["read_file", "write_file"]
        assert config.can_delegate is True

    def test_bundle_dependencies(self):
        """Test BundleDependencies."""
        deps = BundleDependencies(
            tools=["read_file"],
            models=["qwen2.5-coder:7b"],
            plugins=["my-plugin>=1.0"],
        )
        d = deps.to_dict()
        assert d["tools"] == ["read_file"]
        assert d["plugins"] == ["my-plugin>=1.0"]

    def test_bundle_metadata(self):
        """Test BundleMetadata."""
        meta = BundleMetadata(
            version="1.0.0",
            author="Test Author",
            category="specialist",
            tags=["test", "example"],
        )
        assert meta.version == "1.0.0"
        assert meta.sindri_version == ">=0.1.0"

    def test_test_config_defaults(self):
        """Test TestConfig defaults."""
        config = TestConfig()
        assert config.framework == "pytest"
        assert config.path == "tests/"
        assert config.markers == []

    def test_bundle_manifest_to_dict(self):
        """Test BundleManifest serialization."""
        manifest = BundleManifest(
            schema_version=1,
            agent=AgentBundleConfig(
                name="test",
                role="Test agent",
                model="qwen2.5-coder:7b",
            ),
            dependencies=BundleDependencies(),
            metadata=BundleMetadata(version="1.0.0"),
            prompt_file="prompt.txt",
        )
        d = manifest.to_dict()
        assert d["bundle"]["schema_version"] == 1
        assert d["agent"]["name"] == "test"
        assert d["prompt"]["file"] == "prompt.txt"

    def test_bundle_manifest_from_dict(self):
        """Test BundleManifest deserialization."""
        data = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": "test",
                "role": "Test",
                "model": "qwen2.5-coder:7b",
            },
            "dependencies": {},
            "metadata": {"version": "1.0.0"},
            "prompt": {"content": "You are a test agent."},
        }
        manifest = BundleManifest.from_dict(data)
        assert manifest.agent.name == "test"
        assert manifest.prompt_content == "You are a test agent."


class TestBundleLoader:
    """Tests for BundleLoader."""

    @pytest.fixture
    def temp_bundles_dir(self):
        """Create a temporary bundles directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_bundle(self, temp_bundles_dir):
        """Create a sample bundle."""
        bundle_dir = temp_bundles_dir / "sample"
        bundle_dir.mkdir()

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": "sample",
                "role": "Sample agent",
                "model": "qwen2.5-coder:7b",
                "tools": ["read_file"],
            },
            "dependencies": {
                "tools": ["read_file"],
                "models": ["qwen2.5-coder:7b"],
            },
            "metadata": {"version": "1.0.0"},
            "prompt": {"file": "prompt.txt"},
        }

        import toml

        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        (bundle_dir / "prompt.txt").write_text("You are a sample agent.")

        return bundle_dir

    def test_discover_empty_directory(self, temp_bundles_dir):
        """Test discovery with empty directory."""
        loader = BundleLoader(temp_bundles_dir)
        bundles = loader.discover()
        assert bundles == []

    def test_discover_bundles(self, temp_bundles_dir, sample_bundle):
        """Test bundle discovery."""
        loader = BundleLoader(temp_bundles_dir)
        bundles = loader.discover()
        assert len(bundles) == 1
        assert bundles[0].name == "sample"
        assert bundles[0].state == BundleState.DISCOVERED

    def test_load_bundle(self, sample_bundle):
        """Test loading a single bundle."""
        loader = BundleLoader()
        bundle = loader.load(sample_bundle)
        assert bundle.name == "sample"
        assert bundle.manifest is not None
        assert bundle.manifest.agent.model == "qwen2.5-coder:7b"

    def test_load_bundle_missing_manifest(self, temp_bundles_dir):
        """Test loading bundle without manifest."""
        bundle_dir = temp_bundles_dir / "invalid"
        bundle_dir.mkdir()

        loader = BundleLoader()
        bundle = loader.load(bundle_dir)
        assert bundle.state == BundleState.FAILED
        assert "Manifest not found" in bundle.error

    def test_load_bundle_invalid_toml(self, temp_bundles_dir):
        """Test loading bundle with invalid TOML."""
        bundle_dir = temp_bundles_dir / "bad_toml"
        bundle_dir.mkdir()
        (bundle_dir / MANIFEST_FILENAME).write_text("invalid { toml [")

        loader = BundleLoader()
        bundle = loader.load(bundle_dir)
        assert bundle.state == BundleState.FAILED
        assert "Invalid TOML" in bundle.error

    def test_load_bundle_missing_prompt_file(self, temp_bundles_dir):
        """Test loading bundle with missing prompt file."""
        bundle_dir = temp_bundles_dir / "no_prompt"
        bundle_dir.mkdir()

        import toml

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {"name": "test", "role": "Test", "model": "m"},
            "prompt": {"file": "missing.txt"},
        }
        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        loader = BundleLoader()
        bundle = loader.load(bundle_dir)
        assert bundle.state == BundleState.FAILED
        assert "Prompt file not found" in bundle.error

    def test_install_bundle(self, temp_bundles_dir, sample_bundle):
        """Test bundle installation."""
        loader = BundleLoader(temp_bundles_dir / "installed")
        result = loader.install(sample_bundle)

        assert result.success
        assert result.bundle.name == "sample"
        assert result.installed_path.exists()
        assert (result.installed_path / MANIFEST_FILENAME).exists()

    def test_install_bundle_already_exists(self, temp_bundles_dir, sample_bundle):
        """Test installing bundle that already exists."""
        loader = BundleLoader(temp_bundles_dir / "installed")

        # First install
        result1 = loader.install(sample_bundle)
        assert result1.success

        # Second install without force
        result2 = loader.install(sample_bundle, force=False)
        assert not result2.success
        assert "already exists" in result2.error

        # With force
        result3 = loader.install(sample_bundle, force=True)
        assert result3.success

    def test_uninstall_bundle(self, temp_bundles_dir, sample_bundle):
        """Test bundle uninstallation."""
        loader = BundleLoader(temp_bundles_dir / "installed")

        # Install first
        loader.install(sample_bundle)

        # Uninstall
        result = loader.uninstall("sample")
        assert result.success

    def test_get_bundle(self, temp_bundles_dir, sample_bundle):
        """Test getting bundle by name."""
        loader = BundleLoader(temp_bundles_dir / "installed")
        loader.install(sample_bundle)

        bundle = loader.get_bundle("sample")
        assert bundle is not None
        assert bundle.name == "sample"

    def test_get_bundle_not_found(self, temp_bundles_dir):
        """Test getting non-existent bundle."""
        loader = BundleLoader(temp_bundles_dir)
        bundle = loader.get_bundle("nonexistent")
        assert bundle is None

    def test_get_prompt(self, temp_bundles_dir, sample_bundle):
        """Test getting prompt from bundle."""
        loader = BundleLoader(temp_bundles_dir)
        bundle = loader.load(sample_bundle)

        prompt = loader.get_prompt(bundle)
        assert prompt == "You are a sample agent."


class TestBundleValidator:
    """Tests for BundleValidator."""

    @pytest.fixture
    def temp_bundle_dir(self):
        """Create a temporary bundle directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def valid_bundle(self, temp_bundle_dir):
        """Create a valid bundle."""
        bundle_dir = temp_bundle_dir / "valid"
        bundle_dir.mkdir()

        import toml

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": "valid",
                "role": "Valid agent",
                "model": "qwen2.5-coder:7b",
                "tools": ["read_file"],
            },
            "dependencies": {
                "tools": ["read_file"],
                "models": ["qwen2.5-coder:7b"],
            },
            "metadata": {"version": "1.0.0", "sindri_version": ">=0.1.0"},
            "prompt": {"content": "You are a valid agent."},
        }

        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        return bundle_dir

    @pytest.mark.asyncio
    async def test_validate_valid_bundle(self, valid_bundle):
        """Test validating a valid bundle."""
        validator = BundleValidator(
            existing_tools={"read_file", "write_file"},
        )
        result = await validator.validate(valid_bundle, run_tests=False)

        assert result.valid
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_missing_manifest(self, temp_bundle_dir):
        """Test validating bundle without manifest."""
        bundle_dir = temp_bundle_dir / "no_manifest"
        bundle_dir.mkdir()

        validator = BundleValidator()
        result = await validator.validate(bundle_dir)

        assert not result.valid
        assert any(e[0] == ValidationError.MANIFEST_MISSING for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_missing_required_fields(self, temp_bundle_dir):
        """Test validating bundle with missing required fields."""
        bundle_dir = temp_bundle_dir / "incomplete"
        bundle_dir.mkdir()

        import toml

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {"name": ""},  # Empty name
        }

        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        validator = BundleValidator()
        result = await validator.validate(bundle_dir)

        assert not result.valid
        assert any(e[0] == ValidationError.MANIFEST_INVALID for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_name_conflict(self, valid_bundle):
        """Test validating bundle with name conflict."""
        validator = BundleValidator(
            existing_agents={"valid"},  # Conflicts with bundle name
        )
        result = await validator.validate(valid_bundle)

        assert not result.valid
        assert any(e[0] == ValidationError.NAME_CONFLICT for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_warns_missing_tools(self, valid_bundle):
        """Test validation warns about missing tools."""
        validator = BundleValidator(
            existing_tools={"write_file"},  # Missing read_file which bundle needs
        )
        result = await validator.validate(valid_bundle)

        # Should still be valid but with warnings about missing tool
        assert result.valid
        assert len(result.warnings) > 0
        assert any("read_file" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_validate_warns_high_vram(self, temp_bundle_dir):
        """Test validation warns about high VRAM."""
        bundle_dir = temp_bundle_dir / "high_vram"
        bundle_dir.mkdir()

        import toml

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": "high_vram",
                "role": "Test",
                "model": "huge:70b",
                "estimated_vram_gb": 48.0,
            },
            "prompt": {"content": "Test"},
        }

        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        validator = BundleValidator()
        result = await validator.validate(bundle_dir)

        assert any("VRAM" in w or "vram" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_validate_warns_missing_dependency_models(self, temp_bundle_dir):
        """Test validation warns about models in dependencies.models."""
        bundle_dir = temp_bundle_dir / "dep_models"
        bundle_dir.mkdir()

        import toml

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": "dep_models",
                "role": "Test",
                "model": "qwen2.5-coder:7b",
            },
            "dependencies": {
                "models": ["qwen2.5-coder:7b", "extra-model:14b"],  # Extra model
            },
            "prompt": {"content": "Test"},
        }

        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        validator = BundleValidator(
            available_models={"qwen2.5-coder:7b"},  # Missing extra-model
        )
        result = await validator.validate(bundle_dir)

        assert result.valid  # Still valid, just warnings
        assert any("extra-model:14b" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_validate_warns_plugin_dependencies(self, temp_bundle_dir):
        """Test validation warns about plugin dependencies."""
        bundle_dir = temp_bundle_dir / "plugin_deps"
        bundle_dir.mkdir()

        import toml

        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": "plugin_deps",
                "role": "Test",
                "model": "qwen2.5-coder:7b",
            },
            "dependencies": {
                "plugins": ["my-plugin>=1.0", "other-plugin"],
            },
            "prompt": {"content": "Test"},
        }

        with open(bundle_dir / MANIFEST_FILENAME, "w") as f:
            toml.dump(manifest, f)

        validator = BundleValidator()
        result = await validator.validate(bundle_dir)

        assert result.valid  # Still valid, just warnings
        assert any("my-plugin" in w for w in result.warnings)
        assert any("other-plugin" in w for w in result.warnings)


class TestAgentSDK:
    """Tests for AgentSDK."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_create_bundle(self, temp_output_dir):
        """Test creating a new bundle."""
        bundle_path = AgentSDK.create_bundle(
            name="myagent",
            role="My custom agent",
            model="qwen2.5-coder:7b",
            prompt="You are my custom agent.",
            output_dir=temp_output_dir,
            tools=["read_file", "write_file"],
            include_tests=True,
        )

        assert bundle_path.exists()
        assert (bundle_path / MANIFEST_FILENAME).exists()
        assert (bundle_path / "prompt.txt").exists()
        assert (bundle_path / "README.md").exists()
        assert (bundle_path / "tests").is_dir()
        assert (bundle_path / "tests" / "test_myagent.py").exists()

    def test_create_bundle_no_tests(self, temp_output_dir):
        """Test creating bundle without tests."""
        bundle_path = AgentSDK.create_bundle(
            name="notests",
            role="Agent without tests",
            model="qwen2.5-coder:7b",
            prompt="Test prompt",
            output_dir=temp_output_dir,
            include_tests=False,
        )

        assert bundle_path.exists()
        assert not (bundle_path / "tests").exists()

    def test_create_bundle_manifest_content(self, temp_output_dir):
        """Test created bundle manifest content."""
        AgentSDK.create_bundle(
            name="content_test",
            role="Test content",
            model="qwen2.5-coder:7b",
            prompt="Test prompt",
            output_dir=temp_output_dir,
            tools=["read_file"],
            author="Test Author",
            category="specialist",
            can_delegate=True,
            delegate_to=["huginn"],
        )

        import toml

        manifest_path = temp_output_dir / "content_test" / MANIFEST_FILENAME
        manifest = toml.load(manifest_path)

        assert manifest["agent"]["name"] == "content_test"
        assert manifest["agent"]["can_delegate"] is True
        assert manifest["agent"]["delegate_to"] == ["huginn"]
        assert manifest["metadata"]["author"] == "Test Author"

    def test_from_definition(self, temp_output_dir):
        """Test exporting existing agent definition."""
        from sindri.agents.definitions import AgentDefinition

        agent = AgentDefinition(
            name="exported",
            role="Exported agent",
            model="qwen2.5-coder:7b",
            system_prompt="Original prompt",
            tools=["read_file"],
        )

        bundle_path = AgentSDK.from_definition(
            agent=agent,
            output_dir=temp_output_dir,
        )

        assert bundle_path.exists()

        # Verify prompt was exported
        prompt_path = bundle_path / "prompt.txt"
        assert prompt_path.read_text() == "Original prompt"

    def test_scaffold(self, temp_output_dir):
        """Test creating minimal scaffold."""
        bundle_path = AgentSDK.scaffold(temp_output_dir, "scaffold_test")

        assert bundle_path.exists()
        assert (bundle_path / MANIFEST_FILENAME).exists()
        assert (bundle_path / "prompt.txt").exists()
        assert (bundle_path / "tests").is_dir()
        assert (bundle_path / "tools").is_dir()


class TestBundleIntegration:
    """Integration tests for bundle system."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            bundles_dir = base / "bundles"
            bundles_dir.mkdir()
            yield base, bundles_dir

    def test_full_workflow(self, temp_dirs):
        """Test full create -> validate -> install workflow."""
        base, bundles_dir = temp_dirs

        # Create bundle
        bundle_path = AgentSDK.create_bundle(
            name="workflow_test",
            role="Workflow test agent",
            model="qwen2.5-coder:7b",
            prompt="You are a test agent.",
            output_dir=base,
            tools=["read_file"],
        )

        # Validate
        import asyncio

        validator = BundleValidator(existing_tools={"read_file"})
        result = asyncio.get_event_loop().run_until_complete(
            validator.validate(bundle_path, run_tests=False)
        )
        assert result.valid

        # Install
        loader = BundleLoader(bundles_dir)
        install_result = loader.install(bundle_path)
        assert install_result.success

        # Discover
        bundles = loader.discover()
        assert len(bundles) == 1
        assert bundles[0].name == "workflow_test"

    def test_plugin_manager_integration(self, temp_dirs):
        """Test bundle integration with PluginManager."""
        from sindri.plugins.manager import PluginManager
        from sindri.agents.registry import AGENTS

        base, bundles_dir = temp_dirs

        # Create and install a bundle
        bundle_path = AgentSDK.create_bundle(
            name="pm_test",
            role="Plugin manager test",
            model="qwen2.5-coder:7b",
            prompt="Test prompt",
            output_dir=base,
        )

        loader = BundleLoader(bundles_dir)
        loader.install(bundle_path)

        # Use PluginManager
        manager = PluginManager(bundles_dir=bundles_dir)
        discovered = manager.discover_bundles()
        assert len(discovered) == 1

        # Register
        agents = dict(AGENTS)
        original_count = len(agents)
        manager.register_bundles(agents)

        assert len(agents) == original_count + 1
        assert "pm_test" in agents


class TestTestResult:
    """Tests for TestResult model."""

    def test_test_result_passed(self):
        """Test TestResult for passing tests."""
        result = TestResult(
            passed=True,
            total=5,
            passed_count=5,
            failed_count=0,
        )
        assert result.passed
        assert result.total == 5

    def test_test_result_failed(self):
        """Test TestResult for failing tests."""
        result = TestResult(
            passed=False,
            total=5,
            passed_count=3,
            failed_count=2,
            failures=["Test 1 failed", "Test 2 failed"],
        )
        assert not result.passed
        assert result.failed_count == 2
        assert len(result.failures) == 2
