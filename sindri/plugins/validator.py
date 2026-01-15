"""Plugin validation for Sindri.

Validates plugins for safety and correctness before they're loaded.
"""

import ast
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Set
import structlog

from sindri.plugins.loader import PluginInfo, PluginType
from sindri.tools.base import Tool

log = structlog.get_logger()


class ValidationError(Enum):
    """Types of validation errors."""
    SYNTAX_ERROR = auto()           # Invalid Python syntax
    IMPORT_ERROR = auto()           # Problematic imports
    SECURITY_VIOLATION = auto()     # Dangerous code patterns
    MISSING_REQUIRED = auto()        # Missing required attributes
    INVALID_SCHEMA = auto()          # Invalid tool schema
    NAME_CONFLICT = auto()           # Name conflicts with existing tools/agents
    MODEL_NOT_FOUND = auto()         # Referenced model not available
    TOOL_NOT_FOUND = auto()          # Referenced tool not available


@dataclass
class ValidationResult:
    """Result of plugin validation.

    Attributes:
        valid: Whether the plugin is valid
        errors: List of validation errors
        warnings: List of validation warnings
        info: Additional info messages
    """
    valid: bool
    errors: list[tuple[ValidationError, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def add_error(self, error_type: ValidationError, message: str) -> None:
        """Add a validation error."""
        self.errors.append((error_type, message))
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a validation warning."""
        self.warnings.append(message)

    def add_info(self, message: str) -> None:
        """Add an info message."""
        self.info.append(message)


class PluginValidator:
    """Validates plugins for safety and correctness.

    Performs several validation checks:
    1. Syntax validation for Python plugins
    2. Security checks for dangerous imports/patterns
    3. Schema validation for tool definitions
    4. Name conflict detection
    5. Model availability checking

    Example:
        validator = PluginValidator(
            existing_tools={"read_file", "write_file"},
            existing_agents={"brokkr", "huginn"}
        )
        result = validator.validate(plugin_info)
        if not result.valid:
            for error_type, message in result.errors:
                print(f"Error: {message}")
    """

    # Dangerous modules that should not be imported
    DANGEROUS_IMPORTS: Set[str] = {
        "subprocess",        # Already have shell tool
        "socket",           # Network access
        "ctypes",           # Low-level memory access
        "pickle",           # Arbitrary code execution
        "marshal",          # Code object manipulation
        "tempfile",         # Should use provided file tools
        "multiprocessing",  # Complex process management
        "threading",        # Should use async
        "pty",              # Pseudo-terminal (shell escape)
        "fcntl",            # Low-level file control
        "mmap",             # Memory mapping
    }

    # Allowed imports that are explicitly safe
    ALLOWED_IMPORTS: Set[str] = {
        "asyncio",
        "os",               # Limited to path operations
        "pathlib",
        "json",
        "re",
        "typing",
        "dataclasses",
        "enum",
        "abc",
        "datetime",
        "collections",
        "functools",
        "itertools",
        "contextlib",
        "structlog",
        "sindri",
        "pydantic",
        "aiohttp",          # For web tools
        "httpx",            # For web tools
        "aiofiles",         # Async file operations
    }

    # Dangerous function calls
    DANGEROUS_CALLS: Set[str] = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",             # Should use provided file tools (warning only)
        "exit",
        "quit",
    }

    def __init__(
        self,
        existing_tools: Optional[Set[str]] = None,
        existing_agents: Optional[Set[str]] = None,
        available_models: Optional[Set[str]] = None,
        strict: bool = False
    ):
        """Initialize the validator.

        Args:
            existing_tools: Set of existing tool names
            existing_agents: Set of existing agent names
            available_models: Set of available model names (optional)
            strict: If True, treat warnings as errors
        """
        self.existing_tools = existing_tools or set()
        self.existing_agents = existing_agents or set()
        self.available_models = available_models
        self.strict = strict

    def validate(self, plugin: PluginInfo) -> ValidationResult:
        """Validate a plugin.

        Args:
            plugin: PluginInfo to validate

        Returns:
            ValidationResult with errors, warnings, and info
        """
        result = ValidationResult(valid=True)

        # If plugin already has an error from loading, report it
        if plugin.error:
            result.add_error(ValidationError.SYNTAX_ERROR, plugin.error)
            return result

        if plugin.type == PluginType.TOOL:
            self._validate_tool(plugin, result)
        elif plugin.type == PluginType.AGENT:
            self._validate_agent(plugin, result)

        # In strict mode, warnings become errors
        if self.strict and result.warnings:
            for warning in result.warnings:
                result.add_error(ValidationError.SECURITY_VIOLATION, warning)

        return result

    def _validate_tool(self, plugin: PluginInfo, result: ValidationResult) -> None:
        """Validate a tool plugin.

        Args:
            plugin: Tool plugin to validate
            result: ValidationResult to populate
        """
        # Check for name conflicts
        if plugin.name in self.existing_tools:
            result.add_error(
                ValidationError.NAME_CONFLICT,
                f"Tool name '{plugin.name}' conflicts with existing tool"
            )

        # Read and parse source
        try:
            source = plugin.path.read_text()
            tree = ast.parse(source)
        except SyntaxError as e:
            result.add_error(
                ValidationError.SYNTAX_ERROR,
                f"Syntax error at line {e.lineno}: {e.msg}"
            )
            return
        except Exception as e:
            result.add_error(ValidationError.SYNTAX_ERROR, str(e))
            return

        # Check imports
        self._check_imports(tree, result)

        # Check for dangerous patterns
        self._check_dangerous_calls(tree, result)

        # Validate tool class structure
        if plugin.tool_class:
            self._validate_tool_class(plugin.tool_class, result)

    def _validate_agent(self, plugin: PluginInfo, result: ValidationResult) -> None:
        """Validate an agent plugin.

        Args:
            plugin: Agent plugin to validate
            result: ValidationResult to populate
        """
        if not plugin.agent_config:
            result.add_error(
                ValidationError.MISSING_REQUIRED,
                "Agent configuration not loaded"
            )
            return

        config = plugin.agent_config

        # Check for name conflicts
        if config["name"] in self.existing_agents:
            result.add_error(
                ValidationError.NAME_CONFLICT,
                f"Agent name '{config['name']}' conflicts with existing agent"
            )

        # Check model availability (if we have the list)
        if self.available_models and config["model"] not in self.available_models:
            result.add_warning(
                f"Model '{config['model']}' not in available models list. "
                "Ensure it's installed in Ollama."
            )

        # Check tool references
        for tool_name in config.get("tools", []):
            if tool_name not in self.existing_tools and tool_name != "delegate":
                result.add_warning(
                    f"Referenced tool '{tool_name}' not found. "
                    "It may be provided by another plugin."
                )

        # Check delegation targets
        for target in config.get("delegate_to", []):
            if target not in self.existing_agents and target != config["name"]:
                result.add_warning(
                    f"Delegation target '{target}' not found. "
                    "It may be provided by another plugin."
                )

        # Validate VRAM settings
        vram = config.get("estimated_vram_gb", 8.0)
        if vram <= 0:
            result.add_error(
                ValidationError.INVALID_SCHEMA,
                "estimated_vram_gb must be positive"
            )
        elif vram > 24:
            result.add_warning(
                f"estimated_vram_gb ({vram}) is very high. "
                "Ensure you have sufficient GPU memory."
            )

        # Validate iterations
        max_iter = config.get("max_iterations", 30)
        if max_iter <= 0:
            result.add_error(
                ValidationError.INVALID_SCHEMA,
                "max_iterations must be positive"
            )
        elif max_iter > 100:
            result.add_warning(
                f"max_iterations ({max_iter}) is very high. "
                "This may lead to runaway tasks."
            )

        # Check system prompt
        if not config.get("system_prompt"):
            result.add_warning(
                "No system_prompt provided. Agent may behave unpredictably."
            )

        result.add_info(
            f"Agent '{config['name']}' configuration validated: "
            f"model={config['model']}, tools={len(config.get('tools', []))}"
        )

    def _check_imports(self, tree: ast.AST, result: ValidationResult) -> None:
        """Check imports for dangerous modules.

        Args:
            tree: Parsed AST
            result: ValidationResult to populate
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    if module_name in self.DANGEROUS_IMPORTS:
                        result.add_error(
                            ValidationError.SECURITY_VIOLATION,
                            f"Dangerous import: '{alias.name}'. "
                            f"Use Sindri's built-in tools instead."
                        )
                    elif module_name not in self.ALLOWED_IMPORTS:
                        result.add_info(
                            f"Non-standard import: '{alias.name}'"
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split(".")[0]
                    if module_name in self.DANGEROUS_IMPORTS:
                        result.add_error(
                            ValidationError.SECURITY_VIOLATION,
                            f"Dangerous import from '{node.module}'. "
                            f"Use Sindri's built-in tools instead."
                        )

    def _check_dangerous_calls(self, tree: ast.AST, result: ValidationResult) -> None:
        """Check for dangerous function calls.

        Args:
            tree: Parsed AST
            result: ValidationResult to populate
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = None

                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in self.DANGEROUS_CALLS:
                    if func_name == "open":
                        result.add_warning(
                            f"Direct file access with '{func_name}()'. "
                            f"Consider using Sindri's file tools for better integration."
                        )
                    else:
                        result.add_error(
                            ValidationError.SECURITY_VIOLATION,
                            f"Dangerous function call: '{func_name}()'"
                        )

    def _validate_tool_class(self, tool_class: type, result: ValidationResult) -> None:
        """Validate tool class structure.

        Args:
            tool_class: Tool class to validate
            result: ValidationResult to populate
        """
        # Check required attributes
        if not hasattr(tool_class, "name"):
            result.add_error(
                ValidationError.MISSING_REQUIRED,
                "Tool class missing 'name' attribute"
            )

        if not hasattr(tool_class, "description"):
            result.add_error(
                ValidationError.MISSING_REQUIRED,
                "Tool class missing 'description' attribute"
            )

        if not hasattr(tool_class, "parameters"):
            result.add_error(
                ValidationError.MISSING_REQUIRED,
                "Tool class missing 'parameters' attribute"
            )

        # Check execute method
        if not hasattr(tool_class, "execute"):
            result.add_error(
                ValidationError.MISSING_REQUIRED,
                "Tool class missing 'execute' method"
            )
        else:
            import inspect
            if not inspect.iscoroutinefunction(tool_class.execute):
                result.add_error(
                    ValidationError.INVALID_SCHEMA,
                    "Tool 'execute' method must be async"
                )

        # Validate parameters schema
        if hasattr(tool_class, "parameters"):
            params = tool_class.parameters
            if not isinstance(params, dict):
                result.add_error(
                    ValidationError.INVALID_SCHEMA,
                    "Tool 'parameters' must be a dict (JSON Schema)"
                )
            elif "type" not in params:
                result.add_warning(
                    "Tool parameters schema missing 'type' field"
                )

        result.add_info(f"Tool class '{tool_class.__name__}' structure validated")


def validate_plugin_file(path: Path, **kwargs) -> ValidationResult:
    """Convenience function to validate a plugin file.

    Args:
        path: Path to plugin file
        **kwargs: Arguments passed to PluginValidator

    Returns:
        ValidationResult
    """
    from sindri.plugins.loader import PluginLoader

    loader = PluginLoader()

    # Discover just this file
    if path.suffix == ".py":
        loader.plugin_dir = path.parent
    else:
        loader.agent_dir = path.parent

    plugins = loader.discover()

    # Find the plugin for this file
    plugin = None
    for p in plugins:
        if p.path == path:
            plugin = p
            break

    if not plugin:
        result = ValidationResult(valid=False)
        result.add_error(
            ValidationError.SYNTAX_ERROR,
            f"Could not load plugin from {path}"
        )
        return result

    validator = PluginValidator(**kwargs)
    return validator.validate(plugin)
