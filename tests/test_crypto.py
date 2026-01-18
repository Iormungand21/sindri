"""Tests for crypto and encoding tools."""

import base64
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sindri.tools.crypto import (
    DecryptFileTool,
    EncodeBase64Tool,
    EncodeUrlTool,
    EncryptFileTool,
    HashFileTool,
    HashTextTool,
    JwtDecodeTool,
    JwtGenerateTool,
    UuidGenerateTool,
)


# =============================================================================
# HashFileTool Tests
# =============================================================================


class TestHashFileTool:
    """Tests for HashFileTool."""

    @pytest.fixture
    def tool(self):
        return HashFileTool()

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file with known content."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Hello, World!")
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_hash_file_sha256(self, tool, temp_file):
        """Test SHA256 hashing (default)."""
        result = await tool.execute(file_path=temp_file)
        assert result.success
        assert result.metadata["algorithm"] == "sha256"
        assert len(result.metadata["hash"]) == 64  # SHA256 = 64 hex chars
        assert "SHA256" in result.output

    @pytest.mark.asyncio
    async def test_hash_file_md5(self, tool, temp_file):
        """Test MD5 hashing."""
        result = await tool.execute(file_path=temp_file, algorithm="md5")
        assert result.success
        assert result.metadata["algorithm"] == "md5"
        assert len(result.metadata["hash"]) == 32  # MD5 = 32 hex chars
        assert "MD5" in result.output
        assert "checksums only" in result.output  # Security warning

    @pytest.mark.asyncio
    async def test_hash_file_sha512(self, tool, temp_file):
        """Test SHA512 hashing."""
        result = await tool.execute(file_path=temp_file, algorithm="sha512")
        assert result.success
        assert result.metadata["algorithm"] == "sha512"
        assert len(result.metadata["hash"]) == 128  # SHA512 = 128 hex chars

    @pytest.mark.asyncio
    async def test_hash_file_blake2b(self, tool, temp_file):
        """Test BLAKE2b hashing."""
        result = await tool.execute(file_path=temp_file, algorithm="blake2b")
        assert result.success
        assert result.metadata["algorithm"] == "blake2b"
        # BLAKE2b default = 64 bytes = 128 hex chars
        assert len(result.metadata["hash"]) == 128

    @pytest.mark.asyncio
    async def test_hash_file_nonexistent(self, tool):
        """Test hashing nonexistent file."""
        result = await tool.execute(file_path="/nonexistent/file.txt")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_hash_file_directory(self, tool):
        """Test hashing a directory (should fail)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute(file_path=tmpdir)
            assert not result.success
            assert "directory" in result.error.lower()

    @pytest.mark.asyncio
    async def test_hash_file_unsupported_algorithm(self, tool, temp_file):
        """Test unsupported algorithm."""
        result = await tool.execute(file_path=temp_file, algorithm="sha3-256")
        assert not result.success
        assert "unsupported" in result.error.lower()


# =============================================================================
# HashTextTool Tests
# =============================================================================


class TestHashTextTool:
    """Tests for HashTextTool."""

    @pytest.fixture
    def tool(self):
        return HashTextTool()

    @pytest.mark.asyncio
    async def test_hash_text_sha256(self, tool):
        """Test SHA256 text hashing."""
        result = await tool.execute(text="Hello, World!")
        assert result.success
        assert result.metadata["algorithm"] == "sha256"
        assert len(result.metadata["hash"]) == 64

    @pytest.mark.asyncio
    async def test_hash_text_md5(self, tool):
        """Test MD5 text hashing."""
        result = await tool.execute(text="test", algorithm="md5")
        assert result.success
        # Known MD5 of "test"
        assert result.metadata["hash"] == "098f6bcd4621d373cade4e832627b4f6"

    @pytest.mark.asyncio
    async def test_hash_text_empty(self, tool):
        """Test hashing empty string."""
        result = await tool.execute(text="")
        assert result.success
        assert result.metadata["input_length"] == 0

    @pytest.mark.asyncio
    async def test_hash_text_unicode(self, tool):
        """Test hashing unicode text."""
        result = await tool.execute(text="Hello, 世界! 🌍")
        assert result.success
        assert result.metadata["input_bytes"] > result.metadata["input_length"]

    @pytest.mark.asyncio
    async def test_hash_text_different_encoding(self, tool):
        """Test hashing with different encoding."""
        result = await tool.execute(text="test", encoding="latin-1")
        assert result.success
        assert result.metadata["encoding"] == "latin-1"

    @pytest.mark.asyncio
    async def test_hash_text_invalid_encoding(self, tool):
        """Test invalid encoding."""
        result = await tool.execute(text="test", encoding="invalid-encoding")
        assert not result.success
        assert "encoding" in result.error.lower()


# =============================================================================
# EncodeBase64Tool Tests
# =============================================================================


class TestEncodeBase64Tool:
    """Tests for EncodeBase64Tool."""

    @pytest.fixture
    def tool(self):
        return EncodeBase64Tool()

    @pytest.mark.asyncio
    async def test_encode_base64(self, tool):
        """Test base64 encoding."""
        result = await tool.execute(data="Hello, World!", mode="encode")
        assert result.success
        assert result.metadata["result"] == "SGVsbG8sIFdvcmxkIQ=="
        assert result.metadata["mode"] == "encode"

    @pytest.mark.asyncio
    async def test_decode_base64(self, tool):
        """Test base64 decoding."""
        result = await tool.execute(data="SGVsbG8sIFdvcmxkIQ==", mode="decode")
        assert result.success
        assert result.metadata["result"] == "Hello, World!"
        assert result.metadata["mode"] == "decode"

    @pytest.mark.asyncio
    async def test_encode_url_safe_base64(self, tool):
        """Test URL-safe base64 encoding."""
        result = await tool.execute(data="test+/data", mode="encode", url_safe=True)
        assert result.success
        assert result.metadata["url_safe"]
        # URL-safe encoding shouldn't have + or /
        assert "+" not in result.metadata["result"]
        assert "/" not in result.metadata["result"]

    @pytest.mark.asyncio
    async def test_decode_invalid_base64(self, tool):
        """Test decoding invalid base64."""
        result = await tool.execute(data="not-valid-base64!!!", mode="decode")
        assert not result.success
        assert "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_encode_empty_string(self, tool):
        """Test encoding empty string."""
        result = await tool.execute(data="", mode="encode")
        assert result.success
        assert result.metadata["result"] == ""

    @pytest.mark.asyncio
    async def test_roundtrip_base64(self, tool):
        """Test encoding then decoding."""
        original = "Test data with special chars: !@#$%"
        encode_result = await tool.execute(data=original, mode="encode")
        assert encode_result.success

        decode_result = await tool.execute(
            data=encode_result.metadata["result"], mode="decode"
        )
        assert decode_result.success
        assert decode_result.metadata["result"] == original


# =============================================================================
# EncodeUrlTool Tests
# =============================================================================


class TestEncodeUrlTool:
    """Tests for EncodeUrlTool."""

    @pytest.fixture
    def tool(self):
        return EncodeUrlTool()

    @pytest.mark.asyncio
    async def test_encode_url(self, tool):
        """Test URL encoding."""
        result = await tool.execute(data="Hello World!", mode="encode")
        assert result.success
        assert result.metadata["result"] == "Hello%20World%21"

    @pytest.mark.asyncio
    async def test_decode_url(self, tool):
        """Test URL decoding."""
        result = await tool.execute(data="Hello%20World%21", mode="decode")
        assert result.success
        assert result.metadata["result"] == "Hello World!"

    @pytest.mark.asyncio
    async def test_encode_url_plus_mode(self, tool):
        """Test URL encoding with plus mode."""
        result = await tool.execute(data="Hello World", mode="encode", plus_mode=True)
        assert result.success
        assert result.metadata["result"] == "Hello+World"
        assert result.metadata["plus_mode"]

    @pytest.mark.asyncio
    async def test_decode_url_plus_mode(self, tool):
        """Test URL decoding with plus mode."""
        result = await tool.execute(data="Hello+World", mode="decode", plus_mode=True)
        assert result.success
        assert result.metadata["result"] == "Hello World"

    @pytest.mark.asyncio
    async def test_encode_url_safe_chars(self, tool):
        """Test URL encoding with safe characters."""
        result = await tool.execute(data="a/b/c", mode="encode", safe="/")
        assert result.success
        assert "/" in result.metadata["result"]  # Slashes preserved

    @pytest.mark.asyncio
    async def test_encode_unicode(self, tool):
        """Test URL encoding unicode."""
        result = await tool.execute(data="hello=世界", mode="encode")
        assert result.success
        assert "%" in result.metadata["result"]


# =============================================================================
# JwtDecodeTool Tests
# =============================================================================


class TestJwtDecodeTool:
    """Tests for JwtDecodeTool."""

    @pytest.fixture
    def tool(self):
        return JwtDecodeTool()

    @pytest.fixture
    def sample_token(self):
        """Create a sample JWT token."""
        import jwt

        payload = {"sub": "user123", "name": "Test User", "iat": 1700000000}
        return jwt.encode(payload, "secret", algorithm="HS256")

    @pytest.mark.asyncio
    async def test_decode_jwt_unverified(self, tool, sample_token):
        """Test decoding JWT without verification."""
        result = await tool.execute(token=sample_token)
        assert result.success
        assert not result.metadata["verified"]
        assert result.metadata["payload"]["sub"] == "user123"
        assert result.metadata["header"]["alg"] == "HS256"
        assert "Warning" in result.output

    @pytest.mark.asyncio
    async def test_decode_jwt_verified(self, tool, sample_token):
        """Test decoding JWT with verification."""
        result = await tool.execute(token=sample_token, verify=True, secret="secret")
        assert result.success
        assert result.metadata["verified"]
        assert result.metadata["payload"]["sub"] == "user123"

    @pytest.mark.asyncio
    async def test_decode_jwt_wrong_secret(self, tool, sample_token):
        """Test decoding JWT with wrong secret."""
        result = await tool.execute(
            token=sample_token, verify=True, secret="wrong-secret"
        )
        assert not result.success
        assert "signature" in result.error.lower() or "verification" in result.error.lower()

    @pytest.mark.asyncio
    async def test_decode_jwt_invalid_token(self, tool):
        """Test decoding invalid JWT."""
        result = await tool.execute(token="not.a.valid.jwt")
        assert not result.success
        assert "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_decode_jwt_expired(self, tool):
        """Test decoding expired JWT with verification."""
        import jwt

        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        token = jwt.encode(
            {"sub": "user", "exp": int(past.timestamp())}, "secret", algorithm="HS256"
        )

        # Unverified should work
        result = await tool.execute(token=token, verify=False)
        assert result.success

        # Verified should fail due to expiration
        result = await tool.execute(token=token, verify=True, secret="secret")
        assert not result.success
        assert "expired" in result.error.lower()

    @pytest.mark.asyncio
    async def test_decode_jwt_missing_secret(self, tool, sample_token):
        """Test verification without secret."""
        result = await tool.execute(token=sample_token, verify=True)
        assert not result.success
        assert "secret" in result.error.lower()


# =============================================================================
# JwtGenerateTool Tests
# =============================================================================


class TestJwtGenerateTool:
    """Tests for JwtGenerateTool."""

    @pytest.fixture
    def tool(self):
        return JwtGenerateTool()

    @pytest.mark.asyncio
    async def test_generate_jwt_basic(self, tool):
        """Test basic JWT generation."""
        result = await tool.execute(
            payload={"user_id": 123, "role": "admin"}, secret="my-secret"
        )
        assert result.success
        assert "token" in result.metadata
        # Token should have 3 parts
        assert result.metadata["token"].count(".") == 2

    @pytest.mark.asyncio
    async def test_generate_jwt_with_expiration(self, tool):
        """Test JWT generation with expiration."""
        result = await tool.execute(
            payload={"user_id": 123}, secret="secret", expiration_minutes=60
        )
        assert result.success
        assert "exp" in result.metadata["payload"]
        assert result.metadata["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_generate_jwt_hs512(self, tool):
        """Test JWT generation with HS512."""
        result = await tool.execute(
            payload={"data": "test"}, secret="secret", algorithm="HS512"
        )
        assert result.success
        assert result.metadata["algorithm"] == "HS512"

    @pytest.mark.asyncio
    async def test_generate_jwt_auto_iat(self, tool):
        """Test JWT generation auto-adds iat claim."""
        result = await tool.execute(payload={"data": "test"}, secret="secret")
        assert result.success
        assert "iat" in result.metadata["payload"]

    @pytest.mark.asyncio
    async def test_generate_and_decode_roundtrip(self, tool):
        """Test generating then decoding a token."""
        payload = {"user_id": 456, "email": "test@example.com"}
        secret = "roundtrip-secret"

        # Generate
        gen_result = await tool.execute(payload=payload, secret=secret)
        assert gen_result.success

        # Decode with verification
        decode_tool = JwtDecodeTool()
        decode_result = await decode_tool.execute(
            token=gen_result.metadata["token"], verify=True, secret=secret
        )
        assert decode_result.success
        assert decode_result.metadata["payload"]["user_id"] == 456
        assert decode_result.metadata["payload"]["email"] == "test@example.com"


# =============================================================================
# UuidGenerateTool Tests
# =============================================================================


class TestUuidGenerateTool:
    """Tests for UuidGenerateTool."""

    @pytest.fixture
    def tool(self):
        return UuidGenerateTool()

    @pytest.mark.asyncio
    async def test_generate_uuid_v4_default(self, tool):
        """Test UUID v4 generation (default)."""
        result = await tool.execute()
        assert result.success
        assert result.metadata["version"] == 4
        assert len(result.metadata["uuids"]) == 1
        # UUID format: 8-4-4-4-12
        assert len(result.metadata["uuids"][0]) == 36
        assert result.metadata["uuids"][0].count("-") == 4

    @pytest.mark.asyncio
    async def test_generate_uuid_v1(self, tool):
        """Test UUID v1 generation."""
        result = await tool.execute(version=1)
        assert result.success
        assert result.metadata["version"] == 1

    @pytest.mark.asyncio
    async def test_generate_uuid_v5(self, tool):
        """Test UUID v5 generation."""
        result = await tool.execute(version=5, namespace="dns", name="example.com")
        assert result.success
        assert result.metadata["version"] == 5
        # v5 is deterministic - same inputs = same output
        result2 = await tool.execute(version=5, namespace="dns", name="example.com")
        assert result.metadata["uuids"][0] == result2.metadata["uuids"][0]

    @pytest.mark.asyncio
    async def test_generate_multiple_uuids(self, tool):
        """Test generating multiple UUIDs."""
        result = await tool.execute(version=4, count=5)
        assert result.success
        assert len(result.metadata["uuids"]) == 5
        # All should be unique (v4)
        assert len(set(result.metadata["uuids"])) == 5

    @pytest.mark.asyncio
    async def test_generate_uuid_v5_missing_params(self, tool):
        """Test UUID v5 without required params."""
        result = await tool.execute(version=5)
        assert not result.success
        assert "namespace" in result.error.lower() or "name" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_uuid_invalid_version(self, tool):
        """Test invalid UUID version."""
        result = await tool.execute(version=3)
        assert not result.success
        assert "unsupported" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_uuid_count_limit(self, tool):
        """Test UUID count limits."""
        result = await tool.execute(count=101)
        assert not result.success
        assert "100" in result.error or "count" in result.error.lower()


# =============================================================================
# EncryptFileTool Tests
# =============================================================================


class TestEncryptFileTool:
    """Tests for EncryptFileTool."""

    @pytest.fixture
    def tool(self):
        return EncryptFileTool()

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file with known content."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Secret data that needs protection!")
            temp_path = f.name
        yield temp_path
        # Clean up both original and encrypted
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        if os.path.exists(temp_path + ".encrypted"):
            os.unlink(temp_path + ".encrypted")

    @pytest.mark.asyncio
    async def test_encrypt_file_basic(self, tool, temp_file):
        """Test basic file encryption."""
        result = await tool.execute(input_path=temp_file, password="test-password")
        assert result.success
        assert os.path.exists(temp_file + ".encrypted")
        assert result.metadata["encryption"] == "Fernet (AES-128-CBC)"

    @pytest.mark.asyncio
    async def test_encrypt_file_custom_output(self, tool, temp_file):
        """Test encryption with custom output path."""
        output_path = temp_file + ".custom.enc"
        try:
            result = await tool.execute(
                input_path=temp_file, password="test", output_path=output_path
            )
            assert result.success
            assert os.path.exists(output_path)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @pytest.mark.asyncio
    async def test_encrypt_file_nonexistent(self, tool):
        """Test encrypting nonexistent file."""
        result = await tool.execute(
            input_path="/nonexistent/file.txt", password="test"
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_encrypt_file_directory(self, tool):
        """Test encrypting a directory (should fail)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute(input_path=tmpdir, password="test")
            assert not result.success
            assert "directory" in result.error.lower()


