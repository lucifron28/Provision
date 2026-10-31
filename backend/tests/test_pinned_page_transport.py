from __future__ import annotations

import gzip
import socket
import ssl
import subprocess
import threading
import time
from urllib.parse import urlsplit

import pytest

from app.services import pinned_page_transport as transport_module
from app.services.pinned_page_transport import (
    PinnedResponseTooLarge,
    PinnedTLSTransport,
    PinnedTransportError,
)
from app.services.source_urls import validate_redirect_hops
from app.services.wikimedia_robots import RobotsPolicyError, wikimedia_robots_allowed


USER_AGENT = "ProvisionRecipeBot/1.0 (https://operator.example/contact)"


@pytest.fixture(scope="module")
def tls_certificate(tmp_path_factory):
    directory = tmp_path_factory.mktemp("pinned-page-tls")
    certificate = directory / "certificate.pem"
    key = directory / "private-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(certificate), "-days", "1",
            "-subj", "/CN=example.com", "-addext",
            "subjectAltName=DNS:example.com,DNS:en.wikibooks.org",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, key


@pytest.fixture
def tls_server(monkeypatch, tls_certificate):
    certificate, key = tls_certificate
    running = []

    def start(response: bytes, *, delay: float = 0):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)
        port = listener.getsockname()[1]
        seen = {"sni": [], "requests": []}
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(certificate), str(key))
        server_context.set_servername_callback(lambda _sock, name, _ctx: seen["sni"].append(name))

        def serve():
            try:
                connection, _ = listener.accept()
                with connection, server_context.wrap_socket(connection, server_side=True) as tls:
                    tls.settimeout(3)
                    request = bytearray()
                    while b"\r\n\r\n" not in request:
                        chunk = tls.recv(4096)
                        if not chunk:
                            return
                        request.extend(chunk)
                    seen["requests"].append(bytes(request))
                    if delay:
                        tls.sendall(response[:1])
                        threading.Event().wait(delay)
                        tls.sendall(response[1:])
                    else:
                        tls.sendall(response)
                    try:
                        tls.unwrap()
                    except (OSError, ssl.SSLError):
                        pass
            except (OSError, ssl.SSLError):
                pass
            finally:
                listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        running.append((listener, thread))
        monkeypatch.setattr(transport_module, "_HTTPS_PORT", port)

        # The local TLS server is loopback-only; production destination checks
        # are tested separately without this test-only substitution.
        def allow_local(_initial, _redirect, urls, addresses):
            host = urlsplit(urls[0]).hostname
            return [(urls[0], (addresses[host][0],))]

        monkeypatch.setattr(transport_module, "validate_redirect_hops", allow_local)

        def trusted_context():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=str(certificate))
            return context

        monkeypatch.setattr(transport_module, "_tls_context", trusted_context)
        return seen

    yield start
    for listener, thread in running:
        listener.close()
        thread.join(timeout=4)


def fetch(*, url="https://example.com/recipe", max_bytes=1000, timeout=2):
    return PinnedTLSTransport(user_agent=USER_AGENT).fetch_once_pinned(
        url, connect_ip="127.0.0.1", timeout_seconds=timeout, max_bytes=max_bytes
    )


