# Quick Start: Building Sindri with Ralph Loop

## Prerequisites

1. **Claude Code** installed and authenticated
2. **Ralph loop plugin** installed:
   ```bash
   /plugin install ralph-loop@claude-plugins-official
   ```
3. **Python 3.11+** available
4. **Ollama** running with models pulled

## Step-by-Step Build Process

### 1. Create Project Directory

```bash
mkdir -p ~/projects/sindri
cd ~/projects/sindri
```

### 2. Copy Build Files

Copy the contents of this `sindri-build` folder to your project:
- `CLAUDE.md` - Claude Code context file
- `README.md` - Project documentation
- `PROMPT.md` - Master prompt (optional)
- `prompts/` - Phase-specific prompts

### 3. Start Phase 1

Open Claude Code in the project directory, then:

```bash
# Option A: Using Ralph loop plugin (recommended)
/ralph-loop:ralph-loop "$(cat prompts/PHASE1.md)" \
  --completion-promise "PHASE1_COMPLETE" \
  --max-iterations 50

# Option B: Manual iteration
# 1. Paste prompts/PHASE1.md content
# 2. Let Claude work
# 3. When it stops, say "Continue. Verify your work and proceed."
# 4. Repeat until you see <promise>PHASE1_COMPLETE</promise>
```

### 4. Verify Phase 1

```bash
# Install the package
pip install -e ".[dev]"

# Test basic functionality
sindri run "Create hello.py that prints hello world"

# Run tests
pytest tests/ -v
```

### 5. Continue to Phase 2

```bash
/ralph-loop:ralph-loop "$(cat prompts/PHASE2.md)" \
  --completion-promise "PHASE2_COMPLETE" \
  --max-iterations 75
```

### 6. Repeat for Remaining Phases

- **Phase 3**: Memory system (`PHASE3.md`)
- **Phase 4**: TUI (`PHASE4.md`)
- **Phase 5**: Polish (`PHASE5.md`)

## Tips for Success

### Good Prompting Patterns

1. **Be specific about completion criteria**
   ```
   When complete:
   - All tests passing
   - CLI command works
   - Output: <promise>PHASE1_COMPLETE</promise>
   ```

2. **Include self-correction patterns**
   ```
   After each change:
   1. Run tests
   2. If failing, fix
   3. Repeat until green
   ```

3. **Add escape hatches**
   ```
   If stuck after 10 iterations:
   - Document the blocker
   - Output: <sindri:blocked reason="..."/>
   ```

### Common Issues

| Problem | Solution |
|---------|----------|
| Loop runs forever | Add `--max-iterations 50` |
| Same error repeating | Add "Try a different approach" nudge |
| Missing context | Ensure CLAUDE.md is in project root |
| Model errors | Check Ollama is running: `ollama list` |

### Parallel Development

Use git worktrees to work on multiple phases simultaneously:

```bash
# Create worktrees
git worktree add ../sindri-phase2 -b phase2
git worktree add ../sindri-phase3 -b phase3

# Terminal 1: Phase 2
cd ../sindri-phase2
/ralph-loop:ralph-loop "$(cat prompts/PHASE2.md)" --max-iterations 75

# Terminal 2: Phase 3 (simultaneously)
cd ../sindri-phase3
/ralph-loop:ralph-loop "$(cat prompts/PHASE3.md)" --max-iterations 75
```

### Overnight Builds

```bash
#!/bin/bash
# overnight-build.sh

cd ~/projects/sindri

echo "Starting Phase 1..."
claude -p "/ralph-loop:ralph-loop '$(cat prompts/PHASE1.md)' --max-iterations 50"

echo "Starting Phase 2..."
claude -p "/ralph-loop:ralph-loop '$(cat prompts/PHASE2.md)' --max-iterations 75"

echo "Build complete!"
```

## Expected Timeline

| Phase | Estimated Iterations | Time (approx) |
|-------|---------------------|---------------|
| Phase 1 | 20-40 | 1-2 hours |
| Phase 2 | 30-60 | 2-3 hours |
| Phase 3 | 30-60 | 2-3 hours |
| Phase 4 | 40-80 | 3-4 hours |
| Phase 5 | 20-40 | 1-2 hours |

Total: ~10-15 hours of Claude Code time

## After Completion

```bash
# Final verification
sindri doctor

# Install globally
pip install .

# Pull required models
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama pull deepseek-coder-v2:16b-instruct-q4_K_M
ollama pull phi4:3.8b
ollama pull nomic-embed-text

# Start forging!
sindri tui "Build a REST API for a task manager"
```

---

*Iteration > Perfection. Let the loop refine the work.*
