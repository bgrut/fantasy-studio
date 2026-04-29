from __future__ import annotations

"""
json_utils.py
=============
Tiny helpers for JSON parsing that tolerate a leading UTF-8 BOM
(``0xEF 0xBB 0xBF``).

Why this exists
---------------
Several upstream sources we consume happily emit a UTF-8 BOM:
  - The Sketchfab API occasionally returns a BOM'd response body.
  - Some editors on Windows save JSON config files with a BOM.
  - A few PolyHaven CDN-cached JSON metadata blobs start with BOM.

Python's ``json`` module is strict — ``json.loads(text_with_bom)``
raises ``json.JSONDecodeError: Unexpected UTF-8 BOM (decode using
utf-8-sig)``. ``response.json()`` in ``requests`` uses the strict
decoder too.

These helpers centralise BOM tolerance so every asset-pipeline caller
gets the same forgiving behaviour.
"""

import json
from pathlib import Path
from typing import Any


def safe_json_loads(text: str | bytes | bytearray | None) -> Any:
    """
    Parse a JSON string/bytes payload, silently stripping a leading
    UTF-8 BOM. Returns ``None`` for empty/None input.
    """
    if text is None:
        return None
    if isinstance(text, (bytes, bytearray)):
        # utf-8-sig strips BOM if present, otherwise behaves as utf-8.
        decoded = bytes(text).decode("utf-8-sig", errors="replace")
    else:
        decoded = text
        if decoded.startswith("\ufeff"):
            decoded = decoded[1:]
    if not decoded:
        return None
    return json.loads(decoded)


def safe_json_load(path: str | Path) -> Any:
    """
    Load JSON from a file on disk, tolerating a UTF-8 BOM at the head.
    """
    p = Path(path)
    with open(p, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def safe_response_json(response: Any) -> Any:
    """
    Parse a ``requests.Response`` body as JSON, tolerating a leading
    UTF-8 BOM that the stock ``response.json()`` decoder chokes on.
    """
    raw = getattr(response, "content", None)
    if raw is None:
        # Fallback: some mock/shim objects only have .text
        text = getattr(response, "text", "") or ""
        return safe_json_loads(text)
    if not raw:
        return None
    return safe_json_loads(raw)
