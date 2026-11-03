import { ArrowLeftRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Catalog, GraphNode, Relation } from "../types";
import { categoryOf, RELATION_COLORS } from "../visuals";

const GROUP_LABELS: Record<string, string> = {
  auth: "Authentication & security",
  stack: "Hardware & software stack",
  network: "Network",
  data: "Data flow",
  other: "Other",
};

export function allowedRelations(catalog: Catalog, source: GraphNode, target: GraphNode): Relation[] {
  return catalog.relations.filter((r) => r.sources.includes(source.type) && r.targets.includes(target.type));
}

function specificCount(relations: Relation[]) {
  return relations.filter((relation) => relation.category !== "other").length;
}

interface Props {
  catalog: Catalog;
  source: GraphNode;
  target: GraphNode;
  onPick: (relation: string, source: GraphNode, target: GraphNode) => void;
  onCancel: () => void;
}

export default function RelationPicker({ catalog, source, target, onPick, onCancel }: Props) {
  // Starts the way round that has meaningful options, whichever way the line was dragged.
  const [swapped, setSwapped] = useState(
    () => specificCount(allowedRelations(catalog, source, target)) === 0
      && specificCount(allowedRelations(catalog, target, source)) > 0,
  );
  const from = swapped ? target : source;
  const to = swapped ? source : target;
  const allowed = allowedRelations(catalog, from, to);
  const suggestedIds = catalog.suggested_relations[categoryOf(catalog, from.type)] ?? [];
  const suggested = allowed.filter((relation) => suggestedIds.includes(relation.id));

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const option = (relation: Relation, keyPrefix: string) => (
    <button
      key={keyPrefix + relation.id}
      className="relation-option"
      style={{ "--rel-color": RELATION_COLORS[relation.category] } as React.CSSProperties}
      onClick={() => onPick(relation.id, from, to)}
    >
      {relation.label}
    </button>
  );

  return (
    <div className="modal-backdrop" onMouseDown={onCancel}>
      <div className="modal glass" role="dialog" aria-label="Choose relationship" onMouseDown={(e) => e.stopPropagation()}>
        <header>
          <h2>Define the relationship</h2>
          <button className="icon-btn" onClick={onCancel} aria-label="Cancel"><X size={16} /></button>
        </header>
        <div className="relation-sentence">
          <strong>{from.name}</strong>
          <button className="btn small" onClick={() => setSwapped(!swapped)} title="Swap direction">
            <ArrowLeftRight size={13} /> swap
          </button>
          <strong>{to.name}</strong>
        </div>
        <p className="hint">Read it as a sentence: “{from.name} <em>[relationship]</em> {to.name}”. Only ones that make sense for these two are listed.</p>

        {suggested.length > 0 && (
          <div className="relation-group">
            <h4>Suggested</h4>
            <div className="relation-options">{suggested.map((relation) => option(relation, "s-"))}</div>
          </div>
        )}
        {Object.entries(GROUP_LABELS).map(([category, label]) => {
          const inGroup = allowed.filter((r) => r.category === category);
          return inGroup.length > 0 && (
            <div className="relation-group" key={category}>
              <h4>{label}</h4>
              <div className="relation-options">{inGroup.map((relation) => option(relation, ""))}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
