"""
File parsing: extract imports, API calls, routes from source files.
"""

import re
from pathlib import Path

from .patterns import IMPORT_RE, API_CALL_RE, OPENAPI_FETCH_RE, OPENAPI_RQ_RE, ROUTE_RE, normalize_api_endpoint


def scan_file(filepath: Path) -> dict:
    """Parse a single file for imports, API calls, and route definitions."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"imports": [], "api_calls": [], "routes": [], "export_default": False, "is_barrel": False}

    # Imports
    imports = []
    for m in IMPORT_RE.finditer(content):
        imp = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if imp:
            imports.append(imp)

    # API calls — normalize template literals
    api_calls_raw = [m.group(1) for m in API_CALL_RE.finditer(content)]
    api_calls_raw += [m.group(1) for m in OPENAPI_FETCH_RE.finditer(content)]
    api_calls_raw += [m.group(1) for m in OPENAPI_RQ_RE.finditer(content)]
    api_calls = list(dict.fromkeys(
        ep for ep in (normalize_api_endpoint(c) for c in api_calls_raw) if ep
    ))

    # Route definitions
    routes = []
    for m in ROUTE_RE.finditer(content):
        r = m.group(1) or m.group(2) or m.group(3)
        if r:
            routes.append(r)

    has_default = bool(re.search(r"export\s+default", content))

    # Detect barrel files (index.ts that only re-exports)
    is_barrel = False
    if filepath.stem == "index":
        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("//")]
        if lines and all(l.startswith("export ") for l in lines):
            is_barrel = True

    line_count = len(content.split("\n"))

    return {
        "imports": imports,
        "api_calls": api_calls,
        "routes": routes,
        "export_default": has_default,
        "is_barrel": is_barrel,
        "line_count": line_count,
    }
