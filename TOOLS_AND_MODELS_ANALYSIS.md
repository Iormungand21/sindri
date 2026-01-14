# Tools and Models Analysis

**Date:** 2026-01-14
**Purpose:** Audit current tools/models and recommend additions

---

## Current Tools Implemented ✅

### 1. **read_file**
- **Location:** `sindri/tools/filesystem.py`
- **Purpose:** Read file contents
- **Parameters:** `path`
- **Used by:** All agents
- **Status:** ✅ Working

### 2. **write_file**
- **Location:** `sindri/tools/filesystem.py`
- **Purpose:** Create/overwrite files
- **Parameters:** `path`, `content`
- **Auto-creates:** Parent directories
- **Used by:** Brokkr, Huginn, Ratatoskr, Skald, Fenrir
- **Status:** ✅ Working

### 3. **edit_file**
- **Location:** `sindri/tools/filesystem.py`
- **Purpose:** String replacement in files
- **Parameters:** `path`, `old_text`, `new_text`
- **Limitation:** Simple string replace, can break with whitespace changes
- **Used by:** Brokkr, Huginn
- **Status:** ✅ Working (but fragile)

### 4. **shell**
- **Location:** `sindri/tools/shell.py`
- **Purpose:** Execute shell commands
- **Parameters:** `command`
- **Returns:** stdout, stderr, return code
- **Used by:** All agents except Odin
- **Status:** ✅ Working

### 5. **delegate**
- **Location:** `sindri/tools/delegation.py` (special case)
- **Purpose:** Delegate task to another agent
- **Parameters:** `agent`, `task`, `context` (optional)
- **Used by:** Brokkr, Huginn, Odin
- **Status:** ✅ Working

**Total: 5 tools implemented**

---

## Planned Tools (from ROADMAP.md) 📋

### Phase 5.2: Directory Exploration (HIGH PRIORITY)

#### 6. **list_directory**
- **Purpose:** List files/dirs in a path
- **Parameters:**
  - `path` (default: cwd)
  - `recursive` (bool)
  - `pattern` (glob filter)
  - `ignore_hidden` (bool)
- **Use case:** Agents explore project structure
- **Benefit:** Critical for understanding codebases
- **Effort:** Low (1 hour)
- **Priority:** 🔴 Immediate

#### 7. **read_tree**
- **Purpose:** Show directory tree structure
- **Parameters:**
  - `path`
  - `max_depth` (tree depth limit)
  - `gitignore` (respect .gitignore)
- **Use case:** High-level project overview
- **Benefit:** Quick codebase understanding
- **Effort:** Low (30 min)
- **Priority:** 🔴 Immediate

### Phase 7.1: Agent Specialization

#### 8. **SQL Tools for Fenrir**
- `execute_query` - Run SQL queries
- `describe_schema` - Get table schema
- `explain_query` - Query analysis
- **Benefit:** Makes Fenrir truly specialized
- **Effort:** Medium
- **Priority:** 🟠 Next

#### 9. **Test Tools for Skald**
- `run_tests` - Execute test suite
- `coverage_report` - Get coverage stats
- `create_fixture` - Generate test fixtures
- **Benefit:** Makes Skald more effective
- **Effort:** Medium
- **Priority:** 🟠 Next

### Phase 7.3: Interactive Planning

#### 10. **propose_plan**
- **Purpose:** Create execution plan without executing
- **Parameters:** `task_description`
- **Returns:** Structured plan with steps, estimates
- **Benefit:** User review before execution
- **Effort:** Medium
- **Priority:** 🟡 Soon

---

## Recommended New Tools 🌟

### Category: Project Understanding

#### 11. **search_code** (HIGH VALUE)
- **Purpose:** Semantic code search (better than grep)
- **Parameters:**
  - `query` - What to search for
  - `file_types` - Filter by extension
  - `case_sensitive` (bool)
- **Implementation:** ripgrep wrapper or semantic search
- **Benefit:** Agents find relevant code quickly
- **Use case:** "Find all authentication code", "Where is user validation?"
- **Effort:** Low-Medium
- **Priority:** 🔴 Immediate

#### 12. **get_file_info**
- **Purpose:** File metadata without reading content
- **Parameters:** `path`
- **Returns:** Size, modified time, permissions, type
- **Benefit:** Check if file exists, get stats
- **Effort:** Low
- **Priority:** 🟡 Soon

#### 13. **find_symbol**
- **Purpose:** Find function/class definitions
- **Parameters:**
  - `symbol_name`
  - `symbol_type` (function, class, variable)
- **Implementation:** AST parsing or tree-sitter
- **Benefit:** "Where is User class defined?"
- **Effort:** Medium-High
- **Priority:** 🟢 Later

### Category: Code Analysis

