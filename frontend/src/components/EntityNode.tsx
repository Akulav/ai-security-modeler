import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import { Lock, LockOpen, Shield, ShieldAlert } from "lucide-react";
import { memo } from "react";
import { MAX_NODE_TAGS } from "../layout";
import type { GraphNode } from "../types";
import { FALLBACK_ICON, NODE_ICONS } from "../visuals";

export type EntityNodeData = {
  node: GraphNode;
  color: string;
  label: string;
  osLabel: string | null;
  hasOsField: boolean;
  hasEncryption: boolean;
  defenses: string[];
  highlight: "origin" | "loss" | "compromise" | "finding" | "dim" | "fade" | null;
};

export type EntityFlowNode = Node<EntityNodeData, "entity">;

function EntityNodeView({ data, selected }: NodeProps<EntityFlowNode>) {
  const { node, color, label, osLabel, hasOsField, hasEncryption, defenses, highlight } = data;
  const Icon = NODE_ICONS[node.type] ?? FALLBACK_ICON;
  const breached = Boolean(node.breaches?.length);
  const compact = Boolean(node.parent_id);
  const classes = [
    "entity", compact && "compact", breached && "breached", selected && "selected", highlight && `hl-${highlight}`,
  ].filter(Boolean).join(" ");
  const showStrip = !compact && (hasOsField || (hasEncryption && node.encryption !== "unknown"));

  return (
    <div className={classes} style={{ "--node-color": color } as React.CSSProperties}>
      <Handle type="target" position={Position.Left} />
      <div className="entity-main">
        <div className="entity-icon">
          <Icon size={compact ? 13 : 18} />
        </div>
        <div className="entity-text">
          <div className="entity-name" title={node.name}>{node.name}</div>
          {!compact && <div className="entity-type">{label}</div>}
        </div>
        <span className={`level-dot level-${node.security_level}`} title={`Security level: ${node.security_level}`} />
      </div>
      {showStrip && (
        <div className="entity-strip">
          {hasOsField && (
            <span className={osLabel ? "" : "unset"}>
              {osLabel ? `${osLabel}${node.os_version ? ` ${node.os_version}` : ""}` : "OS not set"}
            </span>
          )}
          {node.encryption === "encrypted" && <Lock size={11} className="enc-on" aria-label="Encrypted" />}
          {node.encryption === "none" && <LockOpen size={11} className="enc-off" aria-label="Not encrypted" />}
          {!hasOsField && <span>{node.encryption === "encrypted" ? "Encrypted" : "Not encrypted"}</span>}
        </div>
      )}
      {!compact && defenses.length > 0 && (
        <div className="entity-tags" title={defenses.join(", ")}>
          {defenses.slice(0, MAX_NODE_TAGS).map((defense) => <span key={defense}>{defense}</span>)}
          {defenses.length > MAX_NODE_TAGS && <span>+{defenses.length - MAX_NODE_TAGS}</span>}
        </div>
      )}
      {compact && defenses.length > 0 && (
        <span className="def-count" title={defenses.join(", ")}><Shield size={10} /> {defenses.length}</span>
      )}
      {breached && (
        <span className="breach-badge" title={`${node.breaches!.length} known breach(es)`}>
          <ShieldAlert size={13} /> {node.breaches!.length}
        </span>
      )}
      {node.status === "legacy" && <span className="legacy-badge">legacy</span>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default memo(EntityNodeView);
