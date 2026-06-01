#!/usr/bin/env python3
from __future__ import annotations

import sys

from runtime import main


if __name__ == "__main__":
    raise SystemExit(main(["openai-compatible-report", *sys.argv[1:]]))
