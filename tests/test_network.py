"""Tests for network and HTTP diagnostic tools."""

import asyncio
import socket
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.tools.network import (
    CurlGenerateTool,
    DnsLookupTool,
    HttpTraceTool,
    PingHostTool,
    PortCheckTool,
    SslAnalyzeTool,
)


# =============================================================================
# CurlGenerateTool Tests
# =============================================================================


class TestCurlGenerateTool:
    """Tests for curl command generation."""

    @pytest.fixture
    def tool(self):
        return CurlGenerateTool()

    @pytest.mark.asyncio
    async def test_basic_get(self, tool):
        """Test basic GET request generation."""
        result = await tool.execute(url="https://api.example.com/users")
        assert result.success is True
        assert "curl" in result.output
        assert "https://api.example.com/users" in result.output
        # GET is default, shouldn't have -X GET
        assert "-X" not in result.output or "GET" not in result.output

    @pytest.mark.asyncio
    async def test_post_with_json(self, tool):
        """Test POST request with JSON body."""
        result = await tool.execute(
            url="https://api.example.com/data",
            method="POST",
            json={"key": "value", "count": 42},
        )
        assert result.success is True
        assert "-X POST" in result.output or "-X 'POST'" in result.output
        assert "Content-Type: application/json" in result.output
        assert '{"key": "value", "count": 42}' in result.output

    @pytest.mark.asyncio
    async def test_with_headers(self, tool):
        """Test request with custom headers."""
        result = await tool.execute(
            url="https://api.example.com",
            headers={"Authorization": "Bearer token123", "Accept": "application/json"},
        )
        assert result.success is True
        assert "Authorization: Bearer token123" in result.output
        assert "Accept: application/json" in result.output

    @pytest.mark.asyncio
    async def test_with_query_params(self, tool):
        """Test request with query parameters."""
        result = await tool.execute(
            url="https://api.example.com/search",
            params={"q": "test", "page": "1"},
        )
        assert result.success is True
        # Parameters should be in URL
        assert "q=test" in result.output
        assert "page=1" in result.output

    @pytest.mark.asyncio
    async def test_basic_auth(self, tool):
        """Test basic authentication."""
        result = await tool.execute(
            url="https://api.example.com",
            auth={"type": "basic", "username": "user", "password": "pass"},
        )
        assert result.success is True
        assert "-u" in result.output
        assert "user:pass" in result.output

    @pytest.mark.asyncio
    async def test_bearer_auth(self, tool):
        """Test bearer token authentication."""
        result = await tool.execute(
            url="https://api.example.com",
            auth={"type": "bearer", "token": "mytoken123"},
        )
        assert result.success is True
        assert "Authorization: Bearer mytoken123" in result.output

    @pytest.mark.asyncio
    async def test_with_flags(self, tool):
        """Test various curl flags."""
        result = await tool.execute(
            url="https://api.example.com",
            follow_redirects=True,
            insecure=True,
            verbose=True,
        )
        assert result.success is True
        assert "-L" in result.output  # follow redirects
        assert "-k" in result.output  # insecure
        assert "-v" in result.output  # verbose

    @pytest.mark.asyncio
    async def test_put_with_data(self, tool):
        """Test PUT request with raw data."""
        result = await tool.execute(
            url="https://api.example.com/resource/1",
            method="PUT",
            data="raw body content",
        )
        assert result.success is True
        assert "-X PUT" in result.output or "-X 'PUT'" in result.output
        assert "raw body content" in result.output

    @pytest.mark.asyncio
    async def test_delete_method(self, tool):
        """Test DELETE method."""
        result = await tool.execute(
            url="https://api.example.com/resource/1",
            method="DELETE",
        )
        assert result.success is True
        assert "-X DELETE" in result.output or "-X 'DELETE'" in result.output

    @pytest.mark.asyncio
    async def test_metadata(self, tool):
        """Test metadata in result."""
        result = await tool.execute(url="https://api.example.com")
        assert result.success is True
        assert result.metadata["method"] == "GET"
        assert "command" in result.metadata


# =============================================================================
# DnsLookupTool Tests
# =============================================================================


