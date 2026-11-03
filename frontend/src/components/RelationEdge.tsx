import { BaseEdge, type Edge, EdgeLabelRenderer, type EdgeProps, type InternalNode, useInternalNode, useStore } from "@xyflow/react";
import { memo } from "react";

export type RelationEdgeData = {
  label: string;
  color: string;
  lossMode: string;
  dimmed: boolean;
  lit: boolean;
  /** Set on a busy canvas: drawn faintly and without a label until it's lit. */
  quiet: boolean;
  /** Which of several lines between the same two nodes this is, centred on 0. Absent when it's the only one. */
  lane?: number;
};

export type RelationFlowEdge = Edge<RelationEdgeData, "relation">;

const DASHES: Record<string, string | undefined> = {
  required: undefined,
  alternative: "7 5",
  backup: "7 5",
  network: "7 5",
  none: "2 5",
};
const LABELS_FROM_ZOOM = 0.7;
const MAX_BEND = 34;
const LANE_GAP = 70;

function centre(node: InternalNode) {
  return {
    x: node.internals.positionAbsolute.x + (node.measured.width ?? 0) / 2,
    y: node.internals.positionAbsolute.y + (node.measured.height ?? 0) / 2,
  };
}

/** Where the line from this node's centre towards a point crosses the node's border. */
function borderPoint(node: InternalNode, towards: { x: number; y: number }) {
  const from = centre(node);
  const dx = towards.x - from.x;
  const dy = towards.y - from.y;
  const scale = Math.min(
    dx ? ((node.measured.width ?? 0) / 2) / Math.abs(dx) : Infinity,
    dy ? ((node.measured.height ?? 0) / 2) / Math.abs(dy) : Infinity,
    1,
  );
  return { x: from.x + dx * scale, y: from.y + dy * scale };
}

/** Lines leave whichever side faces the other node, so rings read as well as left-to-right. */
function RelationEdgeView({ source, target, markerEnd, selected, data }: EdgeProps<RelationFlowEdge>) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  const zoom = useStore((state) => state.transform[2]);
  if (!sourceNode?.measured.width || !targetNode?.measured.width) return null;

  const start = borderPoint(sourceNode, centre(targetNode));
  const end = borderPoint(targetNode, centre(sourceNode));
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;
  // A slight bend keeps a pair linked both ways as two separate lines; several links fan out.
  const bend = data?.lane === undefined
    ? Math.min(MAX_BEND, length * 0.08)
    : data.lane * Math.min(LANE_GAP, length * 0.25);
  const control = { x: (start.x + end.x) / 2 - (dy / length) * bend, y: (start.y + end.y) / 2 + (dx / length) * bend };
  const path = `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`;
  // Past the middle, where lines leaving a hub have spread apart and labels have room.
  const t = 0.62;
  const labelX = (1 - t) ** 2 * start.x + 2 * (1 - t) * t * control.x + t ** 2 * end.x;
  const labelY = (1 - t) ** 2 * start.y + 2 * (1 - t) * t * control.y + t ** 2 * end.y;

  const color = data?.color ?? "#7c8a9e";
  const quiet = data?.quiet && !data.lit && !selected;
  const opacity = data?.dimmed ? 0.08 : quiet ? 0.4 : 1;
  const showLabel = !data?.dimmed && (selected || data?.lit || (!quiet && zoom >= LABELS_FROM_ZOOM));

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        interactionWidth={24}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.6 : data?.lit ? 2 : quiet ? 1.2 : 1.5,
          strokeDasharray: DASHES[data?.lossMode ?? "required"],
          opacity,
        }}
      />
      {showLabel && (
        <EdgeLabelRenderer>
          <div
            className={`edge-label${selected ? " selected" : ""}`}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, color }}
          >
            {data?.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export default memo(RelationEdgeView);
