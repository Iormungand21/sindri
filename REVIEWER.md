# Review Summary: Web/API Hardening - Epic A (Safe Defaults and CORS)

**Reviewer:** Codex
**Date:** 2026-01-24
**Author:** Claude Opus 4.5
**PRD:** `docs/prds/WEB_API_HARDENING.md` - Epic A

## Summary

Implemented safe defaults and CORS validation for the Sindri web server. The server now binds to localhost by default, uses a configurable CORS allowlist, and rejects insecure CORS configurations (wildcard + credentials).

## Problem

The web server had security issues:
- Default bind to `0.0.0.0` exposed the API to all network interfaces
- Hardcoded `allow_origins=["*"]` with `allow_credentials=True` - insecure and rejected by browsers
- No configuration options for CORS settings
- No validation of CORS security constraints

## Solution

1. **Default localhost binding** - Server now binds to `127.0.0.1` by default
2. **Configurable CORS** - CLI flags, config file support, and environment variables
3. **Port-aware defaults** - Default origins include both `localhost` and `127.0.0.1` with actual port
4. **Security validation** - Rejects wildcard origin with credentials at startup
5. **Reload mode support** - CORS config passed via environment variables
6. **Full config file integration** - CLI options default to `None`, allowing sindri.toml to provide defaults

## Files Changed

| File | Changes |
|------|---------|
| `sindri/config.py` | Added `ApiConfig` model with `get_allowed_origins()` method (+65 lines) |
| `sindri/cli.py` | Updated `web` command with None defaults, config loading (+70 lines) |
| `sindri/web/server.py` | Configurable CORS, env var support, config-aware run_server (+55 lines) |
| `tests/test_web.py` | Added 20 tests for CORS, env vars, port-aware defaults (+190 lines) |

**Total:** +380 lines

## Key Implementation Details

### 1. CLI Options Default to None (`sindri/cli.py:3802-3824`)

```python
@click.option("--host", "-h", default=None, ...)  # None = use config
@click.option("--port", "-p", default=None, type=int, ...)  # None = use config
@click.option("--allow-credentials/--no-allow-credentials", default=None, ...)  # Tri-state

def web(host, port, allow_credentials, ...):
    config = SindriConfig.load()
    api_config = config.api

    # CLI flags override config file only when explicitly provided
    effective_host = host if host is not None else api_config.bind_host
    effective_port = port if port is not None else api_config.bind_port
    effective_credentials = (
        allow_credentials if allow_credentials is not None else api_config.allow_credentials
    )
```

### 2. Env Vars as Complete Package (`sindri/web/server.py:510-527`)

```python
# Env vars are a complete package - only used when SINDRI_CORS_ORIGINS is set
# AND no explicit allowed_origins were passed. This prevents partial overrides.
env_origins = os.getenv("SINDRI_CORS_ORIGINS")

if env_origins is not None and allowed_origins is None:
    # Reload mode: CLI set env vars, use them as a complete package
    allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    env_credentials = os.getenv("SINDRI_CORS_CREDENTIALS")
    if env_credentials is not None:
        allow_credentials = env_credentials == "1"
    # ...
```

### 3. run_server() Config Integration (`sindri/web/server.py:2212-2255`)

```python
def run_server(
    host: Optional[str] = None,  # None = use config
    port: Optional[int] = None,  # None = use config
    allow_credentials: Optional[bool] = None,  # None = use config
    ...
):
    config = SindriConfig.load()
    api_config = config.api

    effective_host = host if host is not None else api_config.bind_host
    effective_port = port if port is not None else api_config.bind_port
    effective_credentials = (
        allow_credentials if allow_credentials is not None else api_config.allow_credentials
    )
```

## Tests Run

```bash
.venv/bin/pytest tests/test_web.py -v
# 64 passed in 3.16s
```

