"""
Graph analytics: SCC detection (Tarjan), cycle detection (O(V+E)), tree-shaking BFS.
"""

from collections import deque
from pathlib import Path


def detect_circular_deps(
    resolved_imports: dict[Path, list[Path]],
    node_id_map: dict[Path, str],
) -> list[list[str]]:
    """
    Detect circular dependency cycles via DFS (3-color).
    Uses O(1) position dict for back-edge cycle extraction.
    Time: O(V + E). Space: O(V).
    """
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[Path, int] = {fp: WHITE for fp in resolved_imports}
    path: list[Path] = []
    path_pos: dict[Path, int] = {}  # O(1) cycle-start lookup (was path.index → O(n))

    def dfs(fp: Path) -> None:
        color[fp] = GRAY
        pos = len(path)
        path.append(fp)
        path_pos[fp] = pos
        for dep in resolved_imports.get(fp, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                idx = path_pos.get(dep)
                if idx is not None:
                    cycle_ids = [node_id_map[f] for f in path[idx:] if f in node_id_map]
                    if len(cycle_ids) >= 2:
                        key = frozenset(cycle_ids)
                        if key not in seen:
                            seen.add(key)
                            cycles.append(cycle_ids)
            elif color[dep] == WHITE:
                dfs(dep)
        path.pop()
        del path_pos[fp]
        color[fp] = BLACK

    for fp in resolved_imports:
        if color.get(fp, WHITE) == WHITE:
            dfs(fp)
    return cycles


def find_strongly_connected_components(
    graph: dict[Path, list[Path]],
) -> list[list[Path]]:
    """
    Tarjan's algorithm — finds all SCCs in O(V + E).
    Returns only non-trivial SCCs (size >= 2, i.e. circular dependency groups).
    Each SCC represents a set of files that mutually depend on each other.
    """
    index_counter = [0]
    stack: list[Path] = []
    on_stack: set[Path] = set()
    node_index: dict[Path, int] = {}
    lowlink: dict[Path, int] = {}
    sccs: list[list[Path]] = []

    def strongconnect(v: Path) -> None:
        node_index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, []):
            if w not in node_index:
                if w in graph:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], node_index[w])

        if lowlink[v] == node_index[v]:
            scc: list[Path] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) >= 2:
                sccs.append(scc)

    for v in graph:
        if v not in node_index:
            strongconnect(v)

    return sccs


def find_used_files(entry_files: set[Path], all_imports: dict[Path, list[Path]]) -> set[Path]:
    """BFS from entry files to find all transitively used files. O(V+E) with deque."""
    visited: set[Path] = set()
    queue: deque[Path] = deque(entry_files)  # O(1) popleft vs list.pop(0) O(n)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for dep in all_imports.get(current, []):
            if dep not in visited:
                queue.append(dep)
    return visited
