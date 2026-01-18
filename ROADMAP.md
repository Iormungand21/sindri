# Sindri Development Roadmap

**Vision:** A production-ready, local-first LLM orchestration system that serves as a **multi-disciplinary one-stop shop** for creative and technical work. Beyond code, Sindri coordinates specialized agents for 3D modeling, music composition, electronics design, data visualization, game development, scientific documentation, and more — all using local inference.

**Current Status:** Production Ready (v0.1.0) - 12 agents, 59 tools, 2356 backend + 104 frontend tests (100% passing)

---

## Quick Start

```bash
# Verify installation
.venv/bin/pytest tests/ -v --tb=no -q    # 2303 tests
cd sindri/web/static && npm test -- --run  # 104 frontend tests
.venv/bin/sindri doctor --verbose

# Try it
.venv/bin/sindri run "Create hello.py"
.venv/bin/sindri orchestrate "Review this project"
.venv/bin/sindri tui                       # Terminal UI
.venv/bin/sindri web --port 8000           # Web UI
.venv/bin/sindri voice                     # Voice interface
```

**Essential Reading:**
- `STATUS.md` - Current state and recent changes
- `PROJECT_HANDOFF.md` - Comprehensive project context
- `docs/QUICKSTART.md` - User guide

---

## Guiding Principles

1. **Local-First:** No cloud dependencies, works offline, user owns all data
2. **Efficient:** Parallel execution, smart caching, minimal VRAM waste
3. **Intelligent:** Memory-augmented, learns from past work, specialized agents
4. **Developer-Friendly:** Great UX, clear feedback, easy to extend
5. **Production-Ready:** Robust error handling, crash recovery, comprehensive tests

---

## Completed Phases (Summary)

### Phase 5: Polish & Production (Complete)
- CLI commands: agents, sessions, recover, resume, doctor, export, metrics
- Directory tools: list_directory, read_tree
- Memory enabled by default, VRAM gauge in TUI
- Error handling with classification, retry, stuck detection, recovery

### Phase 6: Performance & Parallelism (Complete)
- Parallel task execution with VRAM-aware batching
- Model caching with pre-warming and keep-warm
- Streaming responses with real-time token display

### Phase 7: Intelligence & Learning (Complete)
- Enhanced agent specialization (security, testing, SQL patterns)
- Pattern learning from successful completions
- Interactive planning with execution plans
- Codebase understanding (dependencies, architecture, style)

### Phase 8: Extensibility & Platform (Complete)
- Plugin system for custom tools and agents
- Web API (FastAPI) with REST and WebSocket
- Web UI (React) with dashboard, agent graph, session viewer
- Multi-project memory with cross-project search

### Phase 9: Advanced Features (Complete)
- Code Diff Viewer, Timeline View, Session Replay
- Refactoring tools: move, batch rename, split, merge files
- CI/CD Integration: workflow generation and validation
- Agent Fine-Tuning: feedback collection and training export
- Remote Collaboration: session sharing, comments, presence
- Plugin Marketplace: install from git/URL/local, search, update
- Voice Interface: Whisper STT, multi-engine TTS, wake word
- Dependency Scanner: pip-audit, npm audit, cargo audit, govulncheck, SBOM
- Team Mode: user accounts, team management, role-based permissions

### Phase 10: Advanced Team Collaboration (In Progress)
- Notification System: mentions, comments, team invites, session activity
- User notification preferences with quiet hours
- CLI commands for notification management
- Activity Feed: team activity timeline with filtering and statistics
- Activity Feed API endpoints for web/mobile integration
- Webhooks: external integrations with Slack, Discord, and generic HTTP
- HMAC-SHA256 signature verification for webhook security
- Retry logic with exponential backoff for reliable delivery
- Audit Log System: comprehensive security and compliance logging
- Authentication/authorization event tracking
- Data access and modification auditing
- Security event detection (brute force, suspicious activity)
- Compliance-focused exports (JSON, CSV)
- API Keys: programmatic access for CI/CD and automation
- Scope-based permissions with hierarchy
- Rate limiting and usage tracking
- Key expiration and revocation

