"""Atomic file writes (temporary file, then ``os.replace``)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def write_json_atomic(path: Path, payload: object) -> None:
    write_text_atomic(path, json.dumps(payload, indent=1, sort_keys=True) + "\n")
