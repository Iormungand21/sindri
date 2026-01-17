# Agent Expansion Implementation Plan

**Date:** 2026-01-16
**Goal:** Expand Sindri's agent roster with larger models and fill specialization gaps

---

## Research Findings

### Current State
- 7 agents implemented: Brokkr, Huginn, Mimir, Ratatoskr, Skald, Fenrir, Odin
- Largest model in use: qwen2.5-coder:14b (9GB)
- Available VRAM: 16GB (AMD RX 6950 XT)
- **Untapped potential**: deepseek-r1:14b (9GB) already pulled but unused!

### Models That Fit 16GB VRAM

| Model | Size | VRAM Est. | Specialization | Source |
|-------|------|-----------|----------------|--------|
| **deepseek-r1:14b** | 9.0GB | ~10GB | Deep reasoning | [Already pulled] |
| **qwen3:14b** | ~9GB | ~10GB | Reasoning + thinking mode | [Ollama Library](https://ollama.com/library/qwen3:14b) |
| **codestral:22b-q4_K_M** | 13GB | ~14GB | Multi-lang code (80+ langs) | [Ollama Library](https://ollama.com/library/codestral:22b) |
| **phi4:14b** | ~9GB | ~10GB | Efficient reasoning | [Ollama Library](https://ollama.com/library/phi4:14b) |

### Specialization Gaps Identified

1. **Security Auditing** - No dedicated vulnerability detection
2. **Debugging** - No specialized debugger/problem solver
3. **Documentation** - No dedicated docs agent
4. **Multi-Language** - Current focus is Python/SQL, need broader language support

---

## Proposed New Agents

### 1. Heimdall (Security Guardian)

| Property | Value |
|----------|-------|
| **Role** | Security auditing, vulnerability detection, OWASP analysis |
| **Model** | `qwen3:14b` (with thinking mode for careful analysis) |
| **VRAM** | ~10GB |
| **Tools** | read_file, search_code, git_diff, lint_code, shell |
| **Delegates to** | Mimir (for code review follow-up) |
| **Priority** | HIGH - security is critical |

**Prompt Focus:**
- OWASP Top 10 vulnerability patterns
- Input validation, SQL injection, XSS detection
- Authentication/authorization flaws
- Secrets detection in code
- Dependency vulnerability awareness

### 2. Baldr (Debugger/Problem Solver)

| Property | Value |
|----------|-------|
| **Role** | Debug complex issues, root cause analysis, trace through code |
| **Model** | `deepseek-r1:14b` (already pulled! just needs agent) |
| **VRAM** | ~10GB |
| **Tools** | read_file, search_code, git_diff, git_log, run_tests, shell |
| **Delegates to** | Huginn (for fixes after diagnosis) |
| **Priority** | HIGH - uses already-pulled model |

**Prompt Focus:**
- Systematic debugging methodology
- Root cause analysis techniques
- Stack trace interpretation
- Hypothesis-driven debugging
- Regression identification

### 3. Idunn (Documentation Specialist)

| Property | Value |
|----------|-------|
| **Role** | Generate/update documentation, docstrings, README files |
| **Model** | `llama3.1:8b` (shares with Mimir - VRAM efficient) |
| **VRAM** | ~5GB (shared) |
| **Tools** | read_file, write_file, list_directory, read_tree, search_code |
| **Delegates to** | None |
| **Priority** | MEDIUM - documentation is important but not urgent |

**Prompt Focus:**
- Google/NumPy/Sphinx docstring styles
- API documentation best practices
- README structure and conventions
- Code comment guidelines
- Changelog maintenance

### 4. Vidar (Multi-Language Coder)

| Property | Value |
|----------|-------|
| **Role** | Code generation across 80+ programming languages |
| **Model** | `codestral:22b-q4_K_M` (Mistral's dedicated code model) |
| **VRAM** | ~14GB |
| **Tools** | read_file, write_file, edit_file, search_code, shell, check_syntax |
| **Delegates to** | Skald (for test generation) |
| **Priority** | MEDIUM - expands language coverage significantly |

**Prompt Focus:**
- Multi-language expertise (JS/TS, Rust, Go, Java, C++, etc.)
- Language-specific idioms and best practices
- Cross-language refactoring
- Polyglot project support
- Framework-specific patterns

---

## Implementation Order

### Phase 1: Immediate (No new model pulls)
1. **Baldr** - Uses deepseek-r1:14b which is ALREADY PULLED
   - Zero setup cost, immediate value
   - Fills critical debugging gap

### Phase 2: Pull qwen3:14b (~9GB download)
2. **Heimdall** - Security is critical
   - Uses qwen3:14b's thinking mode for careful analysis
   - Command: `ollama pull qwen3:14b`

### Phase 3: Pull codestral:22b (~13GB download)
3. **Vidar** - Expands language coverage
   - Dedicated code model trained on 80+ languages
   - Command: `ollama pull codestral:22b-v0.1-q4_K_M`

### Phase 4: Add Idunn (No new model)
4. **Idunn** - Shares llama3.1:8b with Mimir
   - VRAM efficient, focused on documentation

---

## Model Upgrade for Existing Agents

### Recommended Upgrades:

| Agent | Current | Upgrade Option | Benefit |
|-------|---------|----------------|---------|
| **Odin** | deepseek-r1:8b | deepseek-r1:14b | Better reasoning, already pulled |
| **Brokkr** | qwen2.5-coder:14b | Keep (already optimal) | - |
| **Mimir** | llama3.1:8b | Keep (cost/benefit balanced) | - |

### Odin Upgrade Rationale:
- deepseek-r1:14b is already pulled and unused
- 14b version has significantly better reasoning
- Same VRAM footprint as 8b (~9-10GB)
- Immediate improvement with zero setup

---

## VRAM Budget Analysis

### Current Peak Usage (worst case):
- Brokkr (9GB) + Huginn (5GB) = 14GB ✓

### After Expansion (examples):
- Vidar (14GB) solo = 14GB ✓
- Heimdall (10GB) + Huginn (5GB) = 15GB ✓
- Baldr (10GB) + Skald (5GB) = 15GB ✓
- Brokkr (9GB) delegating to Heimdall (10GB) = need swap, but fallback available

### Fallback Strategy:
- Heimdall: qwen3:14b → qwen2.5-coder:7b (5GB)
- Baldr: deepseek-r1:14b → deepseek-r1:8b (5GB)
- Vidar: codestral:22b → qwen2.5-coder:7b (5GB)

---

## Files to Modify/Create

### Core Changes:
1. `sindri/agents/registry.py` - Add 4 new agent definitions
2. `sindri/agents/prompts.py` - Add 4 new specialized prompts
3. `tests/test_new_agents.py` - Test new agent configurations

### Documentation:
4. `TOOLS_AND_MODELS_ANALYSIS.md` - Update model recommendations
5. `STATUS.md` - Document new agents
6. `ROADMAP.md` - Update completion status

---

## Storage Requirements

### New Model Downloads:
- qwen3:14b: ~9GB
- codestral:22b-q4_K_M: ~13GB
- **Total new storage**: ~22GB

### Existing (reused):
- deepseek-r1:14b: 9GB (already pulled)
- llama3.1:8b: 5GB (shared with Mimir)

---

## Test Plan

1. **Unit Tests:**
   - Agent definition validation
   - Tool list verification
   - VRAM estimates check
   - Prompt content verification

2. **Integration Tests:**
   - Agent can be retrieved from registry
   - Delegation chains work correctly
   - Fallback models are valid

---

## Summary

| Agent | Model | VRAM | Status | Priority |
|-------|-------|------|--------|----------|
| **Baldr** | deepseek-r1:14b | 10GB | Model ready | HIGH |
| **Heimdall** | qwen3:14b | 10GB | Need pull | HIGH |
| **Vidar** | codestral:22b | 14GB | Need pull | MEDIUM |
| **Idunn** | llama3.1:8b | 5GB | Model ready | MEDIUM |

**Total new capability:**
- 4 new specialized agents
- 2 new models to pull (22GB storage)
- Leverage 1 unused pulled model (deepseek-r1:14b)
- Zero additional VRAM for 1 agent (Idunn shares with Mimir)
