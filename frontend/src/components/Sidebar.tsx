import { Plus } from "lucide-react";
import { type FormEvent, useState } from "react";
import type { Catalog } from "../types";
import { CATEGORY_COLORS, FALLBACK_ICON, NODE_ICONS } from "../visuals";
import NodeFields, { draftForType, EMPTY_DRAFT, type NodeDraft } from "./NodeFields";

interface Props {
  catalog: Catalog;
  onCreate: (draft: NodeDraft) => Promise<boolean>;
}

export const DRAG_MIME = "application/x-security-modeler-type";

export default function Sidebar({ catalog, onCreate }: Props) {
  const [draft, setDraft] = useState<NodeDraft>(EMPTY_DRAFT);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (await onCreate(draft)) setDraft(draftForType(catalog, draft.type));
  };

  return (
    <aside className="sidebar glass">
      <div className="brand">
        <img src="/icon.svg" alt="" width={34} height={34} />
        <div>
          <strong>Security Modeler</strong>
          <span>personal infrastructure map</span>
          <span className="credit">
            made by{" "}
            <a href="https://github.com/Akulav/ai-security-modeler" target="_blank" rel="noopener noreferrer">Akulav</a>
            {" · "}{__APP_VERSION__ === "dev" ? "dev" : `v${__APP_VERSION__}`}
          </span>
        </div>
      </div>

      <section>
        <h3>Drag onto the canvas</h3>
        {Object.entries(catalog.categories).map(([id, category]) => (
          <div key={id} className="palette-group">
            <h4 style={{ color: CATEGORY_COLORS[id] }}>{category.label}</h4>
            <div className="palette">
              {Object.entries(category.types).filter(([type]) => !catalog.palette_hidden.includes(type)).map(([type, label]) => {
                const Icon = NODE_ICONS[type] ?? FALLBACK_ICON;
                return (
                  <button
                    key={type}
                    type="button"
                    className={`chip${draft.type === type ? " active" : ""}`}
                    style={{ "--node-color": CATEGORY_COLORS[id] } as React.CSSProperties}
                    title={`${label}: drag to the canvas, or click to use in the form`}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData(DRAG_MIME, type);
                      event.dataTransfer.effectAllowed = "copy";
                    }}
                    onClick={() => setDraft({ ...draftForType(catalog, type), name: draft.name })}
                  >
                    <Icon size={14} />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </section>

      <section>
        <h3>Add a node</h3>
        <form className="form" onSubmit={submit}>
          <NodeFields catalog={catalog} draft={draft} onChange={setDraft} />
          <button className="btn primary" disabled={!draft.name.trim()}>
            <Plus size={15} /> Add to canvas
          </button>
        </form>
      </section>
    </aside>
  );
}
