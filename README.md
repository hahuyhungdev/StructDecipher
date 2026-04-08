# Repo Visualizer

A high-performance static analysis and visualization system for React/TypeScript repositories. Combines a Python scanner with a React Flow dashboard to produce interactive dependency graphs with real-time runtime tracking.

![Dependency Graph](image.png)
![Active Tracking](image-1.png)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  server/                                                            │
│  ┌──────────────┐    scan_repository()    ┌──────────────────────┐  │
│  │  Scanner      │ ────────────────────►  │  FastAPI Backend     │  │
│  │  (8 modules)  │   structure.json       │  :8000               │  │
│  └──────────────┘                         │  REST + WebSocket    │  │
│                                           └──────┬──────┬───────┘  │
└──────────────────────────────────────────────────┼──────┼──────────┘
                                        WebSocket  │      │  WebSocket
                                                   │      │
                            ┌──────────────────────┘      └───────────────────┐
                            │                                                 │
                    ┌───────▼──────────┐                           ┌──────────▼──────┐
                    │  Dashboard        │                           │  Demo Apps       │
                    │  React Flow       │                           │  :3001  :3002    │
                    │  :5173            │                           │  :3003           │
                    └──────────────────┘                           └─────────────────┘
```

## Components

| Component        | Tech                        | Port | Purpose                                               |
| ---------------- | --------------------------- | ---- | ----------------------------------------------------- |
| **Scanner**      | Python 3.12 + regex         | —    | Static analysis: imports, layers, APIs, cycles        |
| **Backend**      | FastAPI + WebSocket         | 8000 | REST API + real-time event broadcasting               |
| **Dashboard**    | React Flow + Dagre + Vite   | 5173 | Interactive graph visualization with analytics panel  |
| **demo-app**     | Classic React + Router      | 3001 | 12 files, 15 nodes, 22 edges, 4 API endpoints         |
| **demo-openapi** | openapi-fetch + React Query | 3002 | 17 files, 21 nodes, 36 edges, 6 API endpoints         |
| **demo-fsd**     | Feature-Sliced Design       | 3003 | 42 files, 30 nodes, 56 edges, FSD violation detection |

## Quick Start

```bash
chmod +x start.sh
./start.sh
```

Open the Dashboard at `http://localhost:5173`, enter a repo path, and click **Sync**.

### Manual Start

```bash
# 1. Backend
pip3 install -r server/requirements.txt
python3 -m uvicorn server.app:app --reload --port 8000

# 2. Dashboard
cd dashboard && npm install && npm run dev

# 3. Demo App (any of the three)
cd demo-app && npm install && npm run dev
```

---

## Features

### Scanner

- **Multi-framework detection** — Auto-detects Next.js (App/Pages Router), TanStack Router, Remix, Gatsby, and classic React
- **Feature-Sliced Design (FSD)** — Full FSD architecture support with 7-layer classification, slice/segment detection, and import violation checking
- **openapi-ts support** — Recognizes `openapi-fetch` (`client.GET("/path")`) and `openapi-react-query` (`$api.useQuery("get", "/path")`) patterns
- **Path alias resolution** — Reads `tsconfig.json`/`jsconfig.json` `paths` + common aliases (`@/`, `~/`, `#/`)
- **Barrel file resolution** — Traces `export * from` chains through index files to find actual source modules
- **API endpoint extraction** — Detects `fetch`, `axios`, `ky`, `$fetch`, `useFetch`, openapi-fetch, openapi-react-query calls and normalizes endpoints
- **Monorepo support** — Detects npm/yarn/pnpm workspaces and scans each package independently
- **Tree-shaking analysis** — BFS from page entry points; files not transitively reachable are flagged as dead code
- **Circular dependency detection** — DFS 3-color cycle finder + Tarjan's SCC for dependency groups
- **Incremental scanning** — mtime+size fingerprint cache skips unchanged files on rescan

### Dashboard

- **Hierarchical Dagre layout** — Nodes organized in strict layers with clean edge routing
- **Collapse/Expand** — Double-click a Page node to collapse/expand its subtree
- **Real-time tracking** — `useTracking` hook reports mount/unmount/click/navigate/api_call events via WebSocket
- **Active node highlighting** — Nodes glow when their component is mounted in the demo app
- **Search & filter** — Fuzzy search across all nodes with keyboard shortcut (`/`)
- **Export to PNG** — One-click export of the current graph view
- **Analytics panel** — Circular deps, dead files, dependency impact analysis, heatmap
- **Keyboard shortcuts** — `Ctrl+S` sync, `/` search, `Escape` clear selection
- **Event log** — Live stream of runtime events in the sidebar

### Backend API

| Endpoint                | Method  | Purpose                                   |
| ----------------------- | ------- | ----------------------------------------- |
| `/api/structure`        | GET     | Current analyzed structure                |
| `/api/scan`             | POST    | Trigger a (re-)scan of a repository       |
| `/api/interaction`      | POST    | Receive an interaction event              |
| `/api/interactions`     | GET/DEL | List or clear interaction history         |
| `/api/analytics`        | GET     | Heatmap, circular deps, dead files        |
| `/api/analytics/impact` | GET     | Transitive impact analysis for a node     |
| `/api/health`           | GET     | Health check                              |
| `/ws/dashboard`         | WS      | Real-time structure & interaction updates |
| `/ws/tracker`           | WS      | Tracker connection for demo apps          |