class TestDnsLookupTool:
    """Tests for DNS lookup functionality."""

    @pytest.fixture
    def tool(self):
        return DnsLookupTool()

    @pytest.fixture
    def mock_resolver(self):
        """Create a mock DNS resolver."""
        with patch("sindri.tools.network.dns.resolver.Resolver") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance
            yield mock_instance

    @pytest.mark.asyncio
    async def test_dnspython_not_available(self):
        """Test behavior when dnspython is not installed."""
        with patch("sindri.tools.network.DNSPYTHON_AVAILABLE", False):
            tool = DnsLookupTool()
            result = await tool.execute(hostname="example.com")
            assert result.success is False
            assert "dnspython not installed" in result.error

    @pytest.mark.asyncio
    async def test_a_record_lookup(self, tool, mock_resolver):
        """Test A record lookup."""
        # Mock A record response
        mock_rdata = MagicMock()
        mock_rdata.__str__ = MagicMock(return_value="93.184.216.34")
        mock_rrset = MagicMock()
        mock_rrset.ttl = 300
        mock_answers = MagicMock()
        mock_answers.__iter__ = MagicMock(return_value=iter([mock_rdata]))
        mock_answers.rrset = mock_rrset
        mock_resolver.resolve.return_value = mock_answers

        result = await tool.execute(hostname="example.com", record_type="A")

        assert result.success is True
        assert "93.184.216.34" in result.output
        assert "A Records" in result.output
        mock_resolver.resolve.assert_called_with("example.com", "A")

    @pytest.mark.asyncio
    async def test_mx_record_lookup(self, tool, mock_resolver):
        """Test MX record lookup with priority."""
        mock_rdata = MagicMock()
        mock_rdata.__str__ = MagicMock(return_value="10 mail.example.com.")
        mock_rdata.preference = 10
        mock_rdata.exchange = "mail.example.com."
        mock_rrset = MagicMock()
        mock_rrset.ttl = 3600
        mock_answers = MagicMock()
        mock_answers.__iter__ = MagicMock(return_value=iter([mock_rdata]))
        mock_answers.rrset = mock_rrset
        mock_resolver.resolve.return_value = mock_answers

        result = await tool.execute(hostname="example.com", record_type="MX")

        assert result.success is True
        assert "MX Records" in result.output
        assert "priority" in result.output.lower()
        mock_resolver.resolve.assert_called_with("example.com", "MX")

    @pytest.mark.asyncio
    async def test_txt_record_lookup(self, tool, mock_resolver):
        """Test TXT record lookup."""
        mock_rdata = MagicMock()
        mock_rdata.__str__ = MagicMock(return_value="v=spf1 include:_spf.example.com ~all")
        mock_rrset = MagicMock()
        mock_rrset.ttl = 600
        mock_answers = MagicMock()
        mock_answers.__iter__ = MagicMock(return_value=iter([mock_rdata]))
        mock_answers.rrset = mock_rrset
        mock_resolver.resolve.return_value = mock_answers

        result = await tool.execute(hostname="example.com", record_type="TXT")

        assert result.success is True
        assert "TXT Records" in result.output
        mock_resolver.resolve.assert_called_with("example.com", "TXT")

    @pytest.mark.asyncio
    async def test_nxdomain(self, tool, mock_resolver):
        """Test NXDOMAIN (domain not found) handling."""
        import dns.resolver

        mock_resolver.resolve.side_effect = dns.resolver.NXDOMAIN()

        result = await tool.execute(hostname="nonexistent.invalid", record_type="A")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_timeout(self, tool, mock_resolver):
        """Test DNS timeout handling."""
        import dns.exception

        mock_resolver.resolve.side_effect = dns.exception.Timeout()

        result = await tool.execute(hostname="slow.example.com", record_type="A")

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_custom_nameserver(self, tool, mock_resolver):
        """Test using custom nameserver."""
        mock_rdata = MagicMock()
        mock_rdata.__str__ = MagicMock(return_value="1.2.3.4")
        mock_rrset = MagicMock()
        mock_rrset.ttl = 300
        mock_answers = MagicMock()
        mock_answers.__iter__ = MagicMock(return_value=iter([mock_rdata]))
        mock_answers.rrset = mock_rrset
        mock_resolver.resolve.return_value = mock_answers

        result = await tool.execute(
            hostname="example.com",
            record_type="A",
            nameserver="8.8.8.8",
        )

        assert result.success is True
        assert mock_resolver.nameservers == ["8.8.8.8"]

    @pytest.mark.asyncio
    async def test_metadata_contains_records(self, tool, mock_resolver):
        """Test that metadata contains parsed records."""
        mock_rdata = MagicMock()
        mock_rdata.__str__ = MagicMock(return_value="1.2.3.4")
        mock_rrset = MagicMock()
        mock_rrset.ttl = 300
        mock_answers = MagicMock()
        mock_answers.__iter__ = MagicMock(return_value=iter([mock_rdata]))
        mock_answers.rrset = mock_rrset
        mock_resolver.resolve.return_value = mock_answers

        result = await tool.execute(hostname="example.com", record_type="A")

        assert result.success is True
        assert "records" in result.metadata
        assert "A" in result.metadata["records"]


