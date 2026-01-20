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


# Security: Only block cloud metadata endpoints (internal-only mode)
# Localhost and private IPs are allowed for local service integration
BLOCKED_HOSTS = {
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",  # AWS/GCP metadata
    "169.254.170.2",  # ECS metadata
}


def _is_cloud_metadata_ip(ip: str) -> bool:
    """Check if an IP address is a cloud metadata endpoint."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        octets = [int(p) for p in parts]
        # 169.254.169.254 and 169.254.170.2 (cloud metadata)
        if octets[0] == 169 and octets[1] == 254:
            if (octets[2] == 169 and octets[3] == 254) or (octets[2] == 170 and octets[3] == 2):
                return True
        return False
    except (ValueError, IndexError):
        return False


def _is_blocked_host(host: str, allow_localhost: bool = True) -> bool:
    """Check if a host should be blocked for security.

    In internal-only mode, only cloud metadata endpoints are blocked.
    Localhost and private IPs are allowed for local service integration.
    """
    host_lower = host.lower()
    # Block cloud metadata hosts
    if host_lower in BLOCKED_HOSTS:
        return True
    if _is_cloud_metadata_ip(host):
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

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = True):
        """Initialize port check tool (localhost allowed in internal-only mode)."""
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

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = True):
        """Initialize ping tool (localhost allowed in internal-only mode)."""
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

        # Security check (only blocks cloud metadata)
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

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = True):
        """Initialize SSL analyzer (localhost allowed in internal-only mode)."""
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

        # Security check (only blocks cloud metadata)
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

    def __init__(self, work_dir: Optional[Path] = None, allow_localhost: bool = True):
        """Initialize HTTP trace tool (localhost allowed in internal-only mode)."""
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


# =============================================================================
# WebSocket Testing Tools
# =============================================================================

# Try to import websockets
try:
    import websockets
    import websockets.exceptions

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


class WebSocketTestTool(Tool):
    """Test WebSocket connections and protocol behavior."""

    name = "websocket_test"
    description = """Test WebSocket endpoints for connectivity and security.

