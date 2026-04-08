import { memo, useState, useRef, useCallback } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

interface VizNodeData {
  label: string;
  filePath: string | null;
  layer: string;
  layerLabel: string;
  color: string;
  routes: string[];
  apiCalls: string[];
  importCount: number;
  lineCount?: number;
  isGroup: boolean;
  active?: boolean;
  highlighted?: boolean;
  dimmed?: boolean;
  searchMatch?: boolean;
  heatmapIntensity?: number;
  heatmapCount?: number;
  inCycle?: boolean;
  impacted?: boolean;
  apiMatch?: boolean;
}

export const VizNode = memo(function VizNode({
  data,
  selected,
}: NodeProps & { data: VizNodeData }) {
  const d = data as VizNodeData;
  const isHl = d.highlighted || d.active;
  const isDim = d.dimmed && !d.active;
  const [showTooltip, setShowTooltip] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>();

  const onEnter = useCallback(() => {
    hoverTimer.current = setTimeout(() => setShowTooltip(true), 400);
  }, []);
  const onLeave = useCallback(() => {
    clearTimeout(hoverTimer.current);
    setShowTooltip(false);
  }, []);

  return (
    <div
      className={[
        "viz-node",
        isHl && "viz-node--highlighted",
        isDim && "viz-node--dimmed",
        d.active && "viz-node--active",
        selected && "viz-node--selected",
        d.searchMatch && "viz-node--search-match",
        d.inCycle && "viz-node--cycle",
        d.impacted && "viz-node--impacted",
        d.apiMatch && "viz-node--api-match",
      ]
        .filter(Boolean)
        .join(" ")}
      style={
        d.heatmapIntensity && d.heatmapIntensity > 0
          ? {
              borderColor: `rgb(${Math.round(51 + 204 * d.heatmapIntensity)},${Math.round(65 + 130 * Math.max(0, 1 - d.heatmapIntensity * 2))},${Math.round(85 * (1 - d.heatmapIntensity))})`,
              boxShadow: `0 0 ${8 + 16 * d.heatmapIntensity}px rgba(${Math.round(51 + 204 * d.heatmapIntensity)},${Math.round(65 + 130 * Math.max(0, 1 - d.heatmapIntensity * 2))},${Math.round(85 * (1 - d.heatmapIntensity))},0.4)`,
            }
          : undefined
      }
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      {/* Colored left accent bar */}
      <div className="viz-node__accent" style={{ background: d.color }} />

      <Handle
        type="target"
        position={Position.Top}
        style={{
          background: d.color,
          width: 8,
          height: 8,
          border: "2px solid #0f172a",
        }}
      />

      <div className="viz-node__body">
        <div className="viz-node__header">
          <span className="viz-node__label">{d.label}</span>
          <span
            className="viz-node__badge"
            style={{
              background: `${d.color}1A`,
              color: d.color,
              borderColor: `${d.color}33`,
            }}
          >
            {d.layerLabel}
          </span>
        </div>
        {d.filePath && <div className="viz-node__path">{d.filePath}</div>}
        {(d.lineCount ?? 0) > 0 && (
          <div className="viz-node__lines">{d.lineCount} lines</div>
        )}
        {d.routes.length > 0 && (
          <div className="viz-node__routes">
            {d.routes.map((r, i) => (
              <span key={i} className="viz-node__route">
                {r}
              </span>
            ))}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          background: d.color,
          width: 8,
          height: 8,
          border: "2px solid #0f172a",
        }}
      />

      {/* ─── Tooltip ─── */}
      {showTooltip && (
        <div className="viz-tooltip">
          <div className="viz-tooltip__title">{d.label}</div>
          {d.filePath && (
            <div className="viz-tooltip__row">
              <span className="viz-tooltip__key">Path</span>
              {d.filePath}
            </div>
          )}
          <div className="viz-tooltip__row">
            <span className="viz-tooltip__key">Layer</span>
            {d.layerLabel}
          </div>
          <div className="viz-tooltip__row">
            <span className="viz-tooltip__key">Imports</span>
            {d.importCount} file{d.importCount !== 1 ? "s" : ""} import this
          </div>
          {(d.lineCount ?? 0) > 0 && (
            <div className="viz-tooltip__row">
              <span className="viz-tooltip__key">Size</span>
              {d.lineCount} lines
            </div>
          )}
          {(d.heatmapCount ?? 0) > 0 && (
            <div className="viz-tooltip__row">
              <span className="viz-tooltip__key">Visits</span>
              {d.heatmapCount} interactions
            </div>
          )}
          {d.routes.length > 0 && (
            <div className="viz-tooltip__row">
              <span className="viz-tooltip__key">Routes</span>
              {d.routes.join(", ")}
            </div>
          )}
          {d.apiCalls.length > 0 && (
            <div className="viz-tooltip__row">
              <span className="viz-tooltip__key">API</span>
              {d.apiCalls.join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