def test_direct_tls_uses_pinned_peer_original_sni_host_and_identification(tls_server, monkeypatch):
    seen = tls_server(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 5\r\n\r\nhello")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("fetch must not resolve again"))
    result = fetch(url="https://example.com/recipe?b=2&a=1")
    assert result.status_code == 200
    assert result.body == b"hello"
    assert seen["sni"] == ["example.com"]
    request = seen["requests"][0]
    assert request.startswith(b"GET /recipe?a=1&b=2 HTTP/1.1\r\n")
    assert b"\r\nHost: example.com\r\n" in request
    assert f"\r\nUser-Agent: {USER_AGENT}\r\n".encode() in request
    assert b"\r\nAccept-Encoding: gzip, identity\r\n" in request


def test_certificate_hostname_mismatch_fails(tls_server):
    tls_server(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
    with pytest.raises(ssl.SSLCertVerificationError):
        fetch(url="https://other.com/recipe")


def test_robots_request_accepts_plain_text(tls_server):
    body = b"User-agent: *\nDisallow: /private\n"
    seen = tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
        + str(len(body)).encode() + b"\r\n\r\n" + body
    )
    result = fetch(url="https://example.com/robots.txt")
    assert result.body == body
    assert result.headers["content-type"] == "text/plain"
    assert b"\r\nAccept: application/json, text/html, application/xhtml+xml, text/plain\r\n" in seen["requests"][0]


@pytest.mark.parametrize("scenario", ["allowed", "disallowed", "malformed_gzip"])
def test_wikimedia_robots_uses_real_pinned_tls_and_gzip(
    tls_server, monkeypatch, scenario
):
    policy = b"User-agent: *\nDisallow: /wiki/Private\nAllow: /wiki/Cookbook:Adobo\n"
    encoded = gzip.compress(policy, mtime=0)
    if scenario == "malformed_gzip":
        encoded = encoded[:-1]
    seen = tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
        b"Content-Encoding: gzip\r\nContent-Length: "
        + str(len(encoded)).encode() + b"\r\n\r\n" + encoded
    )
    port = transport_module._HTTPS_PORT
    resolutions = []
    connections = []

    class LocalPinnedSocket(socket.socket):
        def connect(self, destination):
            connections.append(destination)
            return super().connect(("127.0.0.1", port))

        def getpeername(self):
            return ("8.8.8.8", port)

    class LocalSocketProvider:
        def __getattr__(self, name):
            return getattr(socket, name)

        def socket(self, *args, **kwargs):
            return LocalPinnedSocket(*args, **kwargs)

        def getaddrinfo(self, host, service, family, kind, protocol):
            resolutions.append((host, service))
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port))]

    # DNS and TCP are routed to the local server; both real public-address
    # validation layers, the transport, TLS, gzip decoder, and robots parser run.
    monkeypatch.setattr(transport_module, "socket", LocalSocketProvider())
    monkeypatch.setattr(transport_module, "validate_redirect_hops", validate_redirect_hops)
    transport = PinnedTLSTransport(user_agent=USER_AGENT)
    target = (
        "https://en.wikibooks.org/wiki/Private"
        if scenario == "disallowed"
        else "https://en.wikibooks.org/wiki/Cookbook:Adobo"
    )
    if scenario == "malformed_gzip":
        with pytest.raises(RobotsPolicyError, match="Robots policy unavailable"):
            wikimedia_robots_allowed(target, transport=transport)
    else:
        assert wikimedia_robots_allowed(target, transport=transport) is (scenario == "allowed")
    assert resolutions == [("en.wikibooks.org", port)]
    assert connections == [("8.8.8.8", port)]
    assert seen["sni"] == ["en.wikibooks.org"]
    request = seen["requests"][0]
    assert request.startswith(b"GET /robots.txt HTTP/1.1\r\n")
    assert b"\r\nHost: en.wikibooks.org\r\n" in request
    assert b"\r\nAccept-Encoding: gzip, identity\r\n" in request
    assert b"text/plain" in request


def test_untrusted_certificate_fails(tls_server, monkeypatch):
    tls_server(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

    def system_context():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_default_certs()
        return context

    monkeypatch.setattr(transport_module, "_tls_context", system_context)
    with pytest.raises(ssl.SSLCertVerificationError):
        fetch()


def test_redirect_is_returned_without_following_or_reading_body(tls_server):
    seen = tls_server(
        b"HTTP/1.1 302 Found\r\nLocation: https://elsewhere.com/recipe\r\n"
        b"Content-Length: 999999999\r\n\r\n"
    )
    result = fetch(max_bytes=4)
    assert result.status_code == 302
    assert result.headers["location"] == "https://elsewhere.com/recipe"
    assert result.body == b""
    assert len(seen["requests"]) == 1


def test_chunked_gzip_is_decoded_and_headers_describe_returned_body(tls_server):
    compressed = gzip.compress(b"abcde", mtime=0)
    first, second = compressed[:10], compressed[10:]
    tls_server(
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Encoding: gzip\r\n\r\n"
        + f"{len(first):x}\r\n".encode() + first + b"\r\n"
        + f"{len(second):x}\r\n".encode() + second + b"\r\n0\r\nX-End: yes\r\n\r\n"
    )
    result = fetch(max_bytes=len(compressed))
    assert result.body == b"abcde"
    assert result.headers["content-encoding"] == "identity"
    assert result.headers["content-length"] == "5"
    assert "transfer-encoding" not in result.headers


def test_gzip_fixed_length_supports_exact_decoded_limit(tls_server):
    plain = b"x" * 1000
    compressed = gzip.compress(plain, mtime=0)
    tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Encoding: GZip\r\nContent-Length: "
        + str(len(compressed)).encode() + b"\r\n\r\n" + compressed
    )
    result = fetch(max_bytes=len(plain))
    assert result.body == plain
    assert result.headers["content-encoding"] == "identity"
    assert result.headers["content-length"] == str(len(plain))


