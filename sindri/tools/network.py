"""Network and HTTP diagnostic tools for Sindri."""

import asyncio
import json
import platform
import shlex
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlencode

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Try to import httpx
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Try to import dnspython
try:
    import dns.resolver
    import dns.exception

    DNSPYTHON_AVAILABLE = True
except ImportError:
    DNSPYTHON_AVAILABLE = False

# Try to import cryptography for certificate parsing
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


# Security: Blocked hosts and private IP ranges (shared with http.py)
BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
}


def _is_private_ip(ip: str) -> bool:
    """Check if an IP address is in a private range."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        octets = [int(p) for p in parts]
        # 10.0.0.0/8
        if octets[0] == 10:
            return True
        # 172.16.0.0/12
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        # 192.168.0.0/16
        if octets[0] == 192 and octets[1] == 168:
            return True
        # 127.0.0.0/8 (loopback)
        if octets[0] == 127:
            return True
        return False
    except (ValueError, IndexError):
        return False


def _is_blocked_host(host: str, allow_localhost: bool = False) -> bool:
    """Check if a host should be blocked for security."""
    if allow_localhost:
        return False
    host_lower = host.lower()
    if host_lower in BLOCKED_HOSTS:
        return True
    if _is_private_ip(host):
        return True
    return False


# =============================================================================
# CurlGenerateTool - Generate curl commands
# =============================================================================


class CurlGenerateTool(Tool):
    """Generate curl commands from HTTP request parameters."""

    name = "curl_generate"
    description = """Generate curl commands from HTTP request parameters.

