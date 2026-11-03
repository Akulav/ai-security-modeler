import {
  Background, BackgroundVariant, type Connection, ConnectionMode, Controls, MarkerType, MiniMap, type OnBeforeDelete, type OnConnectEnd,
  Panel, ReactFlow, useEdgesState, useNodesState, useReactFlow, useStore,
} from "@xyflow/react";
import { Download, FlaskConical, LoaderCircle, Orbit, Radar, ScanSearch, Upload, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import AnalysisPanel, { type LogEntry } from "./components/AnalysisPanel";
import AppGroupNode, { type AppGroupFlowNode } from "./components/AppGroupNode";
import DropMenu from "./components/DropMenu";
import EdgePanel from "./components/EdgePanel";
import EntityNode, { type EntityFlowNode } from "./components/EntityNode";
import { SetupProgress } from "./components/ModelManager";
import { draftForType, type NodeDraft } from "./components/NodeFields";
import PropertiesPanel, { type BlastMode } from "./components/PropertiesPanel";
import RelationEdge, { type RelationFlowEdge } from "./components/RelationEdge";
import RelationPicker from "./components/RelationPicker";
import Sidebar, { DRAG_MIME } from "./components/Sidebar";
import { appPosition, autoLayout, GROUP_WIDTH, groupHeight, type LayoutMode, NODE_HEIGHT, NODE_WIDTH } from "./layout";
import type {
  AnalysisEvent, AnalysisReport, BlastRadius, Catalog, DropMenuItem, Graph, GraphEdge, GraphNode, Highlight, LlmStatus,
} from "./types";
import { CATEGORY_COLORS, categoryOf, RELATION_COLORS, typeLabel } from "./visuals";

type FlowNode = EntityFlowNode | AppGroupFlowNode;

const nodeTypes = { entity: EntityNode, appGroup: AppGroupNode };
const edgeTypes = { relation: RelationEdge };

const errorText = (error: unknown) => (error instanceof Error ? error.message : "Something went wrong");

// From this many links, lines are drawn faintly until hovered and hovering focuses a node.
const DENSE_EDGES = 40;
const FAR_ZOOM = 0.6;
const MAX_NAME_SCALE = 1.75;

/** Names grow as the canvas zooms out, so a big graph stays readable when seen whole. */
function ZoomScale() {
  // Quarter steps, so text only reflows now and then while zooming.
  const scale = useStore((state) => {
    const zoom = state.transform[2];
    return zoom >= FAR_ZOOM ? 1 : Math.min(MAX_NAME_SCALE, Math.round((FAR_ZOOM / zoom) * 4) / 4);
  });
  const root = useStore((state) => state.domNode);
  useEffect(() => {
    root?.style.setProperty("--name-scale", String(scale));
    root?.classList.toggle("far", scale > 1);
  }, [root, scale]);
  return null;
}

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [startupError, setStartupError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [radius, setRadius] = useState<BlastRadius | null>(null);
  const [blastMode, setBlastMode] = useState<BlastMode>("loss");
  const [pending, setPending] = useState<{ source: string; target: string } | null>(null);
  const [dropMenu, setDropMenu] = useState<{ sourceId: string; x: number; y: number } | null>(null);
  const [justCreated, setJustCreated] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string; tone: "error" | "info" } | null>(null);
  const [hibpConfigured, setHibpConfigured] = useState(false);
  const [checking, setChecking] = useState<Set<string>>(new Set());
  const [advising, setAdvising] = useState<Set<string>>(new Set());

  const [showAnalysis, setShowAnalysis] = useState(false);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [webSearch, setWebSearch] = useState(true);
  const [focus, setFocus] = useState<{ title: string; ids: string[] } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<RelationFlowEdge>([]);
  const { screenToFlowPosition, flowToScreenPosition, fitView, getNode } = useReactFlow<FlowNode, RelationFlowEdge>();
  const canvas = useRef<HTMLDivElement>(null);

  const notify = useCallback((text: string, tone: "error" | "info" = "error") => setToast({ text, tone }), []);
  const fail = useCallback((error: unknown) => notify(errorText(error)), [notify]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const refreshLlm = useCallback(async () => {
    const result = await api.llmStatus();
    setLlm(result);
    return result;
  }, []);

  // Quick while a download is running, so the progress bar moves.
  const llmBusy = llm === null || llm.busy;
  useEffect(() => {
    const timer = setInterval(() => refreshLlm().catch(() => undefined), llmBusy ? 1500 : 15000);
    return () => clearInterval(timer);
  }, [llmBusy, refreshLlm]);

  const llmAction = (action: () => Promise<unknown>) =>
    action().catch(fail).finally(() => refreshLlm().catch(() => undefined));

  useEffect(() => {
    Promise.all([api.catalog(), api.graph()])
      .then(([loadedCatalog, loadedGraph]) => {
        setCatalog(loadedCatalog);
        setGraph(loadedGraph);
        setTimeout(() => fitView({ padding: 0.15 }), 60);
      })
      .catch((error) => setStartupError(errorText(error)));
    api.hibpStatus().then((status) => setHibpConfigured(status.configured)).catch(() => undefined);
    api.latestReport().then(setReport).catch(() => undefined);
    refreshLlm().catch(() => undefined);
  }, [fitView, refreshLlm]);

  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge = graph.edges.find((edge) => edge.id === selectedEdgeId) ?? null;

  useEffect(() => {
    if (!selectedNodeId) {
      setRadius(null);
      return;
    }
    let current = true;
    api.blastRadius(selectedNodeId).then((result) => current && setRadius(result)).catch(() => undefined);
    return () => {
      current = false;
    };
  }, [selectedNodeId, graph.edges]);

  const addApp = useCallback(
    async (groupId: string, name: string) => {
      try {
        await api.createNode({ type: "application", name, parent_id: groupId });
        setGraph(await api.graph());
      } catch (error) {
        fail(error);
      }
    },
    [fail],
  );

  const highlight = useMemo<Highlight | null>(() => {
    if (focus) return { ids: new Set(focus.ids), origin: null, tone: "finding" };
    if (selectedNodeId && radius?.node_id === selectedNodeId && radius[blastMode].length > 0) {
      return { ids: new Set(radius[blastMode]), origin: selectedNodeId, tone: blastMode };
    }
    return null;
  }, [focus, selectedNodeId, radius, blastMode]);

  const dense = graph.edges.length >= DENSE_EDGES;
  // On a busy canvas, hovering a node shows just it and what it links to. A highlight takes precedence.
  const hoverFocus = useMemo(() => {
    if (!dense || !hovered || highlight) return null;
    const core = new Set([hovered, ...graph.nodes.filter((node) => node.parent_id === hovered).map((node) => node.id)]);
    const near = new Set(core);
    for (const edge of graph.edges) {
      if (core.has(edge.source_id)) near.add(edge.target_id);
      if (core.has(edge.target_id)) near.add(edge.source_id);
    }
    // An app's Apps node stays visible around it.
    for (const node of graph.nodes) if (node.parent_id && near.has(node.id)) near.add(node.parent_id);
    return { core, near };
  }, [dense, hovered, highlight, graph]);

  // Brings nodes into view when any is off-screen, such as behind a panel that just opened.
  const reveal = (ids: string[]) => {
    const bounds = canvas.current?.getBoundingClientRect();
    if (!bounds) return;
    const nodes = ids.map((id) => getNode(id)).filter((node) => node !== undefined);
    const hidden = nodes.some((node) => {
      const topLeft = flowToScreenPosition(node.position);
      const bottomRight = flowToScreenPosition({
        x: node.position.x + (node.measured?.width ?? NODE_WIDTH),
        y: node.position.y + (node.measured?.height ?? NODE_HEIGHT),
      });
      return topLeft.x < bounds.left || topLeft.y < bounds.top || bottomRight.x > bounds.right || bottomRight.y > bounds.bottom;
    });
    if (hidden) fitView({ nodes: nodes.map(({ id }) => ({ id })), padding: 0.2, maxZoom: 1, duration: 400 });
  };

  useEffect(() => {
    if (!selectedNodeId) return;
    const parent = graph.nodes.find((node) => node.id === selectedNodeId)?.parent_id;
    const timer = setTimeout(() => reveal([parent ?? selectedNodeId]), 80);
    return () => clearTimeout(timer);
    // Only when the selection changes; editing a node shouldn't move the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeId]);

  const highlightKey = highlight ? [highlight.origin, ...highlight.ids].join() : "";
  useEffect(() => {
    if (!highlightKey) return;
    const timer = setTimeout(() => {
      // An app is positioned relative to its Apps node, so the node stands in for it.
      reveal(highlightKey.split(",").map((id) => graph.nodes.find((n) => n.id === id)?.parent_id ?? id));
    }, 80);
    return () => clearTimeout(timer);
    // Positions are read when the highlight changes; moving a node shouldn't move the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightKey]);

  useEffect(() => {
    if (!catalog) return;
    setFlowNodes((previous) => {
      const byId = new Map(previous.map((node) => [node.id, node]));
      const appsIn = (groupId: string) =>
        graph.nodes.filter((n) => n.parent_id === groupId).sort((a, b) => a.name.localeCompare(b.name));
      const color = (node: GraphNode) => CATEGORY_COLORS[categoryOf(catalog, node.type)];
      // React Flow needs a parent listed before the nodes inside it.
      const groups = graph.nodes.filter((node) => node.type === "app_group");
      const others = graph.nodes.filter((node) => node.type !== "app_group");
      return [
        ...groups.map((node): FlowNode => ({
          ...(byId.get(node.id) as AppGroupFlowNode | undefined),
          id: node.id,
          type: "appGroup",
          position: { x: node.pos_x, y: node.pos_y },
          style: { width: GROUP_WIDTH, height: groupHeight(appsIn(node.id).length) },
          data: {
            node,
            color: color(node),
            dimmed: Boolean(highlight) || Boolean(hoverFocus && !hoverFocus.near.has(node.id)),
            autoFocus: justCreated === node.id,
            onAddApp: addApp,
          },
        })),
        ...others.map((node): FlowNode => ({
          ...(byId.get(node.id) as EntityFlowNode | undefined),
          id: node.id,
          type: "entity",
          position: node.parent_id
            ? appPosition(appsIn(node.parent_id).findIndex((app) => app.id === node.id))
            : { x: node.pos_x, y: node.pos_y },
          ...(node.parent_id ? { parentId: node.parent_id, extent: "parent" as const, draggable: false } : {}),
          data: {
            node,
            color: color(node),
            label: typeLabel(catalog, node.type),
            osLabel: node.os ? catalog.operating_systems[node.os] : null,
            hasOsField: catalog.fields[node.type]?.includes("os") ?? false,
            hasEncryption: catalog.fields[node.type]?.includes("encryption") ?? false,
            defenses: (node.defenses ?? []).map((id) => catalog.defenses[id] ?? id),
            highlight: !highlight
              ? hoverFocus && !hoverFocus.near.has(node.id) ? "fade" : null
              : highlight.origin === node.id
                ? "origin"
                : highlight.ids.has(node.id)
                  ? highlight.tone
                  : "dim",
          },
        })),
      ];
    });
  }, [catalog, graph.nodes, highlight, hoverFocus, justCreated, addApp, setFlowNodes]);

  useEffect(() => {
    if (!catalog) return;
    const relations = new Map(catalog.relations.map((relation) => [relation.id, relation]));
    const lit = highlight && new Set([...highlight.ids, ...(highlight.origin ? [highlight.origin] : [])]);
    const parents = new Map(graph.nodes.map((node) => [node.id, node.parent_id]));
    const groups = new Set(graph.nodes.filter((node) => node.type === "app_group").map((node) => node.id));
    // An Apps node reads as growing out of its device, so it's drawn device first.
    const ends = (edge: GraphEdge) =>
      groups.has(edge.source_id) ? [edge.target_id, edge.source_id] : [edge.source_id, edge.target_id];
    // Lines between the same two nodes, so each can take its own lane instead of overlapping.
    const between = new Map<string, string[]>();
    for (const edge of graph.edges) {
      if (parents.get(edge.source_id) === edge.target_id) continue;
      const key = ends(edge).sort().join("|");
      between.set(key, [...(between.get(key) ?? []), edge.id]);
    }
    const laneOf = (edge: GraphEdge) => {
      const [source, target] = ends(edge);
      const shared = between.get([source, target].sort().join("|")) ?? [];
      if (shared.length < 2) return undefined;
      const lane = shared.indexOf(edge.id) - (shared.length - 1) / 2;
      // Bends are measured from the source, so a line drawn the other way bends the other way.
      return source < target ? lane : -lane;
    };
    setFlowEdges((previous) => {
      const byId = new Map(previous.map((edge) => [edge.id, edge]));
      const built = graph.edges.map((edge) => {
        const relation = relations.get(edge.relation);
        const color = RELATION_COLORS[relation?.category ?? "other"];
        const [source, target] = ends(edge);
        const touched = Boolean(hoverFocus && (hoverFocus.core.has(edge.source_id) || hoverFocus.core.has(edge.target_id)));
        const isLit = Boolean(lit && lit.has(edge.source_id) && lit.has(edge.target_id)) || touched;
        return {
          ...byId.get(edge.id),
          id: edge.id,
          type: "relation" as const,
          source,
          target,
          // Being inside its Apps node already says this.
          hidden: parents.get(edge.source_id) === edge.target_id,
          markerEnd: groups.has(edge.source_id) ? undefined : { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          data: {
            label: relation?.label ?? edge.relation,
            color,
            lossMode: edge.loss_mode ?? relation?.loss ?? "required",
            dimmed: Boolean((lit && !isLit) || (hoverFocus && !touched)),
            lit: isLit,
            quiet: dense,
            lane: laneOf(edge),
          },
        };
      });
      // Later lines draw on top, so lit ones aren't buried under faint ones.
      return [...built.filter((edge) => !edge.data.lit), ...built.filter((edge) => edge.data.lit)];
    });
  }, [catalog, graph.edges, graph.nodes, highlight, hoverFocus, dense, setFlowEdges]);

  const replaceNode = useCallback(
    (updated: GraphNode) =>
      setGraph((g) => ({ ...g, nodes: g.nodes.map((node) => (node.id === updated.id ? updated : node)) })),
    [],
  );

  const select = useCallback((nodeId: string | null, edgeId: string | null = null) => {
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(edgeId);
    setFocus(null);
    if (nodeId || edgeId) setShowAnalysis(false);
  }, []);

  const withFlag = (setter: typeof setChecking, id: string, on: boolean) =>
    setter((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const requestAdvice = useCallback(
    async (nodeId: string) => {
      const status = await refreshLlm().catch(() => null);
      if (!status?.available || !status.models.some((m) => m.name === status.selected)) return;
      withFlag(setAdvising, nodeId, true);
      try {
        replaceNode(await api.breachAdvice(nodeId, status.selected));
      } catch {
        // The built-in advice stays in place, so there's nothing the user must act on.
      } finally {
        withFlag(setAdvising, nodeId, false);
      }
    },
    [refreshLlm, replaceNode],
  );

  const checkNode = useCallback(
    async (nodeId: string): Promise<GraphNode | null> => {
      withFlag(setChecking, nodeId, true);
      try {
        const updated = await api.checkBreaches(nodeId);
        replaceNode(updated);
        if (updated.breaches?.length) void requestAdvice(nodeId);
        return updated;
      } catch (error) {
        fail(error);
        return null;
      } finally {
        withFlag(setChecking, nodeId, false);
      }
    },
    [fail, replaceNode, requestAdvice],
  );

  // Saving an address can connect an email node to its accounts on the backend.
  const showEmailLinks = async () => {
    const latest = await api.graph();
    const added = latest.edges.length - graph.edges.length;
    setGraph(latest);
    if (added > 0) notify(`Connected ${added} account${added === 1 ? "" : "s"} by email address.`, "info");
  };

  const createNode = async (draft: NodeDraft, position?: { x: number; y: number }, selectAfter = false) => {
    const bounds = canvas.current?.getBoundingClientRect();
    const place =
      position ??
      screenToFlowPosition({
        x: (bounds?.left ?? 0) + (bounds?.width ?? 800) / 2 - 110 + Math.random() * 60,
        y: (bounds?.top ?? 0) + (bounds?.height ?? 600) / 2 - 35 + Math.random() * 60,
      });
    try {
      const node = await api.createNode({ ...draft, name: draft.name.trim(), pos_x: place.x, pos_y: place.y });
      setGraph((g) => ({ ...g, nodes: [...g.nodes, node] }));
      if (node.email) await showEmailLinks();
      if (selectAfter) {
        select(node.id);
        setJustCreated(node.id);
      }
      if (node.email && hibpConfigured) void checkNode(node.id);
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  };

  const saveNode = async (draft: NodeDraft) => {
    if (!selectedNode) return;
    try {
      const updated = await api.updateNode(selectedNode.id, { ...draft, name: draft.name.trim() });
      const emailChanged = updated.email !== selectedNode.email;
      replaceNode(updated);
      if (emailChanged && updated.email) await showEmailLinks();
      if (emailChanged && updated.email && hibpConfigured) void checkNode(updated.id);
    } catch (error) {
      fail(error);
    }
  };

  const deleteNode = async (node: GraphNode) => {
    const what = node.type === "app_group" ? "and every app in it" : "and all of its relationships";
    if (!window.confirm(`Delete "${node.name}" ${what}?`)) return;
    try {
      await api.deleteNode(node.id);
      setGraph(await api.graph());
      select(null);
    } catch (error) {
      fail(error);
    }
  };

  const deleteEdge = async (edge: GraphEdge) => {
    try {
      await api.deleteEdge(edge.id);
      setGraph((g) => ({ ...g, edges: g.edges.filter((e) => e.id !== edge.id) }));
      select(null);
    } catch (error) {
      fail(error);
    }
  };

  const onConnect = useCallback((connection: Connection) => {
    if (connection.source && connection.target && connection.source !== connection.target) {
      setPending({ source: connection.source, target: connection.target });
    }
  }, []);

  const onConnectEnd = useCallback<OnConnectEnd>((event, state) => {
    if (state.isValid || state.toNode || !state.fromNode) return;
    const { clientX, clientY } = "changedTouches" in event ? event.changedTouches[0] : event;
    setDropMenu({ sourceId: state.fromNode.id, x: clientX, y: clientY });
  }, []);

  const pickDropItem = async (item: DropMenuItem, source: GraphNode, x: number, y: number) => {
    setDropMenu(null);
    if (!catalog) return;
    const sameType = graph.nodes.filter((n) => n.type === item.type);
    const shared = ["location", "network"].includes(categoryOf(catalog, item.type)) && sameType.length === 1;
    // A device has one Apps node, and you usually have one router or WiFi: reuse rather than duplicate.
    const existing =
      item.type === "app_group"
        ? graph.nodes.find((n) => n.type === "app_group" && graph.edges.some((e) => e.source_id === n.id && e.target_id === source.id))
        : shared && sameType[0].id !== source.id ? sameType[0] : undefined;
    if (existing && item.type === "app_group") {
      setJustCreated(existing.id);
      reveal([existing.id]);
      return;
    }
    try {
      const position = screenToFlowPosition({ x, y: y - 30 });
      const other = existing ?? await api.createNode({
        ...draftForType(catalog, item.type, item.type === "app_group" ? `${source.name} Apps` : `New ${typeLabel(catalog, item.type)}`),
        pos_x: position.x,
        pos_y: position.y,
      });
      await api.createEdge(item.new_is === "source"
        ? { source_id: other.id, target_id: source.id, relation: item.relation }
        : { source_id: source.id, target_id: other.id, relation: item.relation });
      setGraph(await api.graph());
      if (!existing) {
        // Apps are typed straight into their node on the canvas, so it needs no side panel.
        if (item.type !== "app_group") select(other.id);
        setJustCreated(other.id);
        setTimeout(() => reveal([source.id, other.id]), 150);
      }
    } catch (error) {
      fail(error);
      setGraph(await api.graph());
    }
  };

  const pickRelation = async (relation: string, source: GraphNode, target: GraphNode) => {
    setPending(null);
    try {
      await api.createEdge({ source_id: source.id, target_id: target.id, relation });
      // Refetched because a new link can combine with an existing one.
      setGraph(await api.graph());
    } catch (error) {
      fail(error);
    }
  };

  const updateEdge = async (id: string, changes: Partial<GraphEdge>) => {
    try {
      const updated = await api.updateEdge(id, changes);
      setGraph(await api.graph());
      if (updated.id !== id) select(null, updated.id);
    } catch (error) {
      fail(error);
    }
  };

  const savePositions = useCallback(
    (moved: { id: string; position: { x: number; y: number } }[]) => {
      setGraph((g) => {
        const positions = new Map(moved.map((node) => [node.id, node.position]));
        return {
          ...g,
          nodes: g.nodes.map((node) => {
            const position = positions.get(node.id);
            return position ? { ...node, pos_x: position.x, pos_y: position.y } : node;
          }),
        };
      });
      Promise.all(
        moved.map((node) => api.updateNode(node.id, { pos_x: node.position.x, pos_y: node.position.y })),
      ).catch(fail);
    },
    [fail],
  );

  const onDrop = (event: React.DragEvent) => {
    const type = event.dataTransfer.getData(DRAG_MIME);
    if (!type || !catalog) return;
    event.preventDefault();
    const position = screenToFlowPosition({ x: event.clientX - 110, y: event.clientY - 35 });
    void createNode(draftForType(catalog, type, `New ${typeLabel(catalog, type)}`), position, true);
  };

  // Keyboard deletes (Delete key) go through here so the database stays in sync.
  const onBeforeDelete: OnBeforeDelete<FlowNode, RelationFlowEdge> = async ({ nodes, edges }) => {
    if (nodes.length > 0 && !window.confirm(`Delete ${nodes.length} node(s) and their relationships?`)) return false;
    try {
      // Deleting a node takes its edges with it, so those may already be gone.
      await Promise.all(nodes.map((n) => api.deleteNode(n.id).catch(() => undefined)));
      await Promise.all(edges.map((e) => api.deleteEdge(e.id).catch(() => undefined)));
      setGraph(await api.graph());
    } catch (error) {
      fail(error);
      return false;
    }
    select(null);
    return false;
  };

  const arrange = ({ nodes, edges }: Graph, mode: LayoutMode = "star") => {
    const positions = autoLayout(nodes, edges, mode);
    savePositions(Object.entries(positions).map(([id, position]) => ({ id, position })));
    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 60);
  };

  const loadSample = async () => {
    try {
      const sample = await api.loadSample();
      setGraph(sample);
      arrange(sample);
    } catch (error) {
      fail(error);
    }
  };

  const exportGraph = async () => {
    try {
      const blob = new Blob([JSON.stringify(await api.exportGraph(), null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "security-model.json";
      link.click();
      URL.revokeObjectURL(link.href);
      notify("Exported. The file includes your email and IP addresses, so store it safely.", "info");
    } catch (error) {
      fail(error);
    }
  };

  const importGraph = async (file: File) => {
    try {
      const data = JSON.parse(await file.text());
      if (graph.nodes.length > 0 && !window.confirm(`Replace all ${graph.nodes.length} current nodes with this file?`)) return;
      setGraph(await api.importGraph(data));
      select(null);
      setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 60);
    } catch (error) {
      notify(error instanceof SyntaxError ? "That file isn't valid JSON." : errorText(error));
    }
  };

  const checkAll = async () => {
    const targets = graph.nodes.filter((node) => node.email);
    if (targets.length === 0) {
      notify("No nodes have an email address yet.", "info");
      return;
    }
    // One at a time: HIBP rate-limits per key, and the backend waits out any 429.
    let breached = 0;
    let completed = 0;
    for (const node of targets) {
      const result = await checkNode(node.id);
      if (result) completed += 1;
      if (result?.breaches?.length) breached += 1;
    }
    if (completed > 0) {
      notify(`Checked ${completed} of ${targets.length} addresses. ${breached} breached.`, breached ? "error" : "info");
    }
  };

  const applyAnalysisEvent = useCallback((event: AnalysisEvent) => {
    const add = (entry: LogEntry) => setLog((current) => [...current, entry]);
    switch (event.type) {
      case "findings":
        setReport({ findings: event.findings, summary: event.summary, narrative: null, llm_error: null });
        break;
      case "status":
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
        add({ tone: "error", text: event.message });
        break;
      case "narrative":
        setReport((current) => current && { ...current, narrative: event.report, model: event.model });
        break;
    }
  }, []);

  const runAnalysis = async () => {
    setRunning(true);
    setLog([]);
    setFocus(null);
    setShowAnalysis(true);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    abort.current = new AbortController();
    try {
      const status = await refreshLlm().catch(() => null);
      await api.runAnalysis(
        { model: status?.selected, web_search: webSearch },
        applyAnalysisEvent,
        abort.current.signal,
      );
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setLog((current) => [...current, { tone: "info", text: "Stopped" }]);
      } else {
        setLog((current) => [...current, {
          tone: "error",
          text: error instanceof ApiError ? error.message : "The analysis stopped unexpectedly.",
        }]);
      }
    } finally {
      setRunning(false);
    }
  };

  if (startupError) {
    return <div className="startup"><h1>Can't load the app</h1><p>{startupError}</p></div>;
  }
  if (!catalog) return <div className="startup"><p>Loading</p></div>;

  const dropSource = dropMenu && graph.nodes.find((node) => node.id === dropMenu.sourceId);
  const pendingSource = pending &&graph.nodes.find((node) => node.id === pending.source);
  const pendingTarget = pending && graph.nodes.find((node) => node.id === pending.target);
  const breachedCount = graph.nodes.filter((node) => node.breaches?.length).length;
  const panelOpen = showAnalysis || selectedNode || selectedEdge;

  return (
    <div className={`app${panelOpen ? " with-panel" : ""}`}>
      <Sidebar catalog={catalog} onCreate={(draft) => createNode(draft)} />

      <main
        className="canvas"
        ref={canvas}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        onDrop={onDrop}
      >
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onConnectEnd={onConnectEnd}
          connectionMode={ConnectionMode.Loose}
          onBeforeDelete={onBeforeDelete}
          deleteKeyCode="Delete"
          onNodeClick={(_, node) => select(node.id)}
          onNodeMouseEnter={(_, node) => setHovered(node.id)}
          onNodeMouseLeave={() => setHovered(null)}
          onEdgeClick={(_, edge) => select(null, edge.id)}
          onPaneClick={() => {
            setSelectedNodeId(null);
            setSelectedEdgeId(null);
            setFocus(null);
          }}
          onNodeDragStop={(_, __, moved) => savePositions(moved)}
          colorMode="dark"
          minZoom={0.15}
          proOptions={{ hideAttribution: true }}
        >
          <ZoomScale />
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="#26344a" />
          <Controls position="bottom-right" />
          <MiniMap
            position="top-right"
            pannable
            zoomable
            maskColor="rgba(6, 10, 18, 0.7)"
            nodeColor={(node) =>
              (node.data as { node: GraphNode }).node.breaches?.length
                ? "#ef4444"
                : (node.data as { color: string }).color
            }
          />

          <Panel position="top-left" className="toolbar glass">
            <button
              className="btn primary"
              // Runs can take many minutes, so reopening never restarts one. "Run analysis" is in the panel.
              onClick={() => (running || report ? setShowAnalysis(true) : runAnalysis())}
            >
              {running ? <LoaderCircle size={15} className="spin" /> : <ScanSearch size={15} />}
              {running ? "Analyzing" : "Analyze Infrastructure"}
            </button>
            <button
              className="btn"
              onClick={checkAll}
              disabled={!hibpConfigured || checking.size > 0}
              title={hibpConfigured ? "Check every email address against HaveIBeenPwned" : "Add HIBP_API_KEY to .env to enable"}
            >
              <Radar size={15} /> Check breaches
              {breachedCount > 0 && <span className="count-badge">{breachedCount}</span>}
            </button>
            <span className="divider" />
            <button className="icon-btn" onClick={() => arrange(graph)} title="Arrange as stars around the busiest nodes" aria-label="Arrange as stars" disabled={!graph.nodes.length}>
              <Orbit size={16} />
            </button>
            <button className="icon-btn" onClick={() => arrange(graph, "flow")} title="Arrange left to right" aria-label="Arrange left to right" disabled={!graph.nodes.length}>
              <Workflow size={16} />
            </button>
            <button className="icon-btn" onClick={exportGraph} title="Export JSON" aria-label="Export JSON">
              <Download size={16} />
            </button>
            <button className="icon-btn" onClick={() => fileInput.current?.click()} title="Import JSON" aria-label="Import JSON">
              <Upload size={16} />
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importGraph(file);
                event.target.value = "";
              }}
            />
          </Panel>

          {!showAnalysis && llm && (llm.busy || llm.phase === "error") && (
            <Panel position="top-center" className="setup-toast glass">
              <SetupProgress
                llm={llm}
                onCancel={() => llmAction(api.cancelPull)}
                onRetry={() => llmAction(api.retryLlm)}
              />
            </Panel>
          )}

          <Panel position="bottom-left" className="legend glass">
            <span><i className="line solid" /> required</span>
            <span><i className="line dashed" /> alternative / backup</span>
            <span><i className="line dotted" /> takeover only</span>
          </Panel>
        </ReactFlow>

        {graph.nodes.length === 0 && (
          <div className="empty-state">
            <h2>Map your digital life</h2>
            <p>Drag a device or account from the left, then pull a line from one node's edge to another to connect them.</p>
            <button className="btn" onClick={loadSample}><FlaskConical size={15} /> Load sample graph</button>
          </div>
        )}
      </main>

      {/* Always mounted, so closing the panel doesn't lose an answer in progress. */}
      {catalog && (
        <AnalysisPanel
          visible={showAnalysis}
          graphVersion={graph}
          report={report}
          running={running}
          log={log}
          llm={llm}
          webSearch={webSearch}
          nodes={graph.nodes}
          activeTitle={focus?.title ?? null}
          onSelectModel={(name) => llmAction(() => api.selectModel(name))}
          onPullModel={(name) => llmAction(() => api.pullModel(name))}
          onDeleteModel={(name) => {
            if (window.confirm(`Delete ${name} from disk? You'd need to download it again to use it.`)) {
              llmAction(() => api.deleteModel(name));
            }
          }}
          onCancelPull={() => llmAction(api.cancelPull)}
          onRetryLlm={() => llmAction(api.retryLlm)}
          onLoadLlm={() => llmAction(api.loadLlm)}
          onUnloadLlm={() => llmAction(api.unloadLlm)}
          onWebSearch={setWebSearch}
          onRun={runAnalysis}
          onStop={() => abort.current?.abort()}
          onFinishResearch={() => api.finishResearch().catch(fail)}
          onFocus={(title, ids) => setFocus(focus?.title === title ? null : { title, ids })}
          onClose={() => {
            setShowAnalysis(false);
            setFocus(null);
          }}
        />
      )}
      {!showAnalysis && selectedNode && (
        <PropertiesPanel
          catalog={catalog}
          node={selectedNode}
          nodes={graph.nodes}
          edges={graph.edges}
          radius={radius?.node_id === selectedNode.id ? radius : null}
          blastMode={blastMode}
          checking={checking.has(selectedNode.id)}
          advising={advising.has(selectedNode.id)}
          hibpConfigured={hibpConfigured}
          focusName={justCreated === selectedNode.id && selectedNode.type !== "app_group"}
          onAddApp={addApp}
          onBlastMode={setBlastMode}
          onSave={saveNode}
          onDelete={() => deleteNode(selectedNode)}
          onCheck={() => checkNode(selectedNode.id)}
          onSelect={(id) => select(id)}
          onClose={() => select(null)}
        />
      )}
      {!showAnalysis && selectedEdge && (
        <EdgePanel
          catalog={catalog}
          edge={selectedEdge}
          source={graph.nodes.find((node) => node.id === selectedEdge.source_id)}
          target={graph.nodes.find((node) => node.id === selectedEdge.target_id)}
          onChange={(changes) => updateEdge(selectedEdge.id, changes)}
          onDelete={() => deleteEdge(selectedEdge)}
          onClose={() => select(null)}
        />
      )}

      {dropMenu && dropSource && catalog.drop_menu[dropSource.type]?.length > 0 && (
        <DropMenu
          catalog={catalog}
          source={dropSource}
          x={dropMenu.x}
          y={dropMenu.y}
          onPick={(item) => pickDropItem(item, dropSource, dropMenu.x, dropMenu.y)}
          onCancel={() => setDropMenu(null)}
        />
      )}

      {pendingSource && pendingTarget && (
        <RelationPicker
          catalog={catalog}
          source={pendingSource}
          target={pendingTarget}
          onPick={pickRelation}
          onCancel={() => setPending(null)}
        />
      )}

      {toast && <div className={`toast ${toast.tone}`} role="status">{toast.text}</div>}
    </div>
  );
}