def test_empty_gzip_is_valid_and_normalized(tls_server):
    compressed = gzip.compress(b"", mtime=0)
    tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: "
        + str(len(compressed)).encode() + b"\r\n\r\n" + compressed
    )
    result = fetch(max_bytes=len(compressed))
    assert result.body == b""
    assert result.headers["content-encoding"] == "identity"
    assert result.headers["content-length"] == "0"


@pytest.mark.parametrize("chunked", [False, True])
def test_gzip_rejects_compressed_wire_over_limit(tls_server, chunked):
    plain = bytes(range(128))
    compressed = gzip.compress(plain, mtime=0)
    assert len(compressed) > len(plain)
    if chunked:
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: chunked\r\n\r\n"
            + f"{len(compressed):x}\r\n".encode() + compressed + b"\r\n0\r\n\r\n"
        )
    else:
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: "
            + str(len(compressed)).encode() + b"\r\n\r\n" + compressed
        )
    tls_server(response)
    with pytest.raises(PinnedResponseTooLarge):
        fetch(max_bytes=len(plain))


def test_gzip_rejects_decoded_body_over_limit(tls_server):
    compressed = gzip.compress(b"x" * 1001, mtime=0)
    assert len(compressed) < 1000
    tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: "
        + str(len(compressed)).encode() + b"\r\n\r\n" + compressed
    )
    with pytest.raises(PinnedResponseTooLarge):
        fetch(max_bytes=1000)


@pytest.mark.parametrize("kind", ["malformed", "truncated", "bad_crc", "concatenated", "trailing"])
def test_gzip_rejects_invalid_or_multiple_members(tls_server, kind):
    compressed = gzip.compress(b"valid", mtime=0)
    variants = {
        "malformed": b"not a gzip stream",
        "truncated": compressed[:-1],
        "bad_crc": compressed[:-8] + bytes([compressed[-8] ^ 1]) + compressed[-7:],
        "concatenated": compressed + gzip.compress(b"x" * 100_000, mtime=0),
        "trailing": compressed + b"unexpected",
    }
    body = variants[kind]
    tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: "
        + str(len(body)).encode() + b"\r\n\r\n" + body
    )
    with pytest.raises(PinnedTransportError):
        fetch(max_bytes=1000)


@pytest.mark.parametrize("encoding", ["br", "gzip, identity", "deflate"])
def test_unsupported_content_encodings_are_rejected(tls_server, encoding):
    tls_server(
        b"HTTP/1.1 200 OK\r\nContent-Encoding: "
        + encoding.encode() + b"\r\nContent-Length: 0\r\n\r\n"
    )
    with pytest.raises(PinnedTransportError, match="Unsupported content encoding"):
        fetch()


def test_redirect_with_gzip_header_is_not_decoded_or_normalized(tls_server):
    tls_server(
        b"HTTP/1.1 302 Found\r\nLocation: https://elsewhere.com/recipe\r\n"
        b"Content-Encoding: gzip\r\nContent-Length: 100\r\n\r\n"
    )
    result = fetch(max_bytes=4)
    assert result.status_code == 302
    assert result.body == b""
    assert result.headers["content-encoding"] == "gzip"