---

## Layering Model

### Standard React Projects

| Layer                 | Source Patterns                                                   | Index |
| --------------------- | ----------------------------------------------------------------- | ----- |
| **Pages / Layouts**   | `pages/`, `views/`, `screens/`, `routes/`, App Router             | 0     |
| **Features**          | `features/`, `modules/`, `containers/`, `domains/`                | 1     |
| **Shared / UI**       | `components/`, `ui/`, `shared/`, `hooks/`, `lib/`, `utils/`       | 2     |
| **API Services**      | `services/`, `api/`, `queries/`, `mutations/`, hooks w/ API calls | 3     |
| **Backend Endpoints** | Extracted from fetch/axios/ky/openapi-fetch calls                 | 4     |

### Feature-Sliced Design Projects

| FSD Layer     | Index | Description                         |
| ------------- | ----- | ----------------------------------- |
| **App**       | 0     | App-wide setup, providers, routes   |
| **Processes** | 1     | Cross-page business processes       |
| **Pages**     | 2     | Full page compositions              |
| **Widgets**   | 3     | Compositional blocks with logic     |
| **Features**  | 4     | User interactions, actions          |
| **Entities**  | 5     | Business entities (user, post, etc) |
| **Shared**    | 6     | Reusable UI, utilities, configs     |

FSD import rule: A layer can only import from layers **strictly below** (higher index). Cross-slice imports at the same layer are also violations (except `app/` and `shared/`).

---

## Scanner Architecture

The scanner is split into 8 focused modules under `server/scanner/`:

```
server/scanner/
├── patterns.py      # Regex constants (IMPORT_RE, API_CALL_RE, OPENAPI_FETCH_RE, etc.)
├── frameworks.py    # Framework detection (Next.js, TanStack, Remix, Gatsby)
├── fsd.py           # FSD detection, classification, violations
├── resolver.py      # Import resolution with caching + pre-indexed file set
├── parser.py        # Single-file parsing (imports, API calls, routes, barrels)
├── layers.py        # Layer classification, display names, route extraction
├── analytics.py     # Cycle detection (DFS), Tarjan's SCC, tree-shaking BFS
└── core.py          # Orchestration: scan_repository(), monorepo, parallel I/O
```

---

## Algorithm Optimizations

### 1. Import Resolution — O(1) File Existence Checks

**Problem:** Each import tries up to 21 candidate paths (exact, +5 extensions, /index+5 ext, /FolderName+5 ext). With `N` files averaging 10 imports each, that's `210N` filesystem `is_file()` syscalls.

**Solution:** Pre-index all discovered project files into a `set[Path]` before resolution begins. Existence checks become `O(1)` hash lookups instead of syscalls.

```python
# Before: 21 × is_file() per import = expensive I/O
# After: 21 × set.__contains__() = O(1) memory lookup
_known_files: set[Path] = set()

def set_known_files(files: set[Path]):
    global _known_files
    _known_files = files
```

### 2. Circular Dependency Detection — O(V+E) DFS with O(1) Back-Edge Lookup

**Problem:** Standard DFS cycle detection uses `path.index(node)` to find where a cycle starts, which is `O(V)` per back-edge.

**Solution:** Maintain a `path_pos: dict[Path, int]` alongside the DFS path stack. Back-edge cycle extraction becomes `O(1)`.

```python
path: list[Path] = []
path_pos: dict[Path, int] = {}  # O(1) lookup replaces path.index()

def dfs(fp):
    path_pos[fp] = len(path)
    path.append(fp)
    for dep in graph[fp]:
        if color[dep] == GRAY:
            idx = path_pos[dep]  # O(1) instead of path.index(dep) O(n)
            cycle = path[idx:]
    path.pop()
    del path_pos[fp]
```

### 3. Tarjan's Strongly Connected Components — O(V+E)

**Problem:** Circular dependency groups (mutually dependent file sets) are useful for understanding which files are tightly coupled. Naive approaches require repeated DFS.

**Solution:** Single-pass Tarjan's SCC algorithm finds all non-trivial SCCs (size ≥ 2) in `O(V+E)`. Each SCC represents a group of files that mutually depend on each other.

```python
def find_strongly_connected_components(graph) -> list[list[Path]]:
    # Tarjan's algorithm with index/lowlink tracking
    # Returns only SCCs with >= 2 nodes (actual circular groups)
```

### 4. Tree-Shaking BFS — O(V+E) with Deque

**Problem:** Finding all transitively used files from page entry points. Original implementation used `list.pop(0)` which is `O(n)` per dequeue.

**Solution:** Replace with `collections.deque.popleft()` for `O(1)` dequeue operations.

```python
from collections import deque
queue: deque[Path] = deque(entry_files)  # O(1) popleft
while queue:
    current = queue.popleft()  # O(1) instead of list.pop(0) O(n)
```

