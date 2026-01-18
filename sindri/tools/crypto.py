"""Cryptography and encoding tools for Sindri.

This module provides tools for:
- Hashing files and text (MD5, SHA1, SHA256, SHA512, BLAKE2)
- Base64 encoding/decoding
- URL encoding/decoding
- JWT token generation and decoding
- UUID generation
- File encryption/decryption (AES via Fernet)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid as uuid_module
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import quote, quote_plus, unquote, unquote_plus

import structlog

from sindri.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

# Hash algorithms supported
HASH_ALGORITHMS = {
    "md5": hashlib.md5,
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
    "blake2b": hashlib.blake2b,
    "blake2s": hashlib.blake2s,
}

# UUID namespaces
UUID_NAMESPACES = {
    "dns": uuid_module.NAMESPACE_DNS,
    "url": uuid_module.NAMESPACE_URL,
    "oid": uuid_module.NAMESPACE_OID,
    "x500": uuid_module.NAMESPACE_X500,
}


class HashFileTool(Tool):
    """Calculate cryptographic hash of a file."""

    name = "hash_file"
    description = """Calculate the cryptographic hash of a file.

Supports multiple algorithms: MD5, SHA1, SHA256, SHA512, BLAKE2b, BLAKE2s.

Examples:
- hash_file(file_path="document.pdf", algorithm="sha256")
- hash_file(file_path="archive.zip", algorithm="md5")  # For checksums
- hash_file(file_path="large_file.bin", algorithm="blake2b")  # Fast

Note: MD5 and SHA1 should only be used for checksums, not security purposes."""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to hash",
            },
            "algorithm": {
                "type": "string",
                "description": "Hash algorithm to use",
                "enum": ["md5", "sha1", "sha256", "sha512", "blake2b", "blake2s"],
                "default": "sha256",
            },
        },
        "required": ["file_path"],
    }

    async def execute(
        self, file_path: str, algorithm: str = "sha256", **kwargs: Any
    ) -> ToolResult:
        """Execute the hash file tool."""
        log.info("hash_file_start", file_path=file_path, algorithm=algorithm)

        try:
            resolved_path = self._resolve_path(file_path)

            if not os.path.exists(resolved_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {file_path}",
                )

            if os.path.isdir(resolved_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is a directory, not a file: {file_path}",
                )

            algorithm = algorithm.lower()
            if algorithm not in HASH_ALGORITHMS:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported algorithm: {algorithm}. Supported: {', '.join(HASH_ALGORITHMS.keys())}",
                )

            # Calculate hash
            hasher = HASH_ALGORITHMS[algorithm]()
            file_size = os.path.getsize(resolved_path)

            with open(resolved_path, "rb") as f:
                # Read in chunks for large files
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)

            hash_digest = hasher.hexdigest()

            output = f"""**File Hash Result**

**File:** {file_path}
**Algorithm:** {algorithm.upper()}
**Hash:** `{hash_digest}`
**File Size:** {file_size:,} bytes"""

            if algorithm in ("md5", "sha1"):
                output += "\n\n*Note: MD5/SHA1 are for checksums only, not cryptographic security.*"

            log.info("hash_file_success", algorithm=algorithm, hash=hash_digest[:16])

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file_path": str(resolved_path),
                    "algorithm": algorithm,
                    "hash": hash_digest,
                    "file_size": file_size,
                    "hash_length": len(hash_digest),
                },
            )

        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied reading file: {file_path}",
            )
        except Exception as e:
            log.error("hash_file_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class HashTextTool(Tool):
    """Calculate cryptographic hash of text."""

    name = "hash_text"
    description = """Calculate the cryptographic hash of a text string.

Supports multiple algorithms: MD5, SHA1, SHA256, SHA512, BLAKE2b, BLAKE2s.