@pytest.mark.parametrize(
    "response,limit,error",
    [
        (b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello", 4, PinnedResponseTooLarge),
        (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n", 4, PinnedResponseTooLarge),
        (b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nab", 4, (PinnedTransportError, ssl.SSLError)),
        (b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\nx", 10, PinnedTransportError),
        (b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 60\r\nRetry-After: 120\r\nContent-Length: 0\r\n\r\n", 10, PinnedTransportError),
        (b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n", 10, PinnedTransportError),
        (b"HTTP/1.1 200 OK\r\nLocation: https://example.com/a\r\nLocation: https://example.com/b\r\n\r\n", 10, PinnedTransportError),
        (b"HTTP/1.1 200 OK\r\nX-Huge: " + b"a" * 32768 + b"\r\n\r\n", 10, PinnedResponseTooLarge),
        (b"HTTP/1.1 200 OK\r\n" + b"X: a\r\n" * 101 + b"\r\n", 10, PinnedResponseTooLarge),
    ],
)
def test_malformed_or_oversized_responses_fail_closed(tls_server, response, limit, error):
    tls_server(response)
    with pytest.raises(error):
        fetch(max_bytes=limit)


def test_absolute_request_deadline_stops_a_slow_response(tls_server):
    tls_server(b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nx", delay=0.4)
    start = time.monotonic()
    with pytest.raises((TimeoutError, socket.timeout)):
        fetch(timeout=0.15)
    assert time.monotonic() - start < 1.5


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:8.8.8.8", "64:ff9b::808:808", "224.0.0.1", "2001:4860:4860::8888%eth0"],
)
def test_nonpublic_and_special_destinations_fail_before_connect(monkeypatch, address):
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("unsafe address reached connect"))
    with pytest.raises(ValueError):
        PinnedTLSTransport(user_agent=USER_AGENT).fetch_once_pinned(
            "https://example.com/recipe", connect_ip=address, timeout_seconds=1, max_bytes=100
        )


def test_connected_peer_must_equal_the_pinned_address(monkeypatch):
    connections = []

    class WrongPeer:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, _timeout):
            pass

        def connect(self, destination):
            connections.append(destination)

        def getpeername(self):
            return ("1.1.1.1", 443)

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: WrongPeer())
    monkeypatch.setattr(transport_module, "_tls_context", lambda: pytest.fail("TLS must not start"))
    with pytest.raises(PinnedTransportError, match="pinned destination"):
        PinnedTLSTransport(user_agent=USER_AGENT).fetch_once_pinned(
            "https://example.com/recipe", connect_ip="8.8.8.8", timeout_seconds=1, max_bytes=100
        )
    assert connections == [("8.8.8.8", 443)]


def test_dns_preserves_all_addresses_so_mixed_answers_are_rejected(monkeypatch):
    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: answers)
    addresses = PinnedTLSTransport(user_agent=USER_AGENT).resolve("example.com")
    assert set(addresses) == {"8.8.8.8", "127.0.0.1"}
    with pytest.raises(ValueError):
        validate_redirect_hops({"example.com"}, set(), ["https://example.com/recipe"], {"example.com": list(addresses)})


def test_dns_timeout_fails_closed_with_bounded_resolver_slots(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: (release.wait(2), [])[1])
    provider = PinnedTLSTransport(user_agent=USER_AGENT, dns_timeout_seconds=0.02)
    try:
        for _ in range(4):
            with pytest.raises(TimeoutError, match="timed out"):
                provider.resolve("example.com")
        with pytest.raises(TimeoutError, match="busy"):
            provider.resolve("example.com")
    finally:
        release.set()


@pytest.mark.parametrize(
    "agent",
    ["", "python-requests/2.0", "python-requests/2.0 (ops@operator.example)",
     "ProvisionBot/1.0", "ProvisionBot/1.0 (no contact)",
     "ProvisionBot/1.0 (https://@)", "ProvisionBot/1.0 (https://operator.example:invalid)",
     "ProvisionBot/1.0 (https://operator.example/)\r\nX-Forged: yes"],
)
def test_identifying_user_agent_is_required_and_header_injection_is_rejected(agent):
    with pytest.raises(ValueError):
        PinnedTLSTransport(user_agent=agent)


def test_email_and_wiki_account_contacts_are_supported():
    assert PinnedTLSTransport(user_agent="ProvisionBot/1.0 (ops@operator.example)")
    assert PinnedTLSTransport(user_agent="ProvisionBot/1.0 (wikipedia:en; User:ExampleBot)")