Examples:
- curl_generate(url="https://api.example.com/users") - Basic GET
- curl_generate(url="https://api.example.com/data", method="POST", json={"key": "value"})
- curl_generate(url="https://api.example.com", headers={"Authorization": "Bearer token"})
- curl_generate(url="https://api.example.com", auth={"type": "basic", "username": "user", "password": "pass"})"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Target URL"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                "description": "HTTP method (default: GET)",
            },
            "headers": {
                "type": "object",
                "description": "Request headers as key-value pairs",
            },
            "json": {
                "type": "object",
                "description": "JSON body for POST/PUT/PATCH",
            },
            "data": {
                "type": "string",
                "description": "Raw body data",
            },
            "params": {
                "type": "object",
                "description": "Query parameters",
            },
            "auth": {
                "type": "object",
                "description": "Authentication: {type: 'basic'|'bearer', username?, password?, token?}",
            },
            "follow_redirects": {
                "type": "boolean",
                "description": "Follow redirects (-L flag)",
            },
            "insecure": {
                "type": "boolean",
                "description": "Skip SSL verification (-k flag)",
            },
            "verbose": {
                "type": "boolean",
                "description": "Verbose output (-v flag)",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
        data: Optional[str] = None,
        params: Optional[dict[str, str]] = None,
        auth: Optional[dict[str, str]] = None,
        follow_redirects: bool = False,
        insecure: bool = False,
        verbose: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate a curl command from parameters."""
        log.info("curl_generate_start", url=url, method=method)

        try:
            # Build URL with query parameters
            if params:
                separator = "&" if "?" in url else "?"
                url = url + separator + urlencode(params)

            parts = ["curl"]

            # Flags
            if verbose:
                parts.append("-v")
            if follow_redirects:
                parts.append("-L")
            if insecure:
                parts.append("-k")

            # Method (only needed for non-GET)
            method = method.upper()
            if method != "GET":
                parts.extend(["-X", method])

            # Headers
            if headers:
                for key, value in headers.items():
                    parts.extend(["-H", f"{key}: {value}"])

            # Authentication
            if auth:
                auth_type = auth.get("type", "").lower()
                if auth_type == "basic":
                    username = auth.get("username", "")
                    password = auth.get("password", "")
                    parts.extend(["-u", f"{username}:{password}"])
                elif auth_type == "bearer":
                    token = auth.get("token", "")
                    parts.extend(["-H", f"Authorization: Bearer {token}"])

            # Body
            if json:
                parts.extend(["-H", "Content-Type: application/json"])
                import json as json_module

                json_str = json_module.dumps(json)
                parts.extend(["-d", json_str])
            elif data:
                parts.extend(["-d", data])

            # URL (must be last)
            parts.append(url)

            # Build the command with proper escaping
            curl_command = " ".join(shlex.quote(p) for p in parts)

            log.info("curl_generate_success", command_length=len(curl_command))

            return ToolResult(
                success=True,
                output=f"Generated curl command:\n\n```bash\n{curl_command}\n```",
                metadata={
                    "command": curl_command,
                    "method": method,
                    "url": url,
                },
            )

        except Exception as e:
            log.error("curl_generate_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate curl command: {e}",
            )


# =============================================================================
# DnsLookupTool - DNS resolution
# =============================================================================


class DnsLookupTool(Tool):
    """Perform DNS lookups for various record types."""

    name = "dns_lookup"
    description = """Perform DNS lookup with support for multiple record types.

Examples:
- dns_lookup(hostname="example.com") - All common records
- dns_lookup(hostname="example.com", record_type="MX") - Mail servers
- dns_lookup(hostname="_dmarc.example.com", record_type="TXT") - DMARC record
- dns_lookup(hostname="example.com", nameserver="8.8.8.8") - Use Google DNS"""

    parameters = {
        "type": "object",
        "properties": {
            "hostname": {"type": "string", "description": "Domain name to resolve"},
            "record_type": {
                "type": "string",
                "enum": ["A", "AAAA", "MX", "TXT", "CNAME", "NS", "SOA", "PTR", "SRV", "ALL"],
                "description": "DNS record type (default: ALL)",
            },
            "nameserver": {
                "type": "string",
                "description": "Custom DNS server to use (e.g., '8.8.8.8')",
            },
            "timeout": {
                "type": "number",
                "description": "Query timeout in seconds (default: 10)",
            },
        },
        "required": ["hostname"],
    }

    async def execute(
        self,
        hostname: str,
        record_type: str = "ALL",
        nameserver: Optional[str] = None,
        timeout: float = 10.0,
        **kwargs,
    ) -> ToolResult:
        """Perform DNS lookup."""
        if not DNSPYTHON_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="dnspython not installed. Install with: pip install dnspython",
            )

        log.info("dns_lookup_start", hostname=hostname, record_type=record_type)

        try:
            resolver = dns.resolver.Resolver()
            if nameserver:
                resolver.nameservers = [nameserver]
            resolver.timeout = timeout
            resolver.lifetime = timeout

            record_type = record_type.upper()
            record_types = (
                ["A", "AAAA", "MX", "TXT", "CNAME", "NS"]
                if record_type == "ALL"
                else [record_type]
            )

            results: dict[str, list[dict[str, Any]]] = {}
            output_lines = [f"DNS Lookup: {hostname}"]
            if nameserver:
                output_lines.append(f"Nameserver: {nameserver}")
            output_lines.append("")

            for rtype in record_types:
                try:
                    answers = resolver.resolve(hostname, rtype)
                    records = []

                    for rdata in answers:
                        record_info: dict[str, Any] = {"value": str(rdata)}

                        # Add TTL
                        record_info["ttl"] = answers.rrset.ttl

                        # Special handling for MX records
                        if rtype == "MX":
                            record_info["priority"] = rdata.preference
                            record_info["exchange"] = str(rdata.exchange)

                        records.append(record_info)

                    if records:
                        results[rtype] = records
                        output_lines.append(f"{rtype} Records:")
                        for rec in records:
                            if rtype == "MX":
                                output_lines.append(
                                    f"  - {rec['exchange']} (priority: {rec['priority']}, TTL: {rec['ttl']})"
                                )
                            else:
                                output_lines.append(f"  - {rec['value']} (TTL: {rec['ttl']})")
                        output_lines.append("")

                except dns.resolver.NXDOMAIN:
                    if record_type != "ALL":
                        return ToolResult(
                            success=False,
                            output="",
                            error=f"Domain not found: {hostname}",
                        )
                except dns.resolver.NoAnswer:
                    # No records of this type, continue
                    pass
                except dns.exception.Timeout:
                    if record_type != "ALL":
                        return ToolResult(
                            success=False,
                            output="",
                            error=f"DNS query timed out after {timeout}s",
                        )

            if not results:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"No DNS records found for {hostname}",
                )

            log.info("dns_lookup_success", hostname=hostname, record_count=len(results))

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "hostname": hostname,
                    "records": results,
                    "nameserver": nameserver,
                },
            )

        except dns.resolver.NXDOMAIN:
            return ToolResult(
                success=False,
                output="",
                error=f"Domain not found: {hostname}",
            )
        except Exception as e:
            log.error("dns_lookup_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"DNS lookup failed: {e}",
            )


# =============================================================================
# PortCheckTool - Check if ports are open
# =============================================================================


class PortCheckTool(Tool):
    """Check if network ports are open on a host."""

    name = "port_check"
    description = """Check if network ports are open on a host.

Examples:
- port_check(host="example.com", port=443) - Check single port
- port_check(host="server.local", ports=[22, 80, 443]) - Check multiple ports
- port_check(host="192.168.1.1", ports=[80, 443, 8080], timeout=2) - Fast scan"""

    parameters = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Host to check"},
            "port": {"type": "integer", "description": "Single port to check"},
            "ports": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of ports to check",
            },
            "timeout": {
                "type": "number",
                "description": "Connection timeout per port in seconds (default: 5)",
            },
        },
        "required": ["host"],
    }

    # Common port to service mapping
    COMMON_PORTS = {
        21: "FTP",
        22: "SSH",
        23: "Telnet",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        110: "POP3",
        143: "IMAP",
        443: "HTTPS",
        465: "SMTPS",
        587: "Submission",
        993: "IMAPS",
        995: "POP3S",
        3306: "MySQL",
        3389: "RDP",
        5432: "PostgreSQL",
        5900: "VNC",
        6379: "Redis",
        8080: "HTTP-Alt",
        8443: "HTTPS-Alt",
        27017: "MongoDB",
    }

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = False):
        """Initialize port check tool."""
        super().__init__(work_dir)
        self.allow_localhost = allow_localhost

    async def execute(
        self,
        host: str,
        port: Optional[int] = None,
        ports: Optional[list[int]] = None,
        timeout: float = 5.0,
        **kwargs,
    ) -> ToolResult:
        """Check if ports are open on a host."""
        log.info("port_check_start", host=host, port=port, ports=ports)

        # Security check
        if _is_blocked_host(host, self.allow_localhost):
            return ToolResult(
                success=False,
                output="",
                error=f"Host blocked for security: {host}",
            )

        # Build port list
        check_ports: list[int] = []
        if port is not None:
            check_ports.append(port)
        if ports:
            check_ports.extend(ports)

        if not check_ports:
            return ToolResult(
                success=False,
                output="",
                error="No ports specified. Provide 'port' or 'ports' parameter.",
            )

        # Dedupe and sort
        check_ports = sorted(set(check_ports))

        # Cap timeout
        timeout = min(timeout, 30.0)

        results: list[dict[str, Any]] = []
        output_lines = [f"Port Check: {host}", ""]

        for p in check_ports:
            try:
                # Use asyncio to check port
                start_time = asyncio.get_event_loop().time()
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, p),
                    timeout=timeout,
                )
                end_time = asyncio.get_event_loop().time()
                writer.close()
                await writer.wait_closed()

                elapsed_ms = (end_time - start_time) * 1000
                service = self.COMMON_PORTS.get(p, "unknown")

                results.append({
                    "port": p,
                    "status": "open",
                    "service": service,
                    "latency_ms": round(elapsed_ms, 2),
                })
                output_lines.append(f"  Port {p:5d} ({service:12s}): OPEN ({elapsed_ms:.1f}ms)")

            except asyncio.TimeoutError:
                service = self.COMMON_PORTS.get(p, "unknown")
                results.append({
                    "port": p,
                    "status": "filtered/timeout",
                    "service": service,
                })
                output_lines.append(f"  Port {p:5d} ({service:12s}): FILTERED (timeout)")

            except ConnectionRefusedError:
                service = self.COMMON_PORTS.get(p, "unknown")
                results.append({
                    "port": p,
                    "status": "closed",
                    "service": service,
                })
                output_lines.append(f"  Port {p:5d} ({service:12s}): CLOSED")

            except OSError as e:
                service = self.COMMON_PORTS.get(p, "unknown")
                results.append({
                    "port": p,
                    "status": "error",
                    "service": service,
                    "error": str(e),
                })
                output_lines.append(f"  Port {p:5d} ({service:12s}): ERROR ({e})")

        # Summary
        open_count = sum(1 for r in results if r["status"] == "open")
        output_lines.append("")
        output_lines.append(f"Summary: {open_count}/{len(check_ports)} ports open")

        log.info("port_check_success", host=host, open_count=open_count)

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={
                "host": host,
                "results": results,
                "open_count": open_count,
                "total_count": len(check_ports),
            },
        )


# =============================================================================
# PingHostTool - Network connectivity test
# =============================================================================


class PingHostTool(Tool):
    """Test network connectivity using ping."""

    name = "ping_host"
    description = """Test network connectivity to a host using ICMP ping.

Examples:
- ping_host(host="google.com") - Default 4 pings
- ping_host(host="192.168.1.1", count=10) - 10 pings
- ping_host(host="example.com", count=5, timeout=2) - Quick ping"""

    parameters = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Host to ping"},
            "count": {
                "type": "integer",
                "description": "Number of ping packets (default: 4, max: 20)",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout per ping in seconds (default: 5)",
            },
        },
        "required": ["host"],
    }

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = False):
        """Initialize ping tool."""
        super().__init__(work_dir)
        self.allow_localhost = allow_localhost

    async def execute(
        self,
        host: str,
        count: int = 4,
        timeout: float = 5.0,
        **kwargs,
    ) -> ToolResult:
        """Ping a host."""
        log.info("ping_host_start", host=host, count=count)

        # Security check
        if _is_blocked_host(host, self.allow_localhost):
            return ToolResult(
                success=False,
                output="",
                error=f"Host blocked for security: {host}",
            )

        # Validate host (prevent command injection)
        if not all(c.isalnum() or c in ".-_" for c in host):
            return ToolResult(
                success=False,
                output="",
                error="Invalid hostname characters",
            )

        # Cap count and timeout
        count = min(max(1, count), 20)
        timeout = min(timeout, 30.0)

        try:
            # Build ping command (cross-platform)
            system = platform.system().lower()
            if system == "windows":
                cmd = ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), host]
            else:
                # Linux/macOS
                cmd = ["ping", "-c", str(count), "-W", str(int(timeout)), host]

            # Run ping
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=count * timeout + 5,  # Allow extra time
            )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            # Parse results
            lines = output.strip().split("\n")
            packet_loss = None
            rtt_min = None
            rtt_avg = None
            rtt_max = None
            ip_address = None

            for line in lines:
                line_lower = line.lower()
                # Extract IP address
                if "(" in line and ")" in line and not ip_address:
                    try:
                        ip_address = line.split("(")[1].split(")")[0]
                    except (IndexError, ValueError):
                        pass

                # Parse packet loss (Linux format: "X% packet loss")
                if "packet loss" in line_lower or "loss" in line_lower:
                    try:
                        for part in line.split():
                            if "%" in part:
                                packet_loss = float(part.replace("%", "").replace(",", ""))
                                break
                    except (ValueError, IndexError):
                        pass

                # Parse RTT stats (Linux: "rtt min/avg/max/mdev = X/Y/Z/W ms")
                if "min/avg/max" in line_lower or "rtt" in line_lower:
                    try:
                        # Extract the numbers after "="
                        if "=" in line:
                            stats_part = line.split("=")[1].strip()
                            values = stats_part.split("/")
                            if len(values) >= 3:
                                rtt_min = float(values[0].strip())
                                rtt_avg = float(values[1].strip())
                                rtt_max = float(values[2].strip().split()[0])
                    except (ValueError, IndexError):
                        pass

            # Determine success
            is_reachable = process.returncode == 0 and (packet_loss is None or packet_loss < 100)

            # Build output
            output_lines = [f"Ping: {host}"]
            if ip_address:
                output_lines.append(f"IP Address: {ip_address}")
            output_lines.append("")

            if is_reachable:
                output_lines.append(f"Status: Reachable")
                if packet_loss is not None:
                    output_lines.append(f"Packet Loss: {packet_loss}%")
                if rtt_avg is not None:
                    output_lines.append(f"RTT: {rtt_min}/{rtt_avg}/{rtt_max} ms (min/avg/max)")
            else:
                output_lines.append("Status: Unreachable")
                if packet_loss is not None:
                    output_lines.append(f"Packet Loss: {packet_loss}%")

            output_lines.append("")
            output_lines.append("Raw output:")
            output_lines.append(output[:2000])  # Limit raw output

            log.info("ping_host_success", host=host, reachable=is_reachable)

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "host": host,
                    "ip_address": ip_address,
                    "reachable": is_reachable,
                    "packet_loss_percent": packet_loss,
                    "rtt_min_ms": rtt_min,
                    "rtt_avg_ms": rtt_avg,
                    "rtt_max_ms": rtt_max,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Ping timed out after {count * timeout + 5}s",
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="ping command not found",
            )
        except Exception as e:
            log.error("ping_host_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Ping failed: {e}",
            )


# =============================================================================
# SslAnalyzeTool - SSL/TLS certificate analysis
# =============================================================================


class SslAnalyzeTool(Tool):
    """Analyze SSL/TLS certificates for a host."""

    name = "ssl_analyze"
    description = """Analyze SSL/TLS certificate for a host.

Examples:
- ssl_analyze(hostname="github.com") - Full certificate analysis
- ssl_analyze(hostname="example.com", port=8443) - Custom port
- ssl_analyze(hostname="api.example.com", check_chain=True) - Include certificate chain"""

    parameters = {
        "type": "object",
        "properties": {
            "hostname": {"type": "string", "description": "Host to analyze"},
            "port": {
                "type": "integer",
                "description": "Port number (default: 443)",
            },
            "check_chain": {
                "type": "boolean",
                "description": "Include certificate chain info (default: true)",
            },
            "timeout": {
                "type": "number",
                "description": "Connection timeout in seconds (default: 10)",
            },
        },
        "required": ["hostname"],
    }

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = False):
        """Initialize SSL analyzer."""
        super().__init__(work_dir)
        self.allow_localhost = allow_localhost

    async def execute(
        self,
        hostname: str,
        port: int = 443,
        check_chain: bool = True,
        timeout: float = 10.0,
        **kwargs,
    ) -> ToolResult:
        """Analyze SSL/TLS certificate."""
        log.info("ssl_analyze_start", hostname=hostname, port=port)

        # Security check
        if _is_blocked_host(hostname, self.allow_localhost):
            return ToolResult(
                success=False,
                output="",
                error=f"Host blocked for security: {hostname}",
            )

        # Cap timeout
        timeout = min(timeout, 60.0)

        try:
            # Create SSL context
            context = ssl.create_default_context()

            # Connect and get certificate
            def get_cert_info():
                with socket.create_connection((hostname, port), timeout=timeout) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert()
                        cert_binary = ssock.getpeercert(binary_form=True)
                        cipher = ssock.cipher()
                        version = ssock.version()
                        return cert, cert_binary, cipher, version

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            cert, cert_binary, cipher, tls_version = await asyncio.wait_for(
                loop.run_in_executor(None, get_cert_info),
                timeout=timeout + 5,
            )

            # Parse certificate details
            subject = dict(x[0] for x in cert.get("subject", []))
            issuer = dict(x[0] for x in cert.get("issuer", []))

            # Parse dates
            not_before = cert.get("notBefore", "")
            not_after = cert.get("notAfter", "")

            # Calculate days until expiry
            days_until_expiry = None
            if not_after:
                try:
                    # Format: "Mon DD HH:MM:SS YYYY GMT"
                    expiry_date = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                    expiry_date = expiry_date.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    days_until_expiry = (expiry_date - now).days
                except ValueError:
                    pass

            # Get SANs
            sans = []
            for ext in cert.get("subjectAltName", []):
                if ext[0] == "DNS":
                    sans.append(ext[1])

            # Build output
            output_lines = [
                f"SSL/TLS Certificate Analysis: {hostname}:{port}",
                "",
                "Certificate:",
                f"  Subject: {subject.get('commonName', 'N/A')}",
                f"  Organization: {subject.get('organizationName', 'N/A')}",
                f"  Issuer: {issuer.get('commonName', 'N/A')}",
                f"  Issuer Org: {issuer.get('organizationName', 'N/A')}",
                "",
                "Validity:",
                f"  Not Before: {not_before}",
                f"  Not After: {not_after}",
            ]

            if days_until_expiry is not None:
                if days_until_expiry < 0:
                    output_lines.append(f"  Status: EXPIRED ({abs(days_until_expiry)} days ago)")
                elif days_until_expiry < 30:
                    output_lines.append(f"  Status: EXPIRING SOON ({days_until_expiry} days)")
                else:
                    output_lines.append(f"  Status: Valid ({days_until_expiry} days remaining)")

            output_lines.extend([
                "",
                "Connection:",
                f"  TLS Version: {tls_version}",
                f"  Cipher: {cipher[0] if cipher else 'N/A'}",
            ])

            if sans:
                output_lines.append("")
                output_lines.append("Subject Alternative Names:")
                for san in sans[:10]:  # Limit to 10
                    output_lines.append(f"  - {san}")
                if len(sans) > 10:
                    output_lines.append(f"  ... and {len(sans) - 10} more")

            # Parse additional details with cryptography if available
            key_info = {}
            if CRYPTOGRAPHY_AVAILABLE and cert_binary:
                try:
                    x509_cert = x509.load_der_x509_certificate(cert_binary, default_backend())
                    public_key = x509_cert.public_key()
                    key_info["algorithm"] = x509_cert.signature_algorithm_oid._name
                    key_info["serial_number"] = format(x509_cert.serial_number, "x")
                    key_info["key_size"] = getattr(public_key, "key_size", None)

                    output_lines.extend([
                        "",
                        "Key Information:",
                        f"  Algorithm: {key_info.get('algorithm', 'N/A')}",
                        f"  Key Size: {key_info.get('key_size', 'N/A')} bits",
                        f"  Serial: {key_info.get('serial_number', 'N/A')[:32]}...",
                    ])
                except Exception:
                    pass

            log.info("ssl_analyze_success", hostname=hostname, days_until_expiry=days_until_expiry)

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "hostname": hostname,
                    "port": port,
                    "subject": subject,
                    "issuer": issuer,
                    "not_before": not_before,
                    "not_after": not_after,
                    "days_until_expiry": days_until_expiry,
                    "tls_version": tls_version,
                    "cipher": cipher[0] if cipher else None,
                    "sans": sans,
                    **key_info,
                },
            )

        except ssl.SSLCertVerificationError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SSL certificate verification failed: {e}",
            )
        except socket.gaierror as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to resolve hostname: {e}",
            )
        except ConnectionRefusedError:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection refused to {hostname}:{port}",
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection timed out after {timeout}s",
            )
        except Exception as e:
            log.error("ssl_analyze_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"SSL analysis failed: {e}",
            )


# =============================================================================
# HttpTraceTool - Detailed HTTP tracing
# =============================================================================


class HttpTraceTool(Tool):
    """Trace HTTP requests with detailed timing and connection info."""

    name = "http_trace"
    description = """Trace HTTP request with detailed timing and connection info.

Examples:
- http_trace(url="https://api.github.com") - Full trace with timing
- http_trace(url="https://example.com", follow_redirects=True) - Trace redirects
- http_trace(url="https://secure.example.com", show_headers=True) - Include response headers"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to trace"},
            "method": {
                "type": "string",
                "enum": ["GET", "HEAD", "OPTIONS"],
                "description": "HTTP method (default: GET)",
            },
            "follow_redirects": {
                "type": "boolean",
                "description": "Follow and trace redirects (default: true)",
            },
            "show_headers": {
                "type": "boolean",
                "description": "Include response headers in output (default: true)",
            },
            "timeout": {
                "type": "number",
                "description": "Request timeout in seconds (default: 30)",
            },
        },
        "required": ["url"],
    }

    BLOCKED_HOSTS = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "169.254.169.254",
    }

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = False):
        """Initialize HTTP trace tool."""
        super().__init__(work_dir)
        self.allow_localhost = allow_localhost

    async def execute(
        self,
        url: str,
        method: str = "GET",
        follow_redirects: bool = True,
        show_headers: bool = True,
        timeout: float = 30.0,
        **kwargs,
    ) -> ToolResult:
        """Trace an HTTP request."""
        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="httpx not installed. Install with: pip install httpx",
            )

        log.info("http_trace_start", url=url, method=method)

        # Parse and validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid URL: {url}",
                )

            host = parsed.hostname or ""
            if _is_blocked_host(host, self.allow_localhost):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Host blocked for security: {host}",
                )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid URL: {e}",
            )

        # Cap timeout
        timeout = min(timeout, 300.0)
        method = method.upper()

        try:
            redirect_history: list[dict[str, Any]] = []

            async with httpx.AsyncClient(
                follow_redirects=follow_redirects,
                timeout=timeout,
            ) as client:
                # Track timing
                start_time = asyncio.get_event_loop().time()

                response = await client.request(method, url)

                end_time = asyncio.get_event_loop().time()
                total_time_ms = (end_time - start_time) * 1000

                # Collect redirect history if available
                if hasattr(response, "history") and response.history:
                    for hist in response.history:
                        redirect_history.append({
                            "url": str(hist.url),
                            "status_code": hist.status_code,
                        })

                # Build output
                output_lines = [
                    f"HTTP Trace: {url}",
                    f"Method: {method}",
                    "",
                ]

                # Redirect chain
                if redirect_history:
                    output_lines.append("Redirect Chain:")
                    for i, redir in enumerate(redirect_history, 1):
                        output_lines.append(f"  {i}. {redir['status_code']} -> {redir['url']}")
                    output_lines.append(f"  Final: {response.status_code} -> {response.url}")
                    output_lines.append("")

                # Response info
                output_lines.extend([
                    f"Status: {response.status_code} {response.reason_phrase}",
                    f"URL: {response.url}",
                    f"Total Time: {total_time_ms:.2f}ms",
                    "",
                ])

                # TLS info for HTTPS
                if str(response.url).startswith("https"):
                    output_lines.append("TLS: Enabled")
                    output_lines.append("")

                # Headers
                if show_headers:
                    output_lines.append("Response Headers:")
                    for name, value in response.headers.items():
                        # Truncate long values
                        if len(value) > 100:
                            value = value[:100] + "..."
                        output_lines.append(f"  {name}: {value}")
                    output_lines.append("")

                # Content info
                content_type = response.headers.get("content-type", "unknown")
                content_length = response.headers.get("content-length", "unknown")
                output_lines.extend([
                    "Content:",
                    f"  Type: {content_type}",
                    f"  Length: {content_length}",
                ])

                log.info("http_trace_success", url=url, status=response.status_code)

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={
                        "url": str(response.url),
                        "method": method,
                        "status_code": response.status_code,
                        "reason": response.reason_phrase,
                        "total_time_ms": round(total_time_ms, 2),
                        "headers": dict(response.headers),
                        "content_type": content_type,
                        "content_length": content_length,
                        "redirect_count": len(redirect_history),
                        "redirects": redirect_history,
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout}s",
            )
        except httpx.ConnectError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection failed: {e}",
            )
        except Exception as e:
            log.error("http_trace_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"HTTP trace failed: {e}",
            )
