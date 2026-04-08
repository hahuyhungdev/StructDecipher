import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toPng, toSvg } from "html-to-image";

import { VizNode } from "./components/CustomNodes";
import { useWebSocket } from "./hooks/useWebSocket";
import { buildFlowElements, LAYER_COLORS, type LayerBand, type VizNodeData } from "./layout";
import type { StructureData } from "./types";

const API_BASE = "/api";

const nodeTypes = { vizNode: VizNode };

function Dashboard() {
  const [repoPath, setRepoPath] = useState("");
  const [structure, setStructure] = useState<StructureData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [layerBands, setLayerBands] = useState<LayerBand[]>([]);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchResults, setSearchResults] = useState<string[]>([]);
  const [searchIdx, setSearchIdx] = useState(0);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Legend collapse
  const [legendCollapsed, setLegendCollapsed] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { setCenter, fitView } = useReactFlow();

  const { connected, activeNodes, events, structureUpdate } = useWebSocket();
  const eventLogRef = useRef<HTMLDivElement>(null);

  // ─── Load initial structure ───
  useEffect(() => {
    fetch(`${API_BASE}/structure`)
      .then((r) => {
        if (r.ok) return r.json();
        throw new Error("No data");
      })
      .then((d: StructureData) => {
        setStructure(d);
        setRepoPath(d.repoPath);
      })
      .catch(() => {});
  }, []);

  // ─── Live structure update from WebSocket ───
  useEffect(() => {
    if (structureUpdate) setStructure(structureUpdate as StructureData);
  }, [structureUpdate]);

  // ─── Recalculate layout ───
  useEffect(() => {
    if (!structure) return;
    const result = buildFlowElements(structure, collapsedGroups, selectedNodeId);
    // Apply search match highlighting
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchIds = new Set<string>();
      for (const n of result.nodes) {
        const d = n.data as VizNodeData;
        if (
          d.label.toLowerCase().includes(q) ||
          (d.filePath && d.filePath.toLowerCase().includes(q)) ||
          d.routes.some((r) => r.toLowerCase().includes(q))
        ) {
          matchIds.add(n.id);
        }
      }
      setSearchResults(Array.from(matchIds));
      result.nodes = result.nodes.map((n) => {
        if (matchIds.has(n.id)) {
          return { ...n, data: { ...n.data, searchMatch: true } };
        }
        return n;
      });
    } else {
      setSearchResults([]);
    }
    setNodes(result.nodes);
    setEdges(result.edges);
    setLayerBands(result.layerBands);
  }, [structure, collapsedGroups, selectedNodeId, searchQuery, setNodes, setEdges]);

  // ─── Runtime active-node glow ───
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const d = n.data as VizNodeData;
        const isActive = activeNodes.some(
          (an) =>
            n.id.toLowerCase().includes(an.toLowerCase()) ||
            an.toLowerCase().includes(d.label.replace(/ [▸▾]$/, "").toLowerCase())
        );
        if (d.active === isActive) return n;
        return { ...n, data: { ...d, active: isActive } };
      })
    );
  }, [activeNodes, setNodes]);

  // ─── Auto-scroll event log ───
  useEffect(() => {
    if (eventLogRef.current) {
      eventLogRef.current.scrollTop = 0; // newest events are at top (reversed list)
    }
  }, [events]);

  // ─── Zoom to search result ───
  const zoomToNode = useCallback(
    (nodeId: string) => {
      const node = nodes.find((n) => n.id === nodeId);
      if (node && node.position) {
        setCenter(node.position.x + 100, node.position.y + 38, {
          zoom: 1.5,
          duration: 500,
        });
        setSelectedNodeId(nodeId);
      }
    },
    [nodes, setCenter]
  );

  // ─── Search navigation ───
  const nextSearchResult = useCallback(() => {
    if (searchResults.length === 0) return;
    const nextIdx = (searchIdx + 1) % searchResults.length;
    setSearchIdx(nextIdx);
    zoomToNode(searchResults[nextIdx]);
  }, [searchResults, searchIdx, zoomToNode]);

  const prevSearchResult = useCallback(() => {
    if (searchResults.length === 0) return;
    const prevIdx = (searchIdx - 1 + searchResults.length) % searchResults.length;
    setSearchIdx(prevIdx);
    zoomToNode(searchResults[prevIdx]);
  }, [searchResults, searchIdx, zoomToNode]);

  // ─── Keyboard shortcuts ───
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // "/" → open search (only if no input focused)
      if (e.key === "/" && !searchOpen && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
        return;
      }
      // Escape → close search or clear selection
      if (e.key === "Escape") {
        if (searchOpen) {
          setSearchOpen(false);
          setSearchQuery("");
          setSearchResults([]);
          setSearchIdx(0);
        } else {
          setSelectedNodeId(null);
        }
        return;
      }
      // "f" → fit view (only if not typing)
      if (e.key === "f" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        fitView({ duration: 400, padding: 0.1 });
        return;
      }
      // Enter / Shift+Enter → navigate search results
      if (e.key === "Enter" && searchOpen) {
        e.preventDefault();
        if (e.shiftKey) prevSearchResult();
        else nextSearchResult();
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [searchOpen, fitView, nextSearchResult, prevSearchResult]);

  // ─── Export diagram ───
  const exportDiagram = useCallback(
    async (format: "png" | "svg") => {
      const el = document.querySelector<HTMLElement>(".react-flow__viewport");
      if (!el) return;
      try {
        const fn = format === "png" ? toPng : toSvg;
        const dataUrl = await fn(el, {
          backgroundColor: "#0a0e1a",
          quality: 1,
          pixelRatio: 2,
        });
        const link = document.createElement("a");
        link.download = `repo-visualization.${format}`;
        link.href = dataUrl;
        link.click();
      } catch (err) {
        console.error("Export failed:", err);
      }
    },
    []
  );

  // ─── Scan handler ───
  const handleScan = useCallback(async () => {
    if (!repoPath.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repoPath: repoPath.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Scan failed");
      const struct = await fetch(`${API_BASE}/structure`).then((r) => r.json());
      setStructure(struct);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [repoPath]);

  // ─── Node click → highlight subgraph; click background → clear ───
  const onNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id));
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  // ─── Double-click → collapse/expand ───
  const onNodeDoubleClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      if (!structure) return;
      const isGroupParent = structure.groups.some(
        (g) => g.parentId === node.id && g.childIds.length > 0
      );
      if (isGroupParent) {
        setCollapsedGroups((prev) => {
          const next = new Set(prev);
          if (next.has(node.id)) next.delete(node.id);
          else next.add(node.id);
          return next;
        });
      }
    },
    [structure]
  );

  // ─── Legend items ───
  const legendItems = useMemo(
    () => [
      { color: LAYER_COLORS.page, label: "Pages" },
      { color: LAYER_COLORS.feature, label: "Features" },
      { color: LAYER_COLORS.shared, label: "Shared / UI" },
      { color: LAYER_COLORS.api_service, label: "API Services" },
      { color: LAYER_COLORS.api_endpoint, label: "Endpoints" },
    ],
    []
  );

  return (
    <div className="app-layout">
      {/* ─── Toolbar ─── */}
      <div className="toolbar">
        <h1>⬡ Repo Visualizer</h1>
        <input
          type="text"
          placeholder="Absolute path to React repository..."
          value={repoPath}
          onChange={(e) => setRepoPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleScan()}
        />
        <button onClick={handleScan} disabled={loading || !repoPath.trim()}>
          {loading ? "Scanning…" : "⟳ Sync"}
        </button>

        {/* Export buttons */}
        <div className="toolbar-group">
          <button className="toolbar-btn-secondary" onClick={() => exportDiagram("png")} title="Export as PNG">
            ⤓ PNG
          </button>
          <button className="toolbar-btn-secondary" onClick={() => exportDiagram("svg")} title="Export as SVG">
            ⤓ SVG
          </button>
        </div>

        <span className="status">
          <span className={`ws-dot ${connected ? "connected" : "disconnected"}`} />
          {connected ? "Live" : "Offline"}
        </span>
        {error && <span style={{ color: "var(--danger)", fontSize: 12 }}>{error}</span>}

        {/* Keyboard hint */}
        <span className="toolbar-shortcuts">
          <kbd>/</kbd> Search <kbd>F</kbd> Fit <kbd>Esc</kbd> Clear
        </span>
      </div>

      {/* ─── Metadata bar ─── */}
      {structure && (
        <div className="metadata-bar">
          <span>Files: <strong>{structure.metadata.analyzedFiles}</strong> / {structure.metadata.totalFiles}</span>
          <span>Tree-shaked: <strong>{structure.metadata.treeShakedFiles}</strong></span>
          <span>Edges: <strong>{structure.metadata.totalEdges}</strong></span>
          <span>Endpoints: <strong>{structure.metadata.apiEndpoints}</strong></span>
          <span>Active: <strong>{activeNodes.length}</strong></span>
          {structure.metadata.framework && (
            <span>Framework: <strong>{structure.metadata.framework}</strong></span>
          )}
        </div>
      )}

      {/* ─── Search overlay ─── */}
      {searchOpen && (
        <div className="search-bar">
          <div className="search-bar__inner">
            <span className="search-bar__icon">⌕</span>
            <input
              ref={searchInputRef}
              type="text"
              className="search-bar__input"
              placeholder="Search components, files, routes..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSearchIdx(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setSearchOpen(false);
                  setSearchQuery("");
                  setSearchResults([]);
                }
              }}
              autoFocus
            />
            {searchResults.length > 0 && (
              <span className="search-bar__count">
                {searchIdx + 1} / {searchResults.length}
              </span>
            )}
            {searchResults.length > 0 && (
              <div className="search-bar__nav">
                <button onClick={prevSearchResult} title="Previous (Shift+Enter)">↑</button>
                <button onClick={nextSearchResult} title="Next (Enter)">↓</button>
              </div>
            )}
            <button className="search-bar__close" onClick={() => { setSearchOpen(false); setSearchQuery(""); setSearchResults([]); }}>
              ✕
            </button>
          </div>
          {/* Search results dropdown */}
          {searchQuery.trim() && searchResults.length > 0 && (
            <div className="search-results">
              {searchResults.map((id, i) => {
                const node = nodes.find((n) => n.id === id);
                if (!node) return null;
                const d = node.data as VizNodeData;
                return (
                  <button
                    key={id}
                    className={`search-result-item ${i === searchIdx ? "search-result-item--active" : ""}`}
                    onClick={() => { setSearchIdx(i); zoomToNode(id); }}
                  >
                    <span className="search-result-dot" style={{ background: d.color }} />
                    <span className="search-result-label">{d.label}</span>
                    <span className="search-result-layer">{d.layerLabel}</span>
                  </button>
                );
              })}
            </div>
          )}
          {searchQuery.trim() && searchResults.length === 0 && (
            <div className="search-results">
              <div className="search-result-empty">No matching components</div>
            </div>
          )}
        </div>
      )}

      {/* ─── Diagram ─── */}
      <div className="diagram-container" style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onNodeDoubleClick={onNodeDoubleClick}
          onPaneClick={onPaneClick}
          fitView
          minZoom={0.1}
          maxZoom={3}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={24} size={1} />
          <Controls position="bottom-right" />
          <MiniMap
            nodeColor={(n) => (n.data as VizNodeData).color || "#475569"}
            maskColor="rgba(15,23,42,0.85)"
            style={{ background: "#0f172a", borderRadius: 8 }}
          />
        </ReactFlow>

        {/* ─── Legend ─── */}
        <div className={`legend ${legendCollapsed ? "legend--collapsed" : ""}`}>
          <button
            className="legend-toggle"
            onClick={() => setLegendCollapsed((p) => !p)}
            title={legendCollapsed ? "Expand legend" : "Collapse legend"}
          >
            {legendCollapsed ? "◆" : "◇"}
          </button>
          {!legendCollapsed && (
            <>
              {legendItems.map((item) => (
                <div className="legend-item" key={item.label}>
                  <div className="legend-dot" style={{ background: item.color }} />
                  {item.label}
                </div>
              ))}
              <div className="legend-hint">Click highlight · Dbl-click collapse</div>
            </>
          )}
        </div>

        {/* ─── Event Log ─── */}
        {events.length > 0 && (
          <div className="event-log">
            <div className="event-log-header">
              <span>Runtime Events</span>
              <span style={{ color: "var(--text-muted)" }}>{events.length}</span>
            </div>
            <div className="event-log-body" ref={eventLogRef}>
              {[...events].reverse().map((ev, i) => (
                <div className={`event-entry ${i === 0 ? "event-entry--new" : ""}`} key={i}>
                  <span
                    className="event-type"
                    style={{
                      color:
                        ev.eventType === "mount"
                          ? "var(--success)"
                          : ev.eventType === "click"
                          ? "var(--warning)"
                          : ev.eventType === "unmount"
                          ? "var(--danger)"
                          : "var(--accent)",
                    }}
                  >
                    {ev.eventType}
                  </span>
                  <span className="event-component">{ev.componentName}</span>
                  <span className="event-time">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Dashboard />
    </ReactFlowProvider>
  );
}
