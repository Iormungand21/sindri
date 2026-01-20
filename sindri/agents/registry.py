"""Agent registry for Sindri."""

from sindri.agents.definitions import AgentDefinition
from sindri.agents.prompts import (
    BROKKR_PROMPT,
    HUGINN_PROMPT,
    MIMIR_PROMPT,
    RATATOSKR_PROMPT,
    SKALD_PROMPT,
    FENRIR_PROMPT,
    ODIN_PROMPT,
    # Phase 9: New agents (2026-01-16)
    HEIMDALL_PROMPT,
    BALDR_PROMPT,
    IDUNN_PROMPT,
    VIDAR_PROMPT,
    # Phase 11: Multi-disciplinary agents (2026-01-18)
    SKULD_PROMPT,
    KVASIR_PROMPT,
    VOLUNDR_PROMPT,
    SAGA_PROMPT,
    # Phase 12: Text/Regex processing agent (2026-01-18)
    VOR_PROMPT,
    # Phase 12: Browser automation agent (2026-01-18)
    RAN_PROMPT,
    # Phase 12: Shell/SysAdmin agent (2026-01-18)
    SIF_PROMPT,
    # Phase 12: Math/Scientific agent (2026-01-19)
    NIDHOGG_PROMPT,
    # Phase 12: Cloud operations agent (2026-01-19)
    TYR_PROMPT,
    # Phase 12: Document/Vision agent (2026-01-20)
    GROA_PROMPT,
    # Phase 12: Advanced SQL agent (2026-01-20)
    FAFNIR_PROMPT,
    # Phase 11: Music composition agent (2026-01-20)
    BRAGI_PROMPT,
    # Phase 11: Game level design agent (2026-01-20)
    NIDHOGR_GAME_PROMPT,
    # Phase 11: Blender Python agent (2026-01-20)
    DVALIN_PROMPT,
    # Phase 11: KiCad electronics design agent (2026-01-20)
    REGIN_PROMPT,
    # Milestone 6: Self-management agent (2026-01-18)
    SINDRI_ADMIN_PROMPT,
)

