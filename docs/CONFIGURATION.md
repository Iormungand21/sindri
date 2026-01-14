# Sindri Configuration

Sindri uses TOML for configuration with flexible search paths and validation.

## Configuration Files

Sindri searches for configuration in this order:

1. `./sindri.toml` (project-specific)
2. `~/.sindri/config.toml` (user default)
3. Built-in defaults

## Full Configuration Example

```toml
# sindri.toml

[general]
data_dir = "~/.sindri"
project_dir = "."
ollama_host = "http://localhost:11434"

[hardware]
total_vram_gb = 16.0
reserve_vram_gb = 2.0

[execution]
default_max_iterations = 50
checkpoint_interval = 5

[memory]
episodic_limit = 5
semantic_limit = 10
max_context_tokens = 32768

[tui]
theme = "dark"
refresh_rate_ms = 100
```

## Configuration Sections

### General

Core Sindri settings:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `data_dir` | string | `~/.sindri` | Data directory for database and state |
| `project_dir` | string | `.` | Current project directory |
| `ollama_host` | string | `http://localhost:11434` | Ollama API endpoint |

### Hardware

GPU and VRAM settings:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `total_vram_gb` | float | `16.0` | Total VRAM available (GB) |
| `reserve_vram_gb` | float | `2.0` | VRAM to reserve for system (GB) |

**VRAM Calculation:**
```
Available VRAM = total_vram_gb - reserve_vram_gb
```

Models are loaded/evicted using LRU to fit within available VRAM.

### Execution

Agent execution settings:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_max_iterations` | int | `50` | Max iterations per agent loop |
| `checkpoint_interval` | int | `5` | Save checkpoint every N iterations |

### Memory

Memory system configuration:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `episodic_limit` | int | `5` | Number of past episodes to retrieve |
| `semantic_limit` | int | `10` | Number of semantic search results |
| `max_context_tokens` | int | `32768` | Maximum context window size |

**Token Budget Distribution:**
- Working memory: 60%
- Episodic memory: 20%
- Semantic memory: 20%

### TUI

Terminal UI settings:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `theme` | string | `dark` | TUI theme (dark/light) |
| `refresh_rate_ms` | int | `100` | UI refresh rate in milliseconds |

## Model Configuration

Define custom models with VRAM requirements:

```toml
[models.orchestrator]
name = "qwen2.5-coder:14b-instruct-q4_K_M"
vram_gb = 10.0

[models.coder]
name = "deepseek-coder-v2:16b-instruct-q4_K_M"
vram_gb = 10.0

[models.reviewer]
name = "qwen2.5-coder:7b-instruct-q4_K_M"
vram_gb = 5.0

[models.executor]
name = "qwen2.5-coder:3b-instruct-q8_0"
vram_gb = 3.0
```

## Agent Configuration

Customize agent settings:

```toml
[agents.brokkr]
model = "orchestrator"
temperature = 0.3
max_context_tokens = 32768
max_iterations = 30

[agents.huginn]
model = "coder"
temperature = 0.2
max_context_tokens = 16384
max_iterations = 40
```

### Agent Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | - | Model reference from `[models]` |
| `temperature` | float | `0.3` | Sampling temperature (0.0-2.0) |
| `max_context_tokens` | int | `16384` | Max context window |
| `max_iterations` | int | `30` | Max iterations for this agent |

## Environment Variables

Override config with environment variables:

| Variable | Config Key | Example |
|----------|------------|---------|
| `SINDRI_DATA_DIR` | `general.data_dir` | `/data/sindri` |
| `SINDRI_OLLAMA_HOST` | `general.ollama_host` | `http://192.168.1.100:11434` |
| `SINDRI_VRAM_GB` | `hardware.total_vram_gb` | `12.0` |

## Validation

Sindri validates configuration on load:

```bash
# Check configuration
sindri doctor

# Output shows warnings:
# ⚠ Total agent VRAM (28.0GB) exceeds available (14.0GB)
```

### Common Validation Warnings

1. **VRAM Overflow**
   ```
   Total agent VRAM exceeds available VRAM
   ```
   **Fix:** Reduce `total_vram_gb` or use smaller models

2. **Directory Not Writable**
   ```
   Data directory not writable: /path/to/dir
   ```
   **Fix:** Check permissions or change `data_dir`

3. **Invalid Model Name**
   ```
   Model name cannot be empty
   ```
   **Fix:** Provide valid model name in `[models]`

## Project-Specific Configuration

Override user defaults for specific projects:

```bash
# In your project directory
cat > sindri.toml << EOF
[general]
project_dir = "."

[memory]
# Larger context for big codebase
max_context_tokens = 65536
semantic_limit = 20

[agents.brokkr]
# More iterations for complex project
max_iterations = 50
EOF

# Run Sindri - uses project config
sindri orchestrate "Refactor auth system"
```

## Advanced: Programmatic Configuration

```python
from sindri.config import SindriConfig, MemoryConfig

# Load from file
config = SindriConfig.load("./sindri.toml")

# Or create programmatically
config = SindriConfig(
    data_dir="/custom/data",
    total_vram_gb=24.0,
    memory=MemoryConfig(
        episodic_limit=10,
        semantic_limit=15
    )
)

# Validate
from sindri.config import validate_config
warnings = validate_config(config)
for warning in warnings:
    print(f"Warning: {warning}")

# Save to file
config.save("./sindri.toml")
```

## Defaults Reference

Complete list of defaults when no config file exists:

```python
SindriConfig(
    # General
    data_dir=Path.home() / ".sindri",
    project_dir=Path.cwd(),
    ollama_host="http://localhost:11434",

    # Hardware
    total_vram_gb=16.0,
    reserve_vram_gb=2.0,

    # Execution
    default_max_iterations=50,
    checkpoint_interval=5,

    # Memory
    memory=MemoryConfig(
        episodic_limit=5,
        semantic_limit=10,
        max_context_tokens=32768
    ),

    # TUI
    tui=TUIConfig(
        theme="dark",
        refresh_rate_ms=100
    )
)
```

## Tips

1. **Start with defaults** - Only override what you need
2. **Use project configs** - Keep project-specific settings in `./sindri.toml`
3. **Check with doctor** - Always run `sindri doctor` after config changes
4. **VRAM headroom** - Reserve 2-3GB more than you think you need
5. **Token budgets** - Larger codebases benefit from higher `max_context_tokens`

## See Also

- [AGENTS.md](AGENTS.md) - Agent configuration details
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common config issues
