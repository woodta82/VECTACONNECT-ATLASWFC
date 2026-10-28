"""Verification matrix #8 (retrieval): SSRF policy."""
import http.server
import threading

import pytest

from app.domain import retrieval as r


def resolver_for(mapping):
    def _resolve(host, port):
        if host not in mapping:
            raise OSError("NXDOMAIN")
        return mapping[host]
    return _resolve


@pytest.mark.parametrize("addr", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "169.254.10.10", "100.64.0.1",
    "0.0.0.0", "224.0.0.1", "240.0.0.1", "::1", "fe80::1", "fc00::1", "fd00:ec2::254", "::ffff:127.0.0.1",
    "::ffff:10.1.2.3", "2002:0a00:0001::1", "64:ff9b::a00:1", "::",
])
def test_forbidden_addresses(addr):
    assert r.is_forbidden_address(addr) is not None


@pytest.mark.parametrize("addr", ["93.184.215.14", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_allowed(addr):
    assert r.is_forbidden_address(addr) is None


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "gopher://x", "ftp://example.com/a", "http://user:pw@example.com/",
    "http://localhost/", "http://metadata.google.internal/", "http://printer.local/", "http://example.com:22/",
    "http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/",
])
def test_blocked_urls(url):
    with pytest.raises(r.RetrievalBlocked):
        r.validate_url(url, resolver_for({"example.com": ["93.184.215.14"]}))


def test_dns_name_resolving_to_private_is_blocked():
    with pytest.raises(r.RetrievalBlocked, match="private"):
        r.validate_url("https://evil.example/", resolver_for({"evil.example": ["93.184.215.14", "10.0.0.7"]}))


def _transport(responses):
    calls = []

    def t(target, pinned, max_bytes, timeout):
        calls.append((target.url, pinned))
        return responses[target.url]
    return t, calls


def test_redirect_to_metadata_is_blocked():
    t, calls = _transport({
        "https://news.example/a": r.RawResponse(302, {"location": "http://169.254.169.254/latest/"}, b"", False),
    })
    with pytest.raises(r.RetrievalBlocked):
        r.fetch("https://news.example/a", resolver=resolver_for({"news.example": ["93.184.215.14"]}), transport=t)
    assert len(calls) == 1  # the metadata address was never contacted


def test_redirect_to_name_rebinding_to_private_is_blocked():
    t, calls = _transport({
        "https://news.example/a": r.RawResponse(301, {"location": "https://rebind.example/x"}, b"", False),
    })
    res = resolver_for({"news.example": ["93.184.215.14"], "rebind.example": ["192.168.0.10"]})
    with pytest.raises(r.RetrievalBlocked):
        r.fetch("https://news.example/a", resolver=res, transport=t)
    assert calls == [("https://news.example/a", "93.184.215.14")]


def test_connection_is_pinned_to_validated_address():
    t, calls = _transport({"https://news.example/a": r.RawResponse(200, {"content-type": "text/html"}, b"<p>ok</p>", False)})
    out = r.fetch("https://news.example/a", resolver=resolver_for({"news.example": ["93.184.215.14"]}), transport=t)
    assert calls[0][1] == "93.184.215.14"
    assert out.sha256 and out.final_url == "https://news.example/a"


def test_size_type_and_hop_limits():
    res = resolver_for({"n.example": ["93.184.215.14"]})
    t, _ = _transport({"https://n.example/big": r.RawResponse(200, {"content-type": "text/html"}, b"x", True)})
    with pytest.raises(r.RetrievalBlocked, match="exceeds"):
        r.fetch("https://n.example/big", resolver=res, transport=t)
    t, _ = _transport({"https://n.example/exe": r.RawResponse(200, {"content-type": "application/x-msdownload"}, b"MZ", False)})
    with pytest.raises(r.RetrievalBlocked, match="content type"):
        r.fetch("https://n.example/exe", resolver=res, transport=t)
    loop = {f"https://n.example/{i}": r.RawResponse(302, {"location": f"/{i + 1}"}, b"", False) for i in range(10)}
    t, _ = _transport(loop)
    with pytest.raises(r.RetrievalBlocked, match="redirects"):
        r.fetch("https://n.example/0", resolver=res, transport=t)


def test_real_socket_to_local_server_is_refused_by_policy():
    """A real HTTP server on loopback: the default resolver + transport must
    refuse before any connection is made."""
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        port = srv.server_address[1]
        with pytest.raises(r.RetrievalBlocked):
            r.fetch(f"http://127.0.0.1:{port}/")
        with pytest.raises(r.RetrievalBlocked):
            r.fetch("http://localhost:8080/")
    finally:
        srv.shutdown()
    assert hits == []
