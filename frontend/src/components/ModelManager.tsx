import { Download, LoaderCircle, Power, PowerOff, RotateCcw, Square, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import type { LlmStatus } from "../types";

const gigabytes = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(1)} GB`;

interface Props {
  llm: LlmStatus | null;
  disabled: boolean;
  onSelect: (model: string) => void;
  onPull: (model: string) => void;
  onDelete: (model: string) => void;
  onCancel: () => void;
  onRetry: () => void;
  onLoad: () => void;
  onUnload: () => void;
}

export function SetupProgress({ llm, onCancel, onRetry }: Pick<Props, "llm" | "onCancel" | "onRetry">) {
  if (!llm) return null;
  if (llm.phase === "error") {
    return (
      <div className="notice error">
        <p>{llm.message}</p>
        <button type="button" className="btn small" onClick={onRetry}><RotateCcw size={12} /> Retry</button>
      </div>
    );
  }
  if (!llm.busy) return llm.message ? <p className="notice">{llm.message}</p> : null;
  const percent = llm.total > 0 ? Math.floor((llm.completed / llm.total) * 100) : null;
  return (
    <div className="setup-progress" aria-live="polite">
      <div className="setup-head">
        <LoaderCircle size={13} className="spin" />
        <span title={llm.message}>{llm.message || "Setting up the local LLM"}</span>
        {llm.phase === "pulling" && (
          <button type="button" className="icon-btn" onClick={onCancel} title="Pause download" aria-label="Pause download">
            <Square size={12} />
          </button>
        )}
      </div>
      {percent !== null && (
        <>
          <div className="bar"><i style={{ width: `${percent}%` }} /></div>
          <small>{gigabytes(llm.completed)} of {gigabytes(llm.total)} ({percent}%)</small>
        </>
      )}
    </div>
  );
}

function memoryText(llm: LlmStatus): string {
  if (llm.phase === "stopped") return "LLM stopped. Nothing in memory.";
  if (llm.loaded.length === 0) return llm.available ? "LLM running. No model in memory." : "LLM not running.";
  const used = llm.loaded.reduce((sum, model) => sum + model.size, 0);
  const onGpu = llm.loaded.reduce((sum, model) => sum + model.size_vram, 0);
  return `In memory: ${gigabytes(used)}, ${Math.round((onGpu / (used || 1)) * 100)}% on the GPU.`;
}

export default function ModelManager({ llm, disabled, onSelect, onPull, onDelete, onCancel, onRetry, onLoad, onUnload }: Props) {
  const [name, setName] = useState("");
  const installed = llm?.models ?? [];
  const selectedInstalled = installed.some((model) => model.name === llm?.selected);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onPull(name.trim());
    setName("");
  };

  return (
    <div className="model-manager">
      <SetupProgress llm={llm} onCancel={onCancel} onRetry={onRetry} />
      {llm && installed.length > 0 && (
        <label>
          Model
          <span className="model-row">
            <select value={selectedInstalled ? llm.selected : ""} onChange={(e) => onSelect(e.target.value)} disabled={disabled}>
              {!selectedInstalled && <option value="" disabled>Choose a model</option>}
              {installed.map((model) => (
                <option key={model.name} value={model.name}>{model.name} ({gigabytes(model.size)})</option>
              ))}
            </select>
            <button
              type="button"
              className="icon-btn"
              title="Delete this model from disk"
              aria-label="Delete this model from disk"
              disabled={disabled || !selectedInstalled}
              onClick={() => llm && onDelete(llm.selected)}
            >
              <Trash2 size={14} />
            </button>
          </span>
        </label>
      )}
      {llm && (
        <div className="memory-row">
          <p className="hint" aria-live="polite">{memoryText(llm)}</p>
          <span>
            {llm.loaded.length === 0 && (
              <button type="button" className="btn small" disabled={disabled || llm.busy} onClick={onLoad} title="Start the LLM and keep the selected model in memory until you unload it">
                <Power size={12} /> Load
              </button>
            )}
            {(llm.loaded.length > 0 || (llm.managed && llm.available)) && (
              <button type="button" className="btn small" disabled={disabled || llm.busy} onClick={onUnload} title="Free the model's memory and stop the LLM. Your files stay on disk.">
                <PowerOff size={12} /> Unload
              </button>
            )}
          </span>
        </div>
      )}
      {llm && !llm.busy && !selectedInstalled && llm.available && (
        <button type="button" className="btn" onClick={() => onPull(llm.selected)} title={llm.selected}>
          <Download size={14} /> Download the selected model
        </button>
      )}
      <form onSubmit={submit}>
        <label>
          Use another model
          <span className="model-row">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="hf.co/owner/repo-GGUF:Q4_K_M or qwen3"
              spellCheck={false}
              maxLength={200}
            />
            <button className="btn" disabled={!name.trim() || disabled || llm?.busy || !llm?.available}>
              <Download size={14} /> Get
            </button>
          </span>
          <span className="hint">Downloaded into this project's llm folder, then selected.</span>
        </label>
      </form>
    </div>
  );
}