Examples:
- websocket_test(url="wss://api.example.com/ws", action="connect") - Test connection
- websocket_test(url="wss://...", action="send", message="ping") - Send message
- websocket_test(url="wss://...", action="ping") - Test ping/pong
- websocket_test(url="wss://...", action="lifecycle", timeout=5) - Full lifecycle test"""

    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "WebSocket URL (ws:// or wss://)",
            },
            "action": {
                "type": "string",
                "enum": ["connect", "send", "receive", "ping", "lifecycle", "close"],
                "description": "Test action to perform",
            },
            "message": {
                "type": "string",
                "description": "Message to send (for send action)",
            },
            "headers": {
                "type": "object",
                "description": "Custom headers for connection",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds (default: 10)",
            },
            "subprotocol": {
                "type": "string",
                "description": "WebSocket subprotocol to request",
            },
            "auth_token": {
                "type": "string",
                "description": "Bearer token for authentication",
            },
        },
        "required": ["url", "action"],
    }

    async def execute(
        self,
        url: str,
        action: str,
        message: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 10.0,
        subprotocol: Optional[str] = None,
        auth_token: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Test WebSocket connections."""
        if not WEBSOCKETS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="websockets not installed. Install with: pip install websockets",
            )

        log.info("websocket_test_start", url=url, action=action)

        # Parse and validate URL
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("ws", "wss"):
                return ToolResult(
                    success=False,
                    output="",
                    error="URL must use ws:// or wss:// scheme",
                )

            host = parsed.hostname or ""
            if _is_blocked_host(host):
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

        # Build connection headers
        extra_headers = headers.copy() if headers else {}
        if auth_token:
            extra_headers["Authorization"] = f"Bearer {auth_token}"

        # Build connection kwargs
        connect_kwargs: dict[str, Any] = {
            "extra_headers": extra_headers if extra_headers else None,
        }
        if subprotocol:
            connect_kwargs["subprotocols"] = [subprotocol]

        try:
            if action == "connect":
                return await self._test_connection(url, connect_kwargs, timeout)
            elif action == "send":
                if not message:
                    return ToolResult(
                        success=False,
                        output="",
                        error="message required for send action",
                    )
                return await self._send_message(url, message, connect_kwargs, timeout)
            elif action == "receive":
                return await self._receive_message(url, connect_kwargs, timeout)
            elif action == "ping":
                return await self._test_ping(url, connect_kwargs, timeout)
            elif action == "lifecycle":
                return await self._test_lifecycle(url, connect_kwargs, timeout)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}",
                )

        except websockets.exceptions.InvalidStatusCode as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection rejected with status: {e.status_code}",
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection timed out after {timeout}s",
            )
        except ConnectionRefusedError:
            return ToolResult(
                success=False,
                output="",
                error="Connection refused by server",
            )
        except Exception as e:
            log.error("websocket_test_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"WebSocket test failed: {e}",
            )

    async def _test_connection(
        self, url: str, connect_kwargs: dict, timeout: float
    ) -> ToolResult:
        """Test basic WebSocket connection."""
        start_time = asyncio.get_event_loop().time()

        async with asyncio.timeout(timeout):
            async with websockets.connect(url, **connect_kwargs) as ws:
                connect_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return ToolResult(
                    success=True,
                    output=f"WebSocket connection successful to {url}\n"
                    f"Connect time: {connect_time:.2f}ms\n"
                    f"Subprotocol: {ws.subprotocol or 'none'}",
                    metadata={
                        "url": url,
                        "connect_time_ms": round(connect_time, 2),
                        "subprotocol": ws.subprotocol,
                        "open": True,
                    },
                )

    async def _send_message(
        self, url: str, message: str, connect_kwargs: dict, timeout: float
    ) -> ToolResult:
        """Send a message and receive response."""
        async with asyncio.timeout(timeout):
            async with websockets.connect(url, **connect_kwargs) as ws:
                await ws.send(message)

                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=timeout / 2)
                    return ToolResult(
                        success=True,
                        output=f"Sent: {message}\nReceived: {response}",
                        metadata={
                            "sent": message,
                            "received": response,
                            "response_type": type(response).__name__,
                        },
                    )
                except asyncio.TimeoutError:
                    return ToolResult(
                        success=True,
                        output=f"Sent: {message}\nNo response received within timeout",
                        metadata={
                            "sent": message,
                            "received": None,
                        },
                    )

    async def _receive_message(
        self, url: str, connect_kwargs: dict, timeout: float
    ) -> ToolResult:
        """Wait to receive a message from server."""
        async with asyncio.timeout(timeout):
            async with websockets.connect(url, **connect_kwargs) as ws:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=timeout / 2)
                    return ToolResult(
                        success=True,
                        output=f"Received: {message}",
                        metadata={
                            "received": message,
                            "message_type": type(message).__name__,
                        },
                    )
                except asyncio.TimeoutError:
                    return ToolResult(
                        success=True,
                        output="No message received within timeout",
                        metadata={"received": None},
                    )

    async def _test_ping(
        self, url: str, connect_kwargs: dict, timeout: float
    ) -> ToolResult:
        """Test WebSocket ping/pong."""
        start_time = asyncio.get_event_loop().time()

        async with asyncio.timeout(timeout):
            async with websockets.connect(url, **connect_kwargs) as ws:
                # Send ping and wait for pong
                pong_waiter = await ws.ping()
                await pong_waiter
                ping_time = (asyncio.get_event_loop().time() - start_time) * 1000

                return ToolResult(
                    success=True,
                    output=f"Ping/pong successful\nRound-trip time: {ping_time:.2f}ms",
                    metadata={
                        "ping_time_ms": round(ping_time, 2),
                        "pong_received": True,
                    },
                )

    async def _test_lifecycle(
        self, url: str, connect_kwargs: dict, timeout: float
    ) -> ToolResult:
        """Test full WebSocket lifecycle: connect, send, receive, close."""
        results = {
            "connect": False,
            "send": False,
            "receive": False,
            "close": False,
        }
        messages = []

        async with asyncio.timeout(timeout):
            async with websockets.connect(url, **connect_kwargs) as ws:
                results["connect"] = True
                messages.append("1. Connected successfully")

                # Try to send a test message
                try:
                    await ws.send("lifecycle_test")
                    results["send"] = True
                    messages.append("2. Sent test message")
                except Exception as e:
                    messages.append(f"2. Send failed: {e}")

                # Try to receive (with short timeout)
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    results["receive"] = True
                    messages.append(f"3. Received: {response[:100] if len(str(response)) > 100 else response}")
                except asyncio.TimeoutError:
                    messages.append("3. No response (timeout)")
                except Exception as e:
                    messages.append(f"3. Receive error: {e}")

                # Close is implicit with context manager
                results["close"] = True
                messages.append("4. Connection closed cleanly")

        return ToolResult(
            success=True,
            output="WebSocket Lifecycle Test\n" + "-" * 30 + "\n" + "\n".join(messages),
            metadata={
                "lifecycle_results": results,
                "all_passed": all(results.values()),
            },
        )