#### 14. **parse_imports**
- **Purpose:** Extract imports/dependencies from file
- **Parameters:** `path`
- **Returns:** List of imports with sources
- **Benefit:** Understand module dependencies
- **Effort:** Medium
- **Priority:** 🟡 Soon

#### 15. **check_syntax**
- **Purpose:** Validate code syntax without executing
- **Parameters:** `path`, `language`
- **Returns:** Syntax errors with line numbers
- **Benefit:** Catch errors before saving
- **Effort:** Low (use language parsers)
- **Priority:** 🟡 Soon

#### 16. **format_code**
- **Purpose:** Auto-format code (black, prettier, etc.)
- **Parameters:** `path`, `formatter`
- **Benefit:** Consistent code style
- **Effort:** Low (wrapper around formatters)
- **Priority:** 🟢 Later

### Category: Git Integration

#### 17. **git_status**
- **Purpose:** Get git status
- **Returns:** Modified, staged, untracked files
- **Benefit:** Understand project state
- **Effort:** Low (git command wrapper)
- **Priority:** 🟡 Soon

#### 18. **git_diff**
- **Purpose:** Show changes in files
- **Parameters:** `file_path` (optional)
- **Returns:** Diff output
- **Benefit:** Review changes before commit
- **Effort:** Low
- **Priority:** 🟡 Soon

#### 19. **git_log**
- **Purpose:** Get commit history
- **Parameters:** `file_path` (optional), `limit`
- **Returns:** Recent commits
- **Benefit:** Understand file history
- **Effort:** Low
- **Priority:** 🟢 Later

### Category: Web & API

#### 20. **http_request**
- **Purpose:** Make HTTP requests
- **Parameters:**
  - `url`
  - `method` (GET, POST, etc.)
  - `headers` (dict)
  - `body` (optional)
- **Benefit:** API testing, data fetching
- **Effort:** Low (httpx wrapper)
- **Priority:** 🟡 Soon

#### 21. **parse_json**
- **Purpose:** Parse and validate JSON
- **Parameters:** `json_string` or `file_path`
- **Returns:** Parsed object or validation errors
- **Benefit:** JSON manipulation tasks
- **Effort:** Low
- **Priority:** 🟢 Later

### Category: Documentation

#### 22. **extract_docstrings**
- **Purpose:** Extract docstrings from code
- **Parameters:** `path`
- **Returns:** Function/class docstrings
- **Benefit:** Understand code without reading implementation
- **Effort:** Medium
- **Priority:** 🟢 Later

#### 23. **generate_docs**
- **Purpose:** Generate documentation from code
- **Parameters:** `path`, `format` (markdown, html)
- **Benefit:** Automatic documentation
- **Effort:** Medium-High
- **Priority:** 🟢 Later

### Category: Testing

#### 24. **run_tests**
- **Purpose:** Execute tests with specific framework
- **Parameters:**
  - `path` - Test file/directory
  - `framework` - pytest, jest, etc.
  - `args` - Additional arguments
- **Returns:** Test results, failures, coverage
- **Benefit:** Validate code changes
- **Effort:** Low (wrapper)
- **Priority:** 🟠 Next

#### 25. **benchmark**
- **Purpose:** Performance benchmarking
- **Parameters:** `code`, `iterations`
- **Returns:** Timing statistics
- **Benefit:** Performance optimization tasks
- **Effort:** Medium
- **Priority:** 🟢 Later

---

## Tool Priority Matrix

| Tool | Impact | Effort | Priority | Phase |
|------|--------|--------|----------|-------|
| list_directory | Very High | Low | 🔴 Immediate | 5.2 |
| read_tree | High | Low | 🔴 Immediate | 5.2 |
| search_code | Very High | Medium | 🔴 Immediate | 5.2 |
| get_file_info | Medium | Low | 🟡 Soon | 6 |
| git_status | Medium | Low | 🟡 Soon | 6 |
| git_diff | Medium | Low | 🟡 Soon | 6 |
| http_request | Medium | Low | 🟡 Soon | 6 |
| parse_imports | Medium | Medium | 🟡 Soon | 7 |
| check_syntax | High | Low | 🟡 Soon | 7 |
| run_tests | High | Low | 🟠 Next | 7.1 |
| SQL tools | Medium | Medium | 🟠 Next | 7.1 |
| format_code | Low | Low | 🟢 Later | 8 |
| find_symbol | High | High | 🟢 Later | 8 |
| git_log | Low | Low | 🟢 Later | 8 |
| parse_json | Low | Low | 🟢 Later | 8 |
| extract_docstrings | Low | Medium | 🟢 Later | 9 |
| generate_docs | Low | High | 🟢 Later | 9 |
| benchmark | Low | Medium | 🟢 Later | 9 |

---

## Current Ollama Models ✅

### Models Available Locally

