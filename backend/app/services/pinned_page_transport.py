"""Direct, single-hop HTTPS transport for the reviewed recipe fetch boundary.

The caller must authorize the source and validate every DNS answer and redirect.
This adapter does not implement robots.txt, publisher permissions, or rate limits.
"""

from __future__ import annotations

import ipaddress
import math
import re
import socket
import ssl
import threading
import time
import zlib
from urllib.parse import urlsplit

from app.services.deepseek_discovery import PageFetchResponse
from app.services.source_urls import canonical_recipe_url, normalize_host, validate_redirect_hops


_HTTPS_PORT = 443
_MAX_BODY_BYTES = 1_000_000
_MAX_HEADER_BYTES = 32_768
_MAX_HEADER_COUNT = 100
_MAX_CHUNK_METADATA_BYTES = 65_536
_MAX_CHUNKS = 16_384
_MAX_DNS_RESULTS = 64
_DNS_SLOTS = 4
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_STATUS = re.compile(rb"HTTP/1\.[01] ([2-5][0-9]{2})(?: [\x20-\x7e\t]*)?\r\n\Z")
_USER_AGENT = re.compile(r"[A-Za-z][A-Za-z0-9._-]*/[A-Za-z0-9._-]+ \(([^()]*)\)\Z")
_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_CONTACT_URL = re.compile(r"https?://[^\s;()]+", re.IGNORECASE)
_WIKI_CONTACT = re.compile(r"[A-Za-z0-9_-]+:[A-Za-z0-9_-]+;\s*User:[A-Za-z0-9 _.-]+", re.IGNORECASE)
_CRITICAL_HEADERS = {"content-length", "transfer-encoding", "content-encoding", "content-type", "location", "retry-after"}


class PinnedTransportError(Exception):
    """The response or destination cannot be handled safely."""


class PinnedResponseTooLarge(PinnedTransportError):
    """The response exceeds a configured byte or header limit."""


def _validate_user_agent(value: str) -> str:
    if not isinstance(value, str) or len(value) > 512 or not value.isascii():
        raise ValueError("An identifying ASCII User-Agent is required")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid User-Agent")
    match = _USER_AGENT.fullmatch(value)
    if not match:
        raise ValueError("User-Agent must identify the client, version, and operator contact")
    if value.split("/", 1)[0].casefold() in {
        "curl", "wget", "python-requests", "python-urllib", "httpx", "urllib3", "mozilla"
    }:
        raise ValueError("User-Agent must identify the operator's own client")
    contact = match.group(1)
    has_website = False
    for found in _CONTACT_URL.finditer(contact):
        try:
            website = urlsplit(found.group())
            _ = website.port
            has_website = bool(website.hostname) and website.username is None and website.password is None
        except ValueError:
            continue
        if has_website:
            break
    if not (_EMAIL.search(contact) or has_website or _WIKI_CONTACT.search(contact)):
        raise ValueError("User-Agent must include an operator email, website, or wiki account")
    return value


def _tls_context() -> ssl.SSLContext:
    # Construct explicitly: create_default_context honors SSLKEYLOGFILE.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    return context