### 5. API Endpoint Edge Creation — Inverted Index O(E+N)

**Problem:** Matching API endpoint nodes to the files that call them was `O(endpoints × files)` — quadratic.

**Solution:** Build an inverted index `endpoint_string → node_id` in one pass, then look up each file's API calls in `O(1)`.

```python
# Build inverted index: endpoint_url → node_id
endpoint_index: dict[str, str] = {}
for node in api_nodes:
    endpoint_index[node["label"]] = node["id"]

# O(1) lookup per API call instead of O(N) linear scan
for file_node in file_nodes:
    for api_call in file_data["api_calls"]:
        target_id = endpoint_index.get(api_call)  # O(1)
```

### 6. Barrel Resolution — Memoized with Cycle Guard

**Problem:** `export * from './sub'` chains can be deeply nested and even circular. Without memoization, resolution is exponential in the worst case.

**Solution:** Cache resolved barrels in `_barrel_cache` and use a `_barrel_resolving` set to detect and break cycles.

```python
_barrel_cache: dict[Path, list[Path]] = {}
_barrel_resolving: set[Path] = set()  # cycle guard

def resolve_through_barrels(fp):
    if fp in _barrel_cache:
        return _barrel_cache[fp]
    if fp in _barrel_resolving:
        return [fp]  # break cycle
    _barrel_resolving.add(fp)
    # ... resolve ...
    _barrel_cache[fp] = result
    return result
```

### 7. Incremental Scanning — mtime+size Fingerprint Cache

**Problem:** Re-scanning an unchanged project re-parses every file with regex, which is wasteful.

**Solution:** Cache parsing results keyed by `(mtime, file_size)`. If the fingerprint matches, return the cached parse result.

```python
_parse_cache: dict[Path, tuple[float, int, dict]] = {}

def _parse_file_incremental(fp: Path) -> dict:
    st = fp.stat()
    mtime, size = st.st_mtime, st.st_size
    cached = _parse_cache.get(fp)
    if cached and cached[0] == mtime and cached[1] == size:
        return cached[2]  # cache hit — skip regex parsing
    result = scan_file(fp)
    _parse_cache[fp] = (mtime, size, result)
    return result
```

### 8. Parallel File Parsing — ThreadPoolExecutor

**Problem:** Sequential file parsing becomes a bottleneck for large projects (>50 files).

**Solution:** Use `concurrent.futures.ThreadPoolExecutor` to parallelize file I/O when the file count exceeds a threshold.

```python
PARALLEL_THRESHOLD = 50

if len(files) > PARALLEL_THRESHOLD:
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(_parse_file_incremental, files))
else:
    results = [_parse_file_incremental(f) for f in files]
```

### 9. Bounded Interaction Log — O(1) Deque

**Problem:** The interaction event log used `list.pop(0)` for eviction — `O(n)` per operation.

**Solution:** Replace with `collections.deque(maxlen=N)` which auto-evicts the oldest entry in `O(1)`.

```python
interaction_log: deque = deque(maxlen=500)  # auto-evicts oldest, O(1) append
```

### Performance Summary

| Project      | Files | First Scan | Incremental | Speedup |
| ------------ | ----- | ---------- | ----------- | ------- |
| demo-app     | 12    | ~4.5ms     | ~2.7ms      | 1.7×    |
| demo-openapi | 16    | ~6.5ms     | ~4.1ms      | 1.6×    |
| demo-fsd     | 42    | ~11.3ms    | ~9.2ms      | 1.2×    |

---

## Tracking Hook

Add real-time tracking to any React component:

```tsx
import { useTracking } from "./hooks/useTracking";

function MyComponent() {
  const { trackClick, trackApiCall } = useTracking("MyComponent", {
    filePath: "src/features/MyComponent.tsx",
  });

  return <button onClick={() => trackClick("save")}>Save</button>;
}
```

## Structure JSON Schema

```json
{
  "repoPath": "/absolute/path/to/repo",
  "framework": "react",
  "isFsd": false,
  "layers": [
    { "id": "page", "index": 0, "label": "Pages", "color": "#4F46E5" }
  ],
  "nodes": [
    {
      "id": "file_hash",
      "label": "HomePage",
      "layer": "page",
      "layerIndex": 0,
      "filePath": "src/pages/HomePage.tsx",
      "lineCount": 42,
      "route": "/home"
    }
  ],
  "edges": [{ "id": "edge_hash", "source": "src_id", "target": "tgt_id" }],
  "groups": [
    { "parentId": "page_id", "childIds": ["feature_id", "shared_id"] }
  ],
  "analytics": {
    "circularDeps": [["fileA", "fileB"]],
    "circularGroups": [["fileA", "fileB", "fileC"]],
    "deadFiles": ["unused_component"],
    "dependents": { "nodeId": ["parent1", "parent2"] }
  },
  "metadata": {
    "totalFiles": 42,
    "analyzedFiles": 30,
    "treeShakedFiles": 12,
    "totalEdges": 56,
    "scanTimeMs": 11.3
  }
}
```