| Model | Size | Purpose | Agent | Status |
|-------|------|---------|-------|--------|
| **qwen2.5-coder:14b** | 9.0GB | Orchestration | Brokkr | ✅ Active |
| **qwen2.5-coder:7b** | 4.7GB | Code gen/tests | Huginn, Skald | ✅ Active |
| **qwen2.5:3b-instruct-q8_0** | 3.3GB | Fast execution | Ratatoskr | ✅ Active |
| **llama3.1:8b** | 4.9GB | Code review | Mimir | ✅ Active |
| **sqlcoder:7b** | 4.1GB | SQL specialist | Fenrir | ✅ Active |
| **deepseek-r1:8b** | 4.9GB | Deep reasoning | Odin | ✅ Active |
| **nomic-embed-text** | 274MB | Embeddings | Memory | ✅ Active |

**Also Available (unused):**
- qwen2.5-coder:3b (1.9GB)
- qwen2.5-coder:1.5b (986MB)
- deepseek-r1:14b (9.0GB)
- deepseek-r1:32b (19GB)
- llava:7b (4.7GB) - Vision model

---

## Recommended Model Additions 🚀

### Tier 1: Immediate Value (Pull Now)

#### 1. **codellama:13b** or **codellama:34b**
- **Purpose:** Alternative code generation (Meta's model)
- **Size:** 7.4GB (13b) or 19GB (34b)
- **Use for:** Huginn alternative, better Python/JS
- **Benefit:** Diversity in code generation approaches
- **Priority:** 🔴 Immediate

#### 2. **mistral:7b** or **mixtral:8x7b**
- **Purpose:** General-purpose, excellent instruction following
- **Size:** 4.1GB (7b) or 26GB (8x7b)
- **Use for:** New general-purpose agent
- **Benefit:** Strong reasoning, good with complex instructions
- **Priority:** 🔴 Immediate

#### 3. **starcoder2:15b**
- **Purpose:** Code completion and generation (BigCode)
- **Size:** 9.1GB
- **Use for:** Huginn alternative, multi-language
- **Benefit:** Excellent at code completion
- **Priority:** 🟠 Next

### Tier 2: Specialized Models

#### 4. **deepseek-coder:33b**
- **Purpose:** Large code model (if VRAM allows)
- **Size:** 18GB
- **Use for:** Complex refactoring agent
- **Benefit:** Best-in-class code understanding
- **Priority:** 🟡 Soon (if 24GB+ VRAM)

#### 5. **phi3:medium** (14b)
- **Purpose:** Microsoft's small but powerful model
- **Size:** 7.9GB
- **Use for:** Fast reasoning, good efficiency
- **Benefit:** Quality close to larger models
- **Priority:** 🟡 Soon

#### 6. **llava:13b** or **llava:34b**
- **Purpose:** Vision + language (better than 7b)
- **Size:** 8GB (13b) or 20GB (34b)
- **Use for:** Screenshot analysis, diagram understanding
- **Benefit:** Understand UI, debug visual issues
- **Priority:** 🟡 Soon

### Tier 3: Experimental / Future

#### 7. **wizard-vicuna-uncensored:13b**
- **Purpose:** Creative, less restricted
- **Size:** 7.4GB
- **Use for:** Creative problem solving
- **Priority:** 🟢 Later

#### 8. **orca2:13b**
- **Purpose:** Reasoning and explanation
- **Size:** 7.4GB
- **Use for:** Planning, explanation agent
- **Priority:** 🟢 Later

#### 9. **falcon:40b** (if VRAM allows)
- **Purpose:** Large general model
- **Size:** 23GB
- **Use for:** Complex multi-step reasoning
- **Priority:** 🟢 Later

---

## Agent-to-Model Mapping Recommendations

### Current Mapping ✅

| Agent | Current Model | VRAM | Purpose |
|-------|--------------|------|---------|
| Brokkr | qwen2.5-coder:14b | 9.0GB | Orchestration |
| Huginn | qwen2.5-coder:7b | 4.7GB | Code implementation |
| Mimir | llama3.1:8b | 4.9GB | Code review |
| Ratatoskr | qwen2.5:3b-instruct | 3.3GB | Fast execution |
| Skald | qwen2.5-coder:7b | 4.7GB | Test generation |
| Fenrir | sqlcoder:7b | 4.1GB | SQL specialist |
| Odin | deepseek-r1:8b | 4.9GB | Deep reasoning |

### Proposed New Agents + Models

#### Thor (Performance Optimizer)
- **Model:** codellama:13b or starcoder2:15b
- **VRAM:** 7-9GB
- **Tools:** read_file, write_file, benchmark, check_syntax
- **Purpose:** Performance analysis and optimization
- **Delegates to:** Huginn (for implementation)

#### Heimdall (Security Guardian)
- **Model:** mistral:7b
- **VRAM:** 4.1GB
- **Tools:** read_file, search_code, check_syntax
- **Purpose:** Security auditing, vulnerability detection
- **Delegates to:** Mimir (for review)

#### Idunn (Documentation Specialist)
- **Model:** llama3.1:8b (same as Mimir)
- **VRAM:** 4.9GB
- **Tools:** read_file, write_file, extract_docstrings, generate_docs
- **Purpose:** Documentation generation and maintenance
- **Delegates to:** None

#### Loki (Debugger/Problem Solver)
- **Model:** deepseek-coder:33b or mixtral:8x7b
- **VRAM:** 18-26GB
- **Tools:** read_file, search_code, git_diff, run_tests
- **Purpose:** Debug complex issues, root cause analysis
- **Delegates to:** Huginn (for fixes)

---

## Model Selection Strategy

### By VRAM Budget

**8GB VRAM:**
- Core: qwen2.5-coder:7b, qwen2.5:3b
- Limit to 2 concurrent agents

**12GB VRAM:**
- Add: llama3.1:8b, sqlcoder:7b
- Can run 2-3 concurrent agents

**16GB VRAM (Your Setup):**
- All current models ✅
- Add: codellama:13b, mistral:7b
- Can run 3-4 concurrent agents

**24GB+ VRAM:**
- Add: deepseek-coder:33b, mixtral:8x7b
- Full parallel execution

### By Task Type

| Task | Primary Model | Backup Model |
|------|---------------|--------------|
| Orchestration | qwen2.5-coder:14b | mixtral:8x7b |
| Python code | qwen2.5-coder:7b | codellama:13b |
| JavaScript/TS | codellama:13b | starcoder2:15b |
| Testing | qwen2.5-coder:7b | mistral:7b |
| SQL | sqlcoder:7b | qwen2.5-coder:7b |
| Review | llama3.1:8b | mistral:7b |
| Reasoning | deepseek-r1:8b | phi3:medium |
| Fast tasks | qwen2.5:3b | qwen2.5-coder:3b |

---

## Implementation Recommendations

### Phase 1: Quick Wins (Today)
```bash
# Pull high-value models
ollama pull codellama:13b     # Python/JS specialist
ollama pull mistral:7b         # General purpose
ollama pull starcoder2:15b     # Code completion

# Implement critical tools
- list_directory (1 hour)
- read_tree (30 min)
- search_code (2 hours)
```

### Phase 2: Tool Expansion (This Week)
```bash
# Implement exploration tools
- get_file_info
- git_status, git_diff
- http_request
- check_syntax

# Add new agent
- Thor (performance optimizer) with codellama:13b
```

### Phase 3: Specialization (Next Week)
```bash
# Pull specialized models
ollama pull phi3:medium        # Efficient reasoning
ollama pull llava:13b          # Vision

# Implement specialized tools
- run_tests
- SQL tools for Fenrir
- parse_imports

# Add agents
- Heimdall (security) with mistral:7b
- Idunn (docs) with llama3.1:8b
```

---

## Tool Implementation Priority

### Immediate (This Session)
1. **list_directory** - Critical for codebase exploration
2. **read_tree** - Quick project overview
3. **search_code** - Better than grep

### This Week
4. **get_file_info** - Check existence, stats
5. **git_status** - Project state awareness
6. **http_request** - API testing
7. **check_syntax** - Validate before saving

### Next Week
8. **run_tests** - Validation loop
9. **parse_imports** - Dependency understanding
10. **SQL tools** - Fenrir specialization

---

## Expected Benefits

### From New Tools
- **60% faster** codebase exploration (list_directory, read_tree, search_code)
- **40% fewer errors** (check_syntax, run_tests)
- **Better context** for agents (git_status, parse_imports)

### From New Models
- **More diverse** code generation approaches (codellama, starcoder2)
- **Better reasoning** for complex tasks (mistral, phi3)
- **Specialized capabilities** (vision with llava)

---

## Storage Requirements

### Current Models: ~45GB
### Recommended Additions:
- codellama:13b: +7.4GB
- mistral:7b: +4.1GB
- starcoder2:15b: +9.1GB
- **Total: ~65GB**

### Full Setup (all tiers): ~100GB

---

## Summary

**Tools Status:**
- ✅ 5 tools implemented
- 📋 5 tools planned (ROADMAP.md)
- 🌟 20 new tools recommended
- 🔴 3 immediate priority (list_directory, read_tree, search_code)

**Models Status:**
- ✅ 7 models active
- 🚀 3 immediate additions (codellama, mistral, starcoder2)
- 💡 6 specialized models for later
- 🎯 4 new agent proposals (Thor, Heimdall, Idunn, Loki)

**Next Steps:**
1. Implement list_directory, read_tree, search_code tools
2. Pull codellama:13b, mistral:7b, starcoder2:15b models
3. Create Thor (performance optimizer) agent
4. Test with real projects
5. Iterate based on usage patterns
