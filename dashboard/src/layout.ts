import Dagre from "@dagrejs/dagre";
import type { Node, Edge } from "@xyflow/react";
import type { StructureData } from "./types";

export const LAYER_COLORS: Record<string, string> = {
  page: "#818cf8",
  feature: "#22d3ee",
  shared: "#34d399",
  api_service: "#fbbf24",
  api_endpoint: "#f87171",
};

export interface VizNodeData {
  label: string;
  filePath: string | null;
  layer: string;
  layerLabel: string;
  color: string;
  routes: string[];
  apiCalls: string[];
  importCount: number;
  lineCount: number;
  isGroup: boolean;
  highlighted: boolean;
  dimmed: boolean;
  active: boolean;
  heatmapIntensity?: number;
  heatmapCount?: number;
  inCycle?: boolean;
  impacted?: boolean;
  apiMatch?: boolean;
  [key: string]: unknown;
}

export interface LayerBand {
  label: string;
  color: string;
  y: number;
  height: number;
}

/**
 * Directed traversal: find all ancestors (who imports me)
 * and all descendants (what I import) of rootId.
 */
export function getConnectedSubgraph(
  rootId: string,
  edges: { source: string; target: string }[],
): Set<string> {
  // source → target means "source imports target"
  const downstream = new Map<string, Set<string>>(); // parent → children
  const upstream = new Map<string, Set<string>>(); // child → parents
  for (const e of edges) {
    if (!downstream.has(e.source)) downstream.set(e.source, new Set());
    downstream.get(e.source)!.add(e.target);
    if (!upstream.has(e.target)) upstream.set(e.target, new Set());
    upstream.get(e.target)!.add(e.source);
  }

  const visited = new Set<string>();
  // BFS downstream (what this node depends on)
  const queue = [rootId];
  while (queue.length) {
    const n = queue.shift()!;
    if (visited.has(n)) continue;
    visited.add(n);
    for (const child of downstream.get(n) || []) {
      if (!visited.has(child)) queue.push(child);
    }
  }
  // BFS upstream (who depends on this node)
  const queue2 = [rootId];
  while (queue2.length) {
    const n = queue2.shift()!;
    if (visited.has(n) && n !== rootId) continue;
    visited.add(n);
    for (const parent of upstream.get(n) || []) {
      if (!visited.has(parent)) queue2.push(parent);
    }
  }
  return visited;
}

export function buildFlowElements(
  structure: StructureData,
  collapsedGroups: Set<string>,
  selectedNodeId: string | null,
): { nodes: Node<VizNodeData>[]; edges: Edge[]; layerBands: LayerBand[] } {
  // Hidden nodes from collapsed groups
  const hiddenNodes = new Set<string>();
  for (const group of structure.groups) {
    if (collapsedGroups.has(group.parentId)) {
      for (const childId of group.childIds) {
        hiddenNodes.add(childId);
      }
    }
  }

  const visibleNodes = structure.nodes.filter((n) => !hiddenNodes.has(n.id));
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = structure.edges.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
  );

  // Connected subgraph for click-highlight
  const connectedIds = selectedNodeId
    ? getConnectedSubgraph(selectedNodeId, visibleEdges)
    : null;

  // Flat Dagre graph with generous spacing
  const g = new Dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "TB",
    ranksep: 120,
    nodesep: 60,
    edgesep: 30,
    marginx: 60,
    marginy: 60,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of visibleNodes) {
    g.setNode(node.id, { width: 200, height: 76 });
  }
  for (const edge of visibleEdges) {
    g.setEdge(edge.source, edge.target);
  }

  Dagre.layout(g);

  const layerBands: LayerBand[] = [];

  // ── Nodes ──
  const flowNodes: Node<VizNodeData>[] = visibleNodes.map((sn) => {
    const pos = g.node(sn.id);
    const color = LAYER_COLORS[sn.layer] || "#64748b";
    const isGroupParent = structure.groups.some(
      (gr) => gr.parentId === sn.id && gr.childIds.length > 0,
    );
    const isCollapsed = collapsedGroups.has(sn.id);
    const highlighted = connectedIds ? connectedIds.has(sn.id) : false;
    const dimmed = connectedIds ? !connectedIds.has(sn.id) : false;

    return {
      id: sn.id,
      type: "vizNode",
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        label: sn.label + (isGroupParent ? (isCollapsed ? " ▸" : " ▾") : ""),
        filePath: sn.filePath,
        layer: sn.layer,
        layerLabel: sn.layerLabel,
        color,
        routes: sn.routes,
        apiCalls: sn.apiCalls,
        importCount: sn.importCount,
        lineCount: sn.lineCount ?? 0,
        isGroup: isGroupParent,
        highlighted,
        dimmed,
        active: false,
      },
    };
  });

  // ── Edges ──
  const flowEdges: Edge[] = visibleEdges.map((e) => {
    const isHL =
      connectedIds !== null &&
      connectedIds.has(e.source) &&
      connectedIds.has(e.target);
    const isDim = connectedIds !== null && !isHL;
    const srcLayer =
      structure.nodes.find((n) => n.id === e.source)?.layer || "shared";

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: isHL,
      style: {
        stroke: isHL
          ? LAYER_COLORS[srcLayer] || "#818cf8"
          : isDim
            ? "#1e293b"
            : "#334155",
        strokeWidth: isHL ? 2.5 : 1.2,
        opacity: isDim ? 0.2 : 1,
      },
    };
  });

  return { nodes: flowNodes, edges: flowEdges, layerBands };
}

export function getHeatmapColor(intensity: number): string {
  if (intensity <= 0) return "#334155";
  const r = Math.round(51 + 204 * intensity);
  const g = Math.round(65 + 130 * Math.max(0, 1 - intensity * 2));
  const b = Math.round(85 * (1 - intensity));
  return `rgb(${r},${g},${b})`;
}
