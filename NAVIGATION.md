# Sindri Documentation Navigation

**Quick guide to find what you need**

---

## 🎯 Start Here

**New to Sindri?**
1. Read [README.md](README.md) - Overview and quick start
2. Check [STATUS.md](STATUS.md) - What works, what doesn't
3. Run `sindri doctor` to verify setup (planned)

**Picking up development?**
1. Read [STATUS.md](STATUS.md) - Current state
2. Check [ROADMAP.md](ROADMAP.md) - What to build next
3. Review [ARCHITECTURE.md](ARCHITECTURE.md) - How it works

**Ready to contribute?**
1. Pick a feature from [ROADMAP.md](ROADMAP.md)
2. Understand the pattern in [ARCHITECTURE.md](ARCHITECTURE.md)
3. Follow conventions in [CLAUDE.md](CLAUDE.md)

---

## 📚 Documentation Map

### For Users

| Document | Purpose | When to Read |
|----------|---------|--------------|
| [README.md](README.md) | Project overview, installation, basic usage | First time using Sindri |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 5-minute getting started guide | Want to try it now |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent capabilities, when to use which | Planning a complex task |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Config file options | Customizing behavior |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and fixes | Something's broken |

### For Developers

| Document | Purpose | When to Read |
|----------|---------|--------------|
| [STATUS.md](STATUS.md) | Current implementation status | Every session start |
| [ROADMAP.md](ROADMAP.md) | Feature roadmap, priorities | Planning what to build |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical design, patterns | Implementing features |
| [CLAUDE.md](CLAUDE.md) | Project context for Claude Code | Working in this codebase |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute (planned) | Want to submit PRs |

### Session Documentation

| Document | Purpose | When to Read |
|----------|---------|--------------|
| [SESSION_2026-01-14_FINAL_SUMMARY.md](SESSION_2026-01-14_FINAL_SUMMARY.md) | Latest session summary | Continuing recent work |
| [SESSION_RESUME_FIX.md](SESSION_RESUME_FIX.md) | Deep dive: session resume fix | Understanding delegation |
| [BROKKR_IMPROVEMENTS.md](BROKKR_IMPROVEMENTS.md) | Deep dive: Brokkr efficiency | Understanding agent behavior |
| [MEMORY_SYSTEM_TEST_RESULTS.md](MEMORY_SYSTEM_TEST_RESULTS.md) | Memory system validation | Working on memory features |
| [TUI_CANCELLATION_FEATURE.md](TUI_CANCELLATION_FEATURE.md) | Cancellation implementation | Understanding task lifecycle |

---

## 🔍 Find Information By Topic

### Understanding the System

**"How does Sindri work?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - System Architecture section

**"What's the Ralph loop?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Core Concepts section
→ [README.md](README.md) - How It Works section

**"How does delegation work?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Hierarchical Delegation
→ [SESSION_RESUME_FIX.md](SESSION_RESUME_FIX.md) - Detailed analysis

**"What are the agents?"**
→ [README.md](README.md) - Agent Hierarchy section
→ [docs/AGENTS.md](docs/AGENTS.md) - Full agent guide
→ `sindri/agents/registry.py` - Agent definitions

**"How does memory work?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Memory System
→ [README.md](README.md) - Memory System section
→ [MEMORY_SYSTEM_TEST_RESULTS.md](MEMORY_SYSTEM_TEST_RESULTS.md)

### Implementing Features

**"What should I build next?"**
→ [ROADMAP.md](ROADMAP.md) - Implementation Priority Matrix
→ [ROADMAP.md](ROADMAP.md) - Quick Wins section

**"How do I add a new tool?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Extension Points: Adding a New Tool

**"How do I add a new agent?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Extension Points: Adding a New Agent

**"How do I add a CLI command?"**
→ [ROADMAP.md](ROADMAP.md) - Phase 5.1: Missing CLI Commands

**"How do I test my changes?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Testing Strategy
→ `tests/` directory - Example tests

### Debugging Issues

