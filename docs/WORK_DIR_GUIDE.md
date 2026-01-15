# Working Directory Guide

## Overview

Sindri now supports a `--work-dir` option that allows you to organize all file outputs into a dedicated directory. This keeps your project directory clean and makes it easy to manage generated code.

## Usage

### CLI Commands

All Sindri commands support the `--work-dir` (or `-w`) option:

```bash
# Run command with work directory
sindri run "Create hello.py" --work-dir ./output

# Orchestrate with work directory
sindri orchestrate "Build a REST API" --work-dir ./my_project

# TUI with work directory
sindri tui --work-dir ./generated
```

### How It Works

When you specify a `--work-dir`:

1. **Relative paths** are resolved relative to the work directory
   - `write_file("hello.py", ...)` creates `./output/hello.py`
   - `write_file("src/main.py", ...)` creates `./output/src/main.py`

2. **Absolute paths** work as normal (not affected by work directory)
   - `write_file("/tmp/test.txt", ...)` creates `/tmp/test.txt`

3. **Shell commands** execute in the work directory
   - `shell("ls")` lists files in the work directory
   - `shell("pwd")` shows the work directory path

### Examples

#### Example 1: Organize Generated Code

```bash
# Create a dedicated output directory for a project
sindri orchestrate "Create a Flask blog API with authentication" \
  --work-dir ./blog_api

# Results in:
# blog_api/
# ├── app.py
# ├── models.py
# ├── routes.py
# └── tests/
#     └── test_api.py
```

#### Example 2: Work in Current Directory (Default)

```bash
# Without --work-dir, files are created in current directory
sindri run "Create hello.py"

# Creates: ./hello.py
```

#### Example 3: Keep Test Outputs Isolated

```bash
# Generate test code in a separate directory
sindri run "Generate unit tests for calculator" \
  --work-dir ./test_generated
```

## Configuration

You can also set a default work directory in your configuration file (`~/.sindri/config.toml` or `./sindri.toml`):

```toml
[paths]
work_dir = "./sindri_output"
```

This will be used as the default if you don't specify `--work-dir` on the command line.

## .gitignore

Common output directory patterns are automatically ignored in `.gitignore`:

```gitignore
# Common Sindri output patterns
sindri_output/
output/
generated/
```

If you use a custom directory, you may want to add it to your `.gitignore`.

## Tips

1. **Use descriptive directory names** - `./blog_api` is better than `./output`
2. **Create the directory beforehand** (optional) - Sindri will create it if it doesn't exist
3. **Combine with git** - Keep generated code in a separate branch or exclude from version control
4. **Review before committing** - Always review generated code before adding to your repository

## Technical Details

### Path Resolution

The path resolution logic works as follows:

```python
def _resolve_path(self, path: str) -> Path:
    """Resolve a path relative to work_dir if set and path is relative."""
    file_path = Path(path).expanduser()

    # If path is absolute, use it as-is
    if file_path.is_absolute():
        return file_path.resolve()

    # If work_dir is set, resolve relative to it
    if self.work_dir:
        return (self.work_dir / file_path).resolve()

    # Otherwise, resolve relative to current directory
    return file_path.resolve()
```

### Implementation

The work directory feature is implemented at the tool level:

- **Tool Base Class** (`sindri/tools/base.py`) - Provides `_resolve_path()` method
- **Filesystem Tools** (`sindri/tools/filesystem.py`) - Use `_resolve_path()` for all operations
- **Shell Tool** (`sindri/tools/shell.py`) - Sets `cwd` parameter for subprocess
- **Tool Registry** (`sindri/tools/registry.py`) - Passes work_dir to all tools
- **Orchestrator** (`sindri/core/orchestrator.py`) - Accepts work_dir parameter
- **CLI** (`sindri/cli.py`) - Adds `--work-dir` option to commands

## Troubleshooting

### Files not appearing in work directory

- Check that you're using relative paths (e.g., `hello.py`, not `/tmp/hello.py`)
- Verify the work directory path is correct
- Check logs for "work_dir" field to see what directory is being used

### Permission errors

- Ensure you have write permissions for the work directory
- Try using an absolute path for the work directory

### Shell commands not finding files

- Remember that shell commands execute in the work directory
- Use relative paths or absolute paths as appropriate