Examples:
- hash_text(text="Hello, World!", algorithm="sha256")
- hash_text(text="password123", algorithm="sha512")
- hash_text(text="data", algorithm="md5", encoding="utf-8")"""

    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to hash",
            },
            "algorithm": {
                "type": "string",
                "description": "Hash algorithm to use",
                "enum": ["md5", "sha1", "sha256", "sha512", "blake2b", "blake2s"],
                "default": "sha256",
            },
            "encoding": {
                "type": "string",
                "description": "Text encoding",
                "default": "utf-8",
            },
        },
        "required": ["text"],
    }

    async def execute(
        self,
        text: str,
        algorithm: str = "sha256",
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the hash text tool."""
        log.info("hash_text_start", algorithm=algorithm, text_length=len(text))

        try:
            algorithm = algorithm.lower()
            if algorithm not in HASH_ALGORITHMS:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported algorithm: {algorithm}. Supported: {', '.join(HASH_ALGORITHMS.keys())}",
                )

            # Encode and hash
            try:
                text_bytes = text.encode(encoding)
            except LookupError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown encoding: {encoding}",
                )

            hasher = HASH_ALGORITHMS[algorithm]()
            hasher.update(text_bytes)
            hash_digest = hasher.hexdigest()

            # Truncate preview if text is long
            preview = text[:50] + "..." if len(text) > 50 else text
            preview = preview.replace("\n", "\\n")

            output = f"""**Text Hash Result**

**Input:** `{preview}`
**Algorithm:** {algorithm.upper()}
**Hash:** `{hash_digest}`
**Input Length:** {len(text)} characters ({len(text_bytes)} bytes)"""

            log.info("hash_text_success", algorithm=algorithm, hash=hash_digest[:16])

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "algorithm": algorithm,
                    "hash": hash_digest,
                    "input_length": len(text),
                    "input_bytes": len(text_bytes),
                    "encoding": encoding,
                },
            )

        except Exception as e:
            log.error("hash_text_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class EncodeBase64Tool(Tool):
    """Encode or decode Base64 data."""

    name = "encode_base64"
    description = """Encode text/binary to Base64 or decode Base64 back to text.

Supports standard Base64 and URL-safe Base64 variants.

Examples:
- encode_base64(data="Hello, World!", mode="encode")
- encode_base64(data="SGVsbG8sIFdvcmxkIQ==", mode="decode")
- encode_base64(data="data+with/special", mode="encode", url_safe=True)"""

    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "Data to encode or decode",
            },
            "mode": {
                "type": "string",
                "description": "Operation mode",
                "enum": ["encode", "decode"],
                "default": "encode",
            },
            "url_safe": {
                "type": "boolean",
                "description": "Use URL-safe Base64 (replaces +/ with -_)",
                "default": False,
            },
        },
        "required": ["data"],
    }

    async def execute(
        self,
        data: str,
        mode: str = "encode",
        url_safe: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the Base64 encode/decode tool."""
        log.info("encode_base64_start", mode=mode, url_safe=url_safe)

        try:
            if mode == "encode":
                data_bytes = data.encode("utf-8")
                if url_safe:
                    result = base64.urlsafe_b64encode(data_bytes).decode("ascii")
                else:
                    result = base64.b64encode(data_bytes).decode("ascii")

                output = f"""**Base64 Encode Result**

**Input:** `{data[:50]}{'...' if len(data) > 50 else ''}`
**Output:** `{result}`
**URL-Safe:** {'Yes' if url_safe else 'No'}
**Input Length:** {len(data)} chars
**Output Length:** {len(result)} chars"""

                return ToolResult(
                    success=True,
                    output=output,
                    metadata={
                        "mode": "encode",
                        "url_safe": url_safe,
                        "result": result,
                        "input_length": len(data),
                        "output_length": len(result),
                    },
                )

            else:  # decode
                try:
                    if url_safe:
                        # Add padding if needed
                        padded = data + "=" * (4 - len(data) % 4) if len(data) % 4 else data
                        result_bytes = base64.urlsafe_b64decode(padded)
                    else:
                        result_bytes = base64.b64decode(data)

                    # Try to decode as UTF-8 text
                    try:
                        result = result_bytes.decode("utf-8")
                        is_text = True
                    except UnicodeDecodeError:
                        # Binary data - show hex representation
                        result = result_bytes.hex()
                        is_text = False

                    output = f"""**Base64 Decode Result**

**Input:** `{data[:50]}{'...' if len(data) > 50 else ''}`
**Output:** `{result[:100]}{'...' if len(result) > 100 else ''}`
**Output Type:** {'Text (UTF-8)' if is_text else 'Binary (hex)'}
**Output Length:** {len(result_bytes)} bytes"""

                    return ToolResult(
                        success=True,
                        output=output,
                        metadata={
                            "mode": "decode",
                            "url_safe": url_safe,
                            "result": result,
                            "is_text": is_text,
                            "output_bytes": len(result_bytes),
                        },
                    )

                except Exception as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid Base64 data: {e}",
                    )

        except Exception as e:
            log.error("encode_base64_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class EncodeUrlTool(Tool):
    """URL encode or decode text."""

    name = "encode_url"
    description = """URL encode or decode text for safe use in URLs.

Supports both standard encoding and plus-style encoding for query strings.

Examples:
- encode_url(data="Hello World!", mode="encode")
- encode_url(data="Hello%20World%21", mode="decode")
- encode_url(data="key=value&foo=bar", mode="encode", plus_mode=True)"""

    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "Data to encode or decode",
            },
            "mode": {
                "type": "string",
                "description": "Operation mode",
                "enum": ["encode", "decode"],
                "default": "encode",
            },
            "plus_mode": {
                "type": "boolean",
                "description": "Use + for spaces (query string style) instead of %20",
                "default": False,
            },
            "safe": {
                "type": "string",
                "description": "Characters to NOT encode (for encode mode)",
                "default": "",
            },
        },
        "required": ["data"],
    }

    async def execute(
        self,
        data: str,
        mode: str = "encode",
        plus_mode: bool = False,
        safe: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the URL encode/decode tool."""
        log.info("encode_url_start", mode=mode, plus_mode=plus_mode)

        try:
            if mode == "encode":
                if plus_mode:
                    result = quote_plus(data, safe=safe)
                else:
                    result = quote(data, safe=safe)

                output = f"""**URL Encode Result**

**Input:** `{data[:50]}{'...' if len(data) > 50 else ''}`
**Output:** `{result[:100]}{'...' if len(result) > 100 else ''}`
**Plus Mode:** {'Yes (spaces become +)' if plus_mode else 'No (spaces become %20)'}
**Safe Chars:** `{safe}` (not encoded)"""

                return ToolResult(
                    success=True,
                    output=output,
                    metadata={
                        "mode": "encode",
                        "plus_mode": plus_mode,
                        "result": result,
                        "safe": safe,
                    },
                )

            else:  # decode
                if plus_mode:
                    result = unquote_plus(data)
                else:
                    result = unquote(data)

                output = f"""**URL Decode Result**

**Input:** `{data[:50]}{'...' if len(data) > 50 else ''}`
**Output:** `{result[:100]}{'...' if len(result) > 100 else ''}`
**Plus Mode:** {'Yes (+ becomes space)' if plus_mode else 'No'}"""

                return ToolResult(
                    success=True,
                    output=output,
                    metadata={
                        "mode": "decode",
                        "plus_mode": plus_mode,
                        "result": result,
                    },
                )

        except Exception as e:
            log.error("encode_url_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class JwtDecodeTool(Tool):
    """Decode and inspect JWT tokens."""

    name = "jwt_decode"
    description = """Decode a JWT token to inspect its header and payload.

By default, decodes WITHOUT verification (inspection mode).
Can optionally verify with a secret key.

Examples:
- jwt_decode(token="eyJhbGciOiJIUzI1NiIs...")
- jwt_decode(token="eyJ...", verify=True, secret="my-secret")

Note: Unverified decoding is useful for debugging but should not be
used to trust the token's claims."""

    parameters = {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "JWT token to decode",
            },
            "verify": {
                "type": "boolean",
                "description": "Verify signature (requires secret)",
                "default": False,
            },
            "secret": {
                "type": "string",
                "description": "Secret key for verification (if verify=True)",
            },
            "algorithms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Allowed algorithms for verification",
                "default": ["HS256", "HS384", "HS512"],
            },
        },
        "required": ["token"],
    }

    async def execute(
        self,
        token: str,
        verify: bool = False,
        secret: Optional[str] = None,
        algorithms: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the JWT decode tool."""
        log.info("jwt_decode_start", verify=verify)

        try:
            import jwt as pyjwt
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="PyJWT not installed. Install with: pip install PyJWT",
            )

        try:
            if algorithms is None:
                algorithms = ["HS256", "HS384", "HS512"]

            # Get header without verification
            try:
                header = pyjwt.get_unverified_header(token)
            except pyjwt.exceptions.DecodeError as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid JWT format: {e}",
                )

            if verify:
                if not secret:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Secret key required for verification",
                    )

                try:
                    payload = pyjwt.decode(
                        token, secret, algorithms=algorithms
                    )
                    verified = True
                except pyjwt.exceptions.InvalidSignatureError:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Invalid signature - token verification failed",
                    )
                except pyjwt.exceptions.ExpiredSignatureError:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Token has expired",
                    )
                except pyjwt.exceptions.InvalidTokenError as e:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid token: {e}",
                    )
            else:
                # Decode without verification
                payload = pyjwt.decode(
                    token, options={"verify_signature": False}
                )
                verified = False

            # Format timestamps if present
            payload_display = dict(payload)
            for ts_field in ("exp", "iat", "nbf"):
                if ts_field in payload_display and isinstance(payload_display[ts_field], int):
                    ts = payload_display[ts_field]
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    payload_display[f"{ts_field}_readable"] = dt.isoformat()

            header_json = json.dumps(header, indent=2)
            payload_json = json.dumps(payload_display, indent=2)

            output = f"""**JWT Decode Result**

**Verified:** {'Yes' if verified else 'No (inspection mode)'}

**Header:**
```json
{header_json}
```

**Payload:**
```json
{payload_json}
```"""

            if not verified:
                output += "\n\n*Warning: Token was decoded without verification. Do not trust claims.*"

            log.info("jwt_decode_success", verified=verified, algorithm=header.get("alg"))

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "header": header,
                    "payload": dict(payload),
                    "verified": verified,
                    "algorithm": header.get("alg"),
                },
            )

        except Exception as e:
            log.error("jwt_decode_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class JwtGenerateTool(Tool):
    """Generate JWT tokens."""

    name = "jwt_generate"
    description = """Generate a JWT token with custom payload.

Supports HS256, HS384, and HS512 algorithms.
Can set expiration time automatically.

Examples:
- jwt_generate(payload={"user_id": 123}, secret="my-secret")
- jwt_generate(payload={"sub": "user@example.com"}, secret="key", expiration_minutes=60)
- jwt_generate(payload={"role": "admin"}, secret="key", algorithm="HS512")"""

    parameters = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "description": "JWT payload (claims)",
            },
            "secret": {
                "type": "string",
                "description": "Secret key for signing",
            },
            "algorithm": {
                "type": "string",
                "description": "Signing algorithm",
                "enum": ["HS256", "HS384", "HS512"],
                "default": "HS256",
            },
            "expiration_minutes": {
                "type": "integer",
                "description": "Token expiration in minutes (optional)",
            },
        },
        "required": ["payload", "secret"],
    }

    async def execute(
        self,
        payload: dict[str, Any],
        secret: str,
        algorithm: str = "HS256",
        expiration_minutes: Optional[int] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the JWT generate tool."""
        log.info("jwt_generate_start", algorithm=algorithm)

        try:
            import jwt as pyjwt
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="PyJWT not installed. Install with: pip install PyJWT",
            )

        try:
            # Build payload with timestamps
            token_payload = dict(payload)
            now = datetime.now(tz=timezone.utc)

            # Add issued-at time
            if "iat" not in token_payload:
                token_payload["iat"] = int(now.timestamp())

            # Add expiration if requested
            if expiration_minutes is not None:
                exp = now + timedelta(minutes=expiration_minutes)
                token_payload["exp"] = int(exp.timestamp())

            # Generate token
            token = pyjwt.encode(token_payload, secret, algorithm=algorithm)

            # Format output
            exp_info = ""
            if "exp" in token_payload:
                exp_dt = datetime.fromtimestamp(token_payload["exp"], tz=timezone.utc)
                exp_info = f"\n**Expires:** {exp_dt.isoformat()}"

            output = f"""**JWT Generated**

**Token:**
```
{token}
```

**Algorithm:** {algorithm}
**Issued At:** {now.isoformat()}{exp_info}

**Payload:**
```json
{json.dumps(token_payload, indent=2)}
```"""

            log.info("jwt_generate_success", algorithm=algorithm)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "token": token,
                    "algorithm": algorithm,
                    "payload": token_payload,
                    "issued_at": now.isoformat(),
                    "expires_at": (
                        datetime.fromtimestamp(
                            token_payload["exp"], tz=timezone.utc
                        ).isoformat()
                        if "exp" in token_payload
                        else None
                    ),
                },
            )

        except Exception as e:
            log.error("jwt_generate_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class UuidGenerateTool(Tool):
    """Generate UUIDs."""

    name = "uuid_generate"
    description = """Generate UUID identifiers.

Supports:
- UUID v1: Time-based (includes MAC address)
- UUID v4: Random (most common)
- UUID v5: Name-based with namespace (deterministic)

Examples:
- uuid_generate(version=4)
- uuid_generate(version=4, count=5)
- uuid_generate(version=5, namespace="dns", name="example.com")
- uuid_generate(version=1)"""

    parameters = {
        "type": "object",
        "properties": {
            "version": {
                "type": "integer",
                "description": "UUID version (1, 4, or 5)",
                "enum": [1, 4, 5],
                "default": 4,
            },
            "count": {
                "type": "integer",
                "description": "Number of UUIDs to generate",
                "default": 1,
            },
            "namespace": {
                "type": "string",
                "description": "Namespace for UUID v5 (dns, url, oid, x500)",
                "enum": ["dns", "url", "oid", "x500"],
            },
            "name": {
                "type": "string",
                "description": "Name for UUID v5",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        version: int = 4,
        count: int = 1,
        namespace: Optional[str] = None,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the UUID generate tool."""
        log.info("uuid_generate_start", version=version, count=count)

        try:
            if version not in (1, 4, 5):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported UUID version: {version}. Use 1, 4, or 5.",
                )

            if count < 1 or count > 100:
                return ToolResult(
                    success=False,
                    output="",
                    error="Count must be between 1 and 100",
                )

            if version == 5:
                if not namespace or not name:
                    return ToolResult(
                        success=False,
                        output="",
                        error="UUID v5 requires both namespace and name parameters",
                    )
                if namespace not in UUID_NAMESPACES:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid namespace: {namespace}. Use: dns, url, oid, x500",
                    )

            uuids = []
            for _ in range(count):
                if version == 1:
                    u = uuid_module.uuid1()
                elif version == 4:
                    u = uuid_module.uuid4()
                else:  # version == 5
                    ns = UUID_NAMESPACES[namespace]
                    u = uuid_module.uuid5(ns, name)
                uuids.append(str(u))

            # For v5, all generated UUIDs are the same (deterministic)
            if version == 5 and count > 1:
                uuids = [uuids[0]] * count

            uuid_list = "\n".join(f"- `{u}`" for u in uuids)

            version_desc = {
                1: "Time-based (includes MAC address)",
                4: "Random",
                5: f"Name-based (namespace={namespace}, name={name})",
            }

            output = f"""**UUID Generation Result**

**Version:** {version} - {version_desc[version]}
**Count:** {count}

**Generated UUIDs:**
{uuid_list}"""

            log.info("uuid_generate_success", version=version, count=count)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "version": version,
                    "count": count,
                    "uuids": uuids,
                    "namespace": namespace,
                    "name": name,
                },
            )

        except Exception as e:
            log.error("uuid_generate_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class EncryptFileTool(Tool):
    """Encrypt a file using AES encryption."""

    name = "encrypt_file"
    description = """Encrypt a file using password-based AES encryption (Fernet).

Uses PBKDF2 key derivation for password-based encryption.
Creates an encrypted file with .encrypted extension by default.

Examples:
- encrypt_file(input_path="secret.txt", password="my-password")
- encrypt_file(input_path="data.json", password="pass", output_path="data.enc")

Note: The password is used with PBKDF2 to derive an encryption key.
Store the password securely - it's required for decryption."""

    parameters = {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to file to encrypt",
            },
            "password": {
                "type": "string",
                "description": "Password for encryption",
            },
            "output_path": {
                "type": "string",
                "description": "Output path (default: input_path + .encrypted)",
            },
        },
        "required": ["input_path", "password"],
    }

    async def execute(
        self,
        input_path: str,
        password: str,
        output_path: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the file encryption tool."""
        log.info("encrypt_file_start", input_path=input_path)

        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="cryptography not installed. Install with: pip install cryptography",
            )

        try:
            resolved_input = self._resolve_path(input_path)

            if not os.path.exists(resolved_input):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {input_path}",
                )

            if os.path.isdir(resolved_input):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is a directory: {input_path}",
                )

            # Determine output path
            if output_path:
                resolved_output = self._resolve_path(output_path)
            else:
                resolved_output = Path(str(resolved_input) + ".encrypted")

            # Generate salt and derive key
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

            # Encrypt file
            fernet = Fernet(key)
            with open(resolved_input, "rb") as f:
                data = f.read()

            encrypted_data = fernet.encrypt(data)

            # Write output: salt + encrypted data
            with open(resolved_output, "wb") as f:
                f.write(salt)
                f.write(encrypted_data)

            input_size = os.path.getsize(resolved_input)
            output_size = os.path.getsize(resolved_output)

            output = f"""**File Encryption Complete**

**Input:** {input_path} ({input_size:,} bytes)
**Output:** {resolved_output} ({output_size:,} bytes)
**Encryption:** AES-128-CBC (Fernet)
**Key Derivation:** PBKDF2-SHA256 (480,000 iterations)

*Store your password securely - it's required for decryption.*"""

            log.info(
                "encrypt_file_success",
                input_size=input_size,
                output_size=output_size,
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "input_path": str(resolved_input),
                    "output_path": str(resolved_output),
                    "input_size": input_size,
                    "output_size": output_size,
                    "encryption": "Fernet (AES-128-CBC)",
                    "kdf": "PBKDF2-SHA256",
                    "kdf_iterations": 480000,
                },
            )

        except Exception as e:
            log.error("encrypt_file_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))


class DecryptFileTool(Tool):
    """Decrypt a file encrypted with encrypt_file."""

    name = "decrypt_file"
    description = """Decrypt a file that was encrypted with encrypt_file.

Requires the same password used for encryption.

Examples:
- decrypt_file(input_path="secret.txt.encrypted", password="my-password")
- decrypt_file(input_path="data.enc", password="pass", output_path="data.json")"""

    parameters = {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to encrypted file",
            },
            "password": {
                "type": "string",
                "description": "Password for decryption",
            },
            "output_path": {
                "type": "string",
                "description": "Output path (default: input without .encrypted)",
            },
        },
        "required": ["input_path", "password"],
    }

    async def execute(
        self,
        input_path: str,
        password: str,
        output_path: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the file decryption tool."""
        log.info("decrypt_file_start", input_path=input_path)

        try:
            from cryptography.fernet import Fernet, InvalidToken
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="cryptography not installed. Install with: pip install cryptography",
            )

        try:
            resolved_input = self._resolve_path(input_path)

            if not os.path.exists(resolved_input):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {input_path}",
                )

            if os.path.isdir(resolved_input):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is a directory: {input_path}",
                )

            # Determine output path
            if output_path:
                resolved_output = self._resolve_path(output_path)
            else:
                # Remove .encrypted extension if present
                input_str = str(resolved_input)
                if input_str.endswith(".encrypted"):
                    resolved_output = Path(input_str[:-10])
                else:
                    resolved_output = Path(input_str + ".decrypted")

            # Read encrypted file
            with open(resolved_input, "rb") as f:
                salt = f.read(16)
                if len(salt) < 16:
                    return ToolResult(
                        success=False,
                        output="",
                        error="Invalid encrypted file format (too small)",
                    )
                encrypted_data = f.read()

            # Derive key from password
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

            # Decrypt
            fernet = Fernet(key)
            try:
                decrypted_data = fernet.decrypt(encrypted_data)
            except InvalidToken:
                return ToolResult(
                    success=False,
                    output="",
                    error="Decryption failed - wrong password or corrupted file",
                )

            # Write output
            with open(resolved_output, "wb") as f:
                f.write(decrypted_data)

            input_size = os.path.getsize(resolved_input)
            output_size = os.path.getsize(resolved_output)

            output = f"""**File Decryption Complete**

**Input:** {input_path} ({input_size:,} bytes)
**Output:** {resolved_output} ({output_size:,} bytes)"""

            log.info(
                "decrypt_file_success",
                input_size=input_size,
                output_size=output_size,
            )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "input_path": str(resolved_input),
                    "output_path": str(resolved_output),
                    "input_size": input_size,
                    "output_size": output_size,
                },
            )

        except Exception as e:
            log.error("decrypt_file_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))
