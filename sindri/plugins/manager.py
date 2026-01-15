"""Plugin manager for Sindri.

Coordinates plugin discovery, validation, loading, and registration.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Set
import structlog

from sindri.plugins.loader import PluginLoader, PluginInfo, PluginType
from sindri.plugins.validator import PluginValidator, ValidationResult
from sindri.tools.base import Tool
from sindri.tools.registry import ToolRegistry
from sindri.agents.definitions import AgentDefinition

log = structlog.get_logger()


class PluginState(Enum):
    """State of a plugin."""
    DISCOVERED = auto()     # Found but not validated
    VALIDATED = auto()      # Passed validation
    LOADED = auto()         # Successfully loaded and registered
    FAILED = auto()         # Failed validation or loading
    DISABLED = auto()       # Explicitly disabled by user


@dataclass
class LoadedPlugin:
    """A loaded and registered plugin.

    Attributes:
        info: Original plugin info
        state: Current state
        validation: Validation result (if validated)
        tool_instance: Instantiated tool (for tool plugins)
        agent_definition: Agent definition (for agent plugins)
        error: Error message if loading failed
    """
    info: PluginInfo
    state: PluginState = PluginState.DISCOVERED
    validation: Optional[ValidationResult] = None
    tool_instance: Optional[Tool] = None
    agent_definition: Optional[AgentDefinition] = None
    error: Optional[str] = None


class PluginManager:
    """Manages plugin lifecycle in Sindri.

    Handles:
    - Plugin discovery from filesystem
    - Validation for safety and correctness
    - Registration with tool and agent registries
    - State tracking for all plugins

    Example:
        manager = PluginManager()
        manager.discover()
        manager.validate_all()

        # Register with existing systems
        tool_registry = ToolRegistry.default()
        agents = dict(AGENTS)  # Copy of agent registry

        manager.register_tools(tool_registry)
        manager.register_agents(agents)
    """

    def __init__(
        self,
        plugin_dir: Optional[Path] = None,
        agent_dir: Optional[Path] = None,
        strict_validation: bool = False
    ):
        """Initialize the plugin manager.

        Args:
            plugin_dir: Directory for Python plugins
            agent_dir: Directory for agent configs
            strict_validation: If True, treat validation warnings as errors
        """
        self.loader = PluginLoader(plugin_dir, agent_dir)
        self.strict_validation = strict_validation
        self._plugins: dict[str, LoadedPlugin] = {}
        self._tool_names: Set[str] = set()
        self._agent_names: Set[str] = set()

    @property
    def plugin_dir(self) -> Path:
        """Get the plugin directory."""
        return self.loader.plugin_dir

    @property
    def agent_dir(self) -> Path:
        """Get the agent directory."""
        return self.loader.agent_dir

    def discover(self) -> list[PluginInfo]:
        """Discover all available plugins.

        Returns:
            List of discovered PluginInfo objects
        """
        discovered = self.loader.discover()

        for info in discovered:
            key = f"{info.type.name}:{info.name}"
            self._plugins[key] = LoadedPlugin(info=info, state=PluginState.DISCOVERED)

        log.info(
            "plugins_discovered",
            count=len(discovered),
            tools=len([p for p in discovered if p.type == PluginType.TOOL]),
            agents=len([p for p in discovered if p.type == PluginType.AGENT])
        )

        return discovered

    def validate_all(
        self,
        existing_tools: Optional[Set[str]] = None,
        existing_agents: Optional[Set[str]] = None,
        available_models: Optional[Set[str]] = None
    ) -> dict[str, ValidationResult]:
        """Validate all discovered plugins.

        Args:
            existing_tools: Set of existing tool names
            existing_agents: Set of existing agent names
            available_models: Set of available model names

        Returns:
            Dict mapping plugin keys to ValidationResults
        """
        # Combine existing with discovered plugin tools/agents
        all_tools = set(existing_tools or set())
        all_agents = set(existing_agents or set())

        # First pass: collect all plugin tool/agent names
        for loaded in self._plugins.values():
            if loaded.info.type == PluginType.TOOL and loaded.info.enabled:
                all_tools.add(loaded.info.name)
            elif loaded.info.type == PluginType.AGENT and loaded.info.enabled:
                if loaded.info.agent_config:
                    all_agents.add(loaded.info.agent_config["name"])

        validator = PluginValidator(
            existing_tools=existing_tools or set(),  # Only check against core tools
            existing_agents=existing_agents or set(),  # Only check against core agents
            available_models=available_models,
            strict=self.strict_validation
        )

        results = {}

        for key, loaded in self._plugins.items():
            if loaded.info.error:
                # Already failed during loading
                loaded.state = PluginState.FAILED
                loaded.error = loaded.info.error
                results[key] = ValidationResult(valid=False)
                results[key].errors.append((None, loaded.info.error))
                continue

            if not loaded.info.enabled:
                loaded.state = PluginState.DISABLED
                continue

            result = validator.validate(loaded.info)
            loaded.validation = result

            if result.valid:
                loaded.state = PluginState.VALIDATED
                log.info("plugin_validated", key=key)
            else:
                loaded.state = PluginState.FAILED
                loaded.error = "; ".join(msg for _, msg in result.errors)
                log.warning(
                    "plugin_validation_failed",
                    key=key,
                    errors=loaded.error
                )

            results[key] = result

        return results

    def register_tools(
        self,
        registry: ToolRegistry,
        work_dir: Optional[Path] = None
    ) -> list[str]:
        """Register validated tool plugins with a ToolRegistry.

        Args:
            registry: ToolRegistry to register tools with
            work_dir: Working directory for tools

        Returns:
            List of registered tool names
        """
        registered = []

        for loaded in self._plugins.values():
            if loaded.info.type != PluginType.TOOL:
                continue

            if loaded.state != PluginState.VALIDATED:
                continue

            if not loaded.info.tool_class:
                continue

            try:
                # Instantiate tool with work_dir
                tool_instance = loaded.info.tool_class(work_dir=work_dir)
                registry.register(tool_instance)

                loaded.tool_instance = tool_instance
                loaded.state = PluginState.LOADED
                registered.append(loaded.info.name)

                log.info(
                    "plugin_tool_registered",
                    name=loaded.info.name,
                    path=str(loaded.info.path)
                )
            except Exception as e:
                loaded.state = PluginState.FAILED
                loaded.error = f"Failed to instantiate: {e}"
                log.error(
                    "plugin_tool_register_failed",
                    name=loaded.info.name,
                    error=str(e)
                )

        self._tool_names.update(registered)
        return registered

    def register_agents(
        self,
        agents: dict[str, AgentDefinition]
    ) -> list[str]:
        """Register validated agent plugins with an agent registry.

        Args:
            agents: Dict of agent definitions to add to

        Returns:
            List of registered agent names
        """
        registered = []

        for loaded in self._plugins.values():
            if loaded.info.type != PluginType.AGENT:
                continue

            if loaded.state != PluginState.VALIDATED:
                continue

            if not loaded.info.agent_config:
                continue

            try:
                config = loaded.info.agent_config

                # Create AgentDefinition
                agent_def = AgentDefinition(
                    name=config["name"],
                    role=config["role"],
                    model=config["model"],
                    system_prompt=config["system_prompt"],
                    tools=config.get("tools", []),
                    can_delegate=config.get("can_delegate", False),
                    delegate_to=config.get("delegate_to", []),
                    estimated_vram_gb=config.get("estimated_vram_gb", 8.0),
                    priority=config.get("priority", 1),
                    max_iterations=config.get("max_iterations", 30),
                    max_context_tokens=config.get("max_context_tokens", 16384),
                    temperature=config.get("temperature", 0.3),
                    fallback_model=config.get("fallback_model"),
                    fallback_vram_gb=config.get("fallback_vram_gb"),
                )

                agents[config["name"]] = agent_def

                loaded.agent_definition = agent_def
                loaded.state = PluginState.LOADED
                registered.append(config["name"])

                log.info(
                    "plugin_agent_registered",
                    name=config["name"],
                    model=config["model"],
                    path=str(loaded.info.path)
                )
            except Exception as e:
                loaded.state = PluginState.FAILED
                loaded.error = f"Failed to create agent: {e}"
                log.error(
                    "plugin_agent_register_failed",
                    name=loaded.info.name,
                    error=str(e)
                )

        self._agent_names.update(registered)
        return registered

    def get_loaded_tools(self) -> list[LoadedPlugin]:
        """Get all loaded tool plugins.

        Returns:
            List of LoadedPlugin for tools
        """
        return [
            p for p in self._plugins.values()
            if p.info.type == PluginType.TOOL and p.state == PluginState.LOADED
        ]

    def get_loaded_agents(self) -> list[LoadedPlugin]:
        """Get all loaded agent plugins.

        Returns:
            List of LoadedPlugin for agents
        """
        return [
            p for p in self._plugins.values()
            if p.info.type == PluginType.AGENT and p.state == PluginState.LOADED
        ]

    def get_failed_plugins(self) -> list[LoadedPlugin]:
        """Get all plugins that failed validation or loading.

        Returns:
            List of LoadedPlugin in FAILED state
        """
        return [
            p for p in self._plugins.values()
            if p.state == PluginState.FAILED
        ]

    def get_all_plugins(self) -> list[LoadedPlugin]:
        """Get all plugins.

        Returns:
            List of all LoadedPlugin objects
        """
        return list(self._plugins.values())

    def get_plugin_count(self) -> dict[str, int]:
        """Get counts of plugins by state.

        Returns:
            Dict with counts by state
        """
        counts = {state.name: 0 for state in PluginState}
        for loaded in self._plugins.values():
            counts[loaded.state.name] += 1
        return counts

    def ensure_directories(self) -> None:
        """Ensure plugin directories exist."""
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        log.debug(
            "plugin_directories_created",
            plugin_dir=str(self.plugin_dir),
            agent_dir=str(self.agent_dir)
        )

    def get_tool_names(self) -> Set[str]:
        """Get names of all loaded plugin tools.

        Returns:
            Set of tool names
        """
        return self._tool_names.copy()

    def get_agent_names(self) -> Set[str]:
        """Get names of all loaded plugin agents.

        Returns:
            Set of agent names
        """
        return self._agent_names.copy()


def load_plugins(
    tool_registry: ToolRegistry,
    agents: dict[str, AgentDefinition],
    plugin_dir: Optional[Path] = None,
    agent_dir: Optional[Path] = None,
    strict: bool = False,
    available_models: Optional[Set[str]] = None
) -> PluginManager:
    """Convenience function to discover, validate, and register all plugins.

    Args:
        tool_registry: ToolRegistry to register tools with
        agents: Dict of agent definitions
        plugin_dir: Plugin directory
        agent_dir: Agent config directory
        strict: If True, treat warnings as errors
        available_models: Available model names

    Returns:
        PluginManager with loaded plugins
    """
    manager = PluginManager(
        plugin_dir=plugin_dir,
        agent_dir=agent_dir,
        strict_validation=strict
    )

    # Discover
    manager.discover()

    # Get existing names
    existing_tools = set(tool_registry._tools.keys())
    existing_agents = set(agents.keys())

    # Validate
    manager.validate_all(
        existing_tools=existing_tools,
        existing_agents=existing_agents,
        available_models=available_models
    )

    # Register
    manager.register_tools(tool_registry, work_dir=tool_registry.work_dir)
    manager.register_agents(agents)

    return manager
