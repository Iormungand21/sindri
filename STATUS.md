# Sindri Project Status Report
**Date:** 2026-01-20
**Status:** Architecture Transformation COMPLETE - All Milestones Complete

---

## Architecture Transformation Progress

Sindri is being transformed from a multi-user deployable tool into an **internal-only research machine assistant**.

### Completed Milestones

#### Milestone 1: Remove Collaboration Module (COMPLETE)
- **Deleted:** `sindri/collaboration/` directory (11 files, ~8,948 lines)
- **Deleted:** 7 test files (~7,271 lines)
- **Removed:** 28+ CLI commands (share, comment, notifications, activity, webhooks, audit, api-keys)
- **Removed:** 50+ API endpoints from web server
- **Removed:** Collaboration database tables
- **Result:** ~16,200 lines removed, tests: 3095 → 2710

#### Milestone 2: Remove IDE Integration (COMPLETE)
- **Deleted:** `sindri/ide/` directory (3 Python files, 3 Lua files, ~1,295 lines)
- **Deleted:** `tests/test_ide.py` (818 lines)
- **Removed:** 2 CLI commands (ide, ide-status)
- **Result:** ~2,100 lines removed, tests: 2710 → 2654

#### Milestone 3: Simplify Marketplace to Local-Only (COMPLETE)
- **Simplified:** `sindri/marketplace/installer.py` - removed git/URL installation methods (~220 lines)
- **Updated:** CLI commands - removed `--ref` option, updated help text for local-only
- **Updated:** `sindri/marketplace/metadata.py` - updated docstrings for local-only mode
- **Removed:** 4 tests for `_detect_source_type()` method
- **Result:** Marketplace now only supports local path installation, tests: 2654 → 2654 (unchanged)