**Total:** 2303 backend tests + 104 frontend tests (100% passing)

---

## Future Features (Phase 9+)

### High Priority

| Feature | Description | Status |
|---------|-------------|--------|
| Voice Interface | Speech-to-text commands, TTS responses | **Complete** |
| Plugin Marketplace | Share and discover community plugins | **Complete** |

### Medium Priority

| Feature | Description | Status |
|---------|-------------|--------|
| AST-Based Refactoring | Tree-sitter for precise multi-language refactoring | **Complete** |
| Dependency Scanner | OWASP/npm audit vulnerability detection | **Complete** |
| Docker Generator | Auto-generate Dockerfile/docker-compose | **Complete** |
| API Spec Generator | OpenAPI from route definitions | **Complete** |
| Coverage Visualization | Code coverage in Web UI | **Complete** |
| Database Migrations | Multi-framework migration management (Alembic, Django, Prisma, Knex, Goose, Diesel) | **Complete** |

### Exploratory

| Feature | Description | Status |
|---------|-------------|--------|
| Infrastructure as Code | Terraform/Pulumi generation for AWS/GCP/Azure | **Complete** |
| IDE Plugins | Neovim plugin, JSON-RPC server | **Complete** |
| Fine-Tuning Pipeline | Streamlined feedback → training → deployment | **Complete** |
| Team Mode | Multi-user sessions, role-based permissions | **Complete** |

---

## Phase 11: Multi-Disciplinary Domain Agents (In Progress)

Sindri's architecture naturally supports specialized agents beyond software development. This phase expands Sindri into a **universal creative and technical assistant**.

**Completed:**
- Diagram Generation Agent ("Skuld") - Mermaid, PlantUML, D2 diagram generation (2026-01-18)

### 3D Modeling & CAD

#### OpenSCAD Agent ("Völundr" - Master Smith)
Generate parametric 3D models for 3D printing using code-based CAD.

| Tool | Description |
|------|-------------|
| `generate_scad` | Generate OpenSCAD code from text description |
| `render_preview` | Render PNG/STL preview of model |
| `export_stl` | Export to STL for 3D printing |
| `validate_scad` | Check syntax and manifold geometry issues |
| `parametrize_model` | Convert hardcoded values to parameters |
| `optimize_printability` | Suggest supports, orientation, tolerances |

**Use Cases:**
- "Create a phone stand with 60° angle and cable routing"
- "Design a parametric box with lid and hinge"
- "Generate a gear with 24 teeth, module 1.5"

**Status:** Planned

#### Blender Python Agent ("Dvalin" - Dwarf Craftsman)
3D modeling and animation via Blender's Python API.

| Tool | Description |
|------|-------------|
| `blender_script` | Generate Blender Python scripts |
| `create_mesh` | Programmatically create 3D meshes |
| `apply_modifier` | Add modifiers (subdivision, boolean, etc.) |
| `create_material` | Generate PBR materials and shaders |
| `setup_animation` | Create keyframe animations |
| `render_scene` | Render to image/video |

**Use Cases:**
- "Create a low-poly tree with wind animation"
- "Generate a procedural terrain with erosion"
- "Build a product visualization scene"

**Status:** Planned

---

### Electronics & Hardware

#### KiCad Agent ("Regin" - Weapon Smith)
Schematic capture and PCB design automation.

| Tool | Description |
|------|-------------|
| `create_schematic` | Generate KiCad schematic from description |
| `add_component` | Place components with footprints |
| `route_pcb` | Auto-route traces between pads |
| `design_rule_check` | Validate against DRC rules |
| `generate_bom` | Create Bill of Materials |
| `export_gerber` | Export manufacturing files |
| `simulate_circuit` | SPICE simulation integration |

**Use Cases:**
- "Create an ESP32 dev board with USB-C and battery charging"
- "Add ESD protection to this USB interface"
- "Design a 4-layer PCB for this RF circuit"

