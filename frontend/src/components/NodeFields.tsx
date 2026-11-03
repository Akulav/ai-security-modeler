import { useEffect, useRef } from "react";
import type { Catalog, GraphNode } from "../types";

export type NodeDraft = Pick<
  GraphNode,
  "type" | "name" | "security_level" | "password_type" | "encryption" | "status" | "notes"
> & { email: string; ip_address: string; os: string; os_version: string; defenses: string[] };

export const EMPTY_DRAFT: NodeDraft = {
  type: "email_account",
  name: "",
  email: "",
  ip_address: "",
  os: "",
  os_version: "",
  encryption: "unknown",
  defenses: [],
  security_level: "high",
  password_type: "unknown",
  status: "active",
  notes: "",
};

export function draftForType(catalog: Catalog, type: string, name = ""): NodeDraft {
  return { ...EMPTY_DRAFT, type, name, security_level: catalog.default_levels[type] ?? "medium" };
}

interface Props {
  catalog: Catalog;
  draft: NodeDraft;
  lockType?: boolean;
  focusName?: boolean;
  onChange: (draft: NodeDraft) => void;
}

/** The metadata form shared by the "add node" sidebar and the properties panel. Shows only what the type has. */
export default function NodeFields({ catalog, draft, lockType, focusName, onChange }: Props) {
  const set = (field: keyof NodeDraft) => (event: { target: { value: string } }) =>
    onChange({ ...draft, [field]: event.target.value });
  const has = (field: string) => catalog.fields[draft.type]?.includes(field);
  const nameInput = useRef<HTMLInputElement>(null);
  const defenseOptions = catalog.defense_options[draft.type] ?? [];
  const isLogin = defenseOptions.includes("password");

  useEffect(() => {
    if (focusName) nameInput.current?.select();
  }, [focusName]);

  return (
    <>
      {!lockType && (
        <label>
          Type
          <select
            value={draft.type}
            onChange={(event) => onChange({
              ...draft,
              type: event.target.value,
              security_level: catalog.default_levels[event.target.value] ?? "medium",
              // These lists differ per type, so a value from the old type may not apply.
              os: "",
              password_type: "unknown",
              defenses: [],
            })}
          >
            {Object.entries(catalog.categories).map(([id, category]) => (
              <optgroup key={id} label={category.label}>
                {Object.entries(category.types)
                  .filter(([type]) => !catalog.palette_hidden.includes(type))
                  .map(([type, label]) => <option key={type} value={type}>{label}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
      )}
      <label>
        Name
        <input ref={nameInput} value={draft.name} onChange={set("name")} maxLength={200} placeholder="Name" />
      </label>
      {has("os") && (
        <div className="field-row">
          <label>
            Operating system
            <select value={draft.os} onChange={set("os")}>
              <option value="">Not set</option>
              {(catalog.os_options[draft.type] ?? []).map((id) => (
                <option key={id} value={id}>{catalog.operating_systems[id]}</option>
              ))}
            </select>
          </label>
          <label>
            Version
            <input value={draft.os_version} onChange={set("os_version")} placeholder="e.g. 24.04" maxLength={64} spellCheck={false} />
          </label>
        </div>
      )}
      {has("email") && (
        <label>
          Email address
          <input type="email" value={draft.email} onChange={set("email")} placeholder="you@example.com" spellCheck={false} />
        </label>
      )}
      {has("ip_address") && (
        <label>
          {catalog.ip_labels[draft.type] ?? "IP address"}
          <input value={draft.ip_address} onChange={set("ip_address")} placeholder={catalog.ip_labels[draft.type] ? "192.168.1.0/24" : "192.168.1.10"} spellCheck={false} maxLength={64} />
        </label>
      )}
      <div className="field-row">
        <label>
          Security level
          <select value={draft.security_level} onChange={set("security_level")}>
            {catalog.security_levels.map((level) => <option key={level} value={level}>{level}</option>)}
          </select>
        </label>
        {has("status") && (
          <label>
            Status
            <select value={draft.status} onChange={set("status")}>
              {catalog.statuses.map((status) => <option key={status} value={status}>{status}</option>)}
            </select>
          </label>
        )}
      </div>
      {has("encryption") && (
        <label>
          Encryption
          <select value={draft.encryption} onChange={set("encryption")}>
            {Object.entries(catalog.encryption_types).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
      )}
      {has("password_type") && (
        <label>
          {catalog.password_labels[draft.type] ?? "Password type"}
          <select value={draft.password_type} onChange={set("password_type")}>
            {(catalog.password_options[draft.type] ?? Object.keys(catalog.password_types)).map((id) => (
              <option key={id} value={id}>{catalog.password_types[id]}</option>
            ))}
          </select>
          <span className="hint">Only the type is stored. Never enter a password here.</span>
        </label>
      )}
      {defenseOptions.length > 0 && (
        <fieldset className="defenses">
          <legend>{isLogin ? "How you log in (tick all that apply)" : "How it's defended (tick all that apply)"}</legend>
          <div>
            {defenseOptions.map((id) => {
              const on = draft.defenses.includes(id);
              return (
                <button
                  key={id}
                  type="button"
                  className={on ? "on" : ""}
                  aria-pressed={on}
                  onClick={() => onChange({
                    ...draft,
                    defenses: on ? draft.defenses.filter((d) => d !== id) : [...draft.defenses, id],
                  })}
                >
                  {catalog.defenses[id]}
                </button>
              );
            })}
          </div>
        </fieldset>
      )}
      <label>
        Notes
        <textarea value={draft.notes} onChange={set("notes")} rows={2} />
      </label>
    </>
  );
}
