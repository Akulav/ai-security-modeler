export interface Breach {
  name: string;
  domain: string;
  breach_date: string | null;
  pwn_count: number | null;
  data_classes: string[];
  description: string;
  is_verified: boolean;
}

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  ip_address: string | null;
  email: string | null;
  security_level: string;
  password_type: string;
  os: string | null;
  os_version: string | null;
  encryption: string;
  defenses: string[] | null;
  parent_id: string | null;
  status: string;
  notes: string;
  pos_x: number;
  pos_y: number;
  breaches: Breach[] | null;
  breach_checked_at: string | null;
  breach_advice: string | null;
}

export interface GraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  loss_mode: string | null;
  notes: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Relation {
  id: string;
  label: string;
  category: string;
  provider: "source" | "target";
  loss: string;
  compromise: boolean;
  sources: string[];
  targets: string[];
}

export interface DropMenuItem {
  label: string;
  type: string;
  relation: string;
  new_is: "source" | "target";
}

export interface Catalog {
  categories: Record<string, { label: string; types: Record<string, string> }>;
  palette_hidden: string[];
  security_levels: string[];
  default_levels: Record<string, string>;
  password_types: Record<string, string>;
  password_options: Record<string, string[]>;
  password_labels: Record<string, string>;
  encryption_types: Record<string, string>;
  operating_systems: Record<string, string>;
  os_options: Record<string, string[]>;
  defenses: Record<string, string>;
  defense_options: Record<string, string[]>;
  ip_labels: Record<string, string>;
  fields: Record<string, string[]>;
  statuses: string[];
  loss_modes: string[];
  relations: Relation[];
  suggested_relations: Record<string, string[]>;
  drop_menu: Record<string, DropMenuItem[]>;
}

export interface BlastRadius {
  node_id: string;
  loss: string[];
  compromise: string[];
  depends_on: string[];
  dependents: string[];
}

export type Severity = "critical" | "high" | "medium" | "low";
export type Section = "vulnerabilities" | "recommendations" | "topology";

export interface Finding {
  kind: string;
  section: Section;
  severity: Severity;
  title: string;
  detail: string;
  node_ids: string[];
}

export interface NarrativeItem {
  title: string;
  detail: string;
  severity: Severity;
  node_names: string[];
}

export interface Narrative {
  summary: string;
  vulnerabilities: NarrativeItem[];
  recommendations: NarrativeItem[];
  topology: NarrativeItem[];
}

export interface AnalysisReport {
  findings: Finding[];
  summary: { nodes: number; edges: number; critical: number; high: number };
  narrative: Narrative | null;
  llm_error: string | null;
  created_at?: string;
  model?: string | null;
}

export type AnalysisEvent =
  | { type: "findings"; findings: Finding[]; summary: AnalysisReport["summary"] }
  | { type: "status"; message: string }
  | { type: "search"; query: string; results: number }
  | { type: "search_blocked"; query: string; reason: string }
  | { type: "search_failed"; query: string; reason: string }
  | { type: "llm_error"; message: string }
  | { type: "narrative"; report: Narrative; model: string }
  | { type: "done" };

export interface QuestionFacts {
  headline: string;
  columns: string[];
  rows: { node_id: string | null; cells: string[] }[];
}

export interface Question {
  id: string;
  label: string;
  web: boolean;
  facts: QuestionFacts;
  answer: string | null;
  answered_at: string | null;
}

export type QuestionEvent =
  | { type: "facts"; facts: QuestionFacts }
  | { type: "status"; message: string }
  | { type: "search"; query: string; results: number }
  | { type: "search_blocked"; query: string; reason: string }
  | { type: "search_failed"; query: string; reason: string }
  | { type: "llm_error"; message: string }
  | { type: "answer"; text: string }
  | { type: "done" };

export interface LlmStatus {
  phase: "idle" | "installing" | "starting" | "pulling" | "loading" | "ready" | "stopped" | "offline" | "error";
  message: string;
  completed: number;
  total: number;
  busy: boolean;
  managed: boolean;
  available: boolean;
  pulling_model: string | null;
  models: { name: string; size: number }[];
  loaded: { name: string; size: number; size_vram: number }[];
  selected: string;
  default: string;
}

export interface Highlight {
  ids: Set<string>;
  origin: string | null;
  tone: "loss" | "compromise" | "finding";
}