**Status:** Planned

---

### Music & Audio

#### Music Composition Agent ("Bragi" - God of Poetry)
Multi-agent music composition using MIDI and ABC notation.

| Tool | Description |
|------|-------------|
| `generate_midi` | Create MIDI from text description |
| `generate_abc` | Create ABC notation (text-based sheet music) |
| `harmonize` | Add chord progressions to melody |
| `arrange` | Create multi-track arrangement |
| `export_audio` | Render to WAV/MP3 via FluidSynth |
| `analyze_music` | Extract key, tempo, structure |

**Sub-Agents:**
- **Melody Agent** - Creates main themes and motifs
- **Harmony Agent** - Chord progressions, accompaniment
- **Rhythm Agent** - Percussion, timing, groove
- **Review Agent** - Musical quality assessment

**Use Cases:**
- "Compose a 16-bar jazz progression in Bb major"
- "Create background music for a puzzle game"
- "Generate a string quartet arrangement of this melody"

**Status:** Planned

---

### Data & Visualization

#### Data Visualization Agent ("Saga" - Goddess of History)
Transform data into interactive visualizations.

| Tool | Description |
|------|-------------|
| `analyze_data` | Understand dataset structure and statistics |
| `suggest_viz` | Recommend appropriate chart types |
| `generate_d3` | Create D3.js interactive visualization |
| `generate_matplotlib` | Create Python/matplotlib visualization |
| `generate_plotly` | Create Plotly interactive charts |
| `create_dashboard` | Multi-chart dashboard layout |
| `export_interactive` | Export standalone HTML with interactions |

**Use Cases:**
- "Create a force-directed graph of this network data"
- "Build a dashboard showing sales trends by region"
- "Visualize this algorithm's performance over time"

**Status:** Planned

---

### Technical Diagrams

#### Diagram Generation Agent ("Skuld" - Norn of the Future)
Auto-generate technical diagrams from code or descriptions.

| Tool | Description |
|------|-------------|
| `generate_mermaid` | Create Mermaid.js diagrams |
| `generate_plantuml` | Create PlantUML diagrams |
| `generate_d2` | Create D2 diagrams |
| `diagram_from_code` | Extract diagrams from source code |
| `generate_sequence` | Sequence diagrams from API flows |
| `generate_erd` | ER diagrams from database schema |
| `generate_architecture` | System architecture from codebase |
| `export_diagram` | Render to SVG/PNG/PDF |

**Diagram Types:**
- Sequence diagrams, Class diagrams, ER diagrams
- Flowcharts, State machines, Mind maps
- Architecture diagrams, Deployment diagrams

**Use Cases:**
- "Generate a sequence diagram for the auth flow"
- "Create an ER diagram from this SQLAlchemy model"
- "Visualize the architecture of this microservices app"

**Status:** ✅ Complete (2026-01-18)

---

### Game Development

#### Level Design Agent ("Níðhöggr" - World Serpent)
Procedural game content and level generation.

| Tool | Description |
|------|-------------|
| `generate_tilemap` | Create 2D level layouts (JSON/TMX) |
| `generate_dungeon` | Procedural dungeon with constraints |
| `balance_difficulty` | Analyze and adjust challenge curve |
| `generate_dialogue` | NPC dialogue trees (Yarn/Ink) |
| `generate_item_stats` | Balanced item/weapon statistics |
| `generate_gdscript` | Godot script generation |
| `generate_unity_script` | Unity C# script generation |

**Use Cases:**
- "Create a roguelike dungeon with 5 rooms and a boss"
- "Generate a balanced loot table for an RPG"
- "Design a puzzle level with increasing difficulty"

**Status:** Planned

---

### Scientific & Academic

#### LaTeX Agent ("Kvasir" - Wisest of All)
Academic paper formatting, equations, and documentation.