# =============================================================================
# HTTP Mock Tool
# =============================================================================


class HttpMockTool(Tool):
    """Create mock HTTP endpoints for testing."""

    name = "http_mock"
    description = """Create mock HTTP endpoints for testing security scenarios.

Examples:
- http_mock(action="create", path="/api/login", response={"token": "..."}, status=200)
- http_mock(action="record", path="/api/test") - Start recording requests
- http_mock(action="list") - List active mocks
- http_mock(action="clear") - Clear all mocks"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "record", "replay", "list", "clear"],
                "description": "Action to perform",
            },
            "path": {
                "type": "string",
                "description": "URL path for the mock endpoint",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
                "description": "HTTP method (default: GET)",
            },
            "response": {
                "type": "object",
                "description": "JSON response body",
            },
            "status": {
                "type": "integer",
                "description": "HTTP status code (default: 200)",
            },
            "headers": {
                "type": "object",
                "description": "Response headers",
            },
            "delay_ms": {
                "type": "integer",
                "description": "Response delay in milliseconds for latency testing",
            },
            "request_id": {
                "type": "string",
                "description": "Request ID for replay action",
            },
        },
        "required": ["action"],
    }

    # Class-level storage for mocks (shared across instances)
    _mocks: dict[str, dict[str, Any]] = {}
    _recordings: dict[str, list[dict[str, Any]]] = {}
    _mock_counter: int = 0

    async def execute(
        self,
        action: str,
        path: Optional[str] = None,
        method: str = "GET",
        response: Optional[dict[str, Any]] = None,
        status: int = 200,
        headers: Optional[dict[str, str]] = None,
        delay_ms: int = 0,
        request_id: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Execute mock HTTP operations."""
        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="httpx not installed. Install with: pip install httpx",
            )

        log.info("http_mock_start", action=action, path=path)

        try:
            if action == "create":
                if not path:
                    return ToolResult(
                        success=False,
                        output="",
                        error="path required for create action",
                    )
                return self._create_mock(path, method, response, status, headers, delay_ms)

            elif action == "record":
                if not path:
                    return ToolResult(
                        success=False,
                        output="",
                        error="path required for record action",
                    )
                return self._start_recording(path)

            elif action == "replay":
                if not request_id:
                    return ToolResult(
                        success=False,
                        output="",
                        error="request_id required for replay action",
                    )
                return self._replay_request(request_id)

            elif action == "list":
                return self._list_mocks()

            elif action == "clear":
                return self._clear_mocks()

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}",
                )

        except Exception as e:
            log.error("http_mock_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Mock operation failed: {e}",
            )

    def _create_mock(
        self,
        path: str,
        method: str,
        response: Optional[dict[str, Any]],
        status: int,
        headers: Optional[dict[str, str]],
        delay_ms: int,
    ) -> ToolResult:
        """Create a mock endpoint."""
        HttpMockTool._mock_counter += 1
        mock_id = f"mock_{HttpMockTool._mock_counter}"

        mock_config = {
            "id": mock_id,
            "path": path,
            "method": method.upper(),
            "response": response or {},
            "status": status,
            "headers": headers or {"Content-Type": "application/json"},
            "delay_ms": delay_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "hit_count": 0,
        }

        key = f"{method.upper()}:{path}"
        HttpMockTool._mocks[key] = mock_config

        return ToolResult(
            success=True,
            output=f"Created mock endpoint: {method.upper()} {path} -> {status}\n"
            f"Mock ID: {mock_id}\n"
            f"Response: {json.dumps(response or {}, indent=2)[:200]}",
            metadata={
                "mock_id": mock_id,
                "path": path,
                "method": method.upper(),
                "status": status,
            },
        )

    def _start_recording(self, path: str) -> ToolResult:
        """Start recording requests to a path."""
        HttpMockTool._mock_counter += 1
        recorder_id = f"rec_{HttpMockTool._mock_counter}"

        HttpMockTool._recordings[recorder_id] = {
            "path": path,
            "requests": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return ToolResult(
            success=True,
            output=f"Recording requests to {path}\nRecorder ID: {recorder_id}",
            metadata={
                "recorder_id": recorder_id,
                "path": path,
            },
        )

    def _replay_request(self, request_id: str) -> ToolResult:
        """Replay a recorded request."""
        # Find the request in recordings
        for recorder_id, recording in HttpMockTool._recordings.items():
            for req in recording.get("requests", []):
                if req.get("id") == request_id:
                    return ToolResult(
                        success=True,
                        output=f"Replayed request: {req.get('method')} {req.get('path')}\n"
                        f"Original time: {req.get('timestamp')}",
                        metadata={"request": req},
                    )

        return ToolResult(
            success=False,
            output="",
            error=f"Request not found: {request_id}",
        )

    def _list_mocks(self) -> ToolResult:
        """List all active mocks."""
        mocks = list(HttpMockTool._mocks.values())
        recordings = list(HttpMockTool._recordings.keys())

        if not mocks and not recordings:
            return ToolResult(
                success=True,
                output="No active mocks or recordings",
                metadata={"mocks": [], "recordings": []},
            )

        output_lines = ["Active Mocks:", "-" * 40]
        for mock in mocks:
            output_lines.append(
                f"  {mock['method']} {mock['path']} -> {mock['status']} (hits: {mock['hit_count']})"
            )

        if recordings:
            output_lines.extend(["", "Active Recordings:", "-" * 40])
            for rec_id in recordings:
                rec = HttpMockTool._recordings[rec_id]
                output_lines.append(f"  {rec_id}: {rec['path']} ({len(rec.get('requests', []))} requests)")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={"mocks": mocks, "recordings": recordings},
        )

    def _clear_mocks(self) -> ToolResult:
        """Clear all mocks and recordings."""
        mock_count = len(HttpMockTool._mocks)
        recording_count = len(HttpMockTool._recordings)

        HttpMockTool._mocks.clear()
        HttpMockTool._recordings.clear()

        return ToolResult(
            success=True,
            output=f"Cleared {mock_count} mocks and {recording_count} recordings",
            metadata={
                "cleared_mocks": mock_count,
                "cleared_recordings": recording_count,
            },
        )


