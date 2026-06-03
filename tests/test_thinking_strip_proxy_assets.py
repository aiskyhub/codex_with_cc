#!/usr/bin/env python3
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