#### Milestone 4: Relax Security Restrictions (COMPLETE)
- **Updated:** `sindri/tools/browser.py` - allow localhost/private IPs, only block cloud metadata
- **Updated:** `sindri/tools/http.py` - same changes, default `allow_localhost=True`
- **Updated:** `sindri/tools/network.py` - same changes for PortCheckTool, PingHostTool, SslAnalyzeTool, HttpTraceTool
- **Updated:** `sindri/tools/scraping.py` - same changes
- **Blocked:** Only cloud metadata endpoints (169.254.169.254, 169.254.170.2, metadata.google.internal) and file:// protocol
- **Allowed:** localhost, 127.0.0.1, private IP ranges (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
- **Result:** Enables local service integration for internal-only mode, tests: 2654 → 2654 (unchanged)

#### Milestone 5: Add System Access Configuration (COMPLETE)
- **Added:** `SystemAccessLevel` enum (RESTRICTED, SUPERVISED, FULL) to `sindri/config.py`
- **Added:** Config fields: `system_access`, `allowed_services`, `allow_self_modification`
- **Created:** `sindri/core/access.py` - Access check utility with confirmation mechanism
- **Added:** CLI commands: `sindri access show`, `sindri access set`, `sindri access services`, `sindri access self-modify`
- **Access Levels:**
  - RESTRICTED: Read-only system info, no modifications
  - SUPERVISED: Modifications require user confirmation (default)
  - FULL: Full autonomous access (for dedicated machine)
- **Result:** Configurable system access for graduated trust, tests: 2654 → 2691 (+37 new tests)

#### Milestone 6: Add Self-Management Tools (COMPLETE)
- **Created:** `sindri/tools/services.py` - 8 service management tools (status, start, stop, restart, enable, disable, logs, list)
- **Created:** `sindri/tools/self_management.py` - 9 self-management tools (sindri_version, sindri_update, sindri_config_get/set, ollama_list/pull/remove/status, vram_status)
- **Created:** `sindri/tools/scheduling.py` - 9 scheduling tools (cron_list/add/remove, timer_list/create/remove, at_schedule/list/remove)
- **Added:** `sindri_admin` agent with all 26 new tools
- **Added:** CLI commands: `sindri service`, `sindri schedule`, `sindri self`
- **Service Management:**
  - `sindri service status <name>` - Check service status
  - `sindri service start/stop/restart <name>` - Control services
  - `sindri service logs <name>` - View service logs
  - `sindri service list` - List services
- **Scheduling:**
  - `sindri schedule list` - List cron jobs, timers, at jobs
  - `sindri schedule cron-add/remove` - Manage cron jobs
  - `sindri schedule timer-create/remove` - Manage systemd user timers
  - `sindri schedule at` - Schedule one-time tasks
- **Self-Management:**
  - `sindri self version` - Show Sindri version
  - `sindri self update` - Update Sindri
  - `sindri self models` - List Ollama models
  - `sindri self pull/remove <model>` - Manage models
  - `sindri self vram` - Show GPU VRAM usage
- **Result:** Full self-management capability for autonomous operation, tests: 2691 → 2778 (+87 new tests)

#### Milestone 7: Simplify Web UI (COMPLETE)
- **Finding:** No auth/collaboration UI existed in the frontend
- **Verified:** React components (23 files) contain no authentication, team management, or multi-user features
- **Verified:** FastAPI server has no auth middleware or team/user context
- **Note:** The collaboration UI was either never built or removed in Milestone 1
- **Result:** No changes needed - frontend already single-user ready

#### Milestone 8: Documentation Update (COMPLETE)
- **Updated:** `README.md` - removed collaboration feature, updated agent/tool/test counts
- **Updated:** `ARCHITECTURE.md` - removed collaboration references, updated counts
- **Updated:** `STATUS.md` - marked all milestones complete
- **Updated:** `ROADMAP.md` - marked all milestones complete
- **Updated:** `ONBOARDING.md` - updated milestone status
- **Result:** Documentation now reflects internal-only mode

### Full Plan
See: `/home/ryan/.claude/plans/silly-kindling-parnas.md`

---

## Current State

**Status:** Internal-only mode COMPLETE (single-user, no collaboration, no IDE integration, local-only marketplace, relaxed security for localhost, configurable system access, self-management tools)
**Test Status:** 3022 tests passing (100%)
**Features:** Diagram Generation, LaTeX, OpenSCAD 3D Modeling, Data Visualization, Text/Regex Processing, Compression, Crypto/Encoding, System/Process, Image, Document Processing, Network/HTTP, Database, Media, Profiling, Browser Automation Tools, System Access Configuration, Service Management, Scheduling, Self-Management, Bash Scripting & Systemd Generation, Docker Runtime Tools, AWS & Kubernetes Tools, **Vision-Based Document Processing (Groa Agent)**

### Try It Out
```bash
# Verify everything works
.venv/bin/pytest tests/ -v --tb=no -q    # 3022 tests
cd sindri/web/static && npm test -- --run  # 104 frontend tests
.venv/bin/sindri doctor --verbose          # Check system health
.venv/bin/sindri agents                    # See all 22 agents (including groa)

# System Access Configuration
.venv/bin/sindri access show               # View current access settings
.venv/bin/sindri access set supervised     # Set access level (restricted/supervised/full)
.venv/bin/sindri access services --list    # List allowed services
.venv/bin/sindri access services --add docker  # Add service to allowlist
.venv/bin/sindri access self-modify        # Check self-modification status

# Service Management (Milestone 6)
.venv/bin/sindri service status ollama     # Check service status
.venv/bin/sindri service logs ollama       # View service logs
.venv/bin/sindri service list              # List running services
.venv/bin/sindri service restart ollama    # Restart a service

# Scheduling (Milestone 6)
.venv/bin/sindri schedule list             # List all scheduled tasks
.venv/bin/sindri schedule cron-add "0 2 * * *" "sindri doctor" -c "Daily health"
.venv/bin/sindri schedule timer-create health "sindri doctor" --calendar daily

# Self-Management (Milestone 6)
.venv/bin/sindri self version              # Show version info
.venv/bin/sindri self models               # List Ollama models
.venv/bin/sindri self vram                 # Show GPU VRAM usage
.venv/bin/sindri self ollama-status        # Check Ollama server

# Launch interfaces
.venv/bin/sindri tui                       # Terminal UI
.venv/bin/sindri web --port 8000           # Web UI at http://localhost:8000
.venv/bin/sindri voice                     # Voice interface

# Fine-tune models
.venv/bin/sindri finetune stats            # View training data statistics
.venv/bin/sindri finetune train            # Start model fine-tuning
.venv/bin/sindri finetune models           # List fine-tuned models

# Database Migrations
.venv/bin/sindri migrate                   # Apply pending migrations
.venv/bin/sindri migrate-status            # Check migration status
.venv/bin/sindri migrate-generate name     # Generate new migration
.venv/bin/sindri migrate-validate          # Validate migrations

# Diagram Generation
.venv/bin/sindri diagram mermaid sequence --title "Auth Flow"  # Mermaid sequence diagram
.venv/bin/sindri diagram mermaid flowchart -d LR -o flow.md    # Mermaid flowchart
.venv/bin/sindri diagram plantuml class --theme blueprint      # PlantUML class diagram
.venv/bin/sindri diagram from-code ./sindri --type class       # Extract class diagram from code
.venv/bin/sindri diagram er models.py --format mermaid         # ER diagram from SQLAlchemy
.venv/bin/sindri diagram sequence -p User -p API -p DB         # Quick sequence diagram

# LaTeX Generation
.venv/bin/sindri latex document "My Paper" --author "J. Smith"  # Generate LaTeX document
.venv/bin/sindri latex equation "x^2 + 2x + 1" --display       # Format equations
.venv/bin/sindri latex tikz neural_network --scale 1.5         # TikZ neural network diagram
.venv/bin/sindri latex beamer "My Talk" --theme Madrid         # Beamer presentation
.venv/bin/sindri latex bib create -f refs.bib                   # Create bibliography
.venv/bin/sindri latex compile document.tex                     # Compile to PDF

# OpenSCAD 3D Modeling
.venv/bin/sindri scad generate "A box with lid" -w 50 -h 30 -d 40  # Generate OpenSCAD code
.venv/bin/sindri scad generate "Phone stand with 60 degree angle"  # Phone stand
.venv/bin/sindri scad generate "Gear with 24 teeth" -o gear.scad   # Gear model
.venv/bin/sindri scad preview model.scad                           # Render PNG preview
.venv/bin/sindri scad export model.scad -o print.stl               # Export to STL
.venv/bin/sindri scad validate model.scad                          # Validate code
.venv/bin/sindri scad parametrize model.scad                       # Add parameters
.venv/bin/sindri scad optimize model.scad                          # Print optimization tips

# Data Visualization
.venv/bin/sindri viz analyze data.csv                              # Analyze dataset structure
.venv/bin/sindri viz suggest data.csv --goal comparison            # Suggest visualizations
.venv/bin/sindri viz d3 bar data.csv -x category -y value          # Generate D3.js bar chart
.venv/bin/sindri viz matplotlib scatter data.csv -x x -y y         # Generate matplotlib scatter
.venv/bin/sindri viz plotly line data.csv -x time -y value         # Generate Plotly line chart
.venv/bin/sindri viz dashboard data.csv -c config.json -o out.html # Create multi-chart dashboard
.venv/bin/sindri viz export chart_code.js -o chart.html            # Export standalone HTML

# Compression & Archives
.venv/bin/sindri archive create backup.zip file1.txt dir/         # Create archive
.venv/bin/sindri archive extract backup.tar.gz -o ./extracted/    # Extract archive
.venv/bin/sindri archive list archive.zip -d                      # List contents (detailed)
.venv/bin/sindri archive compress data.json -f gzip               # Compress file
.venv/bin/sindri archive decompress data.json.gz                  # Decompress file

# Image Manipulation
.venv/bin/sindri image resize photo.jpg --width 800               # Resize to width
.venv/bin/sindri image resize photo.jpg --scale 50                # Scale by percentage
.venv/bin/sindri image crop photo.jpg --x 0 --y 0 -w 640 -h 480   # Crop region
.venv/bin/sindri image convert photo.png --format webp -q 90      # Convert format
.venv/bin/sindri image rotate photo.jpg --angle 90 --expand       # Rotate image
.venv/bin/sindri image thumbnail photo.jpg --size 128             # Create thumbnail
.venv/bin/sindri image info photo.jpg                             # Get image info

# Document Processing
.venv/bin/sindri doc extract document.pdf                         # Extract text from PDF
.venv/bin/sindri doc extract scanned.pdf --ocr                    # OCR scanned PDFs
.venv/bin/sindri doc to-markdown document.pdf -o output.md        # PDF to Markdown
.venv/bin/sindri doc merge -o combined.pdf file1.pdf file2.pdf    # Merge PDFs
.venv/bin/sindri doc split book.pdf --single-pages                # Split PDF into pages
.venv/bin/sindri doc ocr scan.png -o text.txt                     # OCR image to text
.venv/bin/sindri doc read data.csv -n 100 -f json                 # Read spreadsheet
.venv/bin/sindri doc write output.xlsx -d '[{"col": "val"}]'      # Write spreadsheet

# Run a task
.venv/bin/sindri run "Create hello.py that prints hello"
.venv/bin/sindri orchestrate "Review this codebase"
```

---

## Recent Changes

### Vision-Based Document Processing (2026-01-20) - Phase 12 Tier 3 Groa Agent

Added **Groa** - a specialized document processing agent with vision model capability. Named after the Norse Völva (seeress) who could perceive beyond the physical world, Groa uses AI vision to understand documents, going beyond traditional text extraction.

**New Agent:**
- **Groa** (Norse seeress) - Document/vision specialist using granite3.2-vision:2b

**New Tools (3 total):**

*Vision-Based Document Tools:*
- `document_describe` - Describe document content using AI vision (layout, text, charts, tables)
- `document_extract_structured` - Extract structured data (forms, tables, key-value pairs) as JSON/CSV/markdown
- `document_summarize` - AI-powered document summary with multi-page support and focus areas

**Key Features:**
- Uses granite3.2-vision:2b for visual document understanding
- Converts PDF pages to images automatically (PyMuPDF)
- Supports PDF, PNG, JPG, and other image formats
- Returns structured JSON/CSV/markdown output for extracted data
- Combines vision tools with traditional document tools (pdf_extract_text, ocr_image, etc.)

**Agent Assignment:**
- **Groa** has 14 tools: 3 vision + 7 traditional document + 4 file operations
- **Brokkr** can delegate to Groa for document understanding tasks

**OllamaClient Enhancement:**
- Added `images` parameter to `chat()` and `chat_stream()` methods
- Enables vision model support across the system

**Tests:** +63 new tests (3022 total)

---

### AWS & Kubernetes Tools (2026-01-19) - Phase 12 Category 12 Complete

Added **Tyr** - a specialized cloud infrastructure operations agent. Named after the Norse god of law and heroic glory who sacrificed his hand to bind Fenrir, Tyr brings order to cloud chaos and executes infrastructure operations with precision.

**New Agent:**
- **Tyr** (Norse god) - Cloud infrastructure operations specialist using qwen2.5-coder:7b

**New Tools (12 total):**

*AWS Tools (6):*
- `aws_s3_list` - List S3 buckets or objects in a bucket
- `aws_s3_upload` - Upload files or directories to S3
- `aws_s3_download` - Download files or directories from S3
- `aws_logs_query` - Query CloudWatch Logs with filter patterns
- `aws_ec2_list` - List EC2 instances with state/tag filtering
- `aws_lambda_invoke` - Invoke Lambda functions (sync/async)

*Kubernetes Tools (6):*
- `k8s_apply` - Apply manifests from file or inline YAML
- `k8s_get_pods` - List pods with namespace/selector filtering
- `k8s_logs` - Get pod logs with tail/since/container options
- `k8s_get_services` - List services with filtering
- `k8s_describe` - Describe any resource in detail
- `k8s_delete` - Delete resources with force/grace-period options

**Agent Assignment:**
- **Tyr** has access to all 12 cloud tools plus core file operations
- **Brokkr** can delegate to Tyr for AWS and Kubernetes operations

**Key Features:**
- AWS CLI wrapper with async subprocess execution
- kubectl wrapper with full command support
- Automatic s3:// prefix handling
- Relative time parsing for CloudWatch queries (1h, 30m, 1d)
- JSON/table output format options
- Dry-run mode for k8s_apply

**Files:**
- `sindri/tools/aws.py` - AWS tool implementations (~500 lines)
- `sindri/tools/kubernetes.py` - Kubernetes tool implementations (~450 lines)
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/prompts.py` - TYR_PROMPT with cloud best practices
- `sindri/agents/registry.py` - Tyr agent definition
- `tests/test_aws.py` - AWS tool tests (~400 lines)
- `tests/test_kubernetes.py` - K8s tool tests (~350 lines)

**Requirements:**
- AWS CLI (`aws`) - User must have installed and configured
- kubectl - User must have installed and configured

**Tests:** +72 new tests (2959 total)

---

### Math & Scientific Tools (2026-01-19) - Phase 12 Category 13

Added **Nidhogg** - a specialized math and scientific computing agent. Named after the Norse dragon that gnaws at the roots of Yggdrasil, Nidhogg delves deep into mathematical foundations to extract computational insights.

**New Agent:**
- **Nidhogg** (Norse dragon) - Math and scientific computing specialist using mathstral:7b

**New Tools (6 total):**
- `math_evaluate` - Evaluate mathematical expressions (arithmetic, trig, symbolic) with optional variable substitution
- `math_solve` - Solve single equations or systems of equations (linear, quadratic, polynomial) with domain support
- `stats_analyze` - Statistical analysis: descriptive stats, correlation, t-test, ANOVA, regression
- `plot_generate` - Generate plots (function, scatter, histogram, heatmap) with fit lines and export to PNG/SVG/PDF
- `unit_convert` - Physical unit conversion using pint (length, mass, time, temperature, energy, etc.)
- `matrix_operations` - Linear algebra: multiply, inverse, transpose, determinant, eigenvalues, SVD, solve Ax=b

**Agent Assignment:**
- **Nidhogg** has access to all 6 math tools plus core file operations (read_file, write_file, list_directory, read_tree)
- **Brokkr** can delegate to Nidhogg for mathematical and scientific computing tasks

**Key Features:**
- Symbolic math via SymPy (exact fractions, symbolic simplification)
- Numeric mode for floating-point results
- Statistical tests with p-values and confidence intervals
- Multi-format plot export (PNG, SVG, PDF, base64)
- Unit arithmetic (e.g., "5 kg * 9.8 m/s**2" → force in newtons)
- Matrix decompositions (eigenvalues, SVD, LU, QR)

**Files:**
- `sindri/tools/math.py` - All math/scientific tool implementations (~1200 lines)
- `sindri/agents/prompts.py` - NIDHOGG_PROMPT with mathematical best practices
- `sindri/agents/registry.py` - Nidhogg agent definition
- `tests/test_math.py` - Comprehensive test suite

**Dependencies Added:**
- sympy>=1.13.0 (symbolic mathematics)
- scipy>=1.11.0 (statistical analysis)
- matplotlib>=3.8.0 (plotting)
- pint>=0.23.0 (unit conversion)

**Tests:** +70 new tests (2887 total)

---

### Sif Shell/SysAdmin Agent (2026-01-18) - Phase 12 Tier 2

Added **Sif** - a specialized shell scripting and system administration agent. Named after the Norse goddess whose golden hair was replaced by dwarf-forged gold, Sif transforms raw commands into polished, reliable scripts.

**New Agent:**
- **Sif** (Norse goddess) - Shell scripting and sysadmin specialist using qwen2.5-coder:7b

**New Tools (5 total):**
- `bash_generate` - Generate bash scripts from natural language descriptions (backup, deployment, health check, cleanup patterns)
- `bash_explain` - Explain complex bash commands and pipelines in plain English
- `bash_validate` - Validate bash scripts using shellcheck for best practices
- `systemd_generate` - Generate systemd unit files (service, timer, socket, path) with security hardening
- `bash_lint` - Lint bash scripts with optional auto-fix

**Agent Assignment:**
- **Sif** has access to all 5 new bash tools plus system monitoring (read-only) and service status tools
- **Brokkr** can delegate to Sif for shell scripting and automation tasks

**Key Features:**
- Script templates for common use cases (backup, log rotation, deployment, health check, cleanup)
- POSIX-portable mode for cross-platform scripts
- Security hardening options for systemd units
- Shellcheck integration for validation and linting

**Files:**
- `sindri/tools/bash_tools.py` - All bash/systemd tool implementations
- `sindri/agents/prompts.py` - SIF_PROMPT with bash best practices
- `sindri/agents/registry.py` - Sif agent definition
- `tests/test_bash_tools.py` - Comprehensive test suite

**Tests:** +36 new tests (2767 total)

---

### Architecture Transformation Complete (2026-01-18) - Milestones 7-8

Completed the architecture transformation to internal-only mode:

**Milestone 7: Web UI Cleanup**
- Verified: No auth/collaboration UI exists in React frontend (23 components checked)
- Verified: No auth middleware in FastAPI server
- Finding: Frontend was already single-user ready - no changes needed
- Updated: Agent count test (17 → 18 to include sindri_admin)

**Milestone 8: Documentation Update**
- Updated `README.md`: Removed collaboration feature, updated counts (18 agents, 155+ tools, 2726 tests)
- Updated `ARCHITECTURE.md`: Removed collaboration references, updated counts
- Updated `STATUS.md`: Marked all milestones complete
- Updated `ROADMAP.md`: Marked milestones 7-8 complete
- Updated `ONBOARDING.md`: Updated milestone status

**Cleanup:**
- Deleted untracked WIP files: `sindri/tools/docker_tools.py`, `tests/test_docker_tools.py`

**Result:** Architecture transformation complete. Sindri is now a fully internal-only research machine assistant.

---

### Browser & Web Automation Tools (2026-01-18) - Phase 12 Tier 3

Added comprehensive browser automation tools using Playwright and a lightweight web scraping tool:

**New Agent:**
- **Ran** (Norse sea goddess) - Browser automation specialist using qwen2.5-coder:7b

**New Tools (9 total):**
- `browser_navigate` - Navigate to URL and wait for page load (supports load, domcontentloaded, networkidle)
- `browser_click` - Click element by CSS selector or visible text
- `browser_type` - Type text into form fields with clear_first and press_enter options
- `browser_screenshot` - Capture viewport, full page, or element screenshots (PNG/JPEG)
- `browser_extract` - Extract text, attributes, or structured data from elements
- `browser_execute_js` - Run JavaScript in page context, return results
- `browser_pdf` - Save page as PDF with paper format, orientation, and scale options
- `browser_close` - Close browser session and release resources
- `web_scrape` - Lightweight web scraping with httpx (no JavaScript rendering, fast)

**Key Features:**
- Singleton browser session for multi-step workflows (navigate → interact → extract)
- Security by default: blocks localhost, private IPs, cloud metadata endpoints
- Lazy browser initialization (only starts when first tool is called)
- CSS selector and text-based element selection
- Configurable timeouts for all operations
- Headless mode by default (can show browser for debugging)

**Agent Assignment:**
- **Ran** has access to all 9 browser/scraping tools plus read_file, write_file, list_directory
- **Brokkr** can delegate to Ran for browser automation tasks

**Dependencies:**
- playwright>=1.40.0 (optional, in browser extras)
- html2text>=2024.0.0 (optional, for markdown conversion)

**Installation:**
```bash
pip install -e ".[browser]"
playwright install chromium
```

**Files:**
- `sindri/tools/browser.py` - Browser automation tool implementations
- `sindri/tools/scraping.py` - Web scraping tool implementation
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added Ran agent, updated Brokkr delegation
- `sindri/agents/prompts.py` - RAN_PROMPT added
- `pyproject.toml` - Added browser optional dependency
- `tests/test_browser.py` - Browser tool tests
- `tests/test_scraping.py` - Scraping tool tests

**Tests:** +68 new tests (3095 total)

---

### Python Profiling Tools (2026-01-18) - Phase 12 Tier 3

Added comprehensive profiling and performance analysis tools for Python code:

**New Tools (7 total):**
- `profile_python` - CPU profiling with cProfile (optional Scalene for detailed CPU/memory/GPU analysis)
- `profile_time` - Execution timing with timeit, statistical analysis (mean, std, min, max)
- `memory_analyze` - Memory usage breakdown using tracemalloc (optional memory_profiler for line-by-line)
- `detect_memory_leaks` - Memory leak detection via snapshot comparison
- `benchmark_function` - Function benchmarking with warmup, comparison support, and statistics
- `flame_graph` - Flame graph generation using py-spy (speedscope format)
- `complexity_analyze` - Big-O complexity estimation via AST analysis (detects loops, recursion, sorting)

**Agent Assignment:**
- **Ratatoskr** (fast executor) has access to all 7 profiling tools

**Dependencies:**
- cProfile, timeit, tracemalloc (stdlib - no installation required)
- memory-profiler>=0.61.0 (optional, in profiling extras)
- scalene>=1.5.0 (optional, in profiling extras)
- py-spy (system binary, requires elevated permissions)

**Files:**
- `sindri/tools/profiling.py` - All profiling tool implementations
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added tools to Ratatoskr
- `sindri/agents/prompts.py` - Updated Ratatoskr prompt
- `pyproject.toml` - Added profiling optional dependency
- `tests/test_profiling.py` - Comprehensive test suite

**Tests:** +55 new tests (3027 total)

---

### Video/Audio Processing Tools (2026-01-18) - Phase 12 Tier 3

Added comprehensive video and audio processing tools using FFmpeg and Whisper:

**New Tools (11 total):**
- `audio_transcribe` - Transcribe audio files to text using Whisper (tiny/base/small/medium/large)
- `video_transcribe` - Extract and transcribe speech from video files
- `video_generate_subtitles` - Generate SRT/VTT subtitle files from audio/video
- `video_extract_audio` - Extract audio track from video (mp3/wav/flac/aac/ogg)
- `audio_convert` - Convert between audio formats with bitrate control
- `video_convert` - Convert between video formats (mp4/mkv/webm/avi/mov) with CRF quality
- `video_trim` - Cut video to time range (supports HH:MM:SS and seconds)
- `video_thumbnail` - Generate thumbnail image at specific timestamp
- `video_concat` - Join multiple videos into one
- `tts_generate` - Text-to-speech synthesis with voice control
- `video_add_subtitles` - Burn subtitles into video (hardcoded)

**Agent Assignment:**
- **Ratatoskr** (fast executor) has access to all 11 media tools

**Dependencies:**
- FFmpeg binary (system) - Required for video/audio processing
- ffmpeg-python>=0.2.0 (optional, in media extras)
- faster-whisper>=1.0.0 (existing voice extras, for transcription)
- pyttsx3>=2.90 (existing voice extras, for TTS)

**Files:**
- `sindri/tools/media.py` - All media tool implementations
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added tools to Ratatoskr
- `sindri/agents/prompts.py` - Updated Ratatoskr prompt
- `pyproject.toml` - Added media optional dependency
- `tests/test_media.py` - Comprehensive test suite

**Tests:** +50 new tests

---

### Database Tools (2026-01-18) - Phase 12 Tier 2 Complete

Added database tools for SQL generation and test data seeding:

**New Tools (2 total):**
- `sql_generate` - Generate SQL queries from natural language descriptions
- `db_seed` - Generate realistic test data using Faker library

**sql_generate Features:**
- Pattern-based natural language to SQL conversion
- Supports SELECT, COUNT, GROUP BY, JOIN, ORDER BY, LIMIT patterns
- Schema-aware validation when database path provided
- Multiple query patterns: "Get all users", "Count orders per customer", "Top 10 products by price"

**db_seed Features:**
- Automatic data type detection from column names (email → fake.email(), etc.)
- Foreign key relationship handling
- Batch inserts for performance (configurable batch size)
- Reproducible seeding with random seed support
- Locale support for localized test data
- Clear existing data option before seeding

**Agent Assignment:**
- **Fenrir** (SQL specialist) has access to both tools

**Dependencies:**
- faker>=24.0.0 (new dependency)

**Files:**
- `sindri/tools/sql.py` - Added SqlGenerateTool and DbSeedTool classes
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Updated Fenrir's tools list
- `sindri/agents/prompts.py` - Updated FENRIR_PROMPT with new tool documentation

**Tests:** +26 new tests (2920 total)

---

### Network & HTTP Diagnostic Tools (2026-01-18) - Phase 12 Tier 2

Added comprehensive network diagnostic tools for debugging, testing, and connectivity analysis:

**New Tools (6 total):**
- `http_trace` - Detailed HTTP request tracing with timing breakdown, redirects, headers
- `dns_lookup` - DNS resolution for multiple record types (A, AAAA, MX, TXT, CNAME, NS, etc.)
- `curl_generate` - Generate curl commands from parameters (headers, auth, JSON body)
- `ssl_analyze` - SSL/TLS certificate analysis (expiry, chain, cipher, SANs)
- `port_check` - Check if network ports are open (single or multiple ports)
- `ping_host` - Network connectivity test via ICMP ping

**Agent Assignments:**
- **Ratatoskr** (fast executor): All 6 tools for quick diagnostics
- **Heimdall** (security): ssl_analyze, port_check for security auditing

**Key Features:**
- Security by default: blocks localhost, private IPs, cloud metadata endpoints
- Async execution with proper timeout handling
- Detailed metadata in results for programmatic use
- Cross-platform ping support (Linux/macOS/Windows)

**Dependencies:**
- dnspython>=2.6.0 (new dependency)
- httpx, ssl, cryptography (existing)

**Tests:** +53 new tests (2894 total)

---

### Document Processing Tools (2026-01-18) - Phase 12 Tier 2

Added comprehensive document processing tools for PDFs, spreadsheets, and OCR:

**New Tools (7 total):**
- `pdf_extract_text` - Extract text from PDFs (with optional OCR for scanned documents)
- `pdf_to_markdown` - Convert PDF to clean Markdown preserving structure
- `pdf_merge` - Merge multiple PDF files into one
- `pdf_split` - Split PDF by page ranges or into single pages
- `ocr_image` - Extract text from images using Tesseract OCR
- `spreadsheet_read` - Read CSV/Excel files with filtering and limiting
- `spreadsheet_write` - Write data to CSV/Excel files

**CLI Commands:**
- `sindri doc extract <file>` - Extract text from PDF
- `sindri doc to-markdown <file>` - Convert PDF to Markdown
- `sindri doc merge -o <out> <files...>` - Merge PDFs
- `sindri doc split <file>` - Split PDF
- `sindri doc ocr <file>` - OCR image to text
- `sindri doc read <file>` - Read spreadsheet
- `sindri doc write <file>` - Write spreadsheet

**Dependencies:**
- PyMuPDF (fitz) for PDF operations
- pandas + openpyxl for spreadsheet handling
- pytesseract (optional) for OCR

**Tests:** +42 new tests (2841 total)

---

### Image Manipulation Tools (2026-01-18) - Phase 12 Tier 2

Added comprehensive image manipulation tools using Pillow (PIL):

**New Tools (6 total):**
- `image_resize` - Resize images to width/height or scale percentage with aspect ratio preservation
- `image_crop` - Crop images to specified rectangular region
- `image_convert` - Convert between formats (JPEG, PNG, GIF, WebP, BMP, TIFF)
- `image_rotate` - Rotate images by degrees with expand/fill options
- `image_thumbnail` - Generate thumbnails preserving aspect ratio
- `image_info` - Get image metadata (dimensions, format, mode, EXIF)

**Features:**
- Multiple resampling methods (nearest, bilinear, bicubic, lanczos)
- Quality control for JPEG/WebP output
- RGBA to RGB conversion with transparency handling
- Default output path generation with descriptive suffixes
- Comprehensive error handling and validation

**CLI Commands:**
- `sindri image resize <file> --width 800` - Resize to width
- `sindri image resize <file> --scale 50` - Scale by percentage
- `sindri image crop <file> --x 0 --y 0 -w 640 -h 480` - Crop region
- `sindri image convert <file> --format webp` - Convert format
- `sindri image rotate <file> --angle 90 --expand` - Rotate
- `sindri image thumbnail <file> --size 128` - Create thumbnail
- `sindri image info <file>` - Get image metadata

**Agent Assignment:**
- Ratatoskr (fast executor) has access to all image tools

**Files:**
- `sindri/tools/images.py` - Image tools implementation
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added tools to Ratatoskr
- `sindri/cli.py` - CLI commands for image group
- `pyproject.toml` - Added Pillow>=10.0.0 dependency
- `tests/test_images.py` - Comprehensive test suite

**Tests:** 48 new tests (total: 2799 backend tests)

---

### System & Process Tools (2026-01-18) - Phase 12 Tier 1

Added comprehensive system monitoring and process management tools using psutil:

**New Tools (6 total):**
- `process_list` - List running processes with filtering by name/user, sorting by cpu/memory/pid/name
- `process_kill` - Kill process by PID or name with TERM/KILL/HUP signals
- `system_info` - Get system information (OS, CPU cores/freq/usage, memory, uptime)
- `disk_usage` - Check disk space for paths or all mounted partitions
- `memory_usage` - Check RAM and swap usage with human-readable output
- `env_get` - Get environment variables with regex filtering, option to hide values

**Features:**
- Cross-platform support via psutil (Linux, macOS, Windows)
- Human-readable output formatting (sizes, durations)
- Comprehensive filtering and sorting options
- Security-conscious options (hide env values, graceful process termination)

**Agent Assignment:**
- Ratatoskr (fast executor) has access to all system tools

**Files:**
- `sindri/tools/system.py` - System tools implementation
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added tools to Ratatoskr
- `pyproject.toml` - Added psutil dependency
- `tests/test_system.py` - Comprehensive test suite

**Tests:** 52 new tests (total: 2751 backend tests)

---

### Crypto & Encoding Tools (2026-01-18) - Phase 12 Tier 1

Added comprehensive crypto and encoding tools for security and data processing:

**New Tools (9 total):**
- `hash_file` - Calculate file hashes (MD5, SHA1, SHA256, SHA512, BLAKE2b, BLAKE2s)
- `hash_text` - Calculate text hashes with configurable encoding
- `encode_base64` - Base64 encode/decode with URL-safe variant
- `encode_url` - URL encode/decode with plus-mode for query strings
- `jwt_decode` - Decode JWT tokens (with optional verification)
- `jwt_generate` - Generate JWT tokens with expiration support
- `uuid_generate` - Generate UUIDs (v1, v4, v5 with namespaces)
- `encrypt_file` - Encrypt files with AES (Fernet) and password-based key derivation
- `decrypt_file` - Decrypt files encrypted with encrypt_file

**Hash Algorithms:**
- MD5, SHA1 (for checksums only)
- SHA256, SHA512 (cryptographic)
- BLAKE2b, BLAKE2s (fast, secure)

**JWT Features:**
- HS256, HS384, HS512 signing algorithms
- Unverified decode mode for inspection
- Automatic iat (issued-at) timestamp
- Configurable expiration time

**Encryption:**
- Fernet (AES-128-CBC with HMAC-SHA256)
- PBKDF2-SHA256 key derivation (480,000 iterations)
- Automatic salt generation

**Agent Assignment:**
- Ratatoskr (fast executor) has access to all crypto/encoding tools

**Files:**
- `sindri/tools/crypto.py` - Crypto tools implementation
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added tools to Ratatoskr
- `pyproject.toml` - Added PyJWT and cryptography dependencies
- `tests/test_crypto.py` - Comprehensive test suite

**Tests:** 52 new tests (total: 2699 backend tests)

---

### Test Suite Optimization (2026-01-18)

Removed 3 duplicate tests from `test_recovery_integration.py` that were already covered by `test_recovery.py`:

**Removed Tests:**
- `test_clear_checkpoint` - identical implementation existed in both files
- `test_list_recoverable_sessions` - less thorough version removed (comprehensive version kept in test_recovery.py)
- `test_checkpoint_atomic_write` - redundant atomic write test

**Impact:**
- Test count: 2650 → 2647
- No coverage regression (duplicate tests covered same code paths)
- All unique integration tests preserved in test_recovery_integration.py (11 tests remain)

**Analysis Conducted:**
- Reviewed all 70 test files (2,650+ tests)
- Identified literal duplicates vs. legitimate multi-level testing
- Language detection tests across files (docker/cicd/ide/etc) confirmed NOT duplicates - each tests different tool classes
- Parallel execution tests (unit vs integration) preserved - serve different purposes

---

### Compression & Archive Tools (2026-01-18) - Phase 12 Tier 1

Added comprehensive compression and archive tools for file management:

**New Tools (5 total):**
- `archive_create` - Create zip/tar/tar.gz/tar.bz2/tar.xz archives from files and directories
- `archive_extract` - Extract archives with format auto-detection
- `archive_list` - List archive contents with file sizes and dates
- `compress_file` - Compress single files (gzip, bz2, xz, brotli)
- `decompress_file` - Decompress files with format auto-detection

**Archive Formats:**
- ZIP (standard compression)
- TAR (uncompressed)
- TAR.GZ / TGZ (gzip compression)
- TAR.BZ2 / TBZ2 (bzip2 compression)
- TAR.XZ / TXZ (xz/lzma compression)

**Single-File Compression:**
- GZIP (.gz)
- BZIP2 (.bz2)
- XZ/LZMA (.xz)
- Brotli (.br) - optional dependency

**Features:**
- Exclude patterns for archive creation (e.g., `--exclude '*.pyc'`)
- Configurable compression levels (1-9)
- Format auto-detection from file extension or magic bytes
- No-overwrite mode for extraction
- Compression ratio reporting

**CLI Commands:**
- `sindri archive create <output> <paths...>` - Create archive
- `sindri archive extract <archive>` - Extract archive
- `sindri archive list <archive>` - List contents
- `sindri archive compress <file> -f <format>` - Compress file
- `sindri archive decompress <file>` - Decompress file

**Agent Assignment:**
- Ratatoskr (fast executor) has access to all compression tools

**Files:**
- `sindri/tools/compression.py` - Compression tools implementation
- `sindri/tools/registry.py` - Tool registration
- `sindri/agents/registry.py` - Added tools to Ratatoskr
- `sindri/cli.py` - CLI commands for archive group
- `tests/test_compression.py` - Comprehensive test suite

**Tests:** 40 new tests (total: 2650 backend tests)

---

### Text/Regex Processing Tools (2026-01-18) - Phase 12 Start

Added comprehensive text and regex processing tools with the Vör agent for pattern matching and text manipulation:

**New Agent:**
- **Vör** (Norse goddess of wisdom and attention to detail) - Regex and text processing specialist using qwen2.5-coder:7b

**New Tools (5 total):**
- `regex_generate` - Generate regex patterns from natural language descriptions
- `regex_explain` - Explain what a regex pattern matches in plain English
- `regex_test` - Test regex against sample text, show matches and groups
- `text_transform` - Apply transformations (case, naming conventions, replacements)
- `text_extract` - Extract all pattern matches from text with groups

**Supported Patterns:**
- Email addresses, URLs, phone numbers, IP addresses
- Dates (ISO, US), times (12h, 24h)
- UUIDs, hex colors, semantic versions
- Credit cards, SSNs, MAC addresses
- Custom patterns from examples or descriptions

**Text Transformations:**
- Case: upper, lower, title, capitalize, swapcase
- Naming: snake_case, camelCase, PascalCase, kebab-case, slugify
- Whitespace: strip, lstrip, rstrip, normalize_whitespace
- Pattern: replace, regex_replace, reverse, remove_punctuation

**Agent Delegation:**
- Brokkr can now delegate to Vör for regex/text processing tasks
- Vör has access to read_file, write_file, search_code, and all text/regex tools

**Files:**
- `sindri/tools/text_regex.py` - Text/regex tools implementation
- `sindri/agents/prompts.py` - VOR_PROMPT added
- `sindri/agents/registry.py` - Vör agent definition
- `sindri/tools/registry.py` - Tool registration
- `tests/test_text_regex.py` - Comprehensive test suite

**Tests:** 75 new tests (total: 2610 backend tests)

---

### Data Visualization System (2026-01-18) - Phase 11 Complete

Added comprehensive data visualization tools and the Saga agent for creating charts and dashboards:

**New Agent:**
- **Saga** (Norse goddess of history) - Data visualization specialist using qwen2.5-coder:7b

**Visualization Libraries Supported:**
- **D3.js** - Interactive browser visualizations with transitions and tooltips
- **matplotlib** - Python static charts with seaborn-style aesthetics
- **Plotly** - Interactive Python/JavaScript charts with 3D support

**Chart Types:**
- Bar, line, scatter, pie, histogram, heatmap
- Area charts, box plots, violin plots
- 3D scatter and surface plots (Plotly)
- Treemaps and sunburst charts

**New Tools (7 total):**
- `analyze_data` - Parse CSV/JSON, compute statistics (mean, std, correlation)
- `suggest_viz` - Recommend chart types based on data structure and goals
- `generate_d3` - Generate complete D3.js code with SVG, scales, axes, tooltips
- `generate_matplotlib` - Generate Python matplotlib code with styles
- `generate_plotly` - Generate Plotly code (Python or JavaScript)
- `create_dashboard` - Multi-chart layouts with grid positioning
- `export_interactive` - Bundle as standalone HTML with embedded data

**CLI Commands:**
- `sindri viz analyze <file>` - Analyze dataset structure and statistics
- `sindri viz suggest <file>` - Get visualization recommendations
- `sindri viz d3 <type> <file>` - Generate D3.js chart code
- `sindri viz matplotlib <type> <file>` - Generate matplotlib code
- `sindri viz plotly <type> <file>` - Generate Plotly code
- `sindri viz dashboard <file>` - Create multi-chart dashboard
- `sindri viz export <code>` - Export as standalone HTML

**Features:**
- Column type detection (numeric, categorical, datetime)
- Correlation matrix generation
- Goal-based suggestions (comparison, trend, distribution, relationship)
- Interactive tooltips and transitions in D3.js
- Multiple matplotlib styles (seaborn, ggplot, etc.)
- Plotly 3D chart support
- Responsive HTML export with CDN resources
- Dashboard grid layouts with configurable rows/columns

**Agent Delegation:**
- Brokkr can now delegate to Saga for data visualization tasks
- Saga has access to read_file, write_file, search_code, and all DataViz tools

**Files:**
- `sindri/tools/dataviz.py` - Data visualization tools implementation
- `sindri/agents/prompts.py` - SAGA_PROMPT added
- `sindri/agents/registry.py` - Saga agent definition
- `sindri/tools/registry.py` - Tool registration
- `sindri/cli.py` - CLI commands for viz group
- `tests/test_dataviz.py` - Comprehensive test suite

**Tests:** 60 new tests (total: 2535 backend tests)

---

### OpenSCAD 3D Modeling System (2026-01-18) - Phase 11 Continued

Added comprehensive OpenSCAD tools and the Völundr agent for parametric 3D model generation:

**New Agent:**
- **Völundr** (Norse master smith) - OpenSCAD specialist using qwen2.5-coder:7b

**Model Types Supported:**
- **Box with Lid** - Parametric containers with snap-fit or screw lids
- **Phone Stand** - Adjustable angle stands for devices
- **Gears** - Involute gear generation with configurable teeth
- **Electronics Enclosures** - Cases with screw posts and ventilation

**New Tools (6 total):**
- `generate_scad` - Generate OpenSCAD code from text descriptions
- `render_preview` - Render PNG or STL preview (requires OpenSCAD)
- `export_stl` - Export to STL for 3D printing with quality settings
- `validate_scad` - Check syntax, geometry issues, and best practices
- `parametrize_model` - Convert hardcoded values to parameters
- `optimize_printability` - Analyze and suggest print optimizations

**CLI Commands:**
- `sindri scad generate <description>` - Generate OpenSCAD model
- `sindri scad preview <file>` - Render to PNG/STL
- `sindri scad export <file>` - Export to STL for printing
- `sindri scad validate <file>` - Validate syntax and geometry
- `sindri scad parametrize <file>` - Add parameters to model
- `sindri scad optimize <file>` - Get printability suggestions

**Features:**
- Template-based generation for common model types
- FDM, SLA, and SLS printer support
- Wall thickness and overhang detection
- Tolerance suggestions for fits (press, sliding, loose)
- Quality presets: draft, normal, high, ultra
- Automatic syntax validation (braces, brackets, parentheses)

**Agent Delegation:**
- Brokkr can now delegate to Völundr for 3D modeling tasks
- Völundr has access to read_file, write_file, search_code, and all OpenSCAD tools

**Files:**
- `sindri/tools/openscad.py` - OpenSCAD tools implementation
- `sindri/agents/prompts.py` - VOLUNDR_PROMPT added
- `sindri/agents/registry.py` - Völundr agent definition
- `sindri/tools/registry.py` - Tool registration
- `sindri/cli.py` - CLI commands for scad group
- `tests/test_openscad.py` - Comprehensive test suite

**Tests:** 55 new tests (total: 2475 backend tests)

---

### LaTeX Generation System (2026-01-18) - Phase 11 Continued

Added comprehensive LaTeX generation tools and the Kvasir agent for academic documentation:

**New Agent:**
- **Kvasir** (Norse being of ultimate wisdom) - LaTeX specialist using llama3.1:8b

**Document Types Supported:**
- **Article** - Academic papers with IEEE, ACM, APA styles
- **Report** - Long documents with chapters and table of contents
- **Book** - Full-length books with front/back matter
- **Beamer** - Presentation slides with multiple themes

**New Tools (6 total):**
- `generate_latex` - Create complete LaTeX documents with custom structure
- `format_equations` - Convert math notation to LaTeX (Unicode, natural language)
- `generate_tikz` - TikZ diagrams (neural networks, graphs, flowcharts, plots)
- `manage_bibliography` - BibTeX management (create, add, validate, format)
- `create_beamer` - Generate Beamer presentations with themes
- `latex_to_pdf` - Compile LaTeX to PDF (requires texlive)

**CLI Commands:**
- `sindri latex document <title>` - Generate LaTeX document
- `sindri latex equation <expr>` - Format mathematical expression
- `sindri latex tikz <type>` - Generate TikZ diagram
- `sindri latex beamer <title>` - Generate Beamer presentation
- `sindri latex bib <action>` - Manage bibliographies
- `sindri latex compile <file>` - Compile LaTeX to PDF

**Features:**
- Unicode to LaTeX conversion (Greek letters, math symbols)
- Natural language math parsing ("integral from 0 to 1 of x dx")
- TikZ diagram types: neural networks, graphs, flowcharts, plots, timelines, Venn
- Multiple Beamer themes: Madrid, Berlin, Copenhagen, Warsaw
- Academic paper styles: IEEE, ACM, APA, plain

**Agent Delegation:**
- Brokkr can now delegate to Kvasir for LaTeX-related tasks
- Kvasir has access to read_file, write_file, search_code, and all LaTeX tools

**Files:**
- `sindri/tools/latex.py` - LaTeX generation tools implementation
- `sindri/agents/prompts.py` - KVASIR_PROMPT added
- `sindri/agents/registry.py` - Kvasir agent definition
- `sindri/tools/registry.py` - Tool registration
- `sindri/cli.py` - CLI commands for latex group
- `tests/test_latex.py` - Comprehensive test suite

**Tests:** 64 new tests (total: 2420 backend tests)

---

### Diagram Generation System (2026-01-18) - Phase 11 Start

Added comprehensive diagram generation tools and the Skuld agent for technical visualization:

**New Agent:**
- **Skuld** (Norn of the Future) - Diagram generation specialist using qwen2.5-coder:7b

**Diagram Formats Supported:**
- **Mermaid.js** - GitHub/GitLab/Notion compatible
- **PlantUML** - Enterprise standard, rich UML support
- **D2** - Modern aesthetics, auto-layout

**Diagram Types:**
- Sequence diagrams (API flows, service interactions)
- Class diagrams (OOP structures)
- ER diagrams (database schemas)
- Flowcharts (processes, decision trees)
- State diagrams (state machines)
- Architecture diagrams (system overview)
- Mind maps, Gantt charts

**New Tools (6 total):**
- `generate_mermaid` - Create Mermaid.js diagrams with all diagram types
- `generate_plantuml` - Create PlantUML diagrams (sequence, class, component, etc.)
- `generate_d2` - Create D2 diagrams with containers and shapes
- `diagram_from_code` - Extract diagrams from Python/JS/TS/Go/Rust code
- `generate_sequence_diagram` - Specialized sequence diagram generation
- `generate_er_diagram` - ER diagrams from SQLAlchemy/SQL files

**CLI Commands:**
- `sindri diagram mermaid <type>` - Generate Mermaid diagram
- `sindri diagram plantuml <type>` - Generate PlantUML diagram
- `sindri diagram d2` - Generate D2 diagram
- `sindri diagram from-code <path>` - Generate diagram from source code
- `sindri diagram sequence` - Generate sequence diagram with participants
- `sindri diagram er [source]` - Generate ER diagram from models/SQL

**Agent Delegation:**
- Brokkr can now delegate to Skuld for diagram generation tasks
- Skuld has access to read_file, write_file, search_code, and all diagram tools

**Files:**
- `sindri/tools/diagrams.py` - Diagram generation tools implementation
- `sindri/agents/prompts.py` - SKULD_PROMPT added
- `sindri/agents/registry.py` - Skuld agent definition
- `sindri/tools/registry.py` - Tool registration
- `sindri/cli.py` - CLI commands for diagram group
- `tests/test_diagrams.py` - Comprehensive test suite

**Tests:** 53 new tests (total: 2356 backend tests)

---

### API Keys System (2026-01-17)

Added comprehensive API key management for programmatic access and CI/CD integration:

**Key Features:**
- Secure key generation with `sk_` prefix (test keys use `sk_test_`)
- SHA-256 key hashing (only hash is stored, full key shown once at creation)
- Scope-based permissions with hierarchy (admin includes all, write includes read)
- Key expiration with configurable days until expiration
- Rate limiting (configurable requests per minute)
- Team-based key restrictions
- Usage tracking with IP, endpoint, and duration logging

**Scopes:**
- **Read**: read, read:sessions, read:agents, read:metrics
- **Write**: write, write:sessions, write:tasks (includes read)
- **Team**: team:read, team:write, team:admin
- **Webhooks**: webhooks, webhooks:manage
- **Admin**: Full access (all scopes)

**CLI Commands:**
- `sindri api-keys` - List API keys (filter by user/team)
- `sindri api-key-create <user_id> <name> --scope read --scope write` - Create key
- `sindri api-key-info <key_id>` - View key details
- `sindri api-key-stats <key_id>` - Usage statistics
- `sindri api-key-revoke <key_id>` - Revoke (can re-enable later)
- `sindri api-key-enable <key_id>` - Re-enable revoked key
- `sindri api-key-delete <key_id>` - Permanently delete
- `sindri api-key-global-stats` - Global statistics
- `sindri api-key-cleanup --days 90` - Clean up old keys

**API Endpoints:**
- `GET /api/api-keys` - List keys (filter by user/team)
- `POST /api/api-keys` - Create key (returns full key once)
- `GET /api/api-keys/{id}` - Get key details
- `PATCH /api/api-keys/{id}` - Update key settings
- `POST /api/api-keys/{id}/revoke` - Revoke key
- `POST /api/api-keys/{id}/enable` - Re-enable key
- `DELETE /api/api-keys/{id}` - Delete key
- `GET /api/api-keys/{id}/stats` - Get usage statistics
- `GET /api/api-key/stats` - Global statistics
- `POST /api/api-key/verify` - Verify key (X-API-Key header)
- `DELETE /api/api-key/cleanup` - Clean up old keys

**Files:**
- `sindri/collaboration/api_keys.py` - API keys system implementation
- Updated `sindri/collaboration/__init__.py` - Module exports
- Updated `sindri/cli.py` - CLI commands
- Updated `sindri/web/server.py` - API endpoints

**Tests:** 62 new tests (total: 2303 backend tests)

---

### Audit Log System (2026-01-17)

Added comprehensive audit logging system for security and compliance tracking:

**Audit Categories:**
- **Authentication**: login_success, login_failed, logout, password_changed, token_generated, session_expired
- **Authorization**: permission_granted, permission_revoked, role_assigned, role_removed, access_denied
- **Data Access**: session_viewed, session_exported, data_downloaded, search_performed, report_generated
- **Data Modification**: user/team/session CRUD, comment/share operations, webhook management
- **Administrative**: settings_changed, backup operations, maintenance events
- **Security**: suspicious_activity, brute_force_detected, rate_limit_exceeded, invalid_token

**Audit Features:**
- Severity levels: info, warning, error, critical
- Outcome tracking: success, failure, partial, unknown
- Actor/target tracking with type and ID
- IP address and user agent logging
- Metadata storage for structured context
- Team and session association
- Request correlation IDs
- Duration tracking for operations

**Security Features:**
- `is_security_event` property for quick security filtering
- `is_compliance_relevant` property for compliance reporting
- Brute force detection with configurable thresholds
- Failed login tracking by IP and username
- Security event retention during cleanup

**Query Capabilities:**
- Filter by category, action, severity, outcome
- Filter by actor, target, team, IP address
- Date range filtering
- Search text in details/metadata
- Security-only and compliance-only filters
- Pagination support (limit/offset)

**Export Formats:**
- JSON export with full audit data
- CSV export for spreadsheet analysis

**CLI Commands:**
- `sindri audit` - View recent audit events with filters
- `sindri audit --security` - Show only security events
- `sindri audit --compliance` - Show only compliance-relevant events
- `sindri audit --category authentication` - Filter by category
- `sindri audit --actor user123` - Filter by actor
- `sindri audit-stats` - View audit statistics
- `sindri audit-stats --days 30` - Stats for specific period
- `sindri audit-security` - Shortcut for security events
- `sindri audit-export -o audit.json` - Export to JSON
- `sindri audit-export -f csv -o audit.csv` - Export to CSV
- `sindri audit-export --compliance` - Export compliance events
- `sindri audit-cleanup` - Clean up old entries (preserves security events)
- `sindri audit-cleanup --days 60` - Custom retention period
- `sindri audit-failed-logins` - View failed login attempts
- `sindri audit-failed-logins --ip 192.168.1.1` - Filter by IP

**Convenience Functions:**
- `audit_login_success()` - Log successful login
- `audit_login_failed()` - Log failed login attempt
- `audit_logout()` - Log user logout
- `audit_permission_change()` - Log permission grant/revoke
- `audit_role_change()` - Log role changes
- `audit_session_access()` - Log session view/export
- `audit_access_denied()` - Log denied access attempts
- `audit_suspicious_activity()` - Log suspicious behavior
- `audit_brute_force_detected()` - Log brute force detection
- `check_brute_force()` - Check if IP is potentially brute forcing

**Files:**
- `sindri/collaboration/audit.py` - Audit log system implementation
- Updated `sindri/collaboration/__init__.py` - Module exports
- Updated `sindri/cli.py` - CLI commands

**Tests:** 52 new tests (total: 2241 backend tests)

---

### Database Migration Tools (2026-01-17)

Added comprehensive database migration management tools with multi-framework support:

**Supported Frameworks:**
- **Python**: Alembic (SQLAlchemy), Django
- **Node.js**: Prisma, Knex, Sequelize
- **Go**: Goose, Atlas
- **Rust**: Diesel, SeaORM

**Migration Tools (`sindri/tools/migrations.py`):**
- `generate_migration` - Generate new migration files with SQL content
- `migration_status` - Check pending/applied migrations
- `run_migrations` - Apply pending migrations to database
- `rollback_migration` - Rollback to previous migration state
- `validate_migrations` - Check migration consistency and issues

**Auto-Detection Features:**
- Automatically detects framework from project files
- Supports pyproject.toml, package.json, go.mod, Cargo.toml
- Detects configuration files (alembic.ini, knexfile.js, etc.)
- Falls back to manual framework specification

**Migration Generation:**
- Framework-specific templates for each supported ORM
- Timestamp-based naming for unique identifiers
- Support for custom SQL up/down migrations
- Auto-generation from model changes (Alembic, Prisma, Django)
- Dry-run mode for previewing without creating files

**Validation Features:**
- Checks for required migration components
- Warns about missing down/rollback migrations
- Validates migration file structure
- Reports counts and statistics

**CLI Commands:**
- `sindri migrate` - Run pending migrations
- `sindri migrate --dry-run` - Preview SQL without applying
- `sindri migrate --framework alembic --target head` - Target specific revision
- `sindri migrate-status` - Show migration status
- `sindri migrate-status --verbose` - Detailed status
- `sindri migrate-generate <name>` - Create new migration
- `sindri migrate-generate <name> --auto` - Auto-generate from models
- `sindri migrate-generate <name> --sql "..."` - Include custom SQL
- `sindri migrate-rollback` - Rollback last migration
- `sindri migrate-rollback --steps 3` - Rollback multiple
- `sindri migrate-validate` - Validate all migrations

**Files:**
- `sindri/tools/migrations.py` - Migration tools implementation
- Updated `sindri/tools/registry.py` - Tool registration
- Updated `sindri/cli.py` - CLI commands

**Tests:** 65 new tests (total: 2189 backend tests)

---

### Webhooks System (2026-01-17)

Added comprehensive webhook system for external integrations:

**Webhook Event Types (`sindri/collaboration/webhooks.py`):**
- **Session Events**: session.created, session.completed, session.failed, session.resumed
- **Task Events**: task.started, task.completed, task.delegated
- **Team Events**: team.member_joined, team.member_left, team.role_changed, team.settings_changed
- **Comment Events**: comment.added, comment.resolved
- **Share Events**: session.shared, session.share_revoked
- **Notification Events**: notification.created
- **Activity Events**: activity.logged
- **Wildcard**: `*` - receive all events

**Payload Formats:**
- **Generic**: Standard JSON with event, timestamp, team_id, and data
- **Slack**: Slack-compatible blocks format with rich formatting
- **Discord**: Discord embeds with color coding by event type

**Webhook Features:**
- HMAC-SHA256 signature verification for security
- Configurable retry count (default: 3) with exponential backoff
- Configurable timeout (default: 30s)
- Custom headers support
- Event filtering per webhook
- Enable/disable webhooks without deletion
- Secret regeneration

**Delivery Features:**
- Async HTTP delivery with aiohttp
- Delivery status tracking: pending, success, failed, retrying
- Retry delays: 1 min, 5 min, 15 min
- Delivery history with response logging
- Automatic cleanup of old delivery records

**CLI Commands:**
- `sindri webhooks <team_id>` - List webhooks for team
- `sindri webhook-create <team_id> <name> <url>` - Create webhook
- `sindri webhook-create ... --format slack --event session.completed` - Customize
- `sindri webhook-info <id>` - View webhook details
- `sindri webhook-update <id> --enable/--disable` - Enable/disable
- `sindri webhook-delete <id>` - Delete webhook
- `sindri webhook-regenerate-secret <id>` - Regenerate secret
- `sindri webhook-deliveries <id>` - View delivery history
- `sindri webhook-test <id>` - Send test event
- `sindri webhook-stats` - View statistics
- `sindri webhook-cleanup` - Delete old delivery records

**API Endpoints:**
- `GET /api/teams/{team_id}/webhooks` - List team webhooks
- `POST /api/webhooks` - Create webhook
- `GET /api/webhooks/{id}` - Get webhook details
- `PATCH /api/webhooks/{id}` - Update webhook
- `DELETE /api/webhooks/{id}` - Delete webhook
- `POST /api/webhooks/{id}/regenerate-secret` - Regenerate secret
- `GET /api/webhooks/{id}/deliveries` - List deliveries
- `POST /api/webhooks/{id}/test` - Send test event
- `POST /api/webhooks/{id}/trigger` - Manual trigger with custom data
- `GET /api/webhook/stats` - Get statistics
- `DELETE /api/webhook/cleanup` - Clean up old deliveries

**Files:**
- `sindri/collaboration/webhooks.py` - Webhook system
- Updated `sindri/collaboration/__init__.py` - Module exports
- Updated `sindri/cli.py` - CLI commands
- Updated `sindri/web/server.py` - API endpoints

**Tests:** 57 new tests (total: 2124 backend tests)

---

### Activity Feed System (2026-01-17)

Added comprehensive activity feed for team collaboration timeline:

**Activity Types (`sindri/collaboration/activity.py`):**
- **Session Activities**: session_created, session_completed, session_failed, session_resumed
- **Task Activities**: task_started, task_completed, task_delegated
- **Comment Activities**: comment_added, comment_resolved, comment_replied
- **Member Activities**: member_joined, member_left, member_role_changed, member_invited
- **Sharing Activities**: session_shared, share_revoked
- **Team Activities**: team_created, team_updated, team_settings_changed

**Activity Feed Features:**
- Target types: session, task, user, team, comment, share
- Metadata storage for rich activity context
- Query by team, user, or target
- Date range filtering (start_date, end_date)
- Pagination support (limit, offset)
- Activity statistics per team or global
- Automatic cleanup of old activities

**Convenience Functions:**
- `log_session_created()` - Log session creation
- `log_session_completed()` - Log session completion with duration
- `log_session_failed()` - Log session failure with error
- `log_member_joined()` - Log member join (self or invited)
- `log_member_left()` - Log member leave or removal
- `log_role_changed()` - Log role changes
- `log_comment_added()` - Log comment with preview
- `log_session_shared()` - Log session sharing
- `log_team_updated()` - Log team settings changes

**CLI Commands:**
- `sindri activity <team_id>` - List team activities
- `sindri activity <team_id> --limit 50` - Paginate results
- `sindri activity <team_id> --type session_created` - Filter by type
- `sindri activity <team_id> --user <user_id>` - Filter by actor
- `sindri activity-stats` - Global activity statistics
- `sindri activity-stats --team <team_id>` - Team-specific stats
- `sindri activity-cleanup --days 90` - Delete old activities
- `sindri activity-cleanup --dry-run` - Preview cleanup

**API Endpoints:**
- `GET /api/teams/{team_id}/activities` - List team activities
- `GET /api/activities/{activity_id}` - Get specific activity
- `POST /api/activities` - Create activity
- `GET /api/users/{user_id}/activities` - List user activities
- `GET /api/activity/stats` - Get activity statistics
- `DELETE /api/activity/cleanup` - Clean up old activities

**Files:**
- `sindri/collaboration/activity.py` - Activity feed system
- Updated `sindri/collaboration/__init__.py` - Module exports
- Updated `sindri/cli.py` - CLI commands
- Updated `sindri/web/server.py` - API endpoints

**Tests:** 56 new tests (total: 2067 backend tests)

---

### Notification System (2026-01-17)

Added comprehensive notification system for team collaboration:

**Notification Types (`sindri/collaboration/notifications.py`):**
- **MENTION**: User was @mentioned in a comment
- **COMMENT**: New comment on user's session
- **COMMENT_REPLY**: Reply to user's comment
- **TEAM_INVITE**: Invited to join a team
- **TEAM_JOINED**: Someone joined user's team
- **TEAM_LEFT**: Someone left user's team
- **TEAM_ROLE_CHANGED**: User's role in team changed
- **SESSION_SHARED**: Session was shared with user
- **SESSION_ACTIVITY**: Activity on followed session

**Notification Features:**
- Priority levels: low, normal, high, urgent
- Read/unread status tracking with timestamps
- Archive functionality for old notifications
- Automatic cleanup of old read notifications
- Source tracking (user, team, session, comment IDs)

**User Preferences:**
- Global enable/disable for all notifications
- Per-type notification control (mentions, comments, team events, session events)
- Quiet hours configuration (e.g., 22:00 - 07:00)
- Quiet hours can span midnight

**Convenience Functions:**
- `notify_mention()` - Create mention notification
- `notify_comment()` - Create comment notification
- `notify_team_invite()` - Create team invite notification
- `notify_session_shared()` - Create session shared notification

**CLI Commands:**
- `sindri notifications <user_id>` - List notifications
- `sindri notifications <user_id> --unread` - Show only unread
- `sindri notifications <user_id> --type mention` - Filter by type
- `sindri notification-read <id>` - Mark notification as read
- `sindri notification-read-all <user_id>` - Mark all as read
- `sindri notification-prefs <user_id>` - View preferences
- `sindri notification-prefs <user_id> --no-mentions` - Update preferences
- `sindri notification-prefs <user_id> --quiet-start 22 --quiet-end 7` - Set quiet hours
- `sindri notification-stats` - Global statistics
- `sindri notification-stats --user <user_id>` - User statistics

**Files:**
- `sindri/collaboration/notifications.py` - Notification system
- Updated `sindri/collaboration/__init__.py` - Module exports
- Updated `sindri/cli.py` - CLI commands

**Tests:** 56 new tests (total: 2011 backend tests)

---

### Team Mode (2026-01-17)

Added multi-user collaboration with team management and role-based permissions:

**User Management (`sindri/collaboration/users.py`):**
- User accounts with secure password hashing (PBKDF2-SHA256)
- Authentication with username/password
- User profiles with display names and preferences
- Account activation/deactivation
- User search by username, email, or display name

**Team Management (`sindri/collaboration/teams.py`):**
- Create and manage teams with owners
- Invite codes for easy team joining
- Role-based access control with 4 roles:
  - **Owner**: Full control including team deletion
  - **Admin**: Manage team settings and members
  - **Member**: Create and run sessions
  - **Viewer**: Read-only access to team sessions
- Role hierarchy with permission inheritance
- Ownership transfer between members

**Team Sessions:**
- Associate sessions with teams
- Shared sessions visible to all team members
- Private sessions only visible to creator
- Session access control based on membership

**Permission Checking:**
- `can_user_access_session()` - Check session access
- `get_user_role()` - Get user's team role
- Role-based permission properties (can_view, can_create_sessions, etc.)

**Statistics:**
- Per-team statistics (members by role, session count)
- Global statistics (total teams, memberships, sessions)

**Files:**
- `sindri/collaboration/users.py` - User management
- `sindri/collaboration/teams.py` - Team management and permissions
- Updated `sindri/collaboration/__init__.py` - Module exports

**Tests:** 84 new tests (total: 1955 backend tests)

---

### Fine-Tuning Pipeline (2026-01-17)

Added complete fine-tuning pipeline for training local LLMs based on session feedback:

**Data Curation (`sindri/finetuning/curator.py`):**
- Filters sessions by rating, turn count, error status
- Deduplicates similar conversations using content hashing
- Balances training data across task categories
- Computes quality scores based on ratings, tags, and completion status
- Task classification: code generation, bug fix, refactoring, testing, documentation, explanation, debugging, review

**Model Registry (`sindri/finetuning/registry.py`):**
- Track fine-tuned models with metadata
- Version management (auto-increment per model name)
- Training parameters storage (base model, context length, temperature, quantization)
- Training metrics tracking (sessions used, tokens trained, training time)
- Model status lifecycle: training → ready → active → archived

**Training Orchestrator (`sindri/finetuning/trainer.py`):**
- End-to-end training workflow
- Automatic data curation and export
- Ollama Modelfile generation
- Direct integration with `ollama create`
- Progress callbacks for UI integration
- Dry-run mode for previewing training data

**Model Evaluation (`sindri/finetuning/evaluator.py`):**
- Benchmark suites with test prompts
- Pattern matching for quality assessment
- Response time measurement
- Model comparison (A/B testing)
- Improvement tracking (before/after fine-tuning)

**CLI Commands:**
- `sindri finetune prepare` - Analyze and prepare training data
- `sindri finetune train` - Start model fine-tuning
- `sindri finetune models` - List fine-tuned models
- `sindri finetune evaluate <model>` - Benchmark model performance
- `sindri finetune compare <a> <b>` - Compare two models
- `sindri finetune deploy <id>` - Set model as active
- `sindri finetune stats` - View pipeline statistics
- `sindri finetune info <id>` - Show model details
- `sindri finetune delete <id>` - Archive a model

**Example Workflow:**
```bash
# 1. Collect feedback on sessions (existing command)
sindri feedback <session-id> 5 --tag correct --tag efficient

# 2. View available training data
sindri finetune stats

# 3. Prepare and preview training data
sindri finetune prepare --min-rating 4

# 4. Train a custom model
sindri finetune train --base-model qwen2.5-coder:7b --name my-coder

# 5. Evaluate the model
sindri finetune evaluate my-coder

# 6. Compare with base model
sindri finetune compare qwen2.5-coder:7b my-coder

# 7. Deploy if satisfied
sindri finetune deploy 1
```

**Files:**
- `sindri/finetuning/` - New module
  - `__init__.py` - Module exports
  - `curator.py` - Data curation and quality scoring
  - `registry.py` - Model registry with SQLite persistence
  - `trainer.py` - Training orchestrator with Ollama integration
  - `evaluator.py` - Model evaluation and comparison

**Tests:** 72 new tests (total: 1871 backend tests)

---

### IDE Integration (2026-01-17)

Added IDE integration with JSON-RPC server and Neovim plugin for editor-based code assistance:

**IDE Server (`sindri ide`):**
- JSON-RPC 2.0 protocol over stdio (LSP-style)
- Task execution from editor context
- Code explanation, fix suggestions, test generation
- Code refactoring with LLM assistance
- File analysis and symbol search
- Agent info and session management

**Protocol Features:**
- Full request/response lifecycle
- Streaming token notifications
- Task progress notifications
- Document sync notifications

**Neovim Plugin (`sindri/ide/nvim/`):**
- Lua plugin with full JSON-RPC client
- Commands: `:Sindri`, `:SindriRun`, `:SindriExplain`, `:SindriFix`, `:SindriTests`
- Visual selection support for code operations
- Floating window UI for results
- Loading indicators with progress bars
- Configurable keymaps (default: `<leader>s*`)

**Supported Operations:**
- `sindri/executeTask` - Run tasks with editor context
- `sindri/explainCode` - Explain selected code
- `sindri/suggestFix` - Suggest fixes for errors
- `sindri/generateTests` - Generate unit tests
- `sindri/refactorCode` - Refactor with various patterns
- `sindri/analyzeFile` - Analyze file structure
- `sindri/listAgents` - List available agents
- `sindri/listSessions` - List past sessions

**CLI Commands:**
- `sindri ide` - Start IDE server (stdio mode, default)
- `sindri ide --mode http` - HTTP mode (planned)
- `sindri ide-status` - Check IDE integration status

**Files:**
- `sindri/ide/` - IDE integration module
  - `protocol.py` - JSON-RPC protocol definitions
  - `server.py` - IDE server implementation
- `sindri/ide/nvim/` - Neovim plugin
  - `lua/sindri/init.lua` - Main plugin module
  - `lua/sindri/client.lua` - JSON-RPC client
  - `lua/sindri/ui.lua` - Floating windows and UI

**Installation (Neovim):**
```lua
-- Using lazy.nvim
{ dir = "~/projects/sindri/sindri/ide/nvim" }

-- Or copy to your Neovim config
cp -r sindri/ide/nvim/lua/sindri ~/.config/nvim/lua/
```

**Tests:** 56 new tests (total: 1799 backend tests)

---

### Infrastructure as Code Generation (2026-01-17)

Added Terraform and Pulumi generation for multi-cloud infrastructure:

**Supported Cloud Providers:**
- AWS (ECS, Lambda, EKS, EC2, RDS, ElastiCache, SQS, S3, CloudFront, ALB)
- GCP (Cloud Run, Cloud SQL, Memorystore, Cloud Storage)
- Azure (Container Apps, PostgreSQL Flexible Server, Redis Cache, Storage)

**Terraform Generation (`sindri terraform`):**
- Auto-detects project type (Python, Node.js, Rust, Go)
- Detects infrastructure needs from dependencies (database, cache)
- Multiple compute types: container, vm, serverless, kubernetes
- Environment-aware (dev uses FARGATE_SPOT, prod uses FARGATE)
- Generates complete configurations: main.tf, variables.tf, outputs.tf, providers.tf
- VPC module integration for AWS
- Multi-stage resource configuration

**Pulumi Generation (`sindri pulumi`):**
- Python and TypeScript language support
- AWS and GCP provider support
- Generates Pulumi.yaml, requirements.txt/package.json
- Infrastructure-as-code with type safety

**Terraform Validation (`sindri validate-terraform`):**
- Syntax validation (brace matching)
- Sensitive variable detection (password, secret, token, key)
- Required providers suggestions
- Variable description recommendations

**CLI Commands:**
- `sindri terraform` - Generate Terraform for AWS/GCP/Azure
- `sindri terraform --provider gcp --database postgres --cache redis`
- `sindri terraform --compute serverless --dry-run`
- `sindri pulumi` - Generate Pulumi Python code
- `sindri pulumi --language typescript --provider aws`
- `sindri validate-terraform` - Validate Terraform files

**Files:**
- `sindri/tools/iac.py` - GenerateTerraformTool, GeneratePulumiTool, ValidateTerraformTool
- `tests/test_iac.py` - 73 comprehensive tests

**Tests:** 73 new tests (total: 1743 backend tests)

---

### Coverage Visualization (2026-01-17)

Added code coverage visualization to the Web UI with support for multiple coverage formats:

**Coverage Formats Supported:**
- Cobertura XML (coverage.xml from pytest-cov, Istanbul)
- LCOV (lcov.info from gcov, Istanbul)
- JSON (coverage.json from coverage.py)

**Features:**
- Parse and store coverage data per session
- Overall coverage stats (line rate, branch rate, files count)
- Package/directory breakdown with expandable sections
- File-level detail with covered/uncovered line numbers
- Sort by coverage (lowest first), name, or size
- Filter to show only low coverage files (<50%)
- Color-coded coverage indicators (green >80%, yellow 50-80%, red <50%)

**API Endpoints:**
- `GET /api/sessions/{id}/coverage` - Get coverage summary
- `GET /api/sessions/{id}/coverage/detail` - Get detailed breakdown
- `POST /api/sessions/{id}/coverage` - Import coverage from file
- `DELETE /api/sessions/{id}/coverage` - Delete coverage
- `GET /api/coverage` - List all coverage reports
- `GET /api/coverage/stats` - Get aggregate statistics

**Web UI Integration:**
- New "Coverage" tab in Session Detail view
- Shows coverage percentage in tab label when available
- Interactive package/file tree with expand/collapse
- Coverage bars for visual progress indication

**Files:**
- `sindri/persistence/coverage.py` - Parser and storage (CoverageParser, CoverageStore)
- `sindri/web/server.py` - API endpoints
- `sindri/web/static/src/components/CoverageViewer.tsx` - React component
- `sindri/web/static/src/hooks/useApi.ts` - Coverage hooks
- `sindri/web/static/src/api/client.ts` - API client functions
- `sindri/web/static/src/types/api.ts` - TypeScript types

**Tests:** 40 new tests in test_coverage.py

---

### AST-Based Refactoring with Tree-sitter (2026-01-17)

Added precise multi-language code analysis and refactoring using tree-sitter parsers:

**Supported Languages:**
- Python (.py, .pyi)
- JavaScript (.js, .jsx)
- TypeScript (.ts, .tsx)
- Rust (.rs)
- Go (.go)

**New Tools:**
- `parse_ast` - Parse source code into AST structure with node types, names, and positions
- `find_references` - Find all references to a symbol across files using AST (more accurate than grep)
- `symbol_info` - Get detailed info about a symbol (type, scope, docstring, parameters)
- `ast_rename` - Precise symbol renaming using AST (only renames code references, not strings/comments)

**Key Features:**
- More accurate than regex-based refactoring
- Extracts docstrings, function parameters, return types
- Skips excluded directories (node_modules, __pycache__, .git, etc.)
- Supports dry-run mode for previewing changes
- Full AST JSON output for code analysis

**Installation:**
```bash
pip install -e ".[ast]"  # Install tree-sitter dependencies
```

**Usage Examples:**
```python
# Parse a file's AST
parse_ast(file_path="src/main.py")

# Find all references to a function
find_references(symbol_name="calculate_total", path="src/")

# Get detailed info about a symbol
symbol_info(file_path="utils.py", symbol_name="helper_func")

# Rename a symbol precisely
ast_rename(old_name="old_func", new_name="new_func", dry_run=True)
```

**Files:** `sindri/tools/ast_refactoring.py`
**Tests:** 55 new tests in test_ast_refactoring.py
**Dependencies:** tree-sitter, tree-sitter-python, tree-sitter-javascript, tree-sitter-typescript, tree-sitter-rust, tree-sitter-go

---

### CI/CD Fix - Linting, Formatting, and Dependencies (2026-01-17)

Fixed GitHub Actions CI/CD pipeline issues (lint step now passes):

**Linting & Formatting:**
- Fixed ~2800 ruff linting errors across the codebase
- Applied black formatting to 133+ files
- Added TYPE_CHECKING imports for forward references in type hints
- Replaced try/import patterns with `importlib.util.find_spec` for availability checks
- Renamed ambiguous variable names (`l` → `line`, `ln`)
- Fixed import shadowing issues

**CI Dependencies Added:**
- `pytest-cov` to dev dependencies (required for `--cov` flag)
- `pytest-mock` to dev dependencies (for mocker fixture)
- Pytest configuration in pyproject.toml

**CI Configuration Changes:**
- Removed Python 3.13 from test matrix (faster-whisper/ctranslate2 lacks wheels)
- Removed voice extras from CI (tests mock voice dependencies)

**Files Modified:**
- `pyproject.toml` - Added pytest-cov, pytest-mock, pytest config
- `.github/workflows/ci.yml` - Simplified dependencies, removed Python 3.13
- 133+ source files for formatting/linting fixes

**Local Tests:** All 1575 tests pass (100%)
**CI Status:** Lint step passes; test step still failing - requires viewing CI logs

**For Next Agent:**
If CI tests still fail, check the GitHub Actions logs for the actual error message.
The tests pass locally on Python 3.13; issue is specific to CI environment (Python 3.11/3.12).

Sources:
- [faster-whisper Python 3.13 incompatibility](https://github.com/SYSTRAN/faster-whisper/issues/1231)

### API Spec Generator (2026-01-17)

Added automatic OpenAPI 3.0 specification generation from route definitions:

**Framework Detection:**
- Auto-detects Python (Flask, FastAPI, Django), JavaScript/TypeScript (Express.js), Go (Gin, Echo), and Rust (Actix)
- Detection from package files (pyproject.toml, package.json, go.mod, Cargo.toml)
- Source code scanning for framework imports

**Route Extraction:**
- Flask: @app.route, Blueprint routes, method lists
- FastAPI: @app.get/post/etc., APIRouter decorators
- Django: urlpatterns, path(), re_path()
- Express: app.get/post/etc., router methods
- Gin/Echo: Go HTTP method handlers

**OpenAPI Generation:**
- Generates valid OpenAPI 3.0.3 specification
- Path parameter extraction with type inference
- Automatic request body for POST/PUT/PATCH methods
- Multiple output formats (JSON, YAML)
- Custom title, version, description, and servers

**Validation:**
- `validate_api_spec` tool checks for required fields
- Validates HTTP methods and status codes
- Warns about undefined path parameters
- Checks for common issues

**CLI Commands:**
- `sindri api-spec` - Generate OpenAPI spec from routes
- `sindri api-spec --path src/api --format yaml` - Custom path and format
- `sindri api-spec --dry-run` - Preview without writing
- `sindri validate-api-spec openapi.json` - Validate existing spec

**Files:** `sindri/tools/api_spec.py`
**Tests:** 62 new tests in test_api_spec.py

### Docker Generator (2026-01-17)

Added automatic Dockerfile and docker-compose.yml generation for projects:

**Dockerfile Generation:**
- `generate_dockerfile` tool - Auto-detect project type and generate optimized Dockerfile
- Supports Python (pip/poetry), Node.js (npm/yarn/pnpm), Rust, and Go projects
- Multi-stage builds for compiled languages (Rust, Go)
- Alpine-based images option for smaller sizes
- Automatic framework detection (Flask, FastAPI, Django, Next.js, Express)

**Docker Compose Generation:**
- `generate_docker_compose` tool - Generate docker-compose.yml with services
- Supports services: postgres, mysql, mongodb, redis, rabbitmq, kafka, elasticsearch, nginx
- Automatic environment variable configuration
- Production-ready configurations with restart policies
- Persistent volume mounting for data services

**Dockerfile Validation:**
- `validate_dockerfile` tool - Check for common issues and best practices
- Validates FROM instruction, WORKDIR, USER, EXPOSE, HEALTHCHECK
- Detects :latest tag usage, missing cleanup commands
- Suggests pip --no-cache-dir, COPY vs ADD best practices

**Files:** `sindri/tools/docker.py`
**Tests:** 64 new tests in test_docker.py

### Dependency Scanner (2026-01-17)

Added security vulnerability scanning for project dependencies:

**Supported Ecosystems:**
- Python: pip-audit (or safety as fallback)
- Node.js: npm audit
- Rust: cargo audit
- Go: govulncheck

**Scanning Features:**
- `sindri scan` - Scan for vulnerabilities
- `sindri scan --severity high` - Filter by minimum severity
- `sindri scan --format json` - Output as JSON
- `sindri scan --format sarif` - Output as SARIF (GitHub Security)
- `sindri scan --fix` - Attempt automatic fixes
- `sindri scan --outdated` - Also check for outdated packages

**SBOM Generation:**
- `sindri sbom` - Generate Software Bill of Materials
- `sindri sbom --format cyclonedx` - CycloneDX format (default)
- `sindri sbom --format spdx` - SPDX format
- `sindri sbom --output sbom.json` - Save to file

**Additional Commands:**
- `sindri outdated` - Check for outdated packages only
- `sindri security-status` - Check scanner availability

**Tools Added:**
- `scan_dependencies` - Vulnerability scanning tool
- `generate_sbom` - SBOM generation tool
- `check_outdated` - Outdated package detection tool

**Files:** `sindri/tools/dependency_scanner.py`
**Tests:** 58 new tests in test_dependency_scanner.py

### Voice Interface (2026-01-17)

Added speech-to-text and text-to-speech for hands-free interaction:

**Speech-to-Text (Whisper):**
- Local Whisper inference via faster-whisper
- Multiple model sizes: tiny, base, small, medium, large
- Streaming transcription support
- Voice activity detection

**Text-to-Speech:**
- Multiple engine support: pyttsx3, piper, espeak
- Voice customization (rate, pitch, volume)
- Audio output or file synthesis

**Voice Commands:**
- `sindri voice` - Start voice-controlled interface
- `sindri voice --mode wake_word` - Wake word activation
- `sindri say "text"` - Speak text via TTS
- `sindri transcribe audio.wav` - Transcribe audio file
- `sindri voice-status` - Check voice dependencies

**Voice Modes:**
- Push-to-talk: Press Enter to listen
- Wake word: "Hey Sindri" activation
- Continuous: Always listening

**Files:** `sindri/voice/` module (stt.py, tts.py, interface.py)
**Tests:** 56 new tests in test_voice.py

### Plugin Marketplace (2026-01-17)

Added plugin marketplace for discovering, installing, and managing plugins from various sources:

**Installation Sources:**
- Local file paths: `sindri marketplace install /path/to/plugin.py`
- GitHub shorthand: `sindri marketplace install user/repo`
- Git repositories: `sindri marketplace install https://github.com/user/repo.git --ref v1.0.0`
- Direct URLs: `sindri marketplace install https://example.com/plugin.py`

**Marketplace Commands:**
- `sindri marketplace search <query>` - Search plugins by name, description, tags
- `sindri marketplace install <source>` - Install from various sources
- `sindri marketplace uninstall <name>` - Remove installed plugin
- `sindri marketplace update [name]` - Update plugins to latest version
- `sindri marketplace info <name>` - Show detailed plugin information
- `sindri marketplace pin <name>` - Pin plugin to prevent auto-updates
- `sindri marketplace enable <name>` - Enable/disable plugins
- `sindri marketplace stats` - Show marketplace statistics
- `sindri marketplace categories` - List available plugin categories

**Plugin Categories:**
- Tools: filesystem, git, http, database, testing, formatting, refactoring, analysis, security, devops, documentation
- Agents: coder, reviewer, planner, specialist

**Files:** `sindri/marketplace/` module (metadata.py, index.py, installer.py, search.py)
**Tests:** 51 new tests in test_marketplace.py

### Remote Collaboration (2026-01-17)

Added session sharing, real-time presence, and code review comments:

**Session Sharing:**
- `sindri share <session_id>` - Create share link with permissions (read/comment/write)
- `sindri share-list <session_id>` - List shares for a session
- `sindri share-revoke <id>` - Revoke a share link
- Expiration support (time-based) and usage limits

**Review Comments:**
- `sindri comment <session_id> <content>` - Add comment
- `sindri comment-list <session_id>` - List comments
- `sindri comment-resolve <id>` - Resolve a comment
- Comment types: comment, suggestion, question, issue, praise, note
- Session-level, turn-level, and line-specific comments

**Real-time Presence:**
- Participant tracking with status (viewing, active, idle, typing)
- Cursor position tracking
- Color assignment for visual distinction

**Files:** `sindri/collaboration/` module (sharing.py, comments.py, presence.py)
**Tests:** 65 new tests in test_collaboration.py

### Agent Fine-Tuning Infrastructure (2026-01-17)

Feedback collection and training data export for fine-tuning local LLMs:

- `sindri feedback <session_id> <rating>` - Rate sessions 1-5 stars with quality tags
- `sindri feedback-stats` - View feedback statistics
- `sindri export-training <output>` - Export to JSONL, ChatML, or Ollama format

**Files:** `sindri/persistence/feedback.py`, `sindri/persistence/training_export.py`
**Tests:** 36 new tests in test_feedback.py

### CI/CD Integration (2026-01-17)

GitHub Actions workflow generation and validation:

- `generate_workflow` tool - Auto-detect project type, generate test/lint/build/deploy workflows
- `validate_workflow` tool - YAML validation, deprecated action detection
- Matrix testing support, Codecov integration, dependency caching

**Files:** `sindri/tools/cicd.py`
**Tests:** 63 new tests in test_cicd.py

---

## Project Summary

### Agents (17 total)

| Agent | Role | Model |
|-------|------|-------|
| Brokkr | Orchestrator | qwen2.5-coder:14b |
| Huginn | Coder | qwen2.5-coder:7b |
| Mimir | Reviewer | llama3.1:8b |
| Ratatoskr | Executor | qwen2.5-coder:3b |
| Skald | Tester | qwen2.5-coder:7b |
| Fenrir | SQL Expert | sqlcoder:7b |
| Odin | Planner | deepseek-r1:14b |
| Heimdall | Security | qwen3:14b |
| Baldr | Debugger | deepseek-r1:14b |
| Idunn | Documentation | llama3.1:8b |
| Vidar | Multi-lang Coder | codestral:22b |
| Skuld | Diagram Generator | qwen2.5-coder:7b |
| Kvasir | LaTeX Specialist | llama3.1:8b |
| Völundr | OpenSCAD 3D Modeler | qwen2.5-coder:7b |
| Saga | Data Visualization | qwen2.5-coder:7b |
| Vör | Text/Regex Processing | qwen2.5-coder:7b |
| Ran | Browser Automation | qwen2.5-coder:7b |

### Tools (131 total)

**Filesystem:** read_file, write_file, edit_file, list_directory, read_tree
**Compression:** archive_create, archive_extract, archive_list, compress_file, decompress_file
**Crypto:** hash_file, hash_text, encode_base64, encode_url, jwt_decode, jwt_generate, uuid_generate, encrypt_file, decrypt_file
**System:** process_list, process_kill, system_info, disk_usage, memory_usage, env_get
**Image:** image_resize, image_crop, image_convert, image_rotate, image_thumbnail, image_info
**AST:** parse_ast, find_references, symbol_info, ast_rename
**Search:** search_code, find_symbol
**Git:** git_status, git_diff, git_log, git_branch
**HTTP:** http_request, http_get, http_post
**Testing:** run_tests, check_syntax
**Formatting:** format_code, lint_code
**Refactoring:** rename_symbol, extract_function, inline_variable, move_file, batch_rename, split_file, merge_files
**SQL:** execute_query, describe_schema, explain_query, sql_generate, db_seed
**CI/CD:** generate_workflow, validate_workflow
**Security:** scan_dependencies, generate_sbom, check_outdated
**Docker:** generate_dockerfile, generate_docker_compose, validate_dockerfile
**API Spec:** generate_api_spec, validate_api_spec
**Infrastructure as Code:** generate_terraform, generate_pulumi, validate_terraform
**Database Migrations:** generate_migration, migration_status, run_migrations, rollback_migration, validate_migrations
**Diagrams:** generate_mermaid, generate_plantuml, generate_d2, diagram_from_code, generate_sequence_diagram, generate_er_diagram
**LaTeX:** generate_latex, format_equations, generate_tikz, manage_bibliography, create_beamer, latex_to_pdf
**OpenSCAD:** generate_scad, render_preview, export_stl, validate_scad, parametrize_model, optimize_printability
**DataViz:** analyze_data, suggest_viz, generate_d3, generate_matplotlib, generate_plotly, create_dashboard, export_interactive
**Media:** audio_transcribe, video_transcribe, video_generate_subtitles, video_extract_audio, audio_convert, video_convert, video_trim, video_thumbnail, video_concat, tts_generate, video_add_subtitles
**Browser:** browser_navigate, browser_click, browser_type, browser_screenshot, browser_extract, browser_execute_js, browser_pdf, browser_close, web_scrape
**Core:** shell, delegate

### Key Features

- **Parallel Execution:** Independent tasks run concurrently with VRAM-aware batching
- **Streaming Output:** Real-time token display in TUI
- **Memory System:** 5-tier memory (working, episodic, semantic, patterns, analysis)
- **Plugin System:** Custom tools (~/.sindri/plugins/*.py) and agents (~/.sindri/agents/*.toml)
- **Web UI:** React dashboard with D3.js agent graph, session replay, code diff viewer
- **Learning:** Pattern extraction from successful tasks
- **Error Recovery:** Automatic retry, stuck detection, model degradation fallback

---

## Architecture

```
sindri/
├── cli.py                  # Click CLI entry point
├── config.py               # Pydantic config with TOML loading
├── core/                   # Core loop, orchestration, events
├── agents/                 # Agent definitions and prompts
├── llm/                    # Ollama client, model manager
├── tools/                  # 32 tool implementations
├── memory/                 # 5-tier memory system
├── persistence/            # SQLite storage, metrics, export
├── analysis/               # Codebase understanding
├── plugins/                # Plugin loader and validator
├── collaboration/          # Session sharing and comments
├── voice/                  # Voice interface (STT/TTS)
├── tui/                    # Textual TUI
└── web/                    # FastAPI server + React frontend
```

---

## Quick Commands

```bash
# CLI Commands
sindri run "task"              # Single agent execution
sindri orchestrate "task"      # Multi-agent with Brokkr
sindri agents                  # List agents
sindri sessions                # List past sessions
sindri resume <id>             # Resume interrupted session
sindri export <id>             # Export session to markdown
sindri metrics                 # View performance metrics
sindri doctor                  # System health check
sindri web                     # Start web server
sindri tui                     # Start TUI

# Collaboration
sindri share <session>         # Share session
sindri comment <session> "msg" # Add comment

# Marketplace
sindri marketplace search <q>  # Search plugins
sindri marketplace install <s> # Install plugin
sindri marketplace uninstall x # Uninstall plugin
sindri marketplace update      # Update plugins
sindri marketplace info <name> # Plugin details

# Fine-tuning
sindri feedback <session> 5    # Rate session
sindri export-training out.jsonl  # Export training data

# Voice Interface
sindri voice                   # Start voice mode
sindri say "Hello"             # Speak text
sindri transcribe audio.wav    # Transcribe audio
sindri voice-status            # Check dependencies

# Security Scanning
sindri scan                    # Scan for vulnerabilities
sindri scan --severity high    # Filter by severity
sindri sbom                    # Generate SBOM
sindri outdated                # Check outdated packages
sindri security-status         # Check scanner availability

# API Spec Generation
sindri api-spec                # Generate OpenAPI spec
sindri api-spec --format yaml  # Output as YAML
sindri api-spec --dry-run      # Preview without writing
sindri validate-api-spec spec.json  # Validate spec

# Infrastructure as Code
sindri terraform               # Generate Terraform (AWS default)
sindri terraform --provider gcp  # Generate for GCP
sindri terraform --provider azure  # Generate for Azure
sindri terraform --database postgres --cache redis  # Add services
sindri terraform --compute serverless  # Lambda/Functions
sindri terraform --compute kubernetes  # EKS/GKE/AKS
sindri pulumi                  # Generate Pulumi Python
sindri pulumi --language typescript  # Generate TypeScript
sindri validate-terraform      # Validate Terraform files

# Plugins
sindri plugins list            # List plugins
sindri plugins init --tool x   # Create tool template

# Projects
sindri projects add <path>     # Register project
sindri projects search "query" # Cross-project search

# Diagrams
sindri diagram mermaid <type>  # Generate Mermaid diagram
sindri diagram plantuml <type> # Generate PlantUML diagram
sindri diagram from-code <path>  # Extract diagram from code
sindri diagram sequence        # Generate sequence diagram
sindri diagram er [source]     # Generate ER diagram

# LaTeX
sindri latex document <title>  # Generate LaTeX document
sindri latex equation <expr>   # Format math expression
sindri latex tikz <type>       # Generate TikZ diagram
sindri latex beamer <title>    # Generate Beamer slides
sindri latex bib <action>      # Manage bibliography
sindri latex compile <file>    # Compile to PDF

# OpenSCAD 3D Modeling
sindri scad generate <desc>    # Generate OpenSCAD model
sindri scad preview <file>     # Render PNG preview
sindri scad export <file>      # Export to STL for printing
sindri scad validate <file>    # Validate syntax/geometry
sindri scad parametrize <file> # Add parameters
sindri scad optimize <file>    # Print optimization tips

# Data Visualization
sindri viz analyze <file>      # Analyze dataset structure
sindri viz suggest <file>      # Suggest chart types for data
sindri viz d3 <type> <file>    # Generate D3.js chart code
sindri viz matplotlib <type> <file>  # Generate matplotlib code
sindri viz plotly <type> <file>  # Generate Plotly code
sindri viz dashboard <file>    # Create multi-chart dashboard
sindri viz export <code>       # Export as standalone HTML
```

---

## Troubleshooting

**Ollama not running:**
```bash
systemctl --user start ollama
ollama list  # Verify models
```

**Tests failing:**
```bash
.venv/bin/pytest tests/test_failing.py -vv
.venv/bin/sindri doctor
```

**Memory system errors:**
```bash
rm ~/.sindri/memory.db  # Clear if corrupted
.venv/bin/sindri orchestrate --no-memory "Task"
```

**Debug mode:**
```bash
export SINDRI_LOG_LEVEL=DEBUG
.venv/bin/sindri run "Task" 2>&1 | tee debug.log
```

---

## Project Paths

- **Project:** `/home/ryan/projects/sindri`
- **Virtual Environment:** `.venv/`
- **Data Directory:** `~/.sindri/`
- **Plugins:** `~/.sindri/plugins/` and `~/.sindri/agents/`

---

**For detailed history, see:** `docs/archive/STATUS-full-history.md`
**For roadmap and future plans, see:** `ROADMAP.md`
