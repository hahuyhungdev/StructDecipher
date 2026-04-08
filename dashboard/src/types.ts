// Types shared across the dashboard

export interface LayerDef {
  id: string;
  index: number;
  label: string;
  color: string;
}

export interface StructureNode {
  id: string;
  label: string;
  filePath: string | null;
  layer: string;
  layerIndex: number;
  layerLabel: string;
  apiCalls: string[];
  routes: string[];
  importCount: number;
}

export interface StructureEdge {
  id: string;
  source: string;
  target: string;
}

export interface GroupDef {
  parentId: string;
  childIds: string[];
}

export interface StructureData {
  repoPath: string;
  srcRoot: string;
  layers: LayerDef[];
  nodes: StructureNode[];
  edges: StructureEdge[];
  groups: GroupDef[];
  metadata: {
    totalFiles: number;
    analyzedFiles: number;
    treeShakedFiles: number;
    totalEdges: number;
    apiEndpoints: number;
    framework?: string;
  };
}

export interface InteractionEvent {
  eventType: string;
  componentName: string;
  filePath?: string;
  route?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface WsMessage {
  type: "connected" | "interaction" | "structure_update" | "clear";
  data?: unknown;
  activeNodes?: string[];
}
