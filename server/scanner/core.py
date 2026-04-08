"""
Core scanner logic: scan_repository, monorepo detection, _scan_single_repo.

Performance characteristics:
  - Incremental parsing: mtime+size fingerprint skips unchanged files
  - Parallel I/O: ThreadPoolExecutor for file parsing (>50 files)
  - O(1) import resolution via pre-indexed file set (no syscalls)
  - Memoized barrel resolution with cycle protection
  - Inverted index for API endpoint → file edges
  - Tarjan's SCC for circular dependency groups
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .patterns import EXTENSIONS, IGNORE_DIRS
from .frameworks import detect_framework, detect_alias_paths
from .fsd import detect_fsd, detect_fsd_violations
from .resolver import clear_cache, resolve_import_path, set_known_files
from .parser import scan_file
from .layers import classify_layer, compute_display_name, extract_file_route, LAYER_ORDER, LAYER_LABELS
from .analytics import detect_circular_deps, find_strongly_connected_components, find_used_files


# ───────────────────────── Incremental Parse Cache ─────────────────────────
# Persists across scans of the same repo. Key = resolved Path,
# Value = (mtime, size, parsed_data). If mtime+size match, skip regex parsing.

_parse_cache: dict[Path, tuple[float, int, dict]] = {}
_parse_cache_repo: Optional[Path] = None
PARALLEL_THRESHOLD = 50  # use ThreadPoolExecutor above this file count


def _parse_file_incremental(fp: Path) -> dict:
    """Parse a file, returning cached result if mtime+size are unchanged."""
    try:
        st = fp.stat()
        mtime, size = st.st_mtime, st.st_size
    except OSError:
        return scan_file(fp)

    cached = _parse_cache.get(fp)
    if cached and cached[0] == mtime and cached[1] == size:
        return cached[2]

    data = scan_file(fp)
    _parse_cache[fp] = (mtime, size, data)
    return data


def _parse_files(all_files: list[Path]) -> dict[Path, dict]:
    """Parse files with incremental caching and parallel I/O for large projects."""
    if len(all_files) >= PARALLEL_THRESHOLD:
        results: dict[Path, dict] = {}
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as pool:
            future_map = {pool.submit(_parse_file_incremental, fp): fp for fp in all_files}
            for future in future_map:
                fp = future_map[future]
                results[fp] = future.result()
        return results
    return {fp: _parse_file_incremental(fp) for fp in all_files}


# ───────────────────────── Monorepo Detection ─────────────────────────

def detect_workspaces(root: Path) -> list[Path]:
    """Detect monorepo workspace packages from package.json."""
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return []
    try:
        pkg = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []

    workspace_globs = pkg.get("workspaces", [])
    if isinstance(workspace_globs, dict):
        workspace_globs = workspace_globs.get("packages", [])
    if not isinstance(workspace_globs, list):
        return []

    # Also check for pnpm-workspace.yaml
    pnpm_ws = root / "pnpm-workspace.yaml"
    if pnpm_ws.exists():
        try:
            content = pnpm_ws.read_text(encoding="utf-8", errors="ignore")
            in_packages = False
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped == "packages:":
                    in_packages = True
                    continue
                if in_packages and stripped.startswith("- "):
                    glob_pattern = stripped[2:].strip().strip("'\"")
                    if glob_pattern not in workspace_globs:
                        workspace_globs.append(glob_pattern)
                elif in_packages and stripped and not stripped.startswith("#"):
                    in_packages = False
        except Exception:
            pass

    import glob as glob_mod
    packages: list[Path] = []
    for pattern in workspace_globs:
        if not isinstance(pattern, str):
            continue
        matches = glob_mod.glob(str(root / pattern))
        for m in matches:
            mp = Path(m).resolve()
            if mp.is_dir() and (mp / "package.json").exists():
                packages.append(mp)
    return packages


# ───────────────────────── Public API ─────────────────────────

def scan_repository(repo_path: str) -> dict:
    """Scan a React/Next.js/TanStack/Remix repository and produce a hierarchical structure."""
    global _parse_cache_repo
    root = Path(repo_path).resolve()

    if not root.is_dir():
        raise ValueError(f"'{repo_path}' is not a valid directory")

    # Invalidate incremental cache if scanning a different repo
    if _parse_cache_repo != root:
        _parse_cache.clear()
        _parse_cache_repo = root

    # Clear import resolution cache for fresh scan
    clear_cache()

    # Detect monorepo workspaces
    workspace_packages = detect_workspaces(root)
    if workspace_packages:
        return _scan_monorepo(root, workspace_packages)

    return _scan_single_repo(root)


# ───────────────────────── Monorepo Scanner ─────────────────────────

def _scan_monorepo(root: Path, packages: list[Path]) -> dict:
    """Scan a monorepo by scanning each workspace package and merging results."""
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_groups: list[dict] = []
    all_circular_deps: list[list[str]] = []
    all_dead_files: list[dict] = []
    all_dependents: dict[str, list[str]] = {}
    total_files = 0
    analyzed_files = 0
    tree_shaked = 0
    barrel_count = 0
    api_endpoints = 0
    frameworks: set[str] = set()

    for pkg_dir in packages:
        try:
            result = _scan_single_repo(pkg_dir)
        except Exception:
            continue
        pkg_name = pkg_dir.name
        id_map: dict[str, str] = {}
        for node in result["nodes"]:
            old_id = node["id"]
            new_id = f"{pkg_name}__{old_id}"
            id_map[old_id] = new_id
            node["id"] = new_id
            node["label"] = f"{pkg_name}/{node['label']}"
            if node["filePath"]:
                try:
                    abs_path = (pkg_dir / node["filePath"]).resolve()
                    node["filePath"] = str(abs_path.relative_to(root))
                except ValueError:
                    node["filePath"] = f"{pkg_name}/{node['filePath']}"
            all_nodes.append(node)

        for edge in result["edges"]:
            edge["source"] = id_map.get(edge["source"], edge["source"])
            edge["target"] = id_map.get(edge["target"], edge["target"])
            edge["id"] = f"{pkg_name}__{edge['id']}"
            all_edges.append(edge)

        for group in result["groups"]:
            group["parentId"] = id_map.get(group["parentId"], group["parentId"])
            group["childIds"] = [id_map.get(c, c) for c in group["childIds"]]
            all_groups.append(group)

        pkg_analytics = result.get("analytics", {})
        for cycle in pkg_analytics.get("circularDeps", []):
            all_circular_deps.append([id_map.get(c, c) for c in cycle])
        for df in pkg_analytics.get("deadFiles", []):
            df_copy = dict(df)
            df_copy["filePath"] = f"{pkg_name}/{df_copy['filePath']}"
            all_dead_files.append(df_copy)
        for tgt, srcs in pkg_analytics.get("dependents", {}).items():
            mapped_tgt = id_map.get(tgt, tgt)
            mapped_srcs = [id_map.get(s, s) for s in srcs]
            all_dependents.setdefault(mapped_tgt, []).extend(mapped_srcs)

        meta = result["metadata"]
        total_files += meta["totalFiles"]
        analyzed_files += meta["analyzedFiles"]
        tree_shaked += meta["treeShakedFiles"]
        barrel_count += meta["barrelFiles"]
        api_endpoints += meta["apiEndpoints"]
        frameworks.add(meta["framework"])

    layers = [
        {"id": "page", "index": 0, "label": "Pages", "color": "#818cf8"},
        {"id": "layout", "index": 0, "label": "Layouts", "color": "#a78bfa"},
        {"id": "feature", "index": 1, "label": "Features", "color": "#22d3ee"},
        {"id": "shared", "index": 2, "label": "Shared / UI", "color": "#34d399"},
        {"id": "api_service", "index": 3, "label": "API Services", "color": "#fbbf24"},
        {"id": "api_route", "index": 3, "label": "API Routes", "color": "#fb923c"},
        {"id": "api_endpoint", "index": 4, "label": "Backend Endpoints", "color": "#f87171"},
        {"id": "middleware", "index": 2, "label": "Middleware", "color": "#c084fc"},
    ]

    return {
        "repoPath": str(root),
        "srcRoot": str(root),
        "framework": ", ".join(sorted(frameworks)),
        "layers": layers,
        "nodes": all_nodes,
        "edges": all_edges,
        "groups": all_groups,
        "metadata": {
            "totalFiles": total_files,
            "analyzedFiles": analyzed_files,
            "treeShakedFiles": tree_shaked,
            "barrelFiles": barrel_count,
            "totalEdges": len(all_edges),
            "apiEndpoints": api_endpoints,
            "framework": ", ".join(sorted(frameworks)),
            "workspaces": len(packages),
        },
        "analytics": {
            "circularDeps": all_circular_deps,
            "deadFiles": all_dead_files,
            "dependents": all_dependents,
        },
    }


# ───────────────────────── Single Repo Scanner ─────────────────────────

def _scan_single_repo(root: Path) -> dict:
    """Scan a single React/Next.js/TanStack/Remix/FSD repository."""
    t0 = time.perf_counter()
    framework = detect_framework(root)
    aliases = detect_alias_paths(root)
    is_fsd = detect_fsd(root)

    src_root = root / "src" if (root / "src").is_dir() else root
    scan_roots = [src_root]
    if framework == "nextjs":
        for d in ("app", "pages"):
            candidate = root / d
            if candidate.is_dir() and candidate != src_root / d:
                scan_roots.append(candidate)

    # 1. Discover all source files
    all_files: list[Path] = []
    seen_paths: set[Path] = set()
    for scan_dir in scan_roots:
        for dirpath, dirnames, filenames in os.walk(scan_dir):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for fn in filenames:
                fp = (Path(dirpath) / fn).resolve()
                if fp.suffix in EXTENSIONS and fp not in seen_paths:
                    all_files.append(fp)
                    seen_paths.add(fp)

    # 2. Parse files (incremental cache + parallel I/O for large projects)
    file_data = _parse_files(all_files)

    # Register known files for O(1) resolution lookups (eliminates filesystem syscalls)
    set_known_files(set(file_data.keys()))

    # 3. Resolve imports to actual file paths
    resolved_imports: dict[Path, list[Path]] = {}
    for fp, data in file_data.items():
        deps = []
        for imp in data["imports"]:
            resolved = resolve_import_path(fp, imp, src_root, aliases)
            if resolved and resolved in file_data:
                deps.append(resolved)
        resolved_imports[fp] = deps

    # 4. Classify each file into a layer
    file_layers: dict[Path, str] = {}
    for fp in all_files:
        rel = str(fp.relative_to(root))
        file_layers[fp] = classify_layer(rel, framework, file_data[fp], is_fsd=is_fsd)

    # 5. Tree-shaking: find entry points
    entry_files: set[Path] = set()
    if is_fsd:
        for fp, layer in file_layers.items():
            if layer in ("fsd_app", "fsd_pages"):
                entry_files.add(fp)
    else:
        for fp, layer in file_layers.items():
            if layer in ("page", "layout", "api_route"):
                entry_files.add(fp)

    if not entry_files:
        for fp, data in file_data.items():
            if data["routes"]:
                file_layers[fp] = "page"
                entry_files.add(fp)

    for fp in all_files:
        name = fp.stem.lower()
        if name in ("app", "main", "index", "_app", "_document", "root"):
            entry_files.add(fp)

    if entry_files:
        used = find_used_files(entry_files, resolved_imports)
    else:
        used = set(all_files)

    # 6. Skip barrel files from display (but keep connections)
    barrel_files = {fp for fp in used if file_data[fp].get("is_barrel")}

    # 7. Collect API endpoints
    all_api_endpoints: set[str] = set()
    for fp in used:
        for call in file_data[fp].get("api_calls", []):
            all_api_endpoints.add(call)

    for fp in used:
        if file_layers.get(fp) == "api_route":
            route = extract_file_route(fp, root, framework)
            if route:
                all_api_endpoints.add(route)

    # 8. Build output structure
    nodes = []
    edges = []
    node_id_map: dict[Path, str] = {}
    import_count: dict[Path, int] = {}

    for fp in used:
        for dep in resolved_imports.get(fp, []):
            if dep in used:
                import_count[dep] = import_count.get(dep, 0) + 1

    display_files = sorted(used - barrel_files)

    for fp in display_files:
        rel = str(fp.relative_to(root))
        nid = re.sub(r"[^a-zA-Z0-9]", "_", rel)
        node_id_map[fp] = nid
        layer = file_layers[fp]
        display_name = compute_display_name(fp, root, framework, is_fsd=is_fsd)

        file_route = extract_file_route(fp, root, framework)
        routes = file_data[fp].get("routes", [])
        if file_route and file_route not in routes:
            routes = [file_route] + routes

        nodes.append({
            "id": nid,
            "label": display_name,
            "filePath": rel,
            "layer": layer,
            "layerIndex": LAYER_ORDER.get(layer, 2),
            "layerLabel": LAYER_LABELS.get(layer, "Shared / UI"),
            "apiCalls": file_data[fp].get("api_calls", []),
            "routes": routes,
            "importCount": import_count.get(fp, 0),
            "lineCount": file_data[fp].get("line_count", 0),
        })

    # Edges — skip barrel files, connect through them (memoized + cycle-safe)
    _barrel_cache: dict[Path, list[Path]] = {}

    def resolve_through_barrels(target: Path) -> list[Path]:
        """If target is a barrel file, resolve to what the barrel re-exports."""
        if target in _barrel_cache:
            return _barrel_cache[target]
        result = _resolve_barrel(target, set())
        _barrel_cache[target] = result
        return result

    def _resolve_barrel(target: Path, visiting: set[Path]) -> list[Path]:
        if target not in barrel_files:
            return [target] if target in node_id_map else []
        if target in visiting:
            return []  # cycle protection
        visiting.add(target)
        results = []
        for dep in resolved_imports.get(target, []):
            results.extend(_resolve_barrel(dep, visiting))
        return results

    edge_set: set[tuple[str, str]] = set()
    for fp in display_files:
        src_id = node_id_map.get(fp)
        if not src_id:
            continue
        for dep in resolved_imports.get(fp, []):
            targets = resolve_through_barrels(dep)
            for actual_target in targets:
                tgt_id = node_id_map.get(actual_target)
                if tgt_id and src_id != tgt_id and (src_id, tgt_id) not in edge_set:
                    edge_set.add((src_id, tgt_id))
                    edges.append({
                        "id": f"e_{src_id}__{tgt_id}",
                        "source": src_id,
                        "target": tgt_id,
                    })

    # API endpoint nodes — inverted index for O(E+N) instead of O(E×N)
    endpoint_to_files: dict[str, list[Path]] = {}
    for fp in display_files:
        for call in file_data[fp].get("api_calls", []):
            endpoint_to_files.setdefault(call, []).append(fp)

    api_layer_index = 7 if is_fsd else 4
    for i, endpoint in enumerate(sorted(all_api_endpoints)):
        api_id = f"api_ep_{i}"
        nodes.append({
            "id": api_id,
            "label": endpoint,
            "filePath": None,
            "layer": "api_endpoint",
            "layerIndex": api_layer_index,
            "layerLabel": "Backend API Endpoints",
            "apiCalls": [],
            "routes": [],
            "importCount": 0,
            "lineCount": 0,
        })
        for fp in endpoint_to_files.get(endpoint, []):
            src_id = node_id_map[fp]
            if (src_id, api_id) not in edge_set:
                edge_set.add((src_id, api_id))
                edges.append({
                    "id": f"e_{src_id}__{api_id}",
                    "source": src_id,
                    "target": api_id,
                })

    # Groups (pages contain their direct features)
    groups = []
    for fp in display_files:
        if file_layers[fp] in ("page", "layout"):
            page_id = node_id_map[fp]
            children = []
            for dep in resolved_imports.get(fp, []):
                for actual in resolve_through_barrels(dep):
                    if actual in node_id_map and file_layers.get(actual) == "feature":
                        children.append(node_id_map[actual])
            groups.append({"parentId": page_id, "childIds": children})

    if is_fsd:
        layers = [
            {"id": "fsd_app", "index": 0, "label": "App", "color": "#818cf8"},
            {"id": "fsd_processes", "index": 1, "label": "Processes", "color": "#a78bfa"},
            {"id": "fsd_pages", "index": 2, "label": "Pages", "color": "#c084fc"},
            {"id": "fsd_widgets", "index": 3, "label": "Widgets", "color": "#22d3ee"},
            {"id": "fsd_features", "index": 4, "label": "Features", "color": "#2dd4bf"},
            {"id": "fsd_entities", "index": 5, "label": "Entities", "color": "#fbbf24"},
            {"id": "fsd_shared", "index": 6, "label": "Shared", "color": "#34d399"},
            {"id": "api_endpoint", "index": 7, "label": "Backend Endpoints", "color": "#f87171"},
        ]
        groups = []
        for fp in display_files:
            if file_layers[fp] == "fsd_pages":
                page_id = node_id_map[fp]
                children = []
                for dep in resolved_imports.get(fp, []):
                    for actual in resolve_through_barrels(dep):
                        dep_layer = file_layers.get(actual)
                        if actual in node_id_map and dep_layer in ("fsd_widgets", "fsd_features"):
                            children.append(node_id_map[actual])
                groups.append({"parentId": page_id, "childIds": children})
    else:
        layers = [
            {"id": "page", "index": 0, "label": "Pages", "color": "#818cf8"},
            {"id": "layout", "index": 0, "label": "Layouts", "color": "#a78bfa"},
            {"id": "feature", "index": 1, "label": "Features", "color": "#22d3ee"},
            {"id": "shared", "index": 2, "label": "Shared / UI", "color": "#34d399"},
            {"id": "api_service", "index": 3, "label": "API Services", "color": "#fbbf24"},
            {"id": "api_route", "index": 3, "label": "API Routes", "color": "#fb923c"},
            {"id": "api_endpoint", "index": 4, "label": "Backend Endpoints", "color": "#f87171"},
            {"id": "middleware", "index": 2, "label": "Middleware", "color": "#c084fc"},
        ]

    # ── Analytics ──
    circular_deps = detect_circular_deps(resolved_imports, node_id_map)

    # Tarjan's SCC — identifies circular dependency groups
    sccs = find_strongly_connected_components(resolved_imports)
    circular_groups = [
        [node_id_map[fp] for fp in scc if fp in node_id_map]
        for scc in sccs
    ]
    circular_groups = [g for g in circular_groups if len(g) >= 2]

    dead_files = []
    for fp in sorted(set(all_files) - used):
        rel_dead = str(fp.relative_to(root))
        dead_files.append({
            "filePath": rel_dead,
            "label": compute_display_name(fp, root, framework, is_fsd=is_fsd),
            "layer": classify_layer(rel_dead, framework, file_data.get(fp, {}), is_fsd=is_fsd),
        })

    dependents: dict[str, list[str]] = {}
    for src_id, tgt_id in edge_set:
        dependents.setdefault(tgt_id, []).append(src_id)

    fsd_violations: list[dict] = []
    if is_fsd:
        fsd_violations = detect_fsd_violations(
            display_files, file_layers, resolved_imports, node_id_map, resolve_through_barrels
        )

    analytics: dict = {
        "circularDeps": circular_deps,
        "circularGroups": circular_groups,
        "deadFiles": dead_files,
        "dependents": dependents,
    }
    if is_fsd:
        analytics["fsdViolations"] = fsd_violations

    scan_time_ms = round((time.perf_counter() - t0) * 1000)

    return {
        "repoPath": str(root),
        "srcRoot": str(src_root),
        "framework": framework,
        "isFsd": is_fsd,
        "layers": layers,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "metadata": {
            "totalFiles": len(all_files),
            "analyzedFiles": len(used),
            "treeShakedFiles": len(all_files) - len(used),
            "barrelFiles": len(barrel_files),
            "totalEdges": len(edges),
            "apiEndpoints": len(all_api_endpoints),
            "framework": framework,
            "isFsd": is_fsd,
            "scanTimeMs": scan_time_ms,
        },
        "analytics": analytics,
    }