# Agent Registry
# All agents available in the Sindri system
AGENTS: dict[str, AgentDefinition] = {
    # Core orchestration agents
    "brokkr": AgentDefinition(
        name="brokkr",
        role="Master orchestrator - handles simple tasks, delegates complex work",
        model="qwen2.5-coder:14b",  # Using available model
        system_prompt=BROKKR_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "edit_file",
            "list_directory",
            "read_tree",
            "search_code",
            "find_symbol",
            "git_status",
            "git_diff",
            "git_log",
            "git_branch",
            "http_request",
            "run_tests",
            "check_syntax",
            "format_code",
            "lint_code",
            "rename_symbol",
            "extract_function",
            "inline_variable",
            "move_file",
            "batch_rename",
            "split_file",
            "merge_files",
            "generate_workflow",
            "validate_workflow",
            # Docker runtime tools (Phase 12)
            "docker_ps",
            "docker_images",
            "docker_logs",
            "docker_build",
            "docker_run",
            "docker_stop",
            "docker_rm",
            "docker_compose_up",
            "docker_compose_down",
            "shell",
            "delegate",
            "propose_plan",
        ],
        can_delegate=True,
        # Phase 9: Added heimdall, baldr, idunn, vidar to delegation targets
        # Phase 11: Added skuld, kvasir, volundr, saga for multi-disciplinary domains
        # Phase 12: Added vor for text/regex, ran for browser, sif for shell, nidhogg for math/scientific, tyr for cloud, groa for documents, fafnir for advanced SQL
        # Phase 11: Added bragi for music composition
        delegate_to=[
            "huginn",
            "mimir",
            "skald",
            "fenrir",
            "odin",
            "heimdall",
            "baldr",
            "idunn",
            "vidar",
            "skuld",
            "kvasir",
            "volundr",
            "saga",
            "vor",
            "ran",
            "sif",
            "nidhogg",
            "tyr",
            "groa",
            "fafnir",
            "bragi",
            "nidhogr_game",
            "dvalin",
            "regin",
        ],
        estimated_vram_gb=9.0,
        priority=0,
        max_iterations=15,  # Reduced since simple tasks won't take many iterations
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:7b",
        fallback_vram_gb=5.0,
    ),
    "huginn": AgentDefinition(
        name="huginn",
        role="Code implementation specialist",
        model="qwen2.5-coder:7b",  # Using available model
        system_prompt=HUGINN_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "edit_file",
            "list_directory",
            "read_tree",
            "search_code",
            "find_symbol",
            "git_status",
            "git_diff",
            "git_log",
            "http_request",
            "run_tests",
            "check_syntax",
            "format_code",
            "lint_code",
            "rename_symbol",
            "extract_function",
            "inline_variable",
            "move_file",
            "batch_rename",
            "split_file",
            "merge_files",
            "generate_workflow",
            "validate_workflow",
            "shell",
            "delegate",
        ],
        can_delegate=True,
        delegate_to=["ratatoskr", "skald"],
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=30,
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "mimir": AgentDefinition(
        name="mimir",
        role="Code reviewer and quality checker",
        model="llama3.1:8b",  # Using available model
        system_prompt=MIMIR_PROMPT,
        tools=[
            "read_file",
            "search_code",
            "git_diff",
            "git_log",
            "run_tests",
            "check_syntax",
            "lint_code",
            "shell",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=20,
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "ratatoskr": AgentDefinition(
        name="ratatoskr",
        role="Fast executor for simple tasks",
        model="qwen2.5:3b-instruct-q8_0",
        system_prompt=RATATOSKR_PROMPT,
        tools=[
            "shell",
            "read_file",
            "write_file",
            "archive_create",
            "archive_extract",
            "archive_list",
            "compress_file",
            "decompress_file",
            "hash_file",
            "hash_text",
            "encode_base64",
            "encode_url",
            "jwt_decode",
            "jwt_generate",
            "uuid_generate",
            "encrypt_file",
            "decrypt_file",
            "process_list",
            "process_kill",
            "system_info",
            "disk_usage",
            "memory_usage",
            "env_get",
            "image_resize",
            "image_crop",
            "image_convert",
            "image_rotate",
            "image_thumbnail",
            "image_info",
            "pdf_extract_text",
            "pdf_to_markdown",
            "pdf_merge",
            "pdf_split",
            "ocr_image",
            "spreadsheet_read",
            "spreadsheet_write",
            # Network and HTTP diagnostic tools
            "http_trace",
            "dns_lookup",
            "curl_generate",
            "ssl_analyze",
            "port_check",
            "ping_host",
            # Video and audio processing tools
            "audio_transcribe",
            "video_extract_audio",
            "video_transcribe",
            "video_generate_subtitles",
            "audio_convert",
            "video_convert",
            "video_trim",
            "video_thumbnail",
            "video_concat",
            "tts_generate",
            "video_add_subtitles",
            # Profiling tools
            "profile_python",
            "profile_time",
            "memory_analyze",
            "detect_memory_leaks",
            "benchmark_function",
            "flame_graph",
            "complexity_analyze",
            # Docker read-only tools (Phase 12)
            "docker_ps",
            "docker_images",
            "docker_logs",
        ],
        can_delegate=False,
        estimated_vram_gb=3.0,
        priority=2,
        max_iterations=10,
        # No fallback - already the smallest model
    ),
    # Specialized agents
    "skald": AgentDefinition(
        name="skald",
        role="Test writer and quality guardian",
        model="qwen2.5-coder:7b",  # Good for test generation
        system_prompt=SKALD_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "http_request",
            "run_tests",
            "check_syntax",
            "shell",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=25,
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "fenrir": AgentDefinition(
        name="fenrir",
        role="SQL and data specialist",
        model="sqlcoder:7b",  # Specialized SQL model
        system_prompt=FENRIR_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "http_request",
            "execute_query",
            "describe_schema",
            "explain_query",
            "sql_generate",
            "db_seed",
            "shell",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=20,
        # No fallback - sqlcoder is specialized, no smaller equivalent
    ),
    "odin": AgentDefinition(
        name="odin",
        role="Deep reasoning and planning specialist",
        model="deepseek-r1:14b",  # Upgraded to 14b for better reasoning (already pulled!)
        system_prompt=ODIN_PROMPT,
        tools=["read_file", "search_code", "git_status", "git_log", "delegate"],
        can_delegate=True,
        delegate_to=["huginn", "skald", "fenrir"],
        estimated_vram_gb=9.0,  # Updated for 14b model
        priority=0,
        max_iterations=15,
        temperature=0.7,  # Higher temp for creative thinking
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="deepseek-r1:8b",  # Fall back to 8b version
        fallback_vram_gb=5.0,
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Phase 9: New Specialized Agents (2026-01-16)
    # ═══════════════════════════════════════════════════════════════════════════════
    "heimdall": AgentDefinition(
        name="heimdall",
        role="Security guardian - vulnerability detection and OWASP analysis",
        model="qwen3:14b",  # Reasoning model with thinking mode for security analysis
        system_prompt=HEIMDALL_PROMPT,
        tools=[
            "read_file",
            "search_code",
            "git_diff",
            "git_log",
            "lint_code",
            "shell",
            # Network security tools
            "ssl_analyze",
            "port_check",
            "websocket_test",
            "http_mock",
            "pcap_analyze",
        ],
        can_delegate=True,
        delegate_to=["mimir"],  # Can escalate to code reviewer
        estimated_vram_gb=10.0,
        priority=1,
        max_iterations=20,
        temperature=0.3,  # Lower temp for precise security analysis
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:7b",
        fallback_vram_gb=5.0,
    ),
    "baldr": AgentDefinition(
        name="baldr",
        role="Debugger and problem solver - root cause analysis",
        model="deepseek-r1:14b",  # Already pulled! Great for reasoning about bugs
        system_prompt=BALDR_PROMPT,
        tools=[
            "read_file",
            "search_code",
            "git_diff",
            "git_log",
            "run_tests",
            "shell",
            "delegate",
        ],
        can_delegate=True,
        delegate_to=["huginn"],  # Can delegate fixes to coder
        estimated_vram_gb=9.0,
        priority=1,
        max_iterations=25,
        temperature=0.5,  # Balanced for hypothesis exploration
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="deepseek-r1:8b",
        fallback_vram_gb=5.0,
    ),
    "idunn": AgentDefinition(
        name="idunn",
        role="Documentation specialist - docstrings, READMEs, API docs",
        model="llama3.1:8b",  # Shares model with Mimir for VRAM efficiency
        system_prompt=IDUNN_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            "edit_file",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.4,  # Moderate creativity for documentation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "vidar": AgentDefinition(
        name="vidar",
        role="Multi-language code specialist - 80+ programming languages",
        model="codestral:22b-v0.1-q4_K_M",  # Mistral's dedicated code model
        system_prompt=VIDAR_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "edit_file",
            "search_code",
            "check_syntax",
            "shell",
            "delegate",
        ],
        can_delegate=True,
        delegate_to=["skald"],  # Can delegate test writing
        estimated_vram_gb=14.0,
        priority=1,
        max_iterations=30,
        temperature=0.3,  # Lower temp for precise code generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:7b",
        fallback_vram_gb=5.0,
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Phase 11: Multi-Disciplinary Domain Agents (2026-01-18)
    # ═══════════════════════════════════════════════════════════════════════════════
    "skuld": AgentDefinition(
        name="skuld",
        role="Diagram generation specialist - Mermaid, PlantUML, D2 visualization",
        model="qwen2.5-coder:7b",  # Good for structured output generation
        system_prompt=SKULD_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            "generate_mermaid",
            "generate_plantuml",
            "generate_d2",
            "diagram_from_code",
            "generate_sequence_diagram",
            "generate_er_diagram",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.3,  # Lower temp for precise diagram generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "kvasir": AgentDefinition(
        name="kvasir",
        role="LaTeX specialist - documents, equations, TikZ, Beamer, BibTeX",
        model="llama3.1:8b",  # Good for documentation and structured output
        system_prompt=KVASIR_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            "generate_latex",
            "format_equations",
            "generate_tikz",
            "manage_bibliography",
            "create_beamer",
            "latex_to_pdf",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.3,  # Lower temp for precise LaTeX generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "volundr": AgentDefinition(
        name="volundr",
        role="OpenSCAD specialist - parametric 3D models for 3D printing",
        model="qwen2.5-coder:7b",  # Good for code generation
        system_prompt=VOLUNDR_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            "generate_scad",
            "render_preview",
            "export_stl",
            "validate_scad",
            "parametrize_model",
            "optimize_printability",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.3,  # Lower temp for precise code generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    "saga": AgentDefinition(
        name="saga",
        role="Data visualization specialist - D3.js, matplotlib, Plotly dashboards",
        model="qwen2.5-coder:7b",  # Good for code generation
        system_prompt=SAGA_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            "analyze_data",
            "suggest_viz",
            "generate_d3",
            "generate_matplotlib",
            "generate_plotly",
            "create_dashboard",
            "export_interactive",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.3,  # Lower temp for precise code generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Phase 12: Text/Regex Processing Agent (2026-01-18)
    # ═══════════════════════════════════════════════════════════════════════════════
    "vor": AgentDefinition(
        name="vor",
        role="Regex and text processing specialist - pattern matching, parsing, extraction",
        model="qwen2.5-coder:7b",  # Good for pattern generation
        system_prompt=VOR_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            "regex_generate",
            "regex_explain",
            "regex_test",
            "text_transform",
            "text_extract",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.3,  # Lower temp for precise pattern generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    # Phase 12: Browser automation agent (2026-01-18)
    "ran": AgentDefinition(
        name="ran",
        role="Browser automation specialist - web scraping, testing, form automation",
        model="qwen2.5-coder:7b",  # Good for web automation
        system_prompt=RAN_PROMPT,
        tools=[
            "read_file",
            "write_file",
            "list_directory",
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract",
            "browser_execute_js",
            "browser_pdf",
            "browser_close",
            "web_scrape",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,  # Browser operations may need more iterations
        temperature=0.3,  # Lower temp for precise automation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:3b",
        fallback_vram_gb=2.0,
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Milestone 6: Self-Management Agent (2026-01-18)
    # ═══════════════════════════════════════════════════════════════════════════════
    "sindri_admin": AgentDefinition(
        name="sindri_admin",
        role="System self-management and service orchestration",
        model="qwen2.5-coder:7b",  # Good balance of capability and VRAM
        system_prompt=SINDRI_ADMIN_PROMPT,
        tools=[
            # File operations
            "read_file",
            "write_file",
            "shell",
            # Service management tools
            "service_status",
            "service_start",
            "service_stop",
            "service_restart",
            "service_enable",
            "service_disable",
            "service_logs",
            "service_list",
            # Scheduling tools
            "cron_list",
            "cron_add",
            "cron_remove",
            "timer_list",
            "timer_create",
            "timer_remove",
            "at_schedule",
            "at_list",
            "at_remove",
            # Self-management tools
            "sindri_version",
            "sindri_update",
            "sindri_config_get",
            "sindri_config_set",
            "ollama_list",
            "ollama_pull",
            "ollama_remove",
            "ollama_status",
            "vram_status",
            # System tools (existing)
            "process_list",
            "process_kill",
            "system_info",
            "disk_usage",
            "memory_usage",
        ],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=20,
        temperature=0.3,  # Lower temp for precise system operations
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    # Phase 12: Shell/SysAdmin agent (2026-01-18)
    "sif": AgentDefinition(
        name="sif",
        role="Shell scripting and system administration specialist - bash scripts, systemd, automation",
        model="qwen2.5-coder:7b",
        system_prompt=SIF_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # Shell execution
            "shell",
            # System monitoring (existing tools - read-only)
            "process_list",
            "system_info",
            "disk_usage",
            "memory_usage",
            "env_get",
            # Service monitoring (read-only, no modification)
            "service_status",
            "service_logs",
            "service_list",
            # NEW specialized bash tools
            "bash_generate",
            "bash_explain",
            "bash_validate",
            "systemd_generate",
            "bash_lint",
        ],
        can_delegate=False,  # Tier 2 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.3,  # Lower temp for precise script generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    # Phase 12: Math/Scientific agent (2026-01-19)
    "nidhogg": AgentDefinition(
        name="nidhogg",
        role="Math and scientific computing specialist - symbolic math, statistics, plotting, linear algebra",
        model="mathstral:7b",  # Math-specialized model
        system_prompt=NIDHOGG_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # Math and scientific tools
            "math_evaluate",
            "math_solve",
            "stats_analyze",
            "plot_generate",
            "unit_convert",
            "matrix_operations",
        ],
        can_delegate=False,  # Tier 2 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.2,  # Lower temp for precise calculations
        # Fallback to smaller coder model
        fallback_model="qwen2.5-coder:3b",
        fallback_vram_gb=2.5,
    ),
    # Phase 12: Cloud operations agent (2026-01-19)
    "tyr": AgentDefinition(
        name="tyr",
        role="Cloud infrastructure operations specialist - AWS, Kubernetes management",
        model="qwen2.5-coder:7b",
        system_prompt=TYR_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # AWS tools
            "aws_s3_list",
            "aws_s3_upload",
            "aws_s3_download",
            "aws_logs_query",
            "aws_ec2_list",
            "aws_lambda_invoke",
            # Kubernetes tools
            "k8s_apply",
            "k8s_get_pods",
            "k8s_logs",
            "k8s_get_services",
            "k8s_describe",
            "k8s_delete",
        ],
        can_delegate=False,  # Tier 2 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.3,  # Lower temp for precise cloud operations
        # Fallback to smaller coder model
        fallback_model="qwen2.5-coder:3b",
        fallback_vram_gb=2.5,
    ),
    # Phase 12: Document/Vision agent (2026-01-20)
    "groa": AgentDefinition(
        name="groa",
        role="Document seeress - vision-based PDF/document understanding and processing",
        model="granite3.2-vision:2b",  # Vision model for document understanding
        system_prompt=GROA_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # Vision-based document tools (NEW)
            "document_describe",
            "document_extract_structured",
            "document_summarize",
            # Traditional document tools
            "pdf_extract_text",
            "pdf_to_markdown",
            "pdf_merge",
            "pdf_split",
            "ocr_image",
            "spreadsheet_read",
            "spreadsheet_write",
        ],
        can_delegate=False,  # Tier 3 specialist, does not delegate
        estimated_vram_gb=2.0,  # granite3.2-vision:2b is ~2GB
        priority=2,
        max_iterations=15,
        temperature=0.3,  # Lower temp for precise document analysis
        # Fallback to smaller model (no vision, traditional tools only)
        fallback_model="qwen2.5-coder:1.5b",
        fallback_vram_gb=1.0,
    ),
    # Phase 12: Advanced SQL agent (2026-01-20)
    "fafnir": AgentDefinition(
        name="fafnir",
        role="Advanced SQL optimization specialist - query tuning, schema analysis, database maintenance",
        model="sqlcoder:7b",  # Specialized SQL model (same as Fenrir)
        system_prompt=FAFNIR_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # Basic SQL tools (for context)
            "execute_query",
            "describe_schema",
            "explain_query",
            # Advanced SQL tools (Fafnir-specific)
            "sql_optimize",
            "db_schema_diff",
            "db_analyze_indexes",
            "db_backup",
            "db_visualize_schema",
        ],
        can_delegate=False,  # Tier 3 specialist, does not delegate
        estimated_vram_gb=5.0,  # sqlcoder:7b is ~5GB
        priority=2,
        max_iterations=20,
        temperature=0.2,  # Low temp for SQL precision
        # Fallback to general coder model
        fallback_model="qwen2.5-coder:3b",
        fallback_vram_gb=2.5,
    ),
    # Phase 11: Music Composition Agent (2026-01-20)
    "bragi": AgentDefinition(
        name="bragi",
        role="Music composition specialist - MIDI generation, ABC notation, harmony and arrangement",
        model="qwen2.5-coder:7b",  # Good for structured output like music notation
        system_prompt=BRAGI_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # Music generation tools
            "generate_midi",
            "generate_abc",
            "harmonize",
            "arrange",
            "analyze_music",
            "export_audio",
        ],
        can_delegate=False,  # Tier 3 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=15,
        temperature=0.5,  # Balanced - creative but structured
        # Fallback to smaller model
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    # Phase 11: Game Level Design Agent (2026-01-20)
    "nidhogr_game": AgentDefinition(
        name="nidhogr_game",
        role="Game level designer - procedural generation, difficulty balancing, dialogue trees, item stats",
        model="qwen2.5-coder:7b",  # Good for procedural/structured code generation
        system_prompt=NIDHOGR_GAME_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            # Game level generation tools
            "generate_tilemap",
            "generate_dungeon",
            "balance_difficulty",
            "generate_dialogue",
            "generate_item_stats",
            "generate_gdscript",
            "generate_unity_script",
        ],
        can_delegate=False,  # Tier 3 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.4,  # Balanced - creative for procedural but consistent for game logic
        # Fallback to smaller model
        fallback_model="qwen2.5-coder:3b",
        fallback_vram_gb=2.5,
    ),
    # Phase 11: Blender Python agent (2026-01-20)
    "dvalin": AgentDefinition(
        name="dvalin",
        role="Blender Python specialist - 3D modeling, materials, animation, rendering",
        model="qwen2.5-coder:7b",  # Good for Python code generation
        system_prompt=DVALIN_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            # Blender Python tools
            "blender_script",
            "create_mesh",
            "apply_modifier",
            "create_material",
            "setup_animation",
            "render_scene",
        ],
        can_delegate=False,  # Tier 2 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.4,  # Balanced - creative for 3D but precise for code
        # Fallback to smaller model
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),
    # ═══════════════════════════════════════════════════════════════════════════════
    # Phase 11: KiCad Electronics Design Agent (2026-01-20)
    # ═══════════════════════════════════════════════════════════════════════════════
    "regin": AgentDefinition(
        name="regin",
        role="KiCad electronics design specialist - schematics, PCB layout, manufacturing files",
        model="qwen2.5-coder:7b",  # Good for code/script generation
        system_prompt=REGIN_PROMPT,
        tools=[
            # Core file operations
            "read_file",
            "write_file",
            "list_directory",
            "read_tree",
            "search_code",
            # KiCad electronics design tools
            "create_schematic",
            "add_component",
            "route_pcb",
            "design_rule_check",
            "generate_bom",
            "export_gerber",
            "simulate_circuit",
        ],
        can_delegate=False,  # Tier 3 specialist, does not delegate
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.3,  # Lower temp for precise electronics design
        # Fallback to smaller model
        fallback_model="qwen2.5-coder:3b",
        fallback_vram_gb=2.5,
    ),
}


def get_agent(name: str) -> AgentDefinition:
    """Get an agent by name."""
    agent = AGENTS.get(name)
    if not agent:
        raise ValueError(f"Unknown agent: {name}")
    return agent


def list_agents() -> list[str]:
    """List all agent names."""
    return list(AGENTS.keys())
