import { Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Catalog, GraphEdge, GraphNode } from "../types";
import { LOSS_MODE_LABELS } from "../visuals";

interface Props {
  catalog: Catalog;
  edge: GraphEdge;
  source?: GraphNode;
  target?: GraphNode;
  onChange: (changes: Partial<GraphEdge>) => void;
  onDelete: () => void;
  onClose: () => void;
}

export default function EdgePanel({ catalog, edge, source, target, onChange, onDelete, onClose }: Props) {
  const relation = catalog.relations.find((r) => r.id === edge.relation);
  const [notes, setNotes] = useState(edge.notes);
  useEffect(() => setNotes(edge.notes), [edge.id, edge.notes]);

  return (
    <aside className="panel glass" aria-label="Relationship properties">
      <header>
        <h2>Relationship</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close panel"><X size={16} /></button>
      </header>
      <section>
        <p className="edge-sentence">
          <strong>{source?.name}</strong> {relation?.label} <strong>{target?.name}</strong>
        </p>
        <div className="form">
          <label>
            Relationship
            <select value={edge.relation} onChange={(e) => onChange({ relation: e.target.value })}>
              {catalog.relations
                .filter((r) => r.id === edge.relation || (source && target && r.sources.includes(source.type) && r.targets.includes(target.type)))
                .map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </label>
          <label>
            If the provider is lost
            <select
              value={edge.loss_mode ?? ""}
              onChange={(e) => onChange({ loss_mode: e.target.value || null })}
            >
              <option value="">Default ({relation?.loss})</option>
              {catalog.loss_modes.map((mode) => <option key={mode} value={mode}>{LOSS_MODE_LABELS[mode]}</option>)}
            </select>
            <span className="hint">
              Have a backup 2FA method? Set each one to “Alternative” so losing one isn't counted as a lockout.
            </span>
          </label>
          <label>
            Notes
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => notes !== edge.notes && onChange({ notes })}
            />
          </label>
          <p className="muted">
            {relation?.compromise
              ? "If the provider is hacked, an attacker also gains the dependent."
              : "Hacking the provider alone doesn't hand over the dependent."}
          </p>
          <button className="btn danger" onClick={onDelete}><Trash2 size={14} /> Delete relationship</button>
        </div>
      </section>
    </aside>
  );
}
