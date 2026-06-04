#!/usr/bin/env python3
"""Local Anthropic-compatible proxy that strips thinking blocks for Claude Code.

Claude Code can talk to Anthropic-compatible endpoints that emit `thinking`
content blocks, but some proxies cannot accept those blocks back in the next
tool-result turn. This proxy removes thinking blocks both inbound and outbound
while preserving text/tool_use/tool_result traffic.

中文说明：这是给 Claude Code / codex-with-cc 使用的本地兼容层。Claude Code
侧不会看到 thinking block；上游 DeepSeek 兼容端点如果需要 thinking 续轮，
代理会在内部缓存并按 tool_use 关系处理。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_UPSTREAM = "https://api.deepseek.com/anthropic"
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
STRIPPED_BETA_PREFIXES = ("interleaved-thinking", "effort")
THINKING_BLOCK_TYPES = {"thinking", "redacted_thinking"}
THINKING_DELTA_TYPES = {"thinking_delta", "signature_delta"}
OMIT = object()


def strip_thinking(value: Any) -> Any:
    """Remove thinking blocks and thinking config from JSON-like payloads."""
    if isinstance(value, list):
        stripped = []
        for item in value:
            clean = strip_thinking(item)
            if clean is not OMIT:
                stripped.append(clean)
        return stripped
    if isinstance(value, dict):
        if value.get("type") in THINKING_BLOCK_TYPES:
            return OMIT
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"thinking", "signature"}:
                continue
            clean = strip_thinking(item)
            if clean is not OMIT:
                out[key] = clean
        return out
    return value


def inject_cached_thinking(payload: Any, cache: dict[str, list[dict[str, Any]]], *, enabled: bool = True) -> Any:
    """Strip client-visible thinking while reinjecting cached blocks for upstream."""
    if not isinstance(payload, dict):
        return strip_thinking(payload)
    clean = strip_thinking(payload)
    if not enabled:
        return clean
    if not isinstance(clean, dict):
        return clean
    messages = clean.get("messages")
    if not isinstance(messages, list):
        return clean
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        new_content = []
        injected = False
        for block in content:
            if (
                not injected
                and isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("id") in cache
            ):
                new_content.extend(copy.deepcopy(cache[str(block["id"])]))
                injected = True
            new_content.append(block)
        message["content"] = new_content
    return clean


def capture_thinking_for_tool_uses(payload: Any, cache: dict[str, list[dict[str, Any]]]) -> None:
    """Remember hidden thinking blocks so later tool-result turns can satisfy upstream."""
    if not isinstance(payload, dict):
        return
    candidates: list[dict[str, Any]] = []
    content = payload.get("content")
    if isinstance(payload.get("message"), dict):
        content = payload["message"].get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in THINKING_BLOCK_TYPES:
            candidates.append(copy.deepcopy(block))
            continue
        if block.get("type") == "tool_use" and block.get("id") and candidates:
            cache[str(block["id"])] = copy.deepcopy(candidates)
            candidates = []


def strip_beta_header(value: str) -> str:
    kept = []
    for raw in value.split(","):
        beta = raw.strip()
        if not beta:
            continue
        if any(beta.startswith(prefix) for prefix in STRIPPED_BETA_PREFIXES):
            continue
        kept.append(beta)
    return ",".join(kept)


def should_stream(headers: dict[str, str], body: bytes) -> bool:
    if "text/event-stream" in headers.get("content-type", "").lower():
        return True
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return False
    return bool(isinstance(payload, dict) and payload.get("stream"))


def is_thinking_rejection(status: int, body: bytes) -> bool:
    if status not in {400, 422}:
        return False
    text = body.decode("utf-8", errors="ignore").lower()
    return "thinking" in text or "tinking" in text


class ThinkingStripHandler(BaseHTTPRequestHandler):
    server_version = "thinking-strip-proxy/0.1"
    protocol_version = "HTTP/1.1"

    def handle(self) -> None:
        try:
            super().handle()
        except ConnectionResetError:
            return

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/health", "/healthz"}:
            self._send_json(200, {"ok": True, "upstream": self.server.upstream})
            return
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy()

    def _upstream_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.server.upstream)
        incoming = urllib.parse.urlsplit(self.path)
        base_path = parsed.path.rstrip("/")
        request_path = incoming.path
        if base_path and request_path.startswith(base_path + "/"):
            request_path = request_path[len(base_path) :]
        path = f"{base_path}{request_path}"
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, incoming.query, incoming.fragment)
        )

    def _request_body(self, *, inject_cached: bool = True) -> bytes:
        length = int(self.headers.get("content-length") or "0")
        body = self.rfile.read(length) if length else b""
        return self._transform_json_body(body, inject_cached=inject_cached)

    def _transform_json_body(self, body: bytes, *, inject_cached: bool = True) -> bytes:
        if "application/json" not in self.headers.get("content-type", "").lower():
            return body
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            return body
        payload = inject_cached_thinking(payload, self.server.thinking_by_tool_use, enabled=inject_cached)
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _forward_headers(self, body: bytes) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS:
                continue
            if lower == "anthropic-beta":
                value = strip_beta_header(value)
                if not value:
                    continue
            if lower == "accept-encoding":
                continue
            headers[key] = value
        headers["Host"] = urllib.parse.urlsplit(self.server.upstream).netloc
        headers["Accept-Encoding"] = "identity"
        if body:
            headers["Content-Length"] = str(len(body))
        return headers

    def _proxy(self) -> None:
        body = self._request_body()
        headers = self._forward_headers(body)
        req = urllib.request.Request(
            self._upstream_url(),
            data=body if self.command not in {"GET", "HEAD"} else None,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.server.timeout_seconds) as upstream:
                if should_stream(dict(upstream.headers.items()), body):
                    self._send_stream(upstream)
                else:
                    self._send_response(
                        upstream.status,
                        dict(upstream.headers.items()),
                        upstream.read(),
                    )
        except urllib.error.HTTPError as exc:
            error_body = exc.read()
            if self.server.thinking_by_tool_use and is_thinking_rejection(exc.code, error_body):
                self.server.thinking_by_tool_use.clear()
                body = self._transform_json_body(body, inject_cached=False)
                headers = self._forward_headers(body)
                req = urllib.request.Request(
                    self._upstream_url(),
                    data=body if self.command not in {"GET", "HEAD"} else None,
                    headers=headers,
                    method=self.command,
                )
                try:
                    with urllib.request.urlopen(req, timeout=self.server.timeout_seconds) as upstream:
                        if should_stream(dict(upstream.headers.items()), body):
                            self._send_stream(upstream)
                        else:
                            self._send_response(
                                upstream.status,
                                dict(upstream.headers.items()),
                                upstream.read(),
                            )
                except urllib.error.HTTPError as retry_exc:
                    self._send_response(retry_exc.code, dict(retry_exc.headers.items()), retry_exc.read())
                return
            self._send_response(exc.code, dict(exc.headers.items()), error_body)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            self._send_json(502, {"error": "proxy_upstream_error", "detail": str(exc)})

    def _send_response(self, status: int, headers: dict[str, str], body: bytes) -> None:
        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        if "application/json" in content_type.lower() and body:
            try:
                payload = json.loads(body.decode("utf-8"))
                capture_thinking_for_tool_uses(payload, self.server.thinking_by_tool_use)
                body = json.dumps(strip_thinking(payload), ensure_ascii=False).encode("utf-8")
            except json.JSONDecodeError:
                pass
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            if key.lower() == "content-encoding":
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, upstream: Any) -> None:
        self.send_response(upstream.status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        buffer = b""
        hidden_indexes: dict[int, dict[str, Any]] = {}
        pending_thinking: list[dict[str, Any]] = []
        index_map: dict[int, int] = {}
        next_index = 0

        def mapped_index(index: int) -> int | None:
            nonlocal next_index
            if index in hidden_indexes:
                return None
            if index not in index_map:
                index_map[index] = next_index
                next_index += 1
            return index_map[index]

        while True:
            chunk = upstream.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n\n" in buffer or b"\r\n\r\n" in buffer:
                sep = b"\n\n" if b"\n\n" in buffer else b"\r\n\r\n"
                frame, buffer = buffer.split(sep, 1)
                out = self._filter_sse_frame(
                    frame,
                    hidden_indexes,
                    pending_thinking,
                    mapped_index,
                )
                if out:
                    self.wfile.write(out)
                    self.wfile.flush()
        if buffer.strip():
            out = self._filter_sse_frame(
                buffer,
                hidden_indexes,
                pending_thinking,
                mapped_index,
            )
            if out:
                self.wfile.write(out)
                self.wfile.flush()

    def _filter_sse_frame(
        self,
        frame: bytes,
        hidden: dict[int, dict[str, Any]],
        pending_thinking: list[dict[str, Any]],
        mapped_index: Any,
    ) -> bytes:
        text = frame.decode("utf-8", errors="replace")
        event = None
        data_lines = []
        for line in text.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if not data_lines:
            return frame + b"\n\n"
        data = "\n".join(data_lines)
        if data == "[DONE]":
            return (f"event: {event}\n" if event else "").encode() + b"data: [DONE]\n\n"
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return frame + b"\n\n"

        event_type = payload.get("type")
        index = payload.get("index")
        if event_type == "content_block_start":
            block_type = (payload.get("content_block") or {}).get("type")
            if block_type in THINKING_BLOCK_TYPES:
                if isinstance(index, int):
                    block = copy.deepcopy(payload.get("content_block") or {})
                    block.setdefault("type", block_type)
                    block.setdefault("thinking", "")
                    hidden[index] = block
                return b""
            content_block = payload.get("content_block") or {}
            if (
                isinstance(content_block, dict)
                and content_block.get("type") == "tool_use"
                and content_block.get("id")
                and pending_thinking
            ):
                self.server.thinking_by_tool_use[str(content_block["id"])] = copy.deepcopy(
                    pending_thinking
                )
                pending_thinking.clear()
            if isinstance(index, int):
                payload["index"] = mapped_index(index)
        elif event_type in {"content_block_delta", "content_block_stop"} and isinstance(index, int):
            if index in hidden:
                block = hidden[index]
                delta = payload.get("delta") if isinstance(payload.get("delta"), dict) else {}
                if delta.get("type") == "thinking_delta":
                    block["thinking"] = str(block.get("thinking") or "") + str(
                        delta.get("thinking") or ""
                    )
                elif delta.get("type") == "signature_delta":
                    block["signature"] = str(block.get("signature") or "") + str(
                        delta.get("signature") or ""
                    )
                if event_type == "content_block_stop":
                    completed = hidden.pop(index)
                    if completed.get("thinking") or completed.get("signature"):
                        pending_thinking.append(copy.deepcopy(completed))
                return b""
            new_index = mapped_index(index)
            if new_index is None:
                return b""
            payload["index"] = new_index
            delta_type = (payload.get("delta") or {}).get("type")
            if delta_type in THINKING_DELTA_TYPES:
                return b""
        else:
            payload = strip_thinking(payload)
            if payload is OMIT:
                return b""

        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        prefix = f"event: {event}\n" if event else ""
        return f"{prefix}data: {data}\n\n".encode()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("THINKING_STRIP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("THINKING_STRIP_PORT", "9099")))
    parser.add_argument(
        "--upstream",
        default=os.getenv("THINKING_STRIP_UPSTREAM", DEFAULT_UPSTREAM),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("THINKING_STRIP_TIMEOUT", "600")),
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ThinkingStripHandler)
    server.upstream = args.upstream.rstrip("/")
    server.timeout_seconds = args.timeout
    server.thinking_by_tool_use = {}
    print(f"thinking-strip proxy listening on http://{args.host}:{args.port}", file=sys.stderr)
    print(f"upstream: {server.upstream}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
