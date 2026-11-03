import type {
  AnalysisEvent, AnalysisReport, BlastRadius, Catalog, Graph, GraphEdge, GraphNode, LlmStatus, Question, QuestionEvent,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new ApiError("The backend isn't reachable. Is Security Modeler still running? Look for its icon in the system tray.", 0);
  }
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const { detail } = await response.json();
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return `${detail[0].loc?.at(-1) ?? "Field"}: ${detail[0].msg}`;
  } catch {
    // Non-JSON body: fall through to the generic message.
  }
  return `Request failed (${response.status})`;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  catalog: () => request<Catalog>("/catalog"),
  graph: () => request<Graph>("/graph"),
  createNode: (node: Partial<GraphNode>) => request<GraphNode>("/nodes", json("POST", node)),
  updateNode: (id: string, changes: Partial<GraphNode>) => request<GraphNode>(`/nodes/${id}`, json("PATCH", changes)),
  deleteNode: (id: string) => request<void>(`/nodes/${id}`, { method: "DELETE" }),
  blastRadius: (id: string) => request<BlastRadius>(`/nodes/${id}/blast-radius`),
  createEdge: (edge: Partial<GraphEdge>) => request<GraphEdge>("/edges", json("POST", edge)),
  updateEdge: (id: string, changes: Partial<GraphEdge>) => request<GraphEdge>(`/edges/${id}`, json("PATCH", changes)),
  deleteEdge: (id: string) => request<void>(`/edges/${id}`, { method: "DELETE" }),
  exportGraph: () => request<unknown>("/export"),
  importGraph: (data: unknown) => request<Graph>("/import", json("POST", data)),
  loadSample: () => request<Graph>("/seed", { method: "POST" }),
  hibpStatus: () => request<{ configured: boolean }>("/hibp/status"),
  checkBreaches: (id: string) => request<GraphNode>(`/hibp/check/${id}`, { method: "POST" }),
  breachAdvice: (id: string, model: string) =>
    request<GraphNode>(`/hibp/advice/${id}?model=${encodeURIComponent(model)}`, { method: "POST" }),
  llmStatus: () => request<LlmStatus>("/llm/status"),
  selectModel: (model: string) => request<void>("/llm/select", json("POST", { model })),
  pullModel: (model: string) => request<unknown>("/llm/pull", json("POST", { model })),
  deleteModel: (model: string) => request<void>("/llm/models", json("DELETE", { model })),
  cancelPull: () => request<void>("/llm/cancel", { method: "POST" }),
  retryLlm: () => request<void>("/llm/retry", { method: "POST" }),
  loadLlm: () => request<unknown>("/llm/load", { method: "POST" }),
  unloadLlm: () => request<void>("/llm/unload", { method: "POST" }),
  setIdleUnload: (seconds: number) => request<void>("/llm/idle", json("POST", { seconds })),
  finishResearch: () => request<void>("/analysis/finish-research", { method: "POST" }),
  latestReport: () => request<AnalysisReport | null>("/analysis/latest"),

  questions: () => request<Question[]>("/analysis/questions"),
  ask: (
    options: { question_id?: string; text?: string; web_search: boolean },
    onEvent: (event: QuestionEvent) => void,
    signal: AbortSignal,
  ) => streamEvents("/api/analysis/ask", options, onEvent, signal),
  runAnalysis: (
    options: { model?: string; web_search: boolean },
    onEvent: (event: AnalysisEvent) => void,
    signal: AbortSignal,
  ) => streamEvents("/api/analysis/run", options, onEvent, signal),
};

async function streamEvents<T>(path: string, options: unknown, onEvent: (event: T) => void, signal: AbortSignal): Promise<void> {
  {
    const response = await fetch(path, {
      ...json("POST", options),
      headers: { "Content-Type": "application/json" },
      signal,
    });
    if (!response.ok || !response.body) throw new ApiError(await errorMessage(response), response.status);

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += value;
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) onEvent(JSON.parse(line));
      }
    }
  }
}
