"""
Regex patterns and constants for the static analyzer.
"""

import re
from typing import Set

# ───────────────────────── Constants ─────────────────────────

EXTENSIONS: Set[str] = {".tsx", ".ts", ".jsx", ".js", ".mjs"}
INDEX_NAMES: Set[str] = {f"index{e}" for e in EXTENSIONS}
IGNORE_DIRS: Set[str] = {
    "node_modules", ".git", "dist", "build", ".next", ".output",
    "__pycache__", ".cache", ".turbo", ".vercel", "coverage", ".nuxt",
}

# ───────────────────────── Regex Patterns ─────────────────────────

# import ... from 'path' | require('path') | dynamic import('path') | export ... from 'path'
IMPORT_RE = re.compile(
    r"""(?:import\s+(?:(?:type\s+)?(?:[\w*\s{},]+)\s+from\s+)?['"]([^'"]+)['"])|"""
    r"""(?:require\s*\(\s*['"]([^'"]+)['"]\s*\))|"""
    r"""(?:import\s*\(\s*['"]([^'"]+)['"]\s*\))|"""
    r"""(?:export\s+(?:(?:type\s+)?(?:[\w*\s{},]+)\s+from\s+)?['"]([^'"]+)['"])""",
    re.MULTILINE,
)

# API calls: axios.get('/api/...'), fetch('/api/...'), useFetch, $fetch, ky, etc.
API_CALL_RE = re.compile(
    r"""(?:"""
    r"""(?:axios(?:\.(?:get|post|put|patch|delete|request|head|options))?)|"""
    r"""fetch|"""
    r"""\$fetch|"""
    r"""useFetch|"""
    r"""(?:api|http|request|client)(?:\.(?:get|post|put|patch|delete|request))?|"""
    r"""ky(?:\.(?:get|post|put|patch|delete))?"""
    r""")\s*[.(]\s*['"`]([^'"`\s]+)['"`]""",
    re.IGNORECASE,
)

# openapi-fetch: anyVar.GET("/path"), fetchClient.POST("/path"), etc.
OPENAPI_FETCH_RE = re.compile(
    r"""[\w$]+\.(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\(\s*['"`]([^'"`\s]+)['"`]"""
)

# openapi-react-query: $api.useQuery("get", "/path"), $api.useMutation("post", "/path"), etc.
OPENAPI_RQ_RE = re.compile(
    r"""[\w$]+\.(?:useQuery|useSuspenseQuery|useMutation|useInfiniteQuery|queryOptions|prefetchQuery)"""
    r"""\s*\(\s*['"`]\w+['"`]\s*,\s*['"`]([^'"`\s]+)['"`]"""
)

# Route definitions for classic React Router, TanStack, etc.
ROUTE_RE = re.compile(
    r"""(?:path\s*[:=]\s*['"]([^'"]+)['"])|"""
    r"""(?:<Route[^>]*path\s*=\s*[{'"](/?[^'"}\s]+)[}'"]\s*[^>]*>)|"""
    r"""(?:createRoute\s*\(\s*\{[^}]*path\s*:\s*['"]([^'"]+)['"])""",
    re.MULTILINE,
)

# Normalize template-literal API endpoints: ${BASE_URL}/users → /users
TEMPLATE_VAR_RE = re.compile(r"\$\{[^}]+\}")


def normalize_api_endpoint(raw: str) -> str:
    """Strip JS template variables and clean up API endpoint strings."""
    cleaned = TEMPLATE_VAR_RE.sub("", raw)
    # Remove leading empty segments from stripped vars
    cleaned = re.sub(r"^/+", "/", cleaned)
    # Remove trailing ? from query params left behind
    cleaned = cleaned.rstrip("?&")
    # If stripping template vars left nothing meaningful, skip entirely
    if not cleaned or cleaned == "/" or cleaned == raw.replace("${", "").replace("}", ""):
        fully_template = TEMPLATE_VAR_RE.sub("", raw).strip("/").strip()
        if not fully_template:
            return ""  # signal to skip
    return cleaned