# =============================================================================
# PortCheckTool Tests
# =============================================================================


class TestPortCheckTool:
    """Tests for port checking functionality."""

    @pytest.fixture
    def tool(self):
        return PortCheckTool()

    @pytest.mark.asyncio
    async def test_single_port_open(self, tool):
        """Test checking a single open port."""
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_writer = AsyncMock()
            mock_conn.return_value = (MagicMock(), mock_writer)

            result = await tool.execute(host="example.com", port=443)

            assert result.success is True
            assert "OPEN" in result.output
            assert "443" in result.output

    @pytest.mark.asyncio
    async def test_single_port_closed(self, tool):
        """Test checking a closed port."""
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_conn.side_effect = ConnectionRefusedError()

            result = await tool.execute(host="example.com", port=9999)

            assert result.success is True
            assert "CLOSED" in result.output
            assert "9999" in result.output

    @pytest.mark.asyncio
    async def test_port_timeout(self, tool):
        """Test port check timeout (filtered)."""
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_conn.side_effect = asyncio.TimeoutError()

            result = await tool.execute(host="example.com", port=22)

            assert result.success is True
            assert "FILTERED" in result.output or "timeout" in result.output.lower()

    @pytest.mark.asyncio
    async def test_multiple_ports(self, tool):
        """Test checking multiple ports."""
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_writer = AsyncMock()

            def side_effect(host, port):
                if port == 80:
                    return (MagicMock(), mock_writer)
                elif port == 443:
                    return (MagicMock(), mock_writer)
                else:
                    raise ConnectionRefusedError()

            mock_conn.side_effect = side_effect

            result = await tool.execute(host="example.com", ports=[80, 443, 22])

            assert result.success is True
            assert "80" in result.output
            assert "443" in result.output
            assert "22" in result.output
            assert result.metadata["total_count"] == 3

    @pytest.mark.asyncio
    async def test_blocked_host(self, tool):
        """Test that localhost is blocked by default."""
        result = await tool.execute(host="127.0.0.1", port=80)
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_allow_localhost(self):
        """Test allowing localhost when explicitly permitted."""
        tool = PortCheckTool(allow_localhost=True)
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_writer = AsyncMock()
            mock_conn.return_value = (MagicMock(), mock_writer)

            result = await tool.execute(host="127.0.0.1", port=80)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_no_ports_specified(self, tool):
        """Test error when no ports are specified."""
        result = await tool.execute(host="example.com")
        assert result.success is False
        assert "No ports specified" in result.error

    @pytest.mark.asyncio
    async def test_service_name_detection(self, tool):
        """Test that common port names are detected."""
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_writer = AsyncMock()
            mock_conn.return_value = (MagicMock(), mock_writer)

            result = await tool.execute(host="example.com", port=22)

            assert result.success is True
            assert "SSH" in result.output

    @pytest.mark.asyncio
    async def test_summary_count(self, tool):
        """Test summary shows correct open count."""
        with patch("sindri.tools.network.asyncio.open_connection") as mock_conn:
            mock_writer = AsyncMock()

            def side_effect(host, port):
                if port in [80, 443]:
                    return (MagicMock(), mock_writer)
                raise ConnectionRefusedError()

            mock_conn.side_effect = side_effect

            result = await tool.execute(host="example.com", ports=[80, 443, 22, 23])

            assert result.success is True
            assert "2/4" in result.output
            assert result.metadata["open_count"] == 2


# =============================================================================
# PingHostTool Tests
# =============================================================================


