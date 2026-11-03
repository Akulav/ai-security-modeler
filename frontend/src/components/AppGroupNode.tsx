import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import { Boxes, Plus } from "lucide-react";
import { type FormEvent, memo, useEffect, useRef, useState } from "react";
import type { GraphNode } from "../types";

export type AppGroupNodeData = {
  node: GraphNode;
  color: string;
  dimmed: boolean;
  autoFocus: boolean;
  onAddApp: (groupId: string, name: string) => void;
};

export type AppGroupFlowNode = Node<AppGroupNodeData, "appGroup">;

/** A container on the canvas. Its apps render over it as real nodes that can be connected. */
function AppGroupNodeView({ data, selected }: NodeProps<AppGroupFlowNode>) {
  const { node, color, dimmed, autoFocus, onAddApp } = data;
  const [name, setName] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!autoFocus) return;
    // React Flow keeps a new node hidden until it has been measured, and hidden inputs can't
    // take focus, so keep trying for a moment.
    let attempts = 0;
    const timer = setInterval(() => {
      input.current?.focus({ preventScroll: true });
      if (document.activeElement === input.current || ++attempts >= 20) clearInterval(timer);
    }, 100);
    return () => clearInterval(timer);
  }, [autoFocus]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onAddApp(node.id, name.trim());
    setName("");
  };

  return (
    <div
      className={`app-group${selected ? " selected" : ""}${dimmed ? " hl-dim" : ""}`}
      style={{ "--node-color": color } as React.CSSProperties}
    >
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div className="app-group-head">
        <Boxes size={14} />
        <span title={node.name}>{node.name}</span>
      </div>
      {/* Pressing Enter submits by "clicking" the button, which mustn't count as clicking the node. */}
      <form className="app-add nodrag nopan" onSubmit={submit} onClick={(event) => event.stopPropagation()}>
        <input ref={input} value={name} onChange={(e) => setName(e.target.value)} placeholder="Add an app" maxLength={200} aria-label="Add an app" />
        <button className="icon-btn" disabled={!name.trim()} aria-label="Add app"><Plus size={14} /></button>
      </form>
    </div>
  );
}

export default memo(AppGroupNodeView);
