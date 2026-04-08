"""
Import resolution with caching for the static analyzer.
"""

from pathlib import Path
from typing import Optional

from .patterns import EXTENSIONS

# Per-scan import resolution cache to avoid O(n²) repeated disk lookups
_resolve_cache: dict[tuple[str, str], Optional[Path]] = {}

# Pre-indexed set of known project files — eliminates is_file() syscalls
# With N files and ~10 imports each, this saves up to 21×N×10 = 210N syscalls
_known_files: set[Path] = set()


def clear_cache() -> None:
    """Clear all resolution caches (call before each fresh scan)."""
    _resolve_cache.clear()
    _known_files.clear()


def set_known_files(files: set[Path]) -> None:
    """
    Register discovered project files for O(1) existence checks.
    Must be called after file discovery, before import resolution.
    """
    global _known_files
    _known_files = files


def resolve_import_path(
    source_file: Path,
    import_path: str,
    src_root: Path,
    aliases: dict[str, Path],
) -> Optional[Path]:
    """Resolve a relative or alias import to an actual file path (cached)."""
    cache_key = (str(source_file.parent), import_path)
    if cache_key in _resolve_cache:
        return _resolve_cache[cache_key]

    result = _resolve_import_path_uncached(source_file, import_path, src_root, aliases)
    _resolve_cache[cache_key] = result
    return result


def _resolve_import_path_uncached(
    source_file: Path,
    import_path: str,
    src_root: Path,
    aliases: dict[str, Path],
) -> Optional[Path]:
    """Resolve a relative or alias import to an actual file path."""
    resolved: Optional[Path] = None

    if import_path.startswith("."):
        resolved = (source_file.parent / import_path).resolve()
    else:
        # Try aliases first (from tsconfig paths)
        for prefix, target_dir in aliases.items():
            if import_path == prefix or import_path.startswith(prefix + "/"):
                remainder = import_path[len(prefix):].lstrip("/")
                resolved = (target_dir / remainder).resolve()
                break

        if resolved is None:
            # Common hard-coded aliases
            for alias_prefix, rel_target in [
                ("@/", "src/"), ("~/", "src/"), ("#/", "src/"),
                ("@components/", "src/components/"),
                ("@features/", "src/features/"),
                ("@hooks/", "src/hooks/"),
                ("@services/", "src/services/"),
                ("@utils/", "src/utils/"),
                ("@lib/", "src/lib/"),
                ("@app/", "src/app/"),
                ("src/", "src/"),
            ]:
                if import_path.startswith(alias_prefix):
                    remainder = import_path[len(alias_prefix):]
                    resolved = (src_root.parent / rel_target / remainder).resolve()
                    break

        if resolved is None:
            return None

    # Try resolving: exact → +ext → /index.ext → /Name.ext (folder component)
    candidates = [resolved]
    for ext in EXTENSIONS:
        candidates.append(resolved.with_suffix(ext))
    for ext in EXTENSIONS:
        candidates.append(resolved / f"index{ext}")
    # Folder-based component: PostFeed/PostFeed.tsx
    if resolved.name:
        folder_name = resolved.name
        for ext in EXTENSIONS:
            candidates.append(resolved / f"{folder_name}{ext}")

    # O(1) set lookup against pre-indexed project files (no syscalls)
    if _known_files:
        for c in candidates:
            if c in _known_files:
                return c
        return None

    # Fallback: filesystem check (only if known_files not populated)
    for c in candidates:
        if c.is_file():
            return c
    return None