# =============================================================================
# PCAP Analysis Tool
# =============================================================================

# Try to import scapy
try:
    from scapy.all import rdpcap, IP, TCP, UDP, DNS, ICMP, Raw

    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


class PcapAnalyzeTool(Tool):
    """Analyze network packet capture files."""

    name = "pcap_analyze"
    description = """Parse and analyze .pcap/.pcapng files for network security analysis.

Examples:
- pcap_analyze(file="capture.pcap") - Basic analysis with statistics
- pcap_analyze(file="capture.pcap", filter_host="192.168.1.1") - Filter by IP
- pcap_analyze(file="capture.pcap", filter_port=443, protocol="TCP") - Filter HTTPS
- pcap_analyze(file="capture.pcap", action="extract_dns") - Extract DNS queries"""

    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Path to .pcap or .pcapng file",
            },
            "action": {
                "type": "string",
                "enum": ["summary", "filter", "extract_dns", "extract_http", "timing", "conversations"],
                "description": "Analysis action (default: summary)",
            },
            "filter_host": {
                "type": "string",
                "description": "Filter packets by IP address",
            },
            "filter_port": {
                "type": "integer",
                "description": "Filter packets by port number",
            },
            "protocol": {
                "type": "string",
                "enum": ["TCP", "UDP", "ICMP", "DNS", "ALL"],
                "description": "Filter by protocol (default: ALL)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum packets to analyze (default: 1000)",
            },
            "extract_payloads": {
                "type": "boolean",
                "description": "Extract and decode payload data (default: false)",
            },
        },
        "required": ["file"],
    }

    # Maximum file size (100MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024
    # Maximum packets to analyze
    MAX_PACKETS = 10000

    async def execute(
        self,
        file: str,
        action: str = "summary",
        filter_host: Optional[str] = None,
        filter_port: Optional[int] = None,
        protocol: str = "ALL",
        limit: int = 1000,
        extract_payloads: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Analyze pcap files."""
        if not SCAPY_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="scapy not installed. Install with: pip install scapy",
            )

        log.info("pcap_analyze_start", file=file, action=action)

        # Resolve and validate file path
        file_path = self._resolve_path(file)
        if not file_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"File not found: {file}",
            )

        if file_path.suffix.lower() not in (".pcap", ".pcapng", ".cap"):
            return ToolResult(
                success=False,
                output="",
                error="File must be .pcap, .pcapng, or .cap",
            )

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            return ToolResult(
                success=False,
                output="",
                error=f"File too large: {file_size / (1024*1024):.1f}MB (max: {self.MAX_FILE_SIZE / (1024*1024):.0f}MB)",
            )

        # Cap limit
        limit = min(limit, self.MAX_PACKETS)

        try:
            # Load packets (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            packets = await loop.run_in_executor(None, lambda: rdpcap(str(file_path)))

            # Apply filters
            filtered = self._filter_packets(packets, filter_host, filter_port, protocol, limit)

            if action == "summary":
                return self._generate_summary(filtered, file_path, len(packets))
            elif action == "filter":
                return self._format_filtered(filtered)
            elif action == "extract_dns":
                return self._extract_dns(filtered)
            elif action == "extract_http":
                return self._extract_http(filtered, extract_payloads)
            elif action == "timing":
                return self._analyze_timing(filtered)
            elif action == "conversations":
                return self._analyze_conversations(filtered)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}",
                )

        except Exception as e:
            log.error("pcap_analyze_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"PCAP analysis failed: {e}",
            )

    def _resolve_path(self, file: str) -> Path:
        """Resolve file path relative to work_dir if set."""
        path = Path(file)
        if not path.is_absolute() and self.work_dir:
            path = self.work_dir / path
        return path.resolve()

    def _filter_packets(
        self,
        packets: list,
        filter_host: Optional[str],
        filter_port: Optional[int],
        protocol: str,
        limit: int,
    ) -> list:
        """Filter packets by criteria."""
        filtered = []

        for pkt in packets:
            if len(filtered) >= limit:
                break

            # Protocol filter
            if protocol != "ALL":
                if protocol == "TCP" and not pkt.haslayer(TCP):
                    continue
                elif protocol == "UDP" and not pkt.haslayer(UDP):
                    continue
                elif protocol == "ICMP" and not pkt.haslayer(ICMP):
                    continue
                elif protocol == "DNS" and not pkt.haslayer(DNS):
                    continue

            # Host filter
            if filter_host and pkt.haslayer(IP):
                ip_layer = pkt[IP]
                if ip_layer.src != filter_host and ip_layer.dst != filter_host:
                    continue

            # Port filter
            if filter_port:
                if pkt.haslayer(TCP):
                    tcp = pkt[TCP]
                    if tcp.sport != filter_port and tcp.dport != filter_port:
                        continue
                elif pkt.haslayer(UDP):
                    udp = pkt[UDP]
                    if udp.sport != filter_port and udp.dport != filter_port:
                        continue
                else:
                    continue

            filtered.append(pkt)

        return filtered

    def _generate_summary(self, packets: list, file_path: Path, total_count: int) -> ToolResult:
        """Generate summary statistics."""
        stats = {
            "total_packets": total_count,
            "analyzed_packets": len(packets),
            "tcp": 0,
            "udp": 0,
            "icmp": 0,
            "dns": 0,
            "other": 0,
            "unique_src_ips": set(),
            "unique_dst_ips": set(),
            "unique_ports": set(),
        }

        for pkt in packets:
            if pkt.haslayer(TCP):
                stats["tcp"] += 1
                tcp = pkt[TCP]
                stats["unique_ports"].add(tcp.sport)
                stats["unique_ports"].add(tcp.dport)
            elif pkt.haslayer(UDP):
                stats["udp"] += 1
                udp = pkt[UDP]
                stats["unique_ports"].add(udp.sport)
                stats["unique_ports"].add(udp.dport)
            elif pkt.haslayer(ICMP):
                stats["icmp"] += 1
            else:
                stats["other"] += 1

            if pkt.haslayer(DNS):
                stats["dns"] += 1

            if pkt.haslayer(IP):
                ip = pkt[IP]
                stats["unique_src_ips"].add(ip.src)
                stats["unique_dst_ips"].add(ip.dst)

        output_lines = [
            f"PCAP Analysis: {file_path.name}",
            "=" * 50,
            f"Total packets: {stats['total_packets']}",
            f"Analyzed: {stats['analyzed_packets']}",
            "",
            "Protocol Distribution:",
            f"  TCP: {stats['tcp']}",
            f"  UDP: {stats['udp']}",
            f"  ICMP: {stats['icmp']}",
            f"  DNS queries: {stats['dns']}",
            f"  Other: {stats['other']}",
            "",
            f"Unique source IPs: {len(stats['unique_src_ips'])}",
            f"Unique destination IPs: {len(stats['unique_dst_ips'])}",
            f"Unique ports: {len(stats['unique_ports'])}",
        ]

        # Convert sets to lists for JSON serialization
        metadata = {
            "file": str(file_path),
            "total_packets": stats["total_packets"],
            "analyzed_packets": stats["analyzed_packets"],
            "tcp": stats["tcp"],
            "udp": stats["udp"],
            "icmp": stats["icmp"],
            "dns": stats["dns"],
            "unique_src_ips": list(stats["unique_src_ips"])[:20],
            "unique_dst_ips": list(stats["unique_dst_ips"])[:20],
            "unique_ports": sorted(list(stats["unique_ports"]))[:50],
        }

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata=metadata,
        )

    def _format_filtered(self, packets: list) -> ToolResult:
        """Format filtered packets for display."""
        output_lines = [f"Filtered Packets: {len(packets)}", "=" * 50]

        for i, pkt in enumerate(packets[:50]):  # Limit display
            line_parts = [f"{i+1}."]

            if pkt.haslayer(IP):
                ip = pkt[IP]
                line_parts.append(f"{ip.src} -> {ip.dst}")

            if pkt.haslayer(TCP):
                tcp = pkt[TCP]
                line_parts.append(f"TCP {tcp.sport}->{tcp.dport}")
            elif pkt.haslayer(UDP):
                udp = pkt[UDP]
                line_parts.append(f"UDP {udp.sport}->{udp.dport}")
            elif pkt.haslayer(ICMP):
                line_parts.append("ICMP")

            output_lines.append(" ".join(line_parts))

        if len(packets) > 50:
            output_lines.append(f"... and {len(packets) - 50} more packets")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={"packet_count": len(packets)},
        )

    def _extract_dns(self, packets: list) -> ToolResult:
        """Extract DNS queries from packets."""
        dns_queries = []

        for pkt in packets:
            if pkt.haslayer(DNS):
                dns_layer = pkt[DNS]
                if dns_layer.qr == 0:  # Query
                    if dns_layer.qd:
                        query_name = dns_layer.qd.qname.decode() if isinstance(dns_layer.qd.qname, bytes) else str(dns_layer.qd.qname)
                        dns_queries.append({
                            "query": query_name.rstrip("."),
                            "type": dns_layer.qd.qtype,
                            "src": pkt[IP].src if pkt.haslayer(IP) else "unknown",
                        })

        output_lines = [f"DNS Queries: {len(dns_queries)}", "=" * 50]
        for q in dns_queries[:100]:
            output_lines.append(f"  {q['src']} -> {q['query']}")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={"dns_queries": dns_queries[:100]},
        )

    def _extract_http(self, packets: list, extract_payloads: bool) -> ToolResult:
        """Extract HTTP requests from packets."""
        http_requests = []

        for pkt in packets:
            if pkt.haslayer(TCP) and pkt.haslayer(Raw):
                payload = pkt[Raw].load
                try:
                    payload_str = payload.decode("utf-8", errors="ignore")
                    # Check for HTTP request patterns
                    if payload_str.startswith(("GET ", "POST ", "PUT ", "DELETE ", "HEAD ", "OPTIONS ", "PATCH ")):
                        lines = payload_str.split("\r\n")
                        request_line = lines[0] if lines else ""

                        req_info = {
                            "request": request_line[:200],
                            "src": pkt[IP].src if pkt.haslayer(IP) else "unknown",
                            "dst": pkt[IP].dst if pkt.haslayer(IP) else "unknown",
                            "port": pkt[TCP].dport,
                        }

                        if extract_payloads:
                            req_info["payload"] = payload_str[:500]

                        http_requests.append(req_info)
                except Exception:
                    pass

        output_lines = [f"HTTP Requests: {len(http_requests)}", "=" * 50]
        for req in http_requests[:50]:
            output_lines.append(f"  {req['src']} -> {req['dst']}:{req['port']}")
            output_lines.append(f"    {req['request']}")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={"http_requests": http_requests[:50]},
        )

    def _analyze_timing(self, packets: list) -> ToolResult:
        """Analyze packet timing."""
        if len(packets) < 2:
            return ToolResult(
                success=True,
                output="Not enough packets for timing analysis",
                metadata={"packet_count": len(packets)},
            )

        times = [float(pkt.time) for pkt in packets if hasattr(pkt, "time")]
        if len(times) < 2:
            return ToolResult(
                success=True,
                output="No timing information available",
                metadata={},
            )

        duration = times[-1] - times[0]
        intervals = [times[i+1] - times[i] for i in range(len(times)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        min_interval = min(intervals) if intervals else 0
        max_interval = max(intervals) if intervals else 0

        output_lines = [
            "Packet Timing Analysis",
            "=" * 50,
            f"Duration: {duration:.3f}s",
            f"Packet count: {len(packets)}",
            f"Packets/sec: {len(packets) / duration:.2f}" if duration > 0 else "N/A",
            "",
            "Interval Statistics:",
            f"  Average: {avg_interval*1000:.3f}ms",
            f"  Min: {min_interval*1000:.3f}ms",
            f"  Max: {max_interval*1000:.3f}ms",
        ]

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={
                "duration_sec": round(duration, 3),
                "packet_count": len(packets),
                "avg_interval_ms": round(avg_interval * 1000, 3),
                "min_interval_ms": round(min_interval * 1000, 3),
                "max_interval_ms": round(max_interval * 1000, 3),
            },
        )

    def _analyze_conversations(self, packets: list) -> ToolResult:
        """Analyze network conversations (IP pairs)."""
        conversations: dict[str, dict[str, Any]] = {}

        for pkt in packets:
            if not pkt.haslayer(IP):
                continue

            ip = pkt[IP]
            # Create sorted key for bidirectional conversations
            key = tuple(sorted([ip.src, ip.dst]))
            key_str = f"{key[0]} <-> {key[1]}"

            if key_str not in conversations:
                conversations[key_str] = {
                    "endpoints": list(key),
                    "packet_count": 0,
                    "bytes": 0,
                    "protocols": set(),
                }

            conversations[key_str]["packet_count"] += 1
            conversations[key_str]["bytes"] += len(pkt)

            if pkt.haslayer(TCP):
                conversations[key_str]["protocols"].add("TCP")
            elif pkt.haslayer(UDP):
                conversations[key_str]["protocols"].add("UDP")
            elif pkt.haslayer(ICMP):
                conversations[key_str]["protocols"].add("ICMP")

        # Sort by packet count
        sorted_convs = sorted(
            conversations.items(),
            key=lambda x: x[1]["packet_count"],
            reverse=True,
        )

        output_lines = [f"Network Conversations: {len(conversations)}", "=" * 50]
        for conv_key, conv_data in sorted_convs[:20]:
            protocols = ", ".join(conv_data["protocols"])
            output_lines.append(
                f"  {conv_key}: {conv_data['packet_count']} pkts, "
                f"{conv_data['bytes']} bytes ({protocols})"
            )

        # Convert sets to lists for JSON
        metadata_convs = []
        for conv_key, conv_data in sorted_convs[:20]:
            metadata_convs.append({
                "endpoints": conv_data["endpoints"],
                "packet_count": conv_data["packet_count"],
                "bytes": conv_data["bytes"],
                "protocols": list(conv_data["protocols"]),
            })

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            metadata={
                "conversation_count": len(conversations),
                "conversations": metadata_convs,
            },
        )
