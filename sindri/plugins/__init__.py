"""Plugin system for Sindri.

Allows users to extend Sindri with custom tools and agents without
modifying the core codebase.

Plugin locations:
- ~/.sindri/plugins/ - User plugins (Python files)
- ~/.sindri/agents/ - Custom agent definitions (TOML files)

Example tool plugin:
    # ~/.sindri/plugins/my_tool.py
    from sindri.tools import Tool, ToolResult

    class MyCustomTool(Tool):
        name = "my_tool"
        description = "Does something custom"
        parameters = {"type": "object", "properties": {...}}

        async def execute(self, **kwargs) -> ToolResult:
            return ToolResult(success=True, output="...")

Example agent config:
    # ~/.sindri/agents/my_agent.toml
    [agent]
    name = "thor"
    role = "Performance Optimizer"
    model = "qwen2.5-coder:14b"
    tools = ["read_file", "write_file", "my_tool"]
    max_iterations = 30

    [prompt]
    content = "You are Thor, the performance optimization specialist..."
"""

from sindri.plugins.loader import (
    PluginLoader,
    PluginInfo,
    PluginType,
)
from sindri.plugins.validator import (
    PluginValidator,
    ValidationResult,
    ValidationError,
)
from sindri.plugins.manager import (
    PluginManager,
    PluginState,
)

__all__ = [
    # Loader
    "PluginLoader",
    "PluginInfo",
    "PluginType",
    # Validator
    "PluginValidator",
    "ValidationResult",
    "ValidationError",
    # Manager
    "PluginManager",
    "PluginState",
]
