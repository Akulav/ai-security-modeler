import { Ban, Cpu, FileDown, FileText, Globe, LoaderCircle, Play, Sparkles, Square, X } from "lucide-react";
import { useState } from "react";
import type { AnalysisReport, Finding, GraphNode, LlmStatus, NarrativeItem, Section } from "../types";
import ModelManager from "./ModelManager";
import QuestionsView from "./QuestionsView";

const TABS: { id: Section; label: string }[] = [
  { id: "vulnerabilities", label: "Vulnerabilities" },
  { id: "recommendations", label: "Recommendations" },
  { id: "topology", label: "Topology" },
];

export interface LogEntry {
  tone: "info" | "search" | "blocked" | "error";
  text: string;
}

interface Props {
  visible: boolean;
  graphVersion: unknown;
  report: AnalysisReport | null;
  running: boolean;
  log: LogEntry[];
  llm: LlmStatus | null;
  webSearch: boolean;
  nodes: GraphNode[];
  activeTitle: string | null;
  onSelectModel: (model: string) => void;
  onPullModel: (model: string) => void;
  onDeleteModel: (model: string) => void;
  onCancelPull: () => void;
  onRetryLlm: () => void;
  onLoadLlm: () => void;
  onUnloadLlm: () => void;
  onIdleUnload: (seconds: number) => void;
  onWebSearch: (enabled: boolean) => void;
  onRun: () => void;
  onStop: () => void;
  onFinishResearch: () => void;
  onFocus: (title: string, ids: string[]) => void;
  onClose: () => void;
}

export default function AnalysisPanel(props: Props) {
  const { report, running, log, llm, webSearch, nodes, activeTitle } = props;
  const [tab, setTab] = useState<Section>("vulnerabilities");
  const [mode, setMode] = useState<"report" | "questions">("report");
  const [asking, setAsking] = useState(false);
  const researching = running && webSearch && !log.some((entry) => entry.text.endsWith("writing the report") || entry.tone === "error");
  const llmReady =Boolean(llm?.available && llm.models.some((m) => m.name === llm.selected));

  const idsForNames = (names: string[]) => {
    const wanted = new Set(names.map((name) => name.toLowerCase()));
    return nodes.filter((node) => wanted.has(node.name.toLowerCase())).map((node) => node.id);
  };

  const card = (key: string, item: Finding | NarrativeItem, ids: string[], source: "ai" | "engine") => (
    <li key={key}>
      <button
        className={`finding sev-${item.severity}${activeTitle === item.title ? " active" : ""}`}
        onClick={() => props.onFocus(item.title, ids)}
      >
        <div className="finding-head">
          <span className="sev">{item.severity}</span>
          <span className="source">{source === "ai" ? <Sparkles size={11} /> : <Cpu size={11} />}</span>
        </div>
        <strong>{item.title}</strong>
        <p>{item.detail}</p>
      </button>
    </li>
  );

  const narrative = report?.narrative;
  const aiItems = narrative?.[tab] ?? [];
  const engineItems = report?.findings.filter((finding) => finding.section === tab) ?? [];
  const count = (section: Section) =>
    (narrative?.[section].length ?? 0) + (report?.findings.filter((f) => f.section === section).length ?? 0);

  return (
    <aside className="panel analysis glass" aria-label="Infrastructure analysis" hidden={!props.visible}>
      <header>
        <h2>Infrastructure analysis</h2>
        <span className="header-actions">
          <a className="icon-btn" href="/api/analysis/report.pdf" download title="Download PDF report" aria-label="Download PDF report">
            <FileDown size={16} />
          </a>
          <button className="icon-btn" onClick={props.onClose} aria-label="Close panel"><X size={16} /></button>
        </span>
      </header>

      <section className="analysis-controls">
        <ModelManager
          llm={llm}
          disabled={running || asking}
          onLoad={props.onLoadLlm}
          onUnload={props.onUnloadLlm}
          onIdleUnload={props.onIdleUnload}
          onSelect={props.onSelectModel}
          onPull={props.onPullModel}
          onDelete={props.onDeleteModel}
          onCancel={props.onCancelPull}
          onRetry={props.onRetryLlm}
        />
        {llm && !llmReady && (
          <p className="hint">Until the model is ready, analysis gives graph-engine findings without AI commentary.</p>
        )}
        <label className="check" title="Search queries go to DuckDuckGo. Queries with your addresses are blocked.">
          <input type="checkbox" checked={webSearch} onChange={(e) => props.onWebSearch(e.target.checked)} disabled={running} />
          <Globe size={13} /> Let the model search the web
        </label>
        {running ? (
          <div className="form-actions">
            {researching && (
              <button className="btn primary" onClick={props.onFinishResearch} title="Stop searching and write the report with what's been found">
                <FileText size={14} /> Finish research
              </button>
            )}
            <button className="btn" onClick={props.onStop}><Square size={14} /> Stop</button>
          </div>
        ) : (
          mode === "report" && (
            <button className="btn primary" onClick={props.onRun} disabled={asking}><Play size={14} /> Run analysis</button>
          )
        )}
        <div className="segmented" role="group" aria-label="View">
          <button className={mode === "report" ? "on" : ""} onClick={() => setMode("report")}>Full analysis</button>
          <button className={mode === "questions" ? "on" : ""} onClick={() => setMode("questions")}>Questions</button>
        </div>
      </section>

      {/* Stays mounted while hidden, so an answer in progress isn't lost. */}
      <section hidden={mode !== "questions"}>
        <QuestionsView
          visible={props.visible && mode === "questions"}
          graphVersion={props.graphVersion}
          webSearch={webSearch}
          blocked={running}
          onAsking={setAsking}
          onFocus={props.onFocus}
        />
      </section>

      {mode === "report" && <>
      {log.length > 0 && (
        <ul className="run-log" aria-live="polite">
          {log.map((entry, index) => (
            <li key={index} className={entry.tone}>
              {entry.tone === "search" && <Globe size={12} />}
              {entry.tone === "blocked" && <Ban size={12} />}
              {entry.tone === "info" && running && index === log.length - 1 && <LoaderCircle size={12} className="spin" />}
              <span>{entry.text}</span>
            </li>
          ))}
        </ul>
      )}

      {report && (
        <>
          {report.created_at && !running && (
            <p className="hint report-age">
              From {new Date(report.created_at).toLocaleString()}. Run again after changing the graph.
            </p>
          )}
          {narrative?.summary && <p className="summary"><Sparkles size={13} /> {narrative.summary}</p>}
          <div className="tabs" role="tablist">
            {TABS.map(({ id, label }) => (
              <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
                {label} <span>{count(id)}</span>
              </button>
            ))}
          </div>
          <div className="findings">
            {aiItems.length > 0 && <h4><Sparkles size={12} /> AI assessment</h4>}
            <ul>{aiItems.map((item, i) => card(`ai-${i}`, item, idsForNames(item.node_names), "ai"))}</ul>
            {engineItems.length > 0 && <h4><Cpu size={12} /> Calculated from your graph</h4>}
            <ul>{engineItems.map((item, i) => card(`engine-${i}`, item, item.node_ids, "engine"))}</ul>
            {aiItems.length === 0 && engineItems.length === 0 && <p className="muted">Nothing found in this category.</p>}
          </div>
        </>
      )}
      {!report && !running && (
        <p className="muted pad">Finds single points of failure, takeover paths, circular dependencies and backup gaps.</p>
      )}
      </>}
    </aside>
  );
}