class TestPingHostTool:
    """Tests for ping functionality."""

    @pytest.fixture
    def tool(self):
        return PingHostTool()

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess for ping command."""
        with patch("sindri.tools.network.asyncio.create_subprocess_exec") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_successful_ping(self, tool, mock_subprocess):
        """Test successful ping response."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b"PING google.com (142.250.80.46) 56(84) bytes of data.\n"
            b"64 bytes from lhr25s35-in-f14.1e100.net (142.250.80.46): icmp_seq=1 ttl=117 time=12.3 ms\n"
            b"--- google.com ping statistics ---\n"
            b"4 packets transmitted, 4 received, 0% packet loss, time 3004ms\n"
            b"rtt min/avg/max/mdev = 12.3/13.5/15.2/1.1 ms\n",
            b"",
        )
        mock_subprocess.return_value = mock_process

        result = await tool.execute(host="google.com")

        assert result.success is True
        assert "Reachable" in result.output
        assert result.metadata["reachable"] is True

    @pytest.mark.asyncio
    async def test_unreachable_host(self, tool, mock_subprocess):
        """Test unreachable host."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (
            b"PING nonexistent.invalid (127.0.0.1) 56(84) bytes of data.\n"
            b"--- nonexistent.invalid ping statistics ---\n"
            b"4 packets transmitted, 0 received, 100% packet loss, time 3000ms\n",
            b"",
        )
        mock_subprocess.return_value = mock_process

        result = await tool.execute(host="nonexistent.invalid")

        assert result.success is True
        assert "Unreachable" in result.output
        assert result.metadata["reachable"] is False
        assert result.metadata["packet_loss_percent"] == 100

    @pytest.mark.asyncio
    async def test_blocked_host(self, tool):
        """Test that localhost is blocked by default."""
        result = await tool.execute(host="127.0.0.1")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_hostname(self, tool):
        """Test invalid hostname characters are rejected."""
        result = await tool.execute(host="example.com; rm -rf /")
        assert result.success is False
        assert "Invalid hostname" in result.error

    @pytest.mark.asyncio
    async def test_count_limit(self, tool, mock_subprocess):
        """Test that count is capped at 20."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")
        mock_subprocess.return_value = mock_process

        await tool.execute(host="example.com", count=100)

        # Verify the command used count=20 (capped)
        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        # Find the count argument
        if "-c" in cmd:
            count_idx = cmd.index("-c") + 1
            assert cmd[count_idx] == "20"

    @pytest.mark.asyncio
    async def test_rtt_parsing(self, tool, mock_subprocess):
        """Test RTT statistics parsing."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b"PING example.com (93.184.216.34) 56(84) bytes of data.\n"
            b"64 bytes from 93.184.216.34: icmp_seq=1 ttl=56 time=85.4 ms\n"
            b"--- example.com ping statistics ---\n"
            b"4 packets transmitted, 4 received, 0% packet loss, time 3003ms\n"
            b"rtt min/avg/max/mdev = 85.4/90.2/95.0/3.5 ms\n",
            b"",
        )
        mock_subprocess.return_value = mock_process

        result = await tool.execute(host="example.com")

        assert result.success is True
        assert result.metadata["rtt_min_ms"] == 85.4
        assert result.metadata["rtt_avg_ms"] == 90.2
        assert result.metadata["rtt_max_ms"] == 95.0

    @pytest.mark.asyncio
    async def test_ip_address_extraction(self, tool, mock_subprocess):
        """Test IP address extraction from ping output."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b"PING google.com (142.250.80.46) 56(84) bytes of data.\n"
            b"--- google.com ping statistics ---\n"
            b"1 packets transmitted, 1 received, 0% packet loss\n",
            b"",
        )
        mock_subprocess.return_value = mock_process

        result = await tool.execute(host="google.com", count=1)

        assert result.success is True
        assert result.metadata["ip_address"] == "142.250.80.46"


# =============================================================================
# SslAnalyzeTool Tests
# =============================================================================