### Test Coverage (20 new tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestCORSConfiguration | 6 | Default origins, custom origins, wildcard rejection, credentials |
| TestServerDefaults | 2 | Config defaults, None parameters |
| TestApiConfigModel | 5 | Defaults, custom values, security validation, get_allowed_origins() |
| TestCORSEnvironmentVariables | 4 | Env vars for origins, credentials, port; explicit args override |
| TestRunServerConfigIntegration | 1 | run_server uses None defaults |
| TestPortAwareDefaults | 2 | Port-aware defaults, both localhost and 127.0.0.1 |

## Review Findings Addressed (Round 2)

### Finding 1: CLI options had non-None defaults (FIXED)

**Problem:** `--host`, `--port` had hardcoded defaults, ignoring sindri.toml.

**Fix:**
- Changed all config-related options to `default=None`
- Changed `--allow-credentials` to `--allow-credentials/--no-allow-credentials` for tri-state
- CLI now loads `SindriConfig.load()` and uses `config.api` when flags are None

### Finding 2: Env vars could partially override explicit args (FIXED)

**Problem:** `allow_credentials` from env could override explicit `allow_credentials=False`.

**Fix:**
- Env vars are now a complete package: only used when `SINDRI_CORS_ORIGINS` is set AND `allowed_origins is None`
- If explicit origins are passed, no env vars are read

### Finding 3: run_server() didn't pull from SindriConfig (FIXED)

**Problem:** Direct callers of `run_server()` didn't get config-based CORS.

**Fix:**
- `run_server()` parameters now default to `None`
- Loads `SindriConfig.load()` internally and uses `config.api` for defaults

## Backward Compatibility

- **Breaking change:** Default host changed from `0.0.0.0` to `127.0.0.1`
  - Users relying on remote access must explicitly use `--host 0.0.0.0`
- **Breaking change:** CORS no longer allows all origins by default
  - Users need to specify `--allow-origin` for non-localhost origins
- **Credential default:** Changed from `True` to `False` (more secure)

## Usage Examples

```bash
# Local development (default - secure)
sindri web

# Custom port (defaults adapt automatically)
sindri web --port 9000
# CORS: http://localhost:9000, http://127.0.0.1:9000

# Config file (sindri.toml)
# [api]
# bind_host = "0.0.0.0"
# bind_port = 9000
# allowed_origins = ["https://myapp.com"]
# allow_credentials = true
sindri web  # Uses ALL config file settings

# CLI override of specific setting
sindri web --host 127.0.0.1  # Overrides just host, port/credentials from config

# Explicit disable credentials (overrides config)
sindri web --no-allow-credentials

# Reload mode (CORS config preserved via env vars)
sindri web --port 8080 --allow-origin https://dev.local --reload
```

## PRD Epic A Checklist

| Task | Status |
|------|--------|
| Update web CLI and server defaults to `127.0.0.1` | ✅ |
| Add CORS config validation with hard error on wildcard+credentials | ✅ |
| Add config schema for `api.allowed_origins` and `api.allow_credentials` | ✅ |
| Update startup logs to include CORS/auth info | ✅ |
| Add CLI flags `--allow-origin`, `--allow-credentials/--no-allow-credentials` | ✅ |
| CLI options default to None for config integration | ✅ |
| run_server() uses SindriConfig for defaults | ✅ |
| Env vars only apply as complete package | ✅ |
| Default origins include both localhost and 127.0.0.1 | ✅ |
| Port-aware default origins | ✅ |
| Tests for all new behavior | ✅ (20 tests) |

## Files for Focused Review

1. `sindri/config.py:155-230` - ApiConfig model and get_allowed_origins()
2. `sindri/web/server.py:500-560` - create_app CORS and env var handling
3. `sindri/web/server.py:2212-2255` - run_server config integration
4. `sindri/cli.py:3801-3965` - CLI web command with None defaults
5. `tests/test_web.py:1245-1440` - New CORS/config tests

## Next Steps (Future Epics)

- **Epic B:** API Authentication (tokens, middleware, audit logging)
- **Epic C:** API Work Dir and Path Guardrails
- **Epic D:** Documentation and Migration notes
