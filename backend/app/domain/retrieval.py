"""SSRF-safe retrieval (build spec §10).

Rules enforced here:
- HTTP(S) only; no userinfo in URLs; ports restricted to an allow-list.
- Every resolved address (IPv4 and IPv6) must be globally routable. Loopback,
  private, link-local, CGNAT, multicast, reserved, unspecified, unique-local,
  IPv4-mapped/6to4/Teredo-embedded private addresses and cloud metadata
  addresses are blocked.
- DNS rebinding: the host is resolved ONCE per hop, every address is
  validated, and the connection is pinned to a validated address (the
  transport connects to the IP while sending the original Host header / SNI).
- Redirects are never followed automatically. Each hop's Location is
  re-validated from scratch, with a hop limit.
- Response size, time and content-type limits. Downloaded content is never
  executed; it is returned as bytes for parsing.

HTTP success here proves only REACHABILITY. It is recorded as the
`reachability` document check and says nothing about authenticity,
relevance, claim support or current status.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol
from urllib.parse import urljoin, urlsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
    "application/json",
    "application/pdf",
)
USER_AGENT = "VECTA-Connect-ATLAS/3.0 (+market intelligence; contact via configured operator)"

_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class RetrievalBlocked(Exception):
    """The request was refused by policy (never retried)."""


class RetrievalFailed(Exception):
    """The request was allowed but failed (may be retried by the job layer)."""


Resolver = Callable[[str, int], list[str]]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def _embedded_ipv4(addr: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    if addr.sixtofour is not None:
        return addr.sixtofour
    if addr.teredo is not None:
        return addr.teredo[1]
    # NAT64 well-known prefix 64:ff9b::/96
    if addr in ipaddress.ip_network("64:ff9b::/96"):
        return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return None


def is_forbidden_address(raw: str) -> str | None:
    """Return a reason string if the address must not be contacted, else None."""
    try:
        addr = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return f"unparseable address {raw!r}"
    if addr in _METADATA_ADDRESSES:
        return "cloud metadata address"
    if isinstance(addr, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(addr)
        if embedded is not None:
            inner = is_forbidden_address(str(embedded))
            if inner:
                return f"IPv6 embeds forbidden IPv4 ({inner})"
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT:
        return "carrier-grade NAT address"
    for attr, reason in (
        ("is_loopback", "loopback address"),
        ("is_private", "private address"),
        ("is_link_local", "link-local address"),
        ("is_multicast", "multicast address"),
        ("is_reserved", "reserved address"),
        ("is_unspecified", "unspecified address"),
    ):
        if getattr(addr, attr):
            return reason
    if isinstance(addr, ipaddress.IPv6Address) and addr.is_site_local:
        return "site-local address"
    if not addr.is_global:
        return "non-global address"
    return None


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    host: str
    port: int
    path_and_query: str
    addresses: tuple[str, ...]


def validate_url(url: str, resolver: Resolver = system_resolver, allow_private_hosts: frozenset[str] = frozenset()) -> ValidatedTarget:
    if not isinstance(url, str) or len(url) > 2048:
        raise RetrievalBlocked("URL missing or too long")
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise RetrievalBlocked(f"scheme {scheme!r} not allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise RetrievalBlocked("credentials in URL are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise RetrievalBlocked("URL has no host")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise RetrievalBlocked("invalid port") from exc
    allowed_private = host in allow_private_hosts or f"{host}:{port}" in allow_private_hosts
    if port not in ALLOWED_PORTS and not allowed_private:
        raise RetrievalBlocked(f"port {port} not allowed")
    if not allowed_private and (host == "localhost" or host.endswith(".localhost") or host.endswith(".internal") or host.endswith(".local")):
        raise RetrievalBlocked(f"host {host!r} is internal")

    # A literal IP host is validated directly; names are resolved once.
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = resolver(host, port)
        except OSError as exc:
            raise RetrievalFailed(f"DNS resolution failed for {host}") from exc
    if not addresses:
        raise RetrievalFailed(f"no addresses for {host}")
    for address in addresses:
        reason = None if allowed_private else is_forbidden_address(address)
        if reason:
            raise RetrievalBlocked(f"{host} resolves to {address}: {reason}")

    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return ValidatedTarget(url=url, scheme=scheme, host=host, port=port, path_and_query=path, addresses=tuple(addresses))


@dataclass
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    truncated: bool


class Transport(Protocol):
    def __call__(self, target: ValidatedTarget, pinned_address: str, max_bytes: int, timeout: float) -> RawResponse: ...


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned: str, port: int, timeout: float):
        self._tls = ssl.create_default_context()
        super().__init__(host, port=port, timeout=timeout, context=self._tls)
        self._pinned = pinned

    def connect(self) -> None:  # connect to the validated IP, verify cert for the hostname
        sock = socket.create_connection((self._pinned, self.port), self.timeout)
        self.sock = self._tls.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, pinned: str, port: int, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._pinned = pinned

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned, self.port), self.timeout)


def pinned_transport(target: ValidatedTarget, pinned_address: str, max_bytes: int, timeout: float) -> RawResponse:
    cls = _PinnedHTTPSConnection if target.scheme == "https" else _PinnedHTTPConnection
    conn = cls(target.host, pinned_address, target.port, timeout)
    try:
        conn.request("GET", target.path_and_query, headers={"User-Agent": USER_AGENT, "Accept": ", ".join(ALLOWED_CONTENT_TYPES)})
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            return RawResponse(resp.status, headers, b"", truncated=True)
        body = resp.read(max_bytes + 1)
        truncated = len(body) > max_bytes
        return RawResponse(resp.status, headers, body[:max_bytes], truncated)
    except (OSError, http.client.HTTPException) as exc:
        raise RetrievalFailed(f"transport error: {exc.__class__.__name__}") from exc
    finally:
        conn.close()


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    sha256: str
    redirect_chain: list[str] = field(default_factory=list)


def fetch(
    url: str,
    *,
    resolver: Resolver = system_resolver,
    transport: Transport = pinned_transport,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    allowed_content_types: Iterable[str] = ALLOWED_CONTENT_TYPES,
    allow_private_hosts: frozenset[str] = frozenset(),
) -> FetchResult:
    chain: list[str] = []
    current = url
    allowed = tuple(allowed_content_types)
    for _hop in range(MAX_REDIRECTS + 1):
        target = validate_url(current, resolver, allow_private_hosts)
        raw = transport(target, target.addresses[0], max_bytes, timeout)
        if raw.status in (301, 302, 303, 307, 308):
            location = raw.headers.get("location")
            if not location:
                raise RetrievalFailed(f"redirect {raw.status} without Location")
            chain.append(current)
            current = urljoin(current, location)
            continue
        if raw.truncated:
            raise RetrievalBlocked(f"response exceeds {max_bytes} bytes")
        content_type = raw.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in allowed:
            raise RetrievalBlocked(f"content type {content_type or 'missing'!r} not allowed")
        if not (200 <= raw.status < 300):
            raise RetrievalFailed(f"HTTP {raw.status}")
        return FetchResult(
            requested_url=url,
            final_url=current,
            status=raw.status,
            content_type=content_type,
            body=raw.body,
            sha256=hashlib.sha256(raw.body).hexdigest(),
            redirect_chain=chain,
        )
    raise RetrievalBlocked(f"more than {MAX_REDIRECTS} redirects")
