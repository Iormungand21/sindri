"""Tests for the Sindri plugin system."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from sindri.plugins.loader import PluginLoader, PluginType
from sindri.plugins.validator import (
    PluginValidator,
    ValidationError,
)
from sindri.plugins.manager import (
    PluginManager,
    PluginState,
    load_plugins,
)
from sindri.tools.registry import ToolRegistry
from sindri.agents.definitions import AgentDefinition


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_plugin_dir():
    """Create a temporary plugin directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "plugins"
        plugin_dir.mkdir()
        yield plugin_dir


@pytest.fixture
def temp_agent_dir():
    """Create a temporary agent config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "agents"
        agent_dir.mkdir()
        yield agent_dir


@pytest.fixture
def valid_tool_plugin(temp_plugin_dir):
    """Create a valid tool plugin file."""
    plugin_code = '''"""Example tool plugin."""

__version__ = "1.0.0"
__author__ = "Test Author"

from sindri.tools.base import Tool, ToolResult


class EchoTool(Tool):
    """A simple echo tool."""

    name = "echo"
    description = "Echoes input back"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"}
        },
        "required": ["message"]
    }

    async def execute(self, message: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Echo: {message}")
'''
    plugin_path = temp_plugin_dir / "echo_tool.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def invalid_syntax_plugin(temp_plugin_dir):
    """Create a plugin with syntax errors."""
    plugin_code = '''"""Invalid plugin."""

class BadClass(
    # Missing closing parenthesis
'''
    plugin_path = temp_plugin_dir / "bad_syntax.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def dangerous_plugin(temp_plugin_dir):
    """Create a plugin with dangerous imports."""
    plugin_code = '''"""Plugin with dangerous imports."""

import subprocess
import pickle
from sindri.tools.base import Tool, ToolResult


class DangerousTool(Tool):
    name = "dangerous"
    description = "Dangerous tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="")
'''
    plugin_path = temp_plugin_dir / "dangerous.py"
    plugin_path.write_text(plugin_code)
    return plugin_path


@pytest.fixture
def valid_agent_config(temp_agent_dir):
    """Create a valid agent TOML config."""
    config = """[metadata]
version = "1.0.0"
author = "Test Author"

[agent]
name = "thor"
role = "Performance Optimizer"
model = "qwen2.5-coder:7b"
tools = ["read_file", "write_file"]
max_iterations = 25
estimated_vram_gb = 5.0
temperature = 0.4
can_delegate = false

[prompt]
content = "You are Thor, the performance optimizer."
"""
    config_path = temp_agent_dir / "thor.toml"
    config_path.write_text(config)
    return config_path


@pytest.fixture
def invalid_agent_config(temp_agent_dir):
    """Create an invalid agent config (missing required fields)."""
    config = """[agent]