**"Tests are failing"**
→ [STATUS.md](STATUS.md) - If Something Breaks section
→ [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

**"Tasks not completing"**
→ [STATUS.md](STATUS.md) - Known Issues section
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Debugging Tips

**"TUI not showing output"**
→ [STATUS.md](STATUS.md) - TUI Event System fix
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Event Flow

**"Memory errors"**
→ [ARCHITECTURE.md](ARCHITECTURE.md) - VRAM Management

### Project History

**"What was fixed recently?"**
→ [STATUS.md](STATUS.md) - Recent Fixes section
→ [SESSION_2026-01-14_FINAL_SUMMARY.md](SESSION_2026-01-14_FINAL_SUMMARY.md)

**"What's been tested?"**
→ [STATUS.md](STATUS.md) - What Works section
→ [TESTING_RESULTS.md](TESTING_RESULTS.md)

**"What's the development history?"**
→ [PHASE1_STATUS.md](PHASE1_STATUS.md) - Phase 1 work
→ [PHASE2_STATUS.md](PHASE2_STATUS.md) - Phase 2 work
→ [PHASE3_COMPLETE.md](PHASE3_COMPLETE.md) - Phase 3 work
→ [PHASE4_COMPLETE.md](PHASE4_COMPLETE.md) - Phase 4 work

---

## 🎯 Common Workflows

### Starting a New Session

1. ✅ Read [STATUS.md](STATUS.md) - What's the current state?
2. ✅ Run tests: `.venv/bin/pytest tests/ -v`
3. ✅ Check health: `ollama list`, `systemctl status ollama`
4. ✅ Review [ROADMAP.md](ROADMAP.md) - What to work on?
5. ✅ Create branch: `git checkout -b feature/name`

### Implementing a Feature

1. ✅ Check [ROADMAP.md](ROADMAP.md) for design notes
2. ✅ Review [ARCHITECTURE.md](ARCHITECTURE.md) for patterns
3. ✅ Write tests first (TDD approach)
4. ✅ Implement following existing patterns
5. ✅ Run tests: `.venv/bin/pytest tests/test_X.py -v`
6. ✅ Test manually with TUI: `.venv/bin/sindri tui`
7. ✅ Update [STATUS.md](STATUS.md) - Mark feature complete
8. ✅ Update [README.md](README.md) if user-facing

### Debugging a Problem

1. ✅ Enable DEBUG logging (see [ARCHITECTURE.md](ARCHITECTURE.md))
2. ✅ Check structured logs for errors
3. ✅ Inspect database: `sqlite3 ~/.sindri/sindri.db`
4. ✅ Use TUI for real-time visibility
5. ✅ Check [STATUS.md](STATUS.md) - Known Issues
6. ✅ Review recent changes in session docs

### Ending a Session

1. ✅ Commit changes: `git commit -m "..."`
2. ✅ Update [STATUS.md](STATUS.md) with:
   - What was accomplished
   - What works/doesn't work
   - Next steps
3. ✅ Run full test suite: `.venv/bin/pytest tests/ -v`
4. ✅ Push if appropriate: `git push`

---

## 📖 Documentation Standards

### When to Update Documentation

**Always update:**
- [STATUS.md](STATUS.md) - After every significant change
- [ROADMAP.md](ROADMAP.md) - When priorities change or features complete
- [README.md](README.md) - When user-facing behavior changes

**Sometimes update:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - When design patterns change
- Session docs - Create new doc for complex fixes/features

**Never update:**
- Phase completion docs (PHASE*_COMPLETE.md) - Historical record

### Documentation Style

**STATUS.md:**
- ✅/⏳/🚧 emojis for status
- Include file:line references
- Before/after examples for fixes
- Clear "Next Steps" section

**ROADMAP.md:**
- Organized by phase/priority
- Include effort estimates
- Link to related docs
- Code examples for clarity

**ARCHITECTURE.md:**
- Technical, for developers
- Include diagrams/pseudocode
- Explain "why" not just "what"
- Link to actual code files

---

## 🗂️ File Organization

### Root Directory

```
sindri/
├── README.md              ← Start here (users)
├── STATUS.md              ← Current state (developers)
├── ROADMAP.md             ← Future plans (developers)
├── ARCHITECTURE.md        ← Technical design (developers)
├── CLAUDE.md              ← Project context (AI assistants)
├── NAVIGATION.md          ← This file
├── LICENSE                ← MIT license
│
├── docs/                  ← User documentation
│   ├── QUICKSTART.md
│   ├── AGENTS.md
│   ├── CONFIGURATION.md
│   └── TROUBLESHOOTING.md
│
├── SESSION_*.md           ← Session summaries
├── *_FIX.md              ← Deep dive docs
├── *_TEST_RESULTS.md     ← Testing documentation
├── PHASE*.md              ← Historical phase docs
│
├── prompts/               ← Original phase prompts (historical)
├── sindri/                ← Source code
├── tests/                 ← Test suite
└── test_*.py              ← Validation scripts
```

### Key Locations

**Core Logic:**
- `sindri/core/hierarchical.py` - Ralph loop implementation (295 lines)
- `sindri/core/orchestrator.py` - Main entry point
- `sindri/core/delegation.py` - Parent-child task management

**Agent Definitions:**
- `sindri/agents/registry.py` - AGENTS dict
- `sindri/agents/prompts.py` - System prompts

**Tools:**
- `sindri/tools/filesystem.py` - File operations
- `sindri/tools/base.py` - Tool interface

**Memory:**
- `sindri/memory/system.py` - MuninnMemory orchestrator
- `sindri/memory/semantic.py` - Codebase embeddings

**TUI:**
- `sindri/tui/app.py` - Main Textual app
- `sindri/tui/widgets/` - UI components

**Tests:**
- `tests/test_delegation.py` - Delegation tests
- `tests/test_tools.py` - Tool tests
- `tests/test_memory.py` - Memory tests

---

## 🚀 Quick Reference

### Run Tests
```bash
.venv/bin/pytest tests/ -v                    # All tests
.venv/bin/pytest tests/test_delegation.py -v  # Specific test
.venv/bin/pytest tests/ --cov=sindri          # With coverage
```

### Try Sindri
```bash
.venv/bin/sindri run "Create hello.txt"       # CLI
.venv/bin/sindri tui                          # TUI
```

### Check System
```bash
ollama list                                   # Installed models
systemctl status ollama                       # Ollama running?
sqlite3 ~/.sindri/sindri.db "SELECT COUNT(*) FROM sessions;"
```

### Development
```bash
git checkout -b feature/my-feature            # New branch
ruff check sindri/                            # Lint
mypy sindri/                                  # Type check
```

---

## 💡 Tips for Navigation

### Finding Code

**"Where is the session resume fix?"**
→ `sindri/core/hierarchical.py:138-151`

**"Where are child results injected?"**
→ `sindri/core/delegation.py:95-115`

**"Where are events emitted?"**
→ `sindri/core/hierarchical.py:162, 220, 325`

**"Where is the Brokkr prompt?"**
→ `sindri/agents/prompts.py:3-54`

### Searching Documentation

Use your editor's search across all `.md` files:

- Search for keywords: "delegation", "memory", "VRAM"
- Search for file names: "hierarchical.py"
- Search for error messages
- Search for emojis: ✅ (completed), ⏳ (in progress), 🚧 (planned)

### Git History

```bash
# Recent commits
git log --oneline -10

# Changes to specific file
git log -p sindri/core/hierarchical.py

# Find when feature added
git log --all --grep="delegation"
```

---

## 🎓 Learning Path

### Week 1: Understanding
- Day 1-2: Read README, STATUS, try TUI
- Day 3-4: Read ARCHITECTURE, understand Ralph loop
- Day 5-7: Read code in `sindri/core/`, run tests

### Week 2: Contributing
- Day 1-3: Implement a small feature (directory tool?)
- Day 4-5: Add tests, update documentation
- Day 6-7: Review PR, incorporate feedback

### Week 3: Advanced
- Day 1-3: Implement medium feature (CLI command?)
- Day 4-5: Understand memory system
- Day 6-7: Performance optimization

---

## 📝 Documentation Debt

**Current gaps:**
- [ ] CONTRIBUTING.md doesn't exist (planned)
- [ ] API documentation incomplete
- [ ] Some tools lack detailed docs
- [ ] No video walkthrough

**When adding features:**
- Always update STATUS.md
- Add examples to README if user-facing
- Update ARCHITECTURE if design changes
- Create session doc if complex

---

**Last Updated:** 2026-01-14
**Maintained By:** Project maintainers

---

*Lost? Start with [README.md](README.md) or [STATUS.md](STATUS.md)*