| Tool | Description |
|------|-------------|
| `generate_latex` | Create LaTeX documents from outline |
| `format_equations` | Convert math notation to LaTeX |
| `generate_tikz` | Create TikZ diagrams |
| `manage_bibliography` | BibTeX management and citations |
| `create_beamer` | Generate presentation slides |
| `latex_to_pdf` | Compile to PDF |

**Use Cases:**
- "Format this paper in IEEE conference style"
- "Convert these equations to LaTeX"
- "Create a Beamer presentation from this outline"
- "Generate a TikZ diagram of this neural network"

**Status:** Planned

---

### Priority & Complexity Matrix

| Agent | Complexity | Uniqueness | User Value | Dependencies |
|-------|------------|------------|------------|--------------|
| **Diagram Agent** | Low | Medium | High | None (text output) |
| **OpenSCAD Agent** | Medium | High | High | OpenSCAD CLI |
| **LaTeX Agent** | Low | Medium | High | LaTeX distribution |
| **Data Viz Agent** | Medium | Medium | High | D3.js, matplotlib |
| **KiCad Agent** | High | Very High | Medium | KiCad 8+ |
| **Music Agent** | High | Very High | Medium | FluidSynth, MIDI |
| **Game Level Agent** | High | High | Medium | None |
| **Blender Agent** | High | High | Medium | Blender 4+ |

### Implementation Order (Recommended)

**Tier 1 - Quick Wins (Low complexity, high value)**
1. Diagram Generation Agent - Leverages existing codebase analysis
2. LaTeX Agent - Text-based output, complements Idunn

**Tier 2 - Core Differentiators (Medium complexity, unique value)**
3. OpenSCAD Agent - Unique maker/3D printing integration
4. Data Visualization Agent - Broad applicability

**Tier 3 - Advanced Domains (High complexity, specialized)**
5. KiCad Agent - Hardware maker community
6. Music Agent - Creative differentiation
7. Game Level Agent - Game dev community
8. Blender Agent - 3D artist community

---

## Phase 12: Universal Tool Expansion (Planned)

Expand Sindri's core capabilities with universal tools that benefit all agents and workflows. These tools transform Sindri from a coding assistant into a comprehensive automation platform.

---

### Tool Categories

#### 1. Browser & Web Automation Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `browser_navigate` | Navigate to URL, wait for page load | Playwright |
| `browser_click` | Click element by selector/text | Playwright |
| `browser_type` | Type text into form fields | Playwright |
| `browser_screenshot` | Capture page/element screenshot | Playwright |
| `browser_extract` | Extract structured data from page | Playwright |
| `browser_execute_js` | Run JavaScript on page | Playwright |
| `browser_pdf` | Save page as PDF | Playwright |
| `web_scrape` | Scrape URL to markdown/JSON | Firecrawl/httpx |

**Use Cases:** Web testing, data collection, form automation, visual documentation

---

#### 2. Document Processing Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `pdf_extract_text` | Extract text from PDF (with OCR) | PyMuPDF, Tesseract |
| `pdf_extract_tables` | Extract tables as structured data | Camelot, pdfplumber |
| `pdf_to_markdown` | Convert PDF to clean markdown | MinerU |
| `pdf_merge` | Merge multiple PDFs | PyMuPDF |
| `pdf_split` | Split PDF by pages | PyMuPDF |
| `ocr_image` | OCR text from image | Tesseract, PaddleOCR |
| `document_summarize` | AI summary of document | LLM |
| `spreadsheet_read` | Parse Excel/CSV to data | pandas, openpyxl |
| `spreadsheet_write` | Generate Excel/CSV from data | pandas, openpyxl |
| `spreadsheet_transform` | Apply transformations | pandas |

**Use Cases:** Document digitization, report generation, data import/export

---