class TestSslAnalyzeTool:
    """Tests for SSL/TLS certificate analysis."""

    @pytest.fixture
    def tool(self):
        return SslAnalyzeTool()

    @pytest.fixture
    def mock_ssl_context(self):
        """Mock SSL context and socket."""
        with patch("sindri.tools.network.ssl.create_default_context") as mock_ctx:
            yield mock_ctx

    @pytest.fixture
    def mock_socket(self):
        """Mock socket connection."""
        with patch("sindri.tools.network.socket.create_connection") as mock_conn:
            yield mock_conn

    @pytest.mark.asyncio
    async def test_blocked_host(self, tool):
        """Test that localhost is blocked."""
        result = await tool.execute(hostname="127.0.0.1")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_connection_refused(self, tool, mock_ssl_context, mock_socket):
        """Test connection refused handling."""
        mock_socket.side_effect = ConnectionRefusedError()

        result = await tool.execute(hostname="example.com")

        assert result.success is False
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_ssl_verification_error(self, tool, mock_ssl_context, mock_socket):
        """Test SSL verification error handling."""
        mock_socket.side_effect = ssl.SSLCertVerificationError()

        result = await tool.execute(hostname="self-signed.example.com")

        assert result.success is False
        assert "verification failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_hostname_resolution_failure(self, tool, mock_ssl_context, mock_socket):
        """Test hostname resolution failure."""
        mock_socket.side_effect = socket.gaierror(8, "Name or service not known")

        result = await tool.execute(hostname="nonexistent.invalid")

        assert result.success is False
        assert "resolve hostname" in result.error.lower()

    @pytest.mark.asyncio
    async def test_successful_analysis(self, tool):
        """Test successful certificate analysis with mocked socket."""
        mock_cert = {
            "subject": ((("commonName", "example.com"),),),
            "issuer": ((("commonName", "DigiCert Global Root CA"),),),
            "notBefore": "Jan  1 00:00:00 2024 GMT",
            "notAfter": "Dec 31 23:59:59 2025 GMT",
            "subjectAltName": (("DNS", "example.com"), ("DNS", "www.example.com")),
        }

        with patch("sindri.tools.network.socket.create_connection") as mock_conn:
            with patch("sindri.tools.network.ssl.create_default_context") as mock_ctx:
                mock_ssock = MagicMock()
                mock_ssock.getpeercert.side_effect = [mock_cert, b"binary_cert"]
                mock_ssock.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
                mock_ssock.version.return_value = "TLSv1.3"

                mock_context = MagicMock()
                mock_context.wrap_socket.return_value.__enter__ = MagicMock(
                    return_value=mock_ssock
                )
                mock_context.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)
                mock_ctx.return_value = mock_context

                mock_sock = MagicMock()
                mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
                mock_conn.return_value.__exit__ = MagicMock(return_value=False)

                # Run synchronously in executor - mock loop.run_in_executor
                with patch.object(asyncio, "get_event_loop") as mock_loop:
                    async def mock_run_in_executor(executor, func):
                        return func()

                    mock_loop.return_value.run_in_executor = mock_run_in_executor

                    result = await tool.execute(hostname="example.com")

                    assert result.success is True
                    assert "example.com" in result.output
                    assert "TLSv1.3" in result.output

    @pytest.mark.asyncio
    async def test_custom_port(self, tool):
        """Test analysis on custom port."""
        with patch("sindri.tools.network.socket.create_connection") as mock_conn:
            mock_conn.side_effect = ConnectionRefusedError()

            result = await tool.execute(hostname="example.com", port=8443)

            # Verify the correct port was used
            assert result.success is False
            call_args = mock_conn.call_args
            assert call_args[0][0] == ("example.com", 8443)


# =============================================================================
# HttpTraceTool Tests
# =============================================================================


