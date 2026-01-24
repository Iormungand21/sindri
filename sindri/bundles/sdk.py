"""Agent SDK for creating agent bundles programmatically.

Provides utilities for creating new bundles and exporting existing agents.
"""

from pathlib import Path
from typing import Optional

import structlog
import toml

from sindri.agents.definitions import AgentDefinition
from sindri.bundles.loader import MANIFEST_FILENAME
from sindri.bundles.models import (
    AgentBundleConfig,
    BundleDependencies,
    BundleManifest,
    BundleMetadata,
    TestConfig,
)

log = structlog.get_logger()

# Template for test file
TEST_TEMPLATE = '''"""Tests for {name} agent bundle."""

import pytest


class Test{class_name}Agent:
    """Tests for {name} agent."""

    def test_agent_loads(self):
        """Test that agent bundle loads correctly."""
        from sindri.bundles import BundleLoader
        from pathlib import Path

        loader = BundleLoader()
        bundle = loader.load(Path(__file__).parent.parent)
        assert bundle.manifest is not None
        assert bundle.manifest.agent.name == "{name}"

    def test_agent_has_prompt(self):
        """Test that agent has a system prompt."""
        from sindri.bundles import BundleLoader
        from pathlib import Path

        loader = BundleLoader()
        bundle = loader.load(Path(__file__).parent.parent)
        prompt = loader.get_prompt(bundle)
        assert prompt is not None
        assert len(prompt) > 0

    @pytest.mark.asyncio
    async def test_agent_validates(self):
        """Test that agent passes validation."""
        from sindri.bundles import BundleValidator
        from pathlib import Path

        validator = BundleValidator()
        result = await validator.validate(Path(__file__).parent.parent)
        assert result.valid, f"Validation errors: {{result.errors}}"
'''

# Template for README
README_TEMPLATE = '''# {name}

{role}

## Installation

```bash
sindri bundle install ./{name}
```

## Usage

This agent can be used via delegation from the Brokkr orchestrator:

```python
# The agent will be available after installation
from sindri.agents.registry import AGENTS

agent = AGENTS.get("{name}")
```

## Configuration

- **Model**: {model}
- **VRAM**: {vram_gb} GB
- **Max Iterations**: {max_iterations}

## Tools

{tools_list}

## Testing

```bash
sindri bundle test ./{name}
```

## License

{license}
'''


