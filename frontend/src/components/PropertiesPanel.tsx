import { Bomb, LoaderCircle, Plus, Radar, Save, ShieldAlert, ShieldCheck, Skull, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { BlastRadius, Catalog, GraphEdge, GraphNode } from "../types";
import { usesEmail } from "../visuals";
import NodeFields, { type NodeDraft } from "./NodeFields";

function toDraft(node: GraphNode): NodeDraft {
  return {
    type: node.type,
    name: node.name,
    email: node.email ?? "",
    ip_address: node.ip_address ?? "",
    os: node.os ?? "",
    os_version: node.os_version ?? "",
    encryption: node.encryption,
    defenses: node.defenses ?? [],
    security_level: node.security_level,
    password_type: node.password_type,
    status: node.status,
    notes: node.notes,
  };
}

export type BlastMode = "loss" | "compromise";

interface Props {
  catalog: Catalog;
  node: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
  radius: BlastRadius | null;
  blastMode: BlastMode;
  checking: boolean;
  advising: boolean;
  hibpConfigured: boolean;
  focusName: boolean;
  onAddApp: (groupId: string, name: string) => void;
  onBlastMode: (mode: BlastMode) => void;
  onSave: (draft: NodeDraft) => void;
  onDelete: () => void;
  onCheck: () => void;
  onSelect: (id: string) => void;
  onClose: () => void;
}

export default function PropertiesPanel(props: Props) {
  const { catalog, node, nodes, edges, radius, blastMode, checking, advising, hibpConfigured } = props;
  const saved = useMemo(() => toDraft(node), [node]);
  const savedKey = JSON.stringify(saved);
  const [draft, setDraft] = useState(saved);
  const [appName, setAppName] = useState("");
  const isGroup = node.type === "app_group";
  const apps = nodes.filter((n) => n.parent_id === node.id);

  // Keyed on content so dragging the node, which only moves it, keeps unsaved edits.
  useEffect(() => setDraft(JSON.parse(savedKey)), [node.id, savedKey]);

  const dirty = JSON.stringify(draft) !== savedKey;
  const names = useMemo(() => new Map(nodes.map((n) => [n.id, n.name])), [nodes]);
  const labels = useMemo(() => new Map(catalog.relations.map((r) => [r.id, r])), [catalog]);

  const relationTo = (otherId: string): string[] =>
    edges
      .filter(
        (e) => (e.source_id === node.id && e.target_id === otherId) || (e.target_id === node.id && e.source_id === otherId),
      )
      .map((e) => labels.get(e.relation)?.label ?? e.relation);

  const nodeList = (ids: string[], annotate = false) => (
    <ul className="node-list">
      {ids.map((id) => (
        <li key={id}>
          <button onClick={() => props.onSelect(id)}>
            <span>{names.get(id)}</span>
            {annotate && <small>{relationTo(id).join(", ")}</small>}
          </button>
        </li>
      ))}
    </ul>
  );

  const radiusIds = radius ? radius[blastMode] : [];
  const breaches = node.breaches;

  return (
    <aside className="panel glass" aria-label="Node properties">
      <header>
        <h2 title={node.name}>{node.name}</h2>
        <button className="icon-btn" onClick={props.onClose} aria-label="Close panel"><X size={16} /></button>
      </header>

      {usesEmail(catalog, node.type) && (
        <section className={breaches?.length ? "breach-section alert" : "breach-section"}>
          <h3>Breach check</h3>
          {!node.email && <p className="muted">Add an email address to check it against known breaches.</p>}
          {node.email && !hibpConfigured && (
            <p className="muted">Add <code>HIBP_API_KEY</code> to <code>.env</code> and restart to enable breach checks.</p>
          )}
          {node.email && hibpConfigured && (
            <button className="btn" onClick={props.onCheck} disabled={checking || dirty}>
              {checking ? <LoaderCircle size={14} className="spin" /> : <Radar size={14} />}
              {checking ? "Checking" : breaches ? "Check again" : "Check HaveIBeenPwned"}
            </button>
          )}
          {breaches && breaches.length === 0 && (
            <p className="clean"><ShieldCheck size={14} /> No known breaches for this address.</p>
          )}
          {breaches && breaches.length > 0 && (
            <>
              <p className="breached-text"><ShieldAlert size={14} /> Found in {breaches.length} breach{breaches.length > 1 ? "es" : ""}</p>
              {node.breach_advice && (
                <div className="advice">
                  <h4>What to do {advising && <LoaderCircle size={12} className="spin" />}</h4>
                  <p>{node.breach_advice}</p>
                </div>
              )}
              <ul className="breach-list">
                {breaches.map((breach) => (
                  <li key={breach.name + breach.breach_date}>
                    <div className="breach-head">
                      <strong>{breach.name}</strong>
                      <span>{breach.breach_date}</span>
                    </div>
                    {breach.data_classes.length > 0 && (
                      <div className="tags">{breach.data_classes.map((c) => <span key={c}>{c}</span>)}</div>
                    )}
                    {breach.description && <details><summary>Details</summary><p>{breach.description}</p></details>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {node.breach_checked_at && <p className="hint">Last checked {new Date(node.breach_checked_at).toLocaleString()}</p>}
        </section>
      )}

      {isGroup && (
        <section>
          <h3>Apps on this device</h3>
          {apps.length === 0 && <p className="muted">Type app names into the box on the canvas node, or add one here.</p>}
          {nodeList(apps.map((app) => app.id))}
          <form
            className="model-row add-app-row"
            onSubmit={(event) => {
              event.preventDefault();
              if (!appName.trim()) return;
              props.onAddApp(node.id, appName.trim());
              setAppName("");
            }}
          >
            <input value={appName} onChange={(e) => setAppName(e.target.value)} placeholder="Add an app" maxLength={200} />
            <button className="btn" disabled={!appName.trim()}><Plus size={14} /> Add</button>
          </form>
          <p className="hint">Each app has its own handles on the canvas, so you can connect it, such as Authy to GitHub.</p>
        </section>
      )}

      {!isGroup && <section>
        <h3>Blast radius</h3>
        <div className="segmented" role="group" aria-label="Failure scenario">
          <button className={blastMode === "loss" ? "on" : ""} onClick={() => props.onBlastMode("loss")}>
            <Bomb size={13} /> If lost
          </button>
          <button className={blastMode === "compromise" ? "on" : ""} onClick={() => props.onBlastMode("compromise")}>
            <Skull size={13} /> If hacked
          </button>
        </div>
        <p className="muted">
          {radius === null
            ? "Calculating"
            : radiusIds.length === 0
              ? blastMode === "loss" ? "Losing this affects nothing else." : "Taking this over reaches nothing else."
              : blastMode === "loss"
                ? `Losing this takes down ${radiusIds.length} other node${radiusIds.length > 1 ? "s" : ""}:`
                : `An attacker here reaches ${radiusIds.length} other node${radiusIds.length > 1 ? "s" : ""}:`}
        </p>
        {nodeList(radiusIds)}
      </section>}

      {radius && radius.dependents.length > 0 && (
        <section>
          <h3>Directly relies on this</h3>
          {nodeList(radius.dependents, true)}
        </section>
      )}
      {radius && radius.depends_on.length > 0 && (
        <section>
          <h3>This relies on</h3>
          {nodeList(radius.depends_on, true)}
        </section>
      )}

      <section>
        <h3>Details</h3>
        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault();
            props.onSave(draft);
          }}
        >
          <NodeFields
            catalog={catalog}
            draft={draft}
            onChange={setDraft}
            lockType={isGroup || Boolean(node.parent_id)}
            focusName={props.focusName}
          />
          <div className="form-actions">
            <button className="btn primary" disabled={!dirty || !draft.name.trim()}><Save size={14} /> Save</button>
            <button type="button" className="btn danger" onClick={props.onDelete}><Trash2 size={14} /> Delete</button>
          </div>
        </form>
      </section>
    </aside>
  );
}
