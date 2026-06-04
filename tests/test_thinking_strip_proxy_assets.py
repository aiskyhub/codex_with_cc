#!/usr/bin/env python3
import importlib.util
import io
import json
import threading
import urllib.error
import urllib.request
from http.client import HTTPConnection
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_thinking_strip_proxy_launcher_is_utf8_text() -> None:
    launcher = REPO / "scripts" / "start_thinking_strip_proxy.ps1"
    text = read_utf8(launcher)

    assert "thinking_strip_proxy.py" in text
    assert "Start-Process" in text
    assert "Invoke-RestMethod" in text


def test_verification_doc_is_utf8_markdown() -> None:
    verification = REPO / "docs" / "VERIFICATION.md"
    text = read_utf8(verification)

    assert text.startswith("# ")
    assert "verify_delegate_workflow" in text
    assert "RunId" in text


def load_proxy_module():
    path = REPO / "scripts" / "thinking_strip_proxy.py"
    spec = importlib.util.spec_from_file_location("thinking_strip_proxy_for_tests", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_thinking_proxy_retries_without_cached_thinking_when_provider_rejects_it(monkeypatch) -> None:
    proxy = load_proxy_module()
    calls: list[bytes] = []

    class FakeResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self) -> bytes:
            return b'{"ok":true}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0):
        body = request.data or b""
        calls.append(body)
        if len(calls) == 1:
            assert b'"thinking"' in body
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"error":{"message":"content[].tinking is not accepted"}}'),
            )
        assert b'"thinking"' not in body
        assert b'"tinking"' not in body
        return FakeResponse()

    monkeypatch.setattr(proxy.urllib.request, "urlopen", fake_urlopen)

    server = proxy.ThreadingHTTPServer(("127.0.0.1", 0), proxy.ThinkingStripHandler)
    server.upstream = "https://example.invalid/anthropic"
    server.timeout_seconds = 1
    server.thinking_by_tool_use = {"tool-1": [{"type": "thinking", "thinking": "hidden", "signature": "sig"}]}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "tool-1", "name": "run", "input": {}}],
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("POST", "/v1/messages", body=body, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        response_body = response.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == 200
    assert json.loads(response_body.decode("utf-8")) == {"ok": True}
    assert len(calls) == 2
