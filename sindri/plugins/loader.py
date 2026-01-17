"""Plugin discovery and loading for Sindri."""

import ast
import importlib.util
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Type
import structlog

try:
    import toml

    HAS_TOML = True
except ImportError:
    HAS_TOML = False

from sindri.tools.base import Tool

log = structlog.get_logger()


class PluginType(Enum):
    """Type of plugin."""

    TOOL = auto()  # Python tool class
    AGENT = auto()  # TOML agent definition


@dataclass
class PluginInfo:
    """Information about a discovered plugin.

    Attributes:
        name: Plugin name (derived from filename or class name)
        type: Type of plugin (TOOL or AGENT)
        path: Path to the plugin file
        description: Brief description of the plugin
        version: Plugin version (if provided)
        author: Plugin author (if provided)
        enabled: Whether the plugin is enabled
        error: Error message if loading failed
        metadata: Additional metadata
    """

    name: str
    type: PluginType
    path: Path
    description: str = ""
    version: str = "0.1.0"
    author: str = ""
    enabled: bool = True
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    # Loaded artifacts
    tool_class: Optional[Type[Tool]] = None
    agent_config: Optional[dict] = None


class PluginLoader:
    """Discovers and loads plugins from filesystem.

    Plugins are discovered from:
    - ~/.sindri/plugins/*.py - Python tool plugins
    - ~/.sindri/agents/*.toml - TOML agent configurations

    Example:
        loader = PluginLoader()
        plugins = loader.discover()
        for plugin in plugins:
            if plugin.type == PluginType.TOOL and plugin.tool_class:
                registry.register(plugin.tool_class())
    """

    def __init__(
        self, plugin_dir: Optional[Path] = None, agent_dir: Optional[Path] = None
    ):
        """Initialize the plugin loader.

        Args:
            plugin_dir: Directory for Python plugins. Defaults to ~/.sindri/plugins/
            agent_dir: Directory for agent configs. Defaults to ~/.sindri/agents/
        """
        self.plugin_dir = plugin_dir or (Path.home() / ".sindri" / "plugins")
        self.agent_dir = agent_dir or (Path.home() / ".sindri" / "agents")
        self._discovered: list[PluginInfo] = []

    def discover(self) -> list[PluginInfo]:
        """Discover all available plugins.

        Returns:
            List of PluginInfo objects for all discovered plugins.
        """
        self._discovered = []

        # Discover Python tool plugins
        self._discover_tools()

        # Discover TOML agent configs
        self._discover_agents()

        log.info(
            "plugins_discovered",
            tool_count=len([p for p in self._discovered if p.type == PluginType.TOOL]),
            agent_count=len(
                [p for p in self._discovered if p.type == PluginType.AGENT]
            ),
        )

        return self._discovered

    def _discover_tools(self) -> None:
        """Discover Python tool plugins."""
        if not self.plugin_dir.exists():
            log.debug("plugin_dir_not_found", path=str(self.plugin_dir))
            return

        for path in self.plugin_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue

            try:
                plugin_info = self._load_tool_plugin(path)
                if plugin_info:
                    self._discovered.append(plugin_info)
            except Exception as e:
                log.warning("plugin_load_failed", path=str(path), error=str(e))
                self._discovered.append(
                    PluginInfo(
                        name=path.stem,
                        type=PluginType.TOOL,
                        path=path,
                        enabled=False,
                        error=str(e),
                    )
                )

    def _load_tool_plugin(self, path: Path) -> Optional[PluginInfo]:
        """Load a Python tool plugin.

        Args:
            path: Path to the Python file

        Returns:
            PluginInfo if successful, None if no tools found
        """
        # First, do a static analysis to find Tool subclasses
        with open(path, "r") as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            raise ValueError(f"Syntax error in plugin: {e}")

        # Find classes that might be Tool subclasses
        tool_classes = []
        plugin_metadata = self._extract_metadata(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it has Tool-like bases
                for base in node.bases:
                    base_name = self._get_base_name(base)
                    if base_name and "Tool" in base_name:
                        tool_classes.append(node.name)

        if not tool_classes:
            log.debug("no_tools_in_plugin", path=str(path))
            return None

        # Dynamically load the module
        module_name = f"sindri_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            raise ValueError(f"Cannot create module spec for {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            del sys.modules[module_name]
            raise ValueError(f"Error executing plugin: {e}")

        # Find the actual Tool subclass
        tool_class = None
        for name in tool_classes:
            cls = getattr(module, name, None)
            if (
                cls
                and isinstance(cls, type)
                and issubclass(cls, Tool)
                and cls is not Tool
            ):
                tool_class = cls
                break

        if not tool_class:
            del sys.modules[module_name]
            return None

        # Create PluginInfo
        tool_name = getattr(tool_class, "name", path.stem)
        description = getattr(
            tool_class, "description", plugin_metadata.get("description", "")
        )

        return PluginInfo(
            name=tool_name,
            type=PluginType.TOOL,
            path=path,
            description=description,
            version=plugin_metadata.get("version", "0.1.0"),
            author=plugin_metadata.get("author", ""),
            enabled=True,
            tool_class=tool_class,
            metadata=plugin_metadata,
        )

    def _discover_agents(self) -> None:
        """Discover TOML agent configuration files."""
        if not self.agent_dir.exists():
            log.debug("agent_dir_not_found", path=str(self.agent_dir))
            return

        if not HAS_TOML:
            log.warning("toml_not_installed", message="Cannot load agent plugins")
            return

        for path in self.agent_dir.glob("*.toml"):
            if path.name.startswith("_"):
                continue

            try:
                plugin_info = self._load_agent_config(path)
                if plugin_info:
                    self._discovered.append(plugin_info)
            except Exception as e:
                log.warning("agent_config_load_failed", path=str(path), error=str(e))
                self._discovered.append(
                    PluginInfo(
                        name=path.stem,
                        type=PluginType.AGENT,
                        path=path,
                        enabled=False,
                        error=str(e),
                    )
                )

    def _load_agent_config(self, path: Path) -> Optional[PluginInfo]:
        """Load a TOML agent configuration.

        Args:
            path: Path to the TOML file

        Returns:
            PluginInfo if successful, None otherwise
        """
        with open(path, "r") as f:
            config = toml.load(f)

        # Validate required fields
        if "agent" not in config:
            raise ValueError("Missing [agent] section")

        agent = config["agent"]
        required_fields = ["name", "role", "model"]
        for field_name in required_fields:
            if field_name not in agent:
                raise ValueError(f"Missing required field: agent.{field_name}")

        # Get prompt content
        prompt_content = ""
        if "prompt" in config:
            prompt = config["prompt"]
            if "content" in prompt:
                prompt_content = prompt["content"]
            elif "file" in prompt:
                # Load from external file
                prompt_file = path.parent / prompt["file"]
                if prompt_file.exists():
                    prompt_content = prompt_file.read_text()
                else:
                    raise ValueError(f"Prompt file not found: {prompt['file']}")

        # Build agent config dict
        agent_config = {
            "name": agent["name"],
            "role": agent["role"],
            "model": agent["model"],
            "system_prompt": prompt_content,
            "tools": agent.get("tools", []),
            "can_delegate": agent.get("can_delegate", False),
            "delegate_to": agent.get("delegate_to", []),
            "estimated_vram_gb": agent.get("estimated_vram_gb", 8.0),
            "priority": agent.get("priority", 1),
            "max_iterations": agent.get("max_iterations", 30),
            "max_context_tokens": agent.get("max_context_tokens", 16384),
            "temperature": agent.get("temperature", 0.3),
            "fallback_model": agent.get("fallback_model"),
            "fallback_vram_gb": agent.get("fallback_vram_gb"),
        }

        # Get metadata
        metadata = config.get("metadata", {})

        return PluginInfo(
            name=agent["name"],
            type=PluginType.AGENT,
            path=path,
            description=agent.get("description", agent["role"]),
            version=metadata.get("version", "0.1.0"),
            author=metadata.get("author", ""),
            enabled=agent.get("enabled", True),
            agent_config=agent_config,
            metadata=metadata,
        )

    def _extract_metadata(self, tree: ast.AST) -> dict:
        """Extract module-level metadata from AST.

        Looks for module docstring and __version__, __author__, etc.

        Args:
            tree: Parsed AST

        Returns:
            Dict of metadata
        """
        metadata = {}

        # Get module docstring
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            docstring = tree.body[0].value.value
            # First line is description
            lines = docstring.strip().split("\n")
            if lines:
                metadata["description"] = lines[0].strip()

        # Get dunder variables
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "__version__" and isinstance(
                            node.value, ast.Constant
                        ):
                            metadata["version"] = str(node.value.value)
                        elif target.id == "__author__" and isinstance(
                            node.value, ast.Constant
                        ):
                            metadata["author"] = str(node.value.value)

        return metadata

    def _get_base_name(self, node: ast.expr) -> Optional[str]:
        """Get the name from a base class node.

        Args:
            node: AST expression node

        Returns:
            String name or None
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None

    def get_discovered(self) -> list[PluginInfo]:
        """Get list of discovered plugins.

        Returns:
            List of PluginInfo objects
        """
        return self._discovered.copy()

    def get_tools(self) -> list[PluginInfo]:
        """Get discovered tool plugins.

        Returns:
            List of PluginInfo for tool plugins
        """
        return [p for p in self._discovered if p.type == PluginType.TOOL and p.enabled]

    def get_agents(self) -> list[PluginInfo]:
        """Get discovered agent plugins.

        Returns:
            List of PluginInfo for agent plugins
        """
        return [p for p in self._discovered if p.type == PluginType.AGENT and p.enabled]