class TestHttpTraceTool:
    """Tests for HTTP tracing functionality."""

    @pytest.fixture
    def tool(self):
        return HttpTraceTool()

    @pytest.fixture
    def mock_response(self):
        """Create a mock httpx Response."""
        response = MagicMock()
        response.status_code = 200
        response.reason_phrase = "OK"
        response.headers = {
            "content-type": "application/json",
            "content-length": "1234",
        }
        response.url = "https://api.example.com/test"
        response.history = []
        return response

    @pytest.mark.asyncio
    async def test_httpx_not_available(self):
        """Test behavior when httpx is not installed."""
        with patch("sindri.tools.network.HTTPX_AVAILABLE", False):
            tool = HttpTraceTool()
            result = await tool.execute(url="https://example.com")
            assert result.success is False
            assert "httpx not installed" in result.error

    @pytest.mark.asyncio
    async def test_invalid_url(self, tool):
        """Test invalid URL handling."""
        result = await tool.execute(url="not-a-valid-url")
        assert result.success is False
        assert "Invalid URL" in result.error

    @pytest.mark.asyncio
    async def test_blocked_host(self, tool):
        """Test that localhost is blocked."""
        result = await tool.execute(url="http://localhost:8080/api")
        assert result.success is False
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_basic_trace(self, tool, mock_response):
        """Test basic HTTP trace."""
        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(url="https://api.example.com/test")

            assert result.success is True
            assert "200" in result.output
            assert "OK" in result.output
            assert result.metadata["status_code"] == 200

    @pytest.mark.asyncio
    async def test_with_redirects(self, tool):
        """Test tracing with redirect history."""
        mock_redirect = MagicMock()
        mock_redirect.url = "https://example.com/old"
        mock_redirect.status_code = 301

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.url = "https://example.com/new"
        mock_response.history = [mock_redirect]

        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(
                url="https://example.com/old",
                follow_redirects=True,
            )

            assert result.success is True
            assert "Redirect Chain" in result.output
            assert "301" in result.output
            assert result.metadata["redirect_count"] == 1

    @pytest.mark.asyncio
    async def test_timeout_error(self, tool):
        """Test timeout handling."""
        import httpx as real_httpx

        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.side_effect = real_httpx.TimeoutException(
                "Connection timed out"
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(url="https://slow.example.com")

            assert result.success is False
            assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self, tool):
        """Test connection error handling."""
        import httpx as real_httpx

        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.side_effect = real_httpx.ConnectError(
                "Connection refused"
            )
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(url="https://unreachable.example.com")

            assert result.success is False
            assert "Connection failed" in result.error

    @pytest.mark.asyncio
    async def test_headers_in_output(self, tool, mock_response):
        """Test that headers are included when show_headers=True."""
        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(
                url="https://api.example.com/test",
                show_headers=True,
            )

            assert result.success is True
            assert "Response Headers" in result.output
            assert "content-type" in result.output

    @pytest.mark.asyncio
    async def test_timing_metadata(self, tool, mock_response):
        """Test that timing info is in metadata."""
        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(url="https://api.example.com/test")

            assert result.success is True
            assert "total_time_ms" in result.metadata
            assert isinstance(result.metadata["total_time_ms"], float)

    @pytest.mark.asyncio
    async def test_head_method(self, tool, mock_response):
        """Test HEAD method."""
        with patch("sindri.tools.network.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client.return_value.__aexit__.return_value = None

            result = await tool.execute(
                url="https://api.example.com/test",
                method="HEAD",
            )

            assert result.success is True
            mock_client_instance.request.assert_called_once()
            call_args = mock_client_instance.request.call_args
            assert call_args[0][0] == "HEAD"


# =============================================================================
# Integration Tests
# =============================================================================


class TestNetworkToolsIntegration:
    """Integration tests for network tools."""

    @pytest.mark.asyncio
    async def test_all_tools_instantiate(self):
        """Test that all network tools can be instantiated."""
        tools = [
            CurlGenerateTool(),
            DnsLookupTool(),
            PortCheckTool(),
            PingHostTool(),
            SslAnalyzeTool(),
            HttpTraceTool(),
        ]

        for tool in tools:
            assert tool.name is not None
            assert tool.description is not None
            assert tool.parameters is not None

    @pytest.mark.asyncio
    async def test_tools_have_required_properties(self):
        """Test that all tools have required schema properties."""
        tools = [
            CurlGenerateTool(),
            DnsLookupTool(),
            PortCheckTool(),
            PingHostTool(),
            SslAnalyzeTool(),
            HttpTraceTool(),
        ]

        for tool in tools:
            schema = tool.get_schema()
            # Schema is wrapped in 'function' key for Ollama compatibility
            func_schema = schema.get("function", schema)
            assert "name" in func_schema
            assert "description" in func_schema
            assert "parameters" in func_schema
            assert "type" in func_schema["parameters"]
            assert "properties" in func_schema["parameters"]

    @pytest.mark.asyncio
    async def test_security_blocking_consistency(self):
        """Test that all relevant tools block localhost consistently."""
        tools_with_security = [
            PortCheckTool(),
            PingHostTool(),
            SslAnalyzeTool(),
            HttpTraceTool(),
        ]

        for tool in tools_with_security:
            # Each tool should block localhost
            if hasattr(tool, "execute"):
                # Test with various localhost variants
                for host in ["127.0.0.1", "localhost"]:
                    if tool.name == "http_trace":
                        result = await tool.execute(url=f"http://{host}/")
                    elif tool.name == "port_check":
                        result = await tool.execute(host=host, port=80)
                    elif tool.name == "ping_host":
                        result = await tool.execute(host=host)
                    elif tool.name == "ssl_analyze":
                        result = await tool.execute(hostname=host)

                    assert result.success is False, f"{tool.name} should block {host}"
                    assert "blocked" in result.error.lower(), f"{tool.name} error should mention blocked"