# =============================================================================
# DecryptFileTool Tests
# =============================================================================


class TestDecryptFileTool:
    """Tests for DecryptFileTool."""

    @pytest.fixture
    def decrypt_tool(self):
        return DecryptFileTool()

    @pytest.fixture
    def encrypt_tool(self):
        return EncryptFileTool()

    @pytest.fixture
    def encrypted_file(self, encrypt_tool):
        """Create an encrypted file for testing."""
        import asyncio

        original_content = "This is the secret content!"

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write(original_content)
            original_path = f.name

        encrypted_path = original_path + ".encrypted"

        # Encrypt the file
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            encrypt_tool.execute(input_path=original_path, password="decrypt-test")
        )
        loop.close()

        yield encrypted_path, original_content, "decrypt-test"

        # Cleanup
        for path in [original_path, encrypted_path, original_path + ".decrypted"]:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_decrypt_file_basic(self, decrypt_tool, encrypted_file):
        """Test basic file decryption."""
        encrypted_path, original_content, password = encrypted_file

        result = await decrypt_tool.execute(input_path=encrypted_path, password=password)
        assert result.success

        # Check decrypted content
        output_path = encrypted_path.replace(".encrypted", "")
        with open(output_path) as f:
            decrypted = f.read()
        assert decrypted == original_content

    @pytest.mark.asyncio
    async def test_decrypt_file_wrong_password(self, decrypt_tool, encrypted_file):
        """Test decryption with wrong password."""
        encrypted_path, _, _ = encrypted_file

        result = await decrypt_tool.execute(
            input_path=encrypted_path, password="wrong-password"
        )
        assert not result.success
        assert "wrong password" in result.error.lower() or "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_decrypt_file_nonexistent(self, decrypt_tool):
        """Test decrypting nonexistent file."""
        result = await decrypt_tool.execute(
            input_path="/nonexistent/file.encrypted", password="test"
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_decrypt_file_corrupted(self, decrypt_tool):
        """Test decrypting corrupted file."""
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, suffix=".encrypted"
        ) as f:
            # Write garbage data (16 byte "salt" + garbage)
            f.write(os.urandom(16) + b"not valid encrypted data")
            temp_path = f.name

        try:
            result = await decrypt_tool.execute(input_path=temp_path, password="test")
            assert not result.success
            assert "wrong password" in result.error.lower() or "corrupted" in result.error.lower() or "failed" in result.error.lower()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, encrypt_tool, decrypt_tool):
        """Test complete encryption/decryption roundtrip."""
        original_content = "Roundtrip test content with special chars: !@#$%^&*()"
        password = "roundtrip-password"

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write(original_content)
            original_path = f.name

        encrypted_path = original_path + ".encrypted"
        decrypted_path = original_path  # Will overwrite after decryption

        try:
            # Encrypt
            enc_result = await encrypt_tool.execute(
                input_path=original_path, password=password
            )
            assert enc_result.success

            # Delete original to prove we're reading from decrypted
            os.unlink(original_path)

            # Decrypt
            dec_result = await decrypt_tool.execute(
                input_path=encrypted_path, password=password
            )
            assert dec_result.success

            # Verify content
            with open(original_path) as f:
                decrypted = f.read()
            assert decrypted == original_content

        finally:
            for path in [original_path, encrypted_path]:
                if os.path.exists(path):
                    os.unlink(path)