class AgentSDK:
    """SDK for creating agent bundles programmatically.

    Provides methods to:
    - Create new agent bundles from scratch
    - Export existing agents to bundle format
    - Generate bundle scaffolding

    Example:
        # Create a new bundle
        path = AgentSDK.create_bundle(
            name="myagent",
            role="My Custom Agent",
            model="qwen2.5-coder:7b",
            prompt="You are a helpful assistant...",
            output_dir=Path("./bundles"),
        )

        # Export existing agent
        from sindri.agents.registry import AGENTS
        path = AgentSDK.from_definition(
            AGENTS["brokkr"],
            output_dir=Path("./exports"),
        )
    """

    @staticmethod
    def create_bundle(
        name: str,
        role: str,
        model: str,
        prompt: str,
        output_dir: Path,
        tools: Optional[list[str]] = None,
        include_tests: bool = True,
        version: str = "0.1.0",
        author: str = "",
        category: str = "specialist",
        tags: Optional[list[str]] = None,
        license_name: str = "MIT",
        can_delegate: bool = False,
        delegate_to: Optional[list[str]] = None,
        estimated_vram_gb: float = 5.0,
        max_iterations: int = 30,
        temperature: float = 0.3,
        fallback_model: Optional[str] = None,
        fallback_vram_gb: Optional[float] = None,
    ) -> Path:
        """Create a new agent bundle from scratch.

        Args:
            name: Agent name (used as directory name)
            role: Human-readable role description
            model: Ollama model name
            prompt: System prompt content
            output_dir: Directory to create bundle in
            tools: List of tool names
            include_tests: Generate test scaffolding
            version: Bundle version
            author: Author name
            category: Agent category
            tags: Searchable tags
            license_name: License identifier
            can_delegate: Whether agent can delegate
            delegate_to: Agents this agent can delegate to
            estimated_vram_gb: Expected VRAM usage
            max_iterations: Maximum iterations
            temperature: LLM temperature
            fallback_model: Optional fallback model
            fallback_vram_gb: VRAM for fallback

        Returns:
            Path to created bundle directory
        """
        # Create bundle directory
        bundle_dir = output_dir / name
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # Build manifest
        manifest = BundleManifest(
            schema_version=1,
            agent=AgentBundleConfig(
                name=name,
                role=role,
                model=model,
                tools=tools or [],
                can_delegate=can_delegate,
                delegate_to=delegate_to or [],
                estimated_vram_gb=estimated_vram_gb,
                max_iterations=max_iterations,
                temperature=temperature,
                fallback_model=fallback_model,
                fallback_vram_gb=fallback_vram_gb,
            ),
            dependencies=BundleDependencies(
                tools=tools or [],
                models=[model] + ([fallback_model] if fallback_model else []),
                plugins=[],
            ),
            metadata=BundleMetadata(
                version=version,
                author=author,
                category=category,
                tags=tags or [],
                license=license_name,
                description=role,
            ),
            test_config=TestConfig() if include_tests else None,
            prompt_file="prompt.txt",
        )

        # Write manifest
        manifest_path = bundle_dir / MANIFEST_FILENAME
        with open(manifest_path, "w") as f:
            toml.dump(manifest.to_dict(), f)

        # Write prompt
        prompt_path = bundle_dir / "prompt.txt"
        prompt_path.write_text(prompt)

        # Write README
        readme_path = bundle_dir / "README.md"
        tools_list = "\n".join(f"- `{t}`" for t in (tools or [])) or "None"
        readme_content = README_TEMPLATE.format(
            name=name,
            role=role,
            model=model,
            vram_gb=estimated_vram_gb,
            max_iterations=max_iterations,
            tools_list=tools_list,
            license=license_name,
        )
        readme_path.write_text(readme_content)

        # Create tests if requested
        if include_tests:
            tests_dir = bundle_dir / "tests"
            tests_dir.mkdir(exist_ok=True)

            # Create __init__.py
            (tests_dir / "__init__.py").write_text("")

            # Create conftest.py
            conftest_path = tests_dir / "conftest.py"
            conftest_path.write_text('"""Pytest configuration for bundle tests."""\n')

            # Create test file
            test_path = tests_dir / f"test_{name}.py"
            class_name = "".join(word.capitalize() for word in name.split("_"))
            test_content = TEST_TEMPLATE.format(name=name, class_name=class_name)
            test_path.write_text(test_content)

        log.info(
            "bundle_created",
            name=name,
            path=str(bundle_dir),
            include_tests=include_tests,
        )

        return bundle_dir

    @staticmethod
    def from_definition(
        agent: AgentDefinition,
        output_dir: Path,
        include_tests: bool = True,
        version: str = "0.1.0",
        author: str = "",
    ) -> Path:
        """Export an existing AgentDefinition to bundle format.

        Args:
            agent: AgentDefinition to export
            output_dir: Directory to create bundle in
            include_tests: Generate test scaffolding
            version: Bundle version
            author: Author name

        Returns:
            Path to created bundle directory
        """
        return AgentSDK.create_bundle(
            name=agent.name,
            role=agent.role,
            model=agent.model,
            prompt=agent.system_prompt,
            output_dir=output_dir,
            tools=list(agent.tools),
            include_tests=include_tests,
            version=version,
            author=author,
            can_delegate=agent.can_delegate,
            delegate_to=list(agent.delegate_to),
            estimated_vram_gb=agent.estimated_vram_gb,
            max_iterations=agent.max_iterations,
            temperature=agent.temperature,
            fallback_model=agent.fallback_model,
            fallback_vram_gb=agent.fallback_vram_gb,
        )

    @staticmethod
    def scaffold(output_dir: Path, name: str) -> Path:
        """Create minimal bundle scaffold.

        Creates directory structure without full implementation.

        Args:
            output_dir: Directory to create bundle in
            name: Bundle name

        Returns:
            Path to created bundle directory
        """
        bundle_dir = output_dir / name
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # Create empty directories
        (bundle_dir / "tests").mkdir(exist_ok=True)
        (bundle_dir / "tools").mkdir(exist_ok=True)

        # Create placeholder files
        (bundle_dir / "prompt.txt").write_text("# Add your system prompt here\n")
        (bundle_dir / "tests" / "__init__.py").write_text("")

        # Create minimal manifest
        manifest = {
            "bundle": {"schema_version": 1},
            "agent": {
                "name": name,
                "role": "TODO: Add role description",
                "model": "qwen2.5-coder:7b",
                "tools": [],
            },
            "dependencies": {"tools": [], "models": ["qwen2.5-coder:7b"], "plugins": []},
            "metadata": {"version": "0.1.0"},
            "prompt": {"file": "prompt.txt"},
        }

        manifest_path = bundle_dir / MANIFEST_FILENAME
        with open(manifest_path, "w") as f:
            toml.dump(manifest, f)

        log.info("bundle_scaffolded", name=name, path=str(bundle_dir))

        return bundle_dir
