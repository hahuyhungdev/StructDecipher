"""
Framework and alias detection for React/Next.js/TanStack/Remix/Gatsby projects.
"""

import json
import re
from pathlib import Path


def detect_framework(root: Path) -> str:
    """Detect the framework from package.json dependencies."""
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return "react"

    try:
        pkg = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return "react"

    all_deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        all_deps.update(pkg.get(key, {}))

    if "next" in all_deps:
        return "nextjs"
    if "@tanstack/react-router" in all_deps or "@tanstack/router" in all_deps:
        return "tanstack-router"
    if "@remix-run/react" in all_deps or "remix" in all_deps:
        return "remix"
    if "gatsby" in all_deps:
        return "gatsby"
    return "react"


def detect_alias_paths(root: Path) -> dict[str, Path]:
    """Read tsconfig.json / jsconfig.json to resolve path aliases."""
    aliases: dict[str, Path] = {}
    for config_name in ("tsconfig.json", "jsconfig.json"):
        config_path = root / config_name
        if not config_path.exists():
            continue
        try:
            # Strip comments (// and /* */) for JSON parsing
            raw = config_path.read_text(encoding="utf-8", errors="ignore")
            raw = re.sub(r"//[^\n]*", "", raw)
            raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
            cfg = json.loads(raw)
            paths = cfg.get("compilerOptions", {}).get("paths", {})
            base_url = cfg.get("compilerOptions", {}).get("baseUrl", ".")
            base = (root / base_url).resolve()

            for alias_pattern, targets in paths.items():
                if not targets:
                    continue
                # "@/*" -> ["src/*"]
                target = targets[0]
                alias_prefix = alias_pattern.replace("/*", "").replace("*", "")
                target_prefix = target.replace("/*", "").replace("*", "")
                resolved_target = (base / target_prefix).resolve()
                if alias_prefix:
                    aliases[alias_prefix] = resolved_target
        except Exception:
            pass
    return aliases