#### 3. Video & Audio Processing Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `video_transcribe` | Transcribe speech to text | Whisper, faster-whisper |
| `video_generate_subtitles` | Create SRT/VTT files | Whisper + FFmpeg |
| `video_add_subtitles` | Burn subtitles into video | FFmpeg |
| `video_extract_audio` | Extract audio track | FFmpeg |
| `video_trim` | Cut video to time range | FFmpeg |
| `video_concat` | Join multiple videos | FFmpeg |
| `video_thumbnail` | Generate thumbnail images | FFmpeg |
| `video_convert` | Convert video formats | FFmpeg |
| `audio_transcribe` | Transcribe audio file | Whisper |
| `audio_convert` | Convert audio formats | FFmpeg |
| `tts_generate` | Text-to-speech synthesis | pyttsx3, piper, Coqui |

**Use Cases:** Subtitle generation, podcast transcription, video editing automation

---

#### 4. Image Manipulation Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `image_resize` | Resize/scale images | Pillow |
| `image_crop` | Crop to region | Pillow |
| `image_convert` | Convert formats (PNG↔JPG↔WebP) | Pillow |
| `image_compress` | Optimize file size | Pillow, pngquant |
| `image_annotate` | Add text, arrows, boxes | Pillow, ImageMagick |
| `image_combine` | Merge multiple images | Pillow |
| `image_watermark` | Add watermark | Pillow |
| `image_diff` | Visual diff between images | Pillow |
| `screenshot_annotate` | Annotate screenshots | Pillow |

**Use Cases:** Asset optimization, documentation, visual testing

---

#### 5. Advanced Database Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `sql_explain_plan` | Get query execution plan | SQLAlchemy |
| `sql_optimize` | Suggest query optimizations | LLM + EXPLAIN |
| `sql_generate` | Natural language → SQL | LLM |
| `db_schema_diff` | Compare two schemas | SQLAlchemy |
| `db_analyze_indexes` | Suggest index improvements | LLM + stats |
| `db_backup` | Create database backup | pg_dump, mysqldump |
| `db_seed` | Generate realistic test data | Faker |
| `db_visualize_schema` | Generate ER diagram | ERAlchemy |

**Use Cases:** Performance tuning, schema evolution, testing

---

#### 6. Code Profiling & Performance Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `profile_python` | CPU/memory profiling | cProfile, Scalene |
| `profile_time` | Execution time analysis | timeit |
| `memory_analyze` | Memory usage breakdown | memory_profiler |
| `detect_memory_leaks` | Find memory leaks | tracemalloc |
| `benchmark_function` | Run microbenchmarks | pytest-benchmark |
| `flame_graph` | Generate flame graphs | py-spy |
| `complexity_analyze` | Big-O complexity analysis | LLM |

**Use Cases:** Performance optimization, bottleneck identification

---

#### 7. Network & HTTP Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `http_trace` | Detailed HTTP request trace | httpx |
| `curl_generate` | Generate curl commands | LLM |
| `dns_lookup` | DNS resolution with details | dnspython |
| `ssl_analyze` | SSL/TLS certificate analysis | ssl, cryptography |
| `port_check` | Check if ports are open | socket |
| `ping_host` | Network connectivity test | subprocess |
| `http_mock` | Create mock API endpoints | responses |
| `websocket_test` | WebSocket testing | websockets |
| `pcap_analyze` | Analyze packet captures | scapy |

**Use Cases:** API debugging, network troubleshooting, security auditing

---

#### 8. Text Processing & Regex Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `regex_generate` | Natural language → regex | LLM |
| `regex_explain` | Explain regex in plain English | LLM |
| `regex_test` | Test regex against samples | re |
| `text_transform` | Apply text transformations | LLM |
| `text_extract` | Extract patterns from text | re |
| `json_query` | JQ-style JSON querying | jq bindings |
| `xml_query` | XPath querying | lxml |
| `yaml_validate` | Validate YAML syntax | PyYAML |
| `diff_text` | Text diff with highlighting | difflib |
| `markdown_to_html` | Convert markdown | markdown |

**Use Cases:** Data extraction, format conversion, validation

---