name = "incomplete"
# Missing: role, model
"""
    config_path = temp_agent_dir / "incomplete.toml"
    config_path.write_text(config)
    return config_path


# ============================================================================
# PluginLoader Tests
# ============================================================================


class TestPluginLoader:
    """Tests for PluginLoader."""

    def test_init_default_dirs(self):
        """Test loader initializes with default directories."""
        loader = PluginLoader()
        assert loader.plugin_dir == Path.home() / ".sindri" / "plugins"
        assert loader.agent_dir == Path.home() / ".sindri" / "agents"

    def test_init_custom_dirs(self, temp_plugin_dir, temp_agent_dir):
        """Test loader with custom directories."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        assert loader.plugin_dir == temp_plugin_dir
        assert loader.agent_dir == temp_agent_dir

    def test_discover_empty_dirs(self, temp_plugin_dir, temp_agent_dir):
        """Test discovering with empty directories."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()
        assert plugins == []

    def test_discover_tool_plugin(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin
    ):
        """Test discovering a valid tool plugin."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.type == PluginType.TOOL
        assert plugin.name == "echo"
        assert plugin.path == valid_tool_plugin
        assert plugin.version == "1.0.0"
        assert plugin.author == "Test Author"
        assert plugin.enabled is True
        assert plugin.tool_class is not None

    def test_discover_agent_config(
        self, temp_plugin_dir, temp_agent_dir, valid_agent_config
    ):
        """Test discovering a valid agent config."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.type == PluginType.AGENT
        assert plugin.name == "thor"
        assert plugin.path == valid_agent_config
        assert plugin.version == "1.0.0"
        assert plugin.agent_config is not None
        assert plugin.agent_config["model"] == "qwen2.5-coder:7b"

    def test_discover_syntax_error(
        self, temp_plugin_dir, temp_agent_dir, invalid_syntax_plugin
    ):
        """Test handling syntax errors in plugins."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.type == PluginType.TOOL
        assert plugin.enabled is False
        assert plugin.error is not None
        assert "Syntax error" in plugin.error

    def test_discover_skips_hidden_files(self, temp_plugin_dir, temp_agent_dir):
        """Test that hidden files are skipped."""
        hidden_plugin = temp_plugin_dir / "_hidden.py"
        hidden_plugin.write_text("# hidden")

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()
        assert plugins == []

    def test_get_tools(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test get_tools filters correctly."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        loader.discover()

        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].type == PluginType.TOOL

    def test_get_agents(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test get_agents filters correctly."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        loader.discover()

        agents = loader.get_agents()
        assert len(agents) == 1
        assert agents[0].type == PluginType.AGENT

    def test_discover_nonexistent_dirs(self):
        """Test discovering from nonexistent directories."""
        loader = PluginLoader(
            plugin_dir=Path("/nonexistent/plugins"),
            agent_dir=Path("/nonexistent/agents"),
        )
        plugins = loader.discover()
        assert plugins == []


# ============================================================================
# PluginValidator Tests
# ============================================================================


class TestPluginValidator:
    """Tests for PluginValidator."""

    def test_validate_valid_tool(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin
    ):
        """Test validating a valid tool plugin."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator()
        result = validator.validate(plugins[0])

        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_dangerous_imports(
        self, temp_plugin_dir, temp_agent_dir, dangerous_plugin
    ):
        """Test detecting dangerous imports."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator()
        result = validator.validate(plugins[0])

        assert result.valid is False
        error_types = [e[0] for e in result.errors]
        assert ValidationError.SECURITY_VIOLATION in error_types

    def test_validate_name_conflict_tool(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin
    ):
        """Test detecting tool name conflicts."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator(existing_tools={"echo"})
        result = validator.validate(plugins[0])

        assert result.valid is False
        error_types = [e[0] for e in result.errors]
        assert ValidationError.NAME_CONFLICT in error_types

    def test_validate_name_conflict_agent(
        self, temp_plugin_dir, temp_agent_dir, valid_agent_config
    ):
        """Test detecting agent name conflicts."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator(existing_agents={"thor"})
        result = validator.validate(plugins[0])

        assert result.valid is False
        error_types = [e[0] for e in result.errors]
        assert ValidationError.NAME_CONFLICT in error_types

    def test_validate_missing_model_warning(
        self, temp_plugin_dir, temp_agent_dir, valid_agent_config
    ):
        """Test warning for unavailable model."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator(available_models={"llama3.1:8b"})
        result = validator.validate(plugins[0])

        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("not in available models" in w for w in result.warnings)

    def test_validate_invalid_agent_config(
        self, temp_plugin_dir, temp_agent_dir, invalid_agent_config
    ):
        """Test validating invalid agent config."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert len(plugins) == 1
        assert plugins[0].error is not None

    def test_strict_mode(self, temp_plugin_dir, temp_agent_dir, valid_agent_config):
        """Test strict mode treats warnings as errors."""
        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator(available_models={"different:model"}, strict=True)
        result = validator.validate(plugins[0])

        # Strict mode should fail due to model warning
        assert result.valid is False

    def test_validate_tool_missing_attributes(self, temp_plugin_dir, temp_agent_dir):
        """Test validating tool with missing attributes."""
        bad_tool_code = '''"""Bad tool without required attributes."""
from sindri.tools.base import Tool, ToolResult

class BadTool(Tool):
    # Missing name, description, parameters

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="")
'''
        plugin_path = temp_plugin_dir / "bad_tool.py"
        plugin_path.write_text(bad_tool_code)

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator()
        result = validator.validate(plugins[0])

        error_types = [e[0] for e in result.errors]
        assert ValidationError.MISSING_REQUIRED in error_types


# ============================================================================
# PluginManager Tests
# ============================================================================


class TestPluginManager:
    """Tests for PluginManager."""

    def test_init_default(self):
        """Test manager with default directories."""
        manager = PluginManager()
        assert manager.plugin_dir == Path.home() / ".sindri" / "plugins"
        assert manager.agent_dir == Path.home() / ".sindri" / "agents"

    def test_discover_and_validate(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test full discovery and validation flow."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)

        # Discover
        discovered = manager.discover()
        assert len(discovered) == 2

        # Validate
        results = manager.validate_all()
        assert len(results) == 2

        # Check all validated
        for key, result in results.items():
            assert result.valid is True

    def test_register_tools(self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin):
        """Test registering tool plugins with ToolRegistry."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        registry = ToolRegistry()
        registered = manager.register_tools(registry)

        assert "echo" in registered
        assert registry.get_tool("echo") is not None

    def test_register_agents(self, temp_plugin_dir, temp_agent_dir, valid_agent_config):
        """Test registering agent plugins with agent registry."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        agents: dict[str, AgentDefinition] = {}
        registered = manager.register_agents(agents)

        assert "thor" in registered
        assert "thor" in agents
        assert agents["thor"].model == "qwen2.5-coder:7b"
        assert agents["thor"].role == "Performance Optimizer"

    def test_get_loaded_tools(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test get_loaded_tools returns correct plugins."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        registry = ToolRegistry()
        manager.register_tools(registry)

        loaded = manager.get_loaded_tools()
        assert len(loaded) == 1
        assert loaded[0].info.name == "echo"
        assert loaded[0].state == PluginState.LOADED

    def test_get_loaded_agents(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test get_loaded_agents returns correct plugins."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        agents = {}
        manager.register_agents(agents)

        loaded = manager.get_loaded_agents()
        assert len(loaded) == 1
        assert loaded[0].info.name == "thor"
        assert loaded[0].state == PluginState.LOADED

    def test_get_failed_plugins(
        self, temp_plugin_dir, temp_agent_dir, invalid_syntax_plugin
    ):
        """Test get_failed_plugins returns failed plugins."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        failed = manager.get_failed_plugins()
        assert len(failed) == 1
        assert failed[0].state == PluginState.FAILED

    def test_get_plugin_count(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test get_plugin_count returns correct counts."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        counts = manager.get_plugin_count()
        assert counts["VALIDATED"] == 2
        assert counts["FAILED"] == 0

    def test_ensure_directories(self, temp_plugin_dir, temp_agent_dir):
        """Test ensure_directories creates directories."""
        import shutil

        # Remove directories
        if temp_plugin_dir.exists():
            shutil.rmtree(temp_plugin_dir)
        if temp_agent_dir.exists():
            shutil.rmtree(temp_agent_dir)

        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.ensure_directories()

        assert temp_plugin_dir.exists()
        assert temp_agent_dir.exists()


# ============================================================================
# load_plugins Convenience Function Tests
# ============================================================================


class TestLoadPluginsFunction:
    """Tests for the load_plugins convenience function."""

    def test_load_plugins_full_flow(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin, valid_agent_config
    ):
        """Test full plugin loading flow."""
        registry = ToolRegistry.default()
        agents = {"brokkr": MagicMock(spec=AgentDefinition)}

        manager = load_plugins(
            tool_registry=registry,
            agents=agents,
            plugin_dir=temp_plugin_dir,
            agent_dir=temp_agent_dir,
        )

        # Check tools were registered
        assert registry.get_tool("echo") is not None

        # Check agents were added
        assert "thor" in agents

        # Check manager state
        assert len(manager.get_loaded_tools()) == 1
        assert len(manager.get_loaded_agents()) == 1


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestPluginEdgeCases:
    """Tests for edge cases in the plugin system."""

    def test_plugin_with_external_prompt_file(self, temp_plugin_dir, temp_agent_dir):
        """Test agent config with external prompt file."""
        prompt_content = "You are a custom agent with an external prompt."
        prompt_file = temp_agent_dir / "custom_prompt.txt"
        prompt_file.write_text(prompt_content)

        config = """[agent]
name = "custom"
role = "Custom Agent"
model = "llama3.1:8b"

[prompt]
file = "custom_prompt.txt"
"""
        config_path = temp_agent_dir / "custom.toml"
        config_path.write_text(config)

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert len(plugins) == 1
        assert plugins[0].agent_config["system_prompt"] == prompt_content

    def test_plugin_with_delegation(self, temp_plugin_dir, temp_agent_dir):
        """Test agent config with delegation enabled."""
        config = """[agent]
name = "delegator"
role = "Delegating Agent"
model = "qwen2.5-coder:14b"
tools = ["delegate"]
can_delegate = true
delegate_to = ["huginn", "mimir"]

[prompt]
content = "You can delegate to other agents."
"""
        config_path = temp_agent_dir / "delegator.toml"
        config_path.write_text(config)

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert plugins[0].agent_config["can_delegate"] is True
        assert "huginn" in plugins[0].agent_config["delegate_to"]

    def test_multiple_tool_classes_in_file(self, temp_plugin_dir, temp_agent_dir):
        """Test plugin with multiple tool classes (should pick first)."""
        plugin_code = '''"""Multiple tools in one file."""
from sindri.tools.base import Tool, ToolResult

class FirstTool(Tool):
    name = "first"
    description = "First tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="first")

class SecondTool(Tool):
    name = "second"
    description = "Second tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="second")
'''
        plugin_path = temp_plugin_dir / "multi_tools.py"
        plugin_path.write_text(plugin_code)

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        assert len(plugins) == 1
        assert plugins[0].name == "first"

    def test_dangerous_eval_call(self, temp_plugin_dir, temp_agent_dir):
        """Test detecting dangerous eval() calls."""
        plugin_code = '''"""Plugin with eval."""
from sindri.tools.base import Tool, ToolResult

class EvalTool(Tool):
    name = "eval_tool"
    description = "Dangerous tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        result = eval("1 + 1")  # Dangerous!
        return ToolResult(success=True, output=str(result))
'''
        plugin_path = temp_plugin_dir / "eval_tool.py"
        plugin_path.write_text(plugin_code)

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator()
        result = validator.validate(plugins[0])

        assert result.valid is False
        error_types = [e[0] for e in result.errors]
        assert ValidationError.SECURITY_VIOLATION in error_types

    def test_file_open_warning(self, temp_plugin_dir, temp_agent_dir):
        """Test warning for direct file open()."""
        plugin_code = '''"""Plugin with open()."""
from sindri.tools.base import Tool, ToolResult

class FileOpenTool(Tool):
    name = "file_open"
    description = "Uses open()"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        with open("test.txt") as f:
            content = f.read()
        return ToolResult(success=True, output=content)
'''
        plugin_path = temp_plugin_dir / "file_open.py"
        plugin_path.write_text(plugin_code)

        loader = PluginLoader(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        plugins = loader.discover()

        validator = PluginValidator()
        result = validator.validate(plugins[0])

        # Should be warning, not error
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("open()" in w for w in result.warnings)


# ============================================================================
# Plugin Tool Execution Tests
# ============================================================================


class TestPluginToolExecution:
    """Tests for executing plugin tools."""

    @pytest.mark.asyncio
    async def test_execute_plugin_tool(
        self, temp_plugin_dir, temp_agent_dir, valid_tool_plugin
    ):
        """Test executing a loaded plugin tool."""
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        registry = ToolRegistry()
        manager.register_tools(registry)

        result = await registry.execute("echo", {"message": "Hello!"})

        assert result.success is True
        assert "Hello!" in result.output

    @pytest.mark.asyncio
    async def test_plugin_tool_error_handling(self, temp_plugin_dir, temp_agent_dir):
        """Test plugin tool error handling."""
        error_tool_code = '''"""Tool that raises errors."""
from sindri.tools.base import Tool, ToolResult

class ErrorTool(Tool):
    name = "error_tool"
    description = "Raises an error"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        raise ValueError("Intentional error")
'''
        plugin_path = temp_plugin_dir / "error_tool.py"
        plugin_path.write_text(error_tool_code)

        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.discover()
        manager.validate_all()

        registry = ToolRegistry()
        manager.register_tools(registry)

        result = await registry.execute("error_tool", {})

        assert result.success is False
        assert "Intentional error" in (result.error or "")


# ============================================================================
# CLI Integration Tests
# ============================================================================


class TestPluginCLI:
    """Tests for plugin CLI commands."""

    def test_plugins_dirs_command(self, temp_plugin_dir, temp_agent_dir):
        """Test plugins dirs command."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["plugins", "dirs"])

        assert result.exit_code == 0
        assert "Plugin Directories" in result.output

    def test_plugins_list_empty(self, temp_plugin_dir, temp_agent_dir):
        """Test plugins list with no plugins."""
        from click.testing import CliRunner
        from sindri.cli import cli

        runner = CliRunner()

        # Patch the manager at its source module
        with patch("sindri.plugins.manager.PluginManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.plugin_dir = temp_plugin_dir
            mock_instance.agent_dir = temp_agent_dir
            mock_instance.get_all_plugins.return_value = []
            mock_instance.get_plugin_count.return_value = {}
            MockManager.return_value = mock_instance

            # Also patch the import in the function's namespace
            with patch.dict(
                "sys.modules", {"sindri.plugins": MagicMock(PluginManager=MockManager)}
            ):
                result = runner.invoke(cli, ["plugins", "list"])

        # Just check it runs without error - actual output depends on real manager
        assert result.exit_code == 0

    def test_plugins_init_tool_template(self, temp_plugin_dir, temp_agent_dir):
        """Test creating tool plugin template."""
        from click.testing import CliRunner
        from sindri.cli import cli
        from sindri.plugins import PluginManager

        runner = CliRunner()

        # Create a real manager with temp dirs
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.ensure_directories()

        with patch("sindri.plugins.PluginManager", return_value=manager):
            result = runner.invoke(cli, ["plugins", "init", "--tool", "my_tool"])

        assert result.exit_code == 0
        assert (temp_plugin_dir / "my_tool.py").exists()

    def test_plugins_init_agent_template(self, temp_plugin_dir, temp_agent_dir):
        """Test creating agent plugin template."""
        from click.testing import CliRunner
        from sindri.cli import cli
        from sindri.plugins import PluginManager

        runner = CliRunner()

        # Create a real manager with temp dirs
        manager = PluginManager(plugin_dir=temp_plugin_dir, agent_dir=temp_agent_dir)
        manager.ensure_directories()

        with patch("sindri.plugins.PluginManager", return_value=manager):
            result = runner.invoke(cli, ["plugins", "init", "--agent", "my_agent"])

        assert result.exit_code == 0
        assert (temp_agent_dir / "my_agent.toml").exists()
