import { Ban, Cpu, FileText, Globe, LoaderCircle, Send, Sparkles, Square } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Question, QuestionEvent, QuestionFacts } from "../types";

interface Props {
  visible: boolean;
  graphVersion: unknown;
  webSearch: boolean;
  blocked: boolean;
  onAsking: (asking: boolean) => void;
  onFocus: (title: string, ids: string[]) => void;
}

interface LogLine {
  tone: "info" | "search" | "blocked" | "error";
  text: string;
}

/** Ready-made questions. Each list is calculated instantly; asking the AI adds research and advice. */
export default function QuestionsView({ visible, graphVersion, webSearch, blocked, onAsking, onFocus }: Props) {
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [custom, setCustom] = useState("");
  const [customView, setCustomView] = useState<{ label: string; facts: QuestionFacts | null; answer: string | null } | null>(null);
  const [asking, setAsking] = useState(false);
  const [writing, setWriting] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const result = useRef<HTMLDivElement>(null);

  const refresh = useCallback(() => {
    api.questions().then(setQuestions).catch((failure) => setError(failure.message));
  }, []);

  useEffect(() => {
    if (visible) refresh();
  }, [visible, graphVersion, refresh]);

  const run = async (request: { question_id?: string; text?: string }) => {
    setAsking(true);
    onAsking(true);
    setWriting(false);
    setLog([]);
    setError(null);
    abort.current = new AbortController();
    const add = (line: LogLine) => setLog((current) => [...current, line]);
    const onEvent = (event: QuestionEvent) => {
      switch (event.type) {
        case "facts":
          if (request.text) setCustomView((current) => current && { ...current, facts: event.facts });
          break;
        case "status":
          if (event.message.endsWith("writing the answer")) setWriting(true);
          add({ tone: "info", text: event.message });
          break;
        case "search":
          add({ tone: "search", text: `Searched: ${event.query}` });
          break;
        case "search_blocked":
          add({ tone: "blocked", text: `Blocked a search: ${event.reason}` });
          break;
        case "search_failed":
          add({ tone: "error", text: `Search failed: ${event.query}` });
          break;
        case "llm_error":
          setError(event.message);
          break;
        case "answer":
          if (request.text) setCustomView((current) => current && { ...current, answer: event.text });
          break;
      }
    };
    try {
      await api.ask({ ...request, web_search: webSearch }, onEvent, abort.current.signal);
      refresh();
    } catch (failure) {
      if ((failure as Error).name !== "AbortError") setError("The answer stopped unexpectedly.");
    } finally {
      setAsking(false);
      onAsking(false);
    }
  };

  const active = questions?.find((question) => question.id === activeId) ?? null;
  const shown = customView ?? active;

  const askCustom = (event: FormEvent) => {
    event.preventDefault();
    const text = custom.trim();
    if (!text || asking || blocked) return;
    setActiveId(null);
    setCustomView({ label: text, facts: null, answer: null });
    void run({ text });
  };

  const choose = (question: Question) => {
    setCustomView(null);
    setActiveId(question.id);
    setError(null);
    if (!asking) setLog([]);
    onFocus(question.label, question.facts.rows.flatMap((row) => (row.node_id ? [row.node_id] : [])));
    // The list of questions is long enough to push the result out of view.
    setTimeout(() => result.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  return (
    <div className="questions">
      {questions === null && !error && <p className="muted">Loading</p>}
      <ul className="question-list">
        {questions?.map((question) => (
          <li key={question.id}>
            <button className={question.id === activeId && !customView ? "on" : ""} onClick={() => choose(question)}>
              <span>{question.label}</span>
              {question.answer && <Sparkles size={11} aria-label="Answered by AI" />}
              {question.web && <Globe size={11} aria-label="Uses web research" />}
            </button>
          </li>
        ))}
      </ul>

      <form className="model-row" onSubmit={askCustom}>
        <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Ask your own question" maxLength={500} aria-label="Ask your own question" />
        <button className="btn" disabled={!custom.trim() || asking || blocked} aria-label="Ask"><Send size={14} /></button>
      </form>

      {shown && (
        <div className="question-result" ref={result}>
          <h3>{shown.label}</h3>
          {shown.facts && (
            <>
              <h4><Cpu size={12} /> Calculated from your map</h4>
              <p className="muted">{shown.facts.headline}</p>
              {shown.facts.rows.length > 0 && !customView && (
                <div className="facts-scroll">
                  <table className="facts">
                    <thead><tr>{shown.facts.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                    <tbody>
                      {shown.facts.rows.map((row, index) => (
                        <tr
                          key={index}
                          className={row.node_id ? "clickable" : ""}
                          onClick={() => row.node_id && onFocus(`${shown.label}:${index}`, [row.node_id])}
                        >
                          {row.cells.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {active && !customView && (asking ? null : (
            <button className={active.answer ? "btn" : "btn primary"} disabled={blocked} onClick={() => run({ question_id: active.id })}>
              <Sparkles size={14} /> {active.answer ? "Ask the AI again" : "Ask the AI"}
            </button>
          ))}
          {asking && (
            <div className="form-actions">
              {webSearch && !writing && (
                <button className="btn primary" onClick={() => api.finishResearch().catch(() => undefined)}>
                  <FileText size={14} /> Finish research
                </button>
              )}
              <button className="btn" onClick={() => abort.current?.abort()}><Square size={14} /> Stop</button>
            </div>
          )}
          {log.length > 0 && (
            <ul className="run-log inline" aria-live="polite">
              {log.map((line, index) => (
                <li key={index} className={line.tone}>
                  {line.tone === "search" && <Globe size={12} />}
                  {line.tone === "blocked" && <Ban size={12} />}
                  {line.tone === "info" && asking && index === log.length - 1 && <LoaderCircle size={12} className="spin" />}
                  <span>{line.text}</span>
                </li>
              ))}
            </ul>
          )}
          {shown.answer && (
            <div className="ai-answer">
              <h4><Sparkles size={12} /> AI answer</h4>
              <p>{shown.answer.replace(/\*\*/g, "")}</p>
              <span className="hint">
                {!customView && active?.answered_at && `From ${new Date(active.answered_at).toLocaleString()}. `}
                AI text can contain mistakes.
              </span>
            </div>
          )}
        </div>
      )}
      {error && <p className="notice error">{error}</p>}
    </div>
  );
}