#### 9. System & Process Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `process_list` | List running processes | psutil |
| `process_kill` | Kill process by PID/name | psutil |
| `system_info` | Get system information | psutil, platform |
| `disk_usage` | Check disk space | psutil |
| `memory_usage` | Check memory usage | psutil |
| `env_get` | Get environment variables | os |
| `service_status` | Check systemd service | subprocess |
| `service_restart` | Restart systemd service | subprocess |
| `cron_list` | List cron jobs | subprocess |
| `cron_add` | Add cron job | crontab |

**Use Cases:** System monitoring, automation, DevOps

---

#### 10. Compression & Archive Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `archive_create` | Create zip/tar archives | zipfile, tarfile |
| `archive_extract` | Extract archives | zipfile, tarfile |
| `archive_list` | List archive contents | zipfile, tarfile |
| `compress_file` | Compress files (gzip, brotli) | gzip, brotli |
| `decompress_file` | Decompress files | gzip, brotli |

---

#### 11. Crypto & Encoding Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `hash_file` | Calculate file hashes | hashlib |
| `hash_text` | Hash text (MD5, SHA256) | hashlib |
| `encode_base64` | Base64 encode/decode | base64 |
| `encode_url` | URL encode/decode | urllib |
| `jwt_decode` | Decode JWT tokens | PyJWT |
| `jwt_generate` | Generate JWT tokens | PyJWT |
| `uuid_generate` | Generate UUIDs | uuid |
| `encrypt_file` | Encrypt file (AES) | cryptography |
| `decrypt_file` | Decrypt file | cryptography |

---

#### 12. Cloud & Container Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `aws_s3_list` | List S3 buckets/objects | boto3 |
| `aws_s3_upload` | Upload to S3 | boto3 |
| `aws_s3_download` | Download from S3 | boto3 |
| `aws_logs_query` | Query CloudWatch logs | boto3 |
| `docker_build` | Build Docker image | docker-py |
| `docker_run` | Run Docker container | docker-py |
| `docker_logs` | Get container logs | docker-py |
| `docker_compose_up` | Start compose stack | subprocess |
| `k8s_apply` | Apply K8s manifest | kubernetes |
| `k8s_get_pods` | List pods | kubernetes |
| `k8s_logs` | Get pod logs | kubernetes |

---

#### 13. Math & Scientific Tools

| Tool | Description | Backend |
|------|-------------|---------|
| `math_evaluate` | Evaluate math expressions | SymPy |
| `math_solve` | Solve equations symbolically | SymPy |
| `stats_analyze` | Statistical analysis | SciPy, pandas |
| `plot_generate` | Generate plots/charts | matplotlib |
| `unit_convert` | Convert between units | pint |
| `matrix_operations` | Matrix math | NumPy |

---

### Specialized Agents for Tool Categories

In addition to tools, certain domains benefit from **dedicated agents** with specialized prompts or models optimized for specific tasks.

#### New Specialized Agents

| Agent | Norse Name | Domain | Recommended Model | VRAM |
|-------|------------|--------|-------------------|------|
| **SQL Agent** | Nidhogg (Dragon) | Database queries, optimization | duckdb-nsql:7b or sqlcoder:7b | ~5GB |
| **Document Agent** | Groa (Seeress) | PDF/OCR/document processing | granite3.2-vision:2b | ~2GB |
| **Network Agent** | Heimdall (extended) | HTTP debugging, traffic analysis | qwen2.5-coder:7b | ~5GB |
| **Data Agent** | Saga (extended) | Data analysis, visualization | qwen2.5-coder:14b | ~9GB |
| **Math Agent** | Mímir (extended) | Calculations, symbolic math | mathstral:7b or qwq:32b | ~5-20GB |
| **Shell Agent** | Sif (Golden Hair) | Bash scripting, sysadmin | qwen2.5-coder:7b | ~5GB |
| **Regex Agent** | Vör (Wisdom) | Pattern generation, text processing | qwen2.5-coder:7b | ~5GB |
| **Browser Agent** | Rán (Sea) | Web automation, scraping | qwen2.5-coder:7b | ~5GB |

#### Specialized Model Recommendations