class _Reader:
    def __init__(self, sock: ssl.SSLSocket, deadline: float) -> None:
        self.sock = sock
        self.deadline = deadline

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Page request deadline exceeded")
        return remaining

    def recv(self, size: int) -> bytes:
        self.sock.settimeout(self.remaining())
        result = self.sock.recv(size)
        self.remaining()
        return result

    def line(self, limit: int) -> bytes:
        result = bytearray()
        while len(result) < limit:
            part = self.recv(1)
            if not part:
                raise PinnedTransportError("Unexpected end of response headers")
            result.extend(part)
            if part == b"\n":
                if len(result) < 2 or result[-2:] != b"\r\n":
                    raise PinnedTransportError("Invalid response line ending")
                return bytes(result)
        raise PinnedResponseTooLarge("Response headers or chunk metadata exceed the limit")

    def exact(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            part = self.recv(min(65_536, size - len(result)))
            if not part:
                raise PinnedTransportError("Truncated response body")
            result.extend(part)
        return bytes(result)

    def until_eof(self, maximum: int) -> bytes:
        result = bytearray()
        while True:
            part = self.recv(min(65_536, maximum + 1 - len(result)))
            if not part:
                return bytes(result)
            result.extend(part)
            if len(result) > maximum:
                raise PinnedResponseTooLarge("Response body exceeds the limit")


def _header_line(line: bytes) -> tuple[str, str]:
    if not line.endswith(b"\r\n") or b":" not in line:
        raise PinnedTransportError("Invalid response header")
    name, value = line[:-2].split(b":", 1)
    if not _TOKEN.fullmatch(name) or any(char < 32 and char != 9 or char == 127 for char in value):
        raise PinnedTransportError("Invalid response header")
    return name.decode("ascii").lower(), value.decode("latin-1").strip(" \t")


def _response_headers(reader: _Reader) -> tuple[int, dict[str, str]]:
    status_line = reader.line(_MAX_HEADER_BYTES)
    status_match = _STATUS.fullmatch(status_line)
    if not status_match:
        raise PinnedTransportError("Invalid HTTP status line")
    status = int(status_match.group(1))
    used = len(status_line)
    headers: dict[str, str] = {}
    count = 0
    while True:
        line = reader.line(_MAX_HEADER_BYTES - used)
        used += len(line)
        if line == b"\r\n":
            break
        count += 1
        if count > _MAX_HEADER_COUNT:
            raise PinnedResponseTooLarge("Too many response headers")
        name, value = _header_line(line)
        if name in headers:
            if name in _CRITICAL_HEADERS:
                raise PinnedTransportError("Ambiguous response headers")
            headers[name] += ", " + value
        else:
            headers[name] = value
    return status, headers


def _chunked_body(reader: _Reader, maximum: int) -> bytes:
    result = bytearray()
    metadata = 0
    for _ in range(_MAX_CHUNKS):
        line = reader.line(min(8192, _MAX_CHUNK_METADATA_BYTES - metadata))
        metadata += len(line)
        size_text, _, extension = line[:-2].partition(b";")
        if (not size_text or not re.fullmatch(rb"[0-9A-Fa-f]+", size_text)
                or any(char < 32 or char == 127 for char in extension)):
            raise PinnedTransportError("Invalid chunk framing")
        size = int(size_text, 16)
        if size > maximum - len(result):
            raise PinnedResponseTooLarge("Response body exceeds the limit")
        if size == 0:
            trailers = 0
            while True:
                trailer = reader.line(_MAX_HEADER_BYTES - trailers)
                trailers += len(trailer)
                if trailer == b"\r\n":
                    return bytes(result)
                name, _ = _header_line(trailer)
                if name in _CRITICAL_HEADERS:
                    raise PinnedTransportError("Forbidden response trailer")
        result.extend(reader.exact(size))
        if reader.exact(2) != b"\r\n":
            raise PinnedTransportError("Invalid chunk framing")
    raise PinnedResponseTooLarge("Too many response chunks")


def _response_body(reader: _Reader, status: int, headers: dict[str, str], maximum: int) -> bytes:
    if "transfer-encoding" in headers and "content-length" in headers:
        raise PinnedTransportError("Ambiguous response framing")
    if status in {204, 304} or status in {301, 302, 303, 307, 308}:
        return b""
    transfer = headers.get("transfer-encoding")
    if transfer is not None:
        if transfer.casefold() != "chunked":
            raise PinnedTransportError("Unsupported transfer encoding")
        return _chunked_body(reader, maximum)
    length = headers.get("content-length")
    if length is not None:
        if not re.fullmatch(r"[0-9]{1,20}", length):
            raise PinnedTransportError("Invalid content length")
        size = int(length)
        if size > maximum:
            raise PinnedResponseTooLarge("Response body exceeds the limit")
        return reader.exact(size)
    return reader.until_eof(maximum)


def _decode_gzip(reader: _Reader, encoded: bytes, maximum: int) -> bytes:
    """Decode exactly one complete gzip member, with a bounded output."""
    reader.remaining()
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decoded = decoder.decompress(encoded, maximum + 1)
    except zlib.error:
        raise PinnedTransportError("Invalid gzip response") from None
    reader.remaining()
    if len(decoded) > maximum or decoder.unconsumed_tail:
        raise PinnedResponseTooLarge("Decoded response body exceeds the limit")
    if not decoder.eof or decoder.unused_data:
        raise PinnedTransportError("Incomplete or concatenated gzip response")
    return decoded


class PinnedTLSTransport:
    """Resolve DNS and perform direct TLS requests to a caller-selected IP.

    The caller must supply a real operator contact in the User-Agent. DNS calls
    have a deadline and at most four concurrent resolver threads per instance;
    a stuck system resolver holds its slot until the OS call returns.
    """

    def __init__(self, *, user_agent: str, dns_timeout_seconds: float = 3.0) -> None:
        self._user_agent = _validate_user_agent(user_agent)
        if (isinstance(dns_timeout_seconds, bool) or not isinstance(dns_timeout_seconds, (int, float))
                or not math.isfinite(dns_timeout_seconds) or not 0 < dns_timeout_seconds <= 30):
            raise ValueError("Invalid DNS timeout")
        self.dns_timeout_seconds = float(dns_timeout_seconds)
        self._dns_slots = threading.BoundedSemaphore(_DNS_SLOTS)

    @property
    def user_agent(self) -> str:
        return self._user_agent

    def resolve(self, hostname: str) -> tuple[str, ...]:
        host = normalize_host(hostname)
        if not self._dns_slots.acquire(blocking=False):
            raise TimeoutError("DNS resolver is busy")
        done = threading.Event()
        result: list[object] = []

        def lookup() -> None:
            try:
                result.append(socket.getaddrinfo(host, _HTTPS_PORT, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP))
            except Exception as exc:
                result.append(exc)
            finally:
                self._dns_slots.release()
                done.set()

        try:
            threading.Thread(target=lookup, daemon=True, name="recipe-dns").start()
        except Exception:
            self._dns_slots.release()
            raise
        if not done.wait(self.dns_timeout_seconds):
            raise TimeoutError("DNS lookup timed out")
        if not result or isinstance(result[0], Exception):
            raise PinnedTransportError("DNS lookup failed")
        addresses: set[str] = set()
        for family, socktype, _proto, _canonname, sockaddr in result[0]:
            if family not in {socket.AF_INET, socket.AF_INET6} or socktype != socket.SOCK_STREAM:
                raise PinnedTransportError("Unexpected DNS response")
            if family == socket.AF_INET6 and len(sockaddr) > 3 and sockaddr[3] != 0:
                raise PinnedTransportError("Scoped IPv6 addresses are not allowed")
            address = ipaddress.ip_address(sockaddr[0])
            if (sockaddr[1] != _HTTPS_PORT or address.version != (4 if family == socket.AF_INET else 6)
                    or (address.version == 6 and address.scope_id is not None)):
                raise PinnedTransportError("Unexpected DNS address")
            addresses.add(str(address))
            if len(addresses) > _MAX_DNS_RESULTS:
                raise PinnedTransportError("Too many DNS addresses")
        if not addresses:
            raise PinnedTransportError("No DNS addresses")
        return tuple(sorted(addresses))

    def fetch_once_pinned(
        self, url: str, *, connect_ip: str, timeout_seconds: float, max_bytes: int
    ) -> PageFetchResponse:
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120):
            raise ValueError("Invalid request timeout")
        if type(max_bytes) is not int or not 0 < max_bytes <= _MAX_BODY_BYTES:
            raise ValueError("Invalid response body limit")
        if not isinstance(connect_ip, str) or "%" in connect_ip:
            raise ValueError("A numeric unscoped destination is required")
        canonical = canonical_recipe_url(url)
        parsed = urlsplit(canonical)
        host = parsed.hostname
        assert host is not None
        validated = validate_redirect_hops({host}, set(), [canonical], {host: [connect_ip]})
        address = ipaddress.ip_address(validated[0][1][0])
        family = socket.AF_INET if address.version == 4 else socket.AF_INET6
        destination = (str(address), _HTTPS_PORT) if address.version == 4 else (str(address), _HTTPS_PORT, 0, 0)
        target = parsed.path + ("?" + parsed.query if parsed.query else "")
        request = (f"GET {target} HTTP/1.1\r\nHost: {host}\r\n"
                   f"User-Agent: {self.user_agent}\r\nAccept: text/html, application/xhtml+xml, text/plain\r\n"
                   "Accept-Encoding: gzip, identity\r\nConnection: close\r\n\r\n").encode("ascii")
        deadline = time.monotonic() + float(timeout_seconds)
        with socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP) as raw:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Page request deadline exceeded")
            raw.settimeout(remaining)
            raw.connect(destination)
            peer = raw.getpeername()
            if ipaddress.ip_address(peer[0]) != address or peer[1] != _HTTPS_PORT:
                raise PinnedTransportError("Connected peer does not match the pinned destination")
            context = _tls_context()
            if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
                raise PinnedTransportError("TLS certificate verification is required")
            with context.wrap_socket(raw, server_hostname=host, do_handshake_on_connect=False,
                                     suppress_ragged_eofs=False) as tls:
                reader = _Reader(tls, deadline)
                tls.settimeout(reader.remaining())
                tls.do_handshake()
                tls.settimeout(reader.remaining())
                tls.sendall(request)
                reader.remaining()
                status, headers = _response_headers(reader)
                has_body = status not in {204, 304, 301, 302, 303, 307, 308}
                encoding = headers.get("content-encoding", "identity").strip().casefold()
                if has_body and encoding not in {"identity", "gzip"}:
                    raise PinnedTransportError("Unsupported content encoding")
                body = _response_body(reader, status, headers, max_bytes)
                if has_body and encoding == "gzip":
                    body = _decode_gzip(reader, body, max_bytes)
                    headers["content-encoding"] = "identity"
                    headers.pop("transfer-encoding", None)
                    headers["content-length"] = str(len(body))
                return PageFetchResponse(status_code=status, headers=headers, body=body)