Based on research, these specialized models outperform general-purpose models for specific tasks:

**Text-to-SQL (Local Options):**
- [duckdb-nsql:7b](https://ollama.com/library/duckdb-nsql) - MotherDuck/Numbers Station, optimized for DuckDB
- [sqlcoder:7b](https://github.com/defog-ai/sqlcoder) - Defog.ai, general SQL
- [distil-text2sql:4b](https://github.com/distil-labs/distil-text2sql) - 170x smaller than teacher, same accuracy

**Document/Vision (Local Options):**
- [granite3.2-vision:2b](https://ollama.com/library/granite3.2-vision) - IBM, document understanding
- [llama3.2-vision:11b](https://ollama.com/library/llama3.2-vision) - Meta, general vision
- [olmocr-2-7b](https://huggingface.co/allenai/OLMoE-1B-7B-0125) - OCR-optimized

**Math/Reasoning (Local Options):**
- [mathstral:7b](https://ollama.com/library/mathstral) - Mistral, math-specialized
- [qwq:32b](https://ollama.com/library/qwq) - Alibaba, strong reasoning
- [deepseek-r1:14b](https://ollama.com/library/deepseek-r1) - Deep reasoning

**Audio/Speech (Local Options):**
- [whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) - 6x faster, 1-2% accuracy loss
- [voxtral-small:24b](https://huggingface.co/mistralai/Voxtral-Small-24B-Instruct) - Mistral, semantic understanding

---

### Tool Implementation Priority

**Tier 1 - High ROI, Low Complexity (Implement First)**

| Category | Tools | Effort |
|----------|-------|--------|
| Text/Regex | regex_generate, regex_explain, text_transform | Low |
| Compression | archive_create, archive_extract | Low |
| Crypto/Encoding | hash_file, encode_base64, jwt_decode | Low |
| System | process_list, system_info, disk_usage | Low |

**Tier 2 - High Value, Medium Complexity**

| Category | Tools | Effort |
|----------|-------|--------|
| Image | image_resize, image_crop, image_annotate | Medium |
| Document | pdf_extract_text, pdf_to_markdown, ocr_image | Medium |
| Database | sql_explain_plan, sql_generate, db_seed | Medium |
| Network | http_trace, dns_lookup, curl_generate | Medium |

**Tier 3 - High Value, Higher Complexity**

| Category | Tools | Effort |
|----------|-------|--------|
| Video/Audio | video_transcribe, video_generate_subtitles | Medium |
| Profiling | profile_python, flame_graph | Medium |
| Browser | browser_navigate, browser_screenshot | High |
| Cloud | aws_s3_*, docker_*, k8s_* | High |

---

### Agent Implementation Priority

**Tier 1 - Extend Existing Agents**
- Extend **Fenrir** (SQL) with specialized sqlcoder model + new DB tools
- Extend **Heimdall** (Security) with network analysis tools

**Tier 2 - New Lightweight Agents**
- **Vör** (Regex/Text) - General text processing, pattern generation
- **Sif** (Shell/SysAdmin) - System automation, scripting

**Tier 3 - New Specialized Agents**
- **Groa** (Documents) - PDF/OCR with vision model
- **Nidhogg** (Advanced SQL) - Complex query optimization

---

## Development Guidelines

### Code Patterns
- **Async everywhere** - All I/O should be async
- **Structured logging** - Use `structlog`, not print
- **Type hints** - All functions fully typed
- **Pydantic models** - For all data structures
- **Error handling** - Always return ToolResult, never raise in tools
- **Tests** - One test file per module, use pytest fixtures

### Adding Features

**New Tool:**
1. Create class in `sindri/tools/` inheriting from `Tool`
2. Register in `sindri/tools/registry.py`
3. Add to agent tool lists in `sindri/agents/registry.py`
4. Write tests in `tests/test_<tool>.py`

**New Agent:**
1. Define in `sindri/agents/registry.py` with AgentDefinition
2. Create system prompt in `sindri/agents/prompts.py`
3. Add to parent agent's `delegate_to` list
4. Write tests in `tests/test_<agent>.py`

### Testing

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run specific test file
.venv/bin/pytest tests/test_tools.py -v

# Run with coverage
.venv/bin/pytest --cov=sindri --cov-report=term-missing

# Frontend tests
cd sindri/web/static && npm test -- --run
```

---

## Changelog (Recent)

| Date | Feature | Tests |
|------|---------|-------|
| 2026-01-17 | API Keys (programmatic access, scopes, rate limiting, usage tracking) | +62 |
| 2026-01-17 | Audit Log System (security/compliance logging, brute force detection) | +52 |
| 2026-01-17 | Database Migrations (Alembic, Django, Prisma, Knex, Goose, Diesel, SeaORM) | +65 |
| 2026-01-17 | Webhooks (Slack/Discord/Generic HTTP, HMAC signatures, retry logic) | +57 |
| 2026-01-17 | Activity Feed (team timeline, filtering, stats, API endpoints) | +56 |
| 2026-01-17 | Notification System (mentions, comments, team invites, preferences) | +56 |
| 2026-01-17 | Team Mode (user accounts, teams, role-based permissions) | +84 |
| 2026-01-17 | Fine-Tuning Pipeline (curation, registry, training, evaluation) | +72 |
| 2026-01-17 | IDE Integration (JSON-RPC server, Neovim plugin) | +56 |
| 2026-01-17 | Infrastructure as Code (Terraform AWS/GCP/Azure, Pulumi Python/TS) | +73 |
| 2026-01-17 | Coverage Visualization (Cobertura XML, LCOV, JSON; Web UI) | +40 |
| 2026-01-17 | AST-Based Refactoring (tree-sitter, Python/JS/TS/Rust/Go) | +55 |
| 2026-01-17 | API Spec Generator (OpenAPI 3.0 from Flask/FastAPI/Express/Django/Gin/Echo) | +62 |
| 2026-01-17 | Docker Generator (Dockerfile, docker-compose, validation) | +64 |
| 2026-01-17 | Dependency Scanner (pip-audit, npm audit, cargo audit, SBOM) | +58 |
| 2026-01-17 | Voice Interface (Whisper STT, multi-engine TTS) | +56 |
| 2026-01-17 | Plugin Marketplace (install, search, update, uninstall) | +51 |
| 2026-01-17 | Remote Collaboration (sharing, comments, presence) | +65 |
| 2026-01-17 | Agent Fine-Tuning (feedback, training export) | +36 |
| 2026-01-17 | CI/CD Integration (workflow generation/validation) | +63 |
| 2026-01-16 | MergeFilesTool | +28 |
| 2026-01-16 | SplitFileTool | +28 |
| 2026-01-16 | BatchRenameTool | +32 |
| 2026-01-16 | MoveFileTool | +28 |
| 2026-01-16 | Session Replay | +33 |
| 2026-01-16 | Timeline View | +18 |
| 2026-01-16 | Code Diff Viewer | +25 |
| 2026-01-16 | D3.js Agent Graph | +15 |
| 2026-01-16 | Multi-Project Memory | +47 |
| 2026-01-16 | New Agents (Heimdall, Baldr, Idunn, Vidar) | +53 |

**For complete history, see:** `docs/archive/ROADMAP-full-history.md`

---

## Target Platform

- **OS:** Linux (Arch/EndeavourOS)
- **GPU:** AMD Radeon 6950XT (16GB VRAM)
- **Python:** 3.11+
- **LLM Backend:** Ollama with ROCm

---

**Last Updated:** 2026-01-17
**Phase 11 Added:** Multi-Disciplinary Domain Agents (OpenSCAD, Music, KiCad, Diagrams, Data Viz, Game Dev, LaTeX, Blender)
**Phase 12 Added:** Universal Tool Expansion (100+ tools across 13 categories) + 8 New Specialized Agents
**Maintained By:** Project contributors
