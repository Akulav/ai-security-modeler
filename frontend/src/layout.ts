import dagre from "@dagrejs/dagre";
import type { GraphEdge, GraphNode } from "./types";

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 58;
const STRIP_HEIGHT = 25;
const TAG_ROW_HEIGHT = 22;
const TAGS_PER_ROW = 3;
export const MAX_NODE_TAGS = 5;

export const GROUP_WIDTH = 240;
const GROUP_HEADER = 34;
const GROUP_FOOTER = 42;
const APP_ROW = 44;
const APP_INSET = 10;

export type LayoutMode = "star" | "flow";
type Point = { x: number; y: number };
type Size = { width: number; height: number };

export function groupHeight(appCount: number): number {
  return GROUP_HEADER + appCount * APP_ROW + GROUP_FOOTER;
}

/** Where an app sits inside its Apps node, relative to the node. */
export function appPosition(index: number): Point {
  return { x: APP_INSET, y: GROUP_HEADER + index * APP_ROW };
}

function sizeOf(node: GraphNode, nodes: GraphNode[]): Size {
  if (node.type === "app_group") {
    return { width: GROUP_WIDTH, height: groupHeight(nodes.filter((n) => n.parent_id === node.id).length) };
  }
  const tags = Math.min(node.defenses?.length ?? 0, MAX_NODE_TAGS + 1);
  return {
    width: NODE_WIDTH,
    height: NODE_HEIGHT
      + (node.os || node.encryption !== "unknown" ? STRIP_HEIGHT : 0)
      + Math.ceil(tags / TAGS_PER_ROW) * TAG_ROW_HEIGHT,
  };
}

/** Links between top-level nodes: an app's links count as its Apps node's, since it moves with it. */
function topLevelLinks(nodes: GraphNode[], edges: GraphEdge[]): [string, string][] {
  const parents = new Map(nodes.map((node) => [node.id, node.parent_id ?? node.id]));
  const groups = new Set(nodes.filter((node) => node.type === "app_group").map((node) => node.id));
  const links: [string, string][] = [];
  for (const edge of edges) {
    const source = parents.get(edge.source_id);
    const target = parents.get(edge.target_id);
    if (!source || !target || source === target) continue;
    // Matches how the canvas draws it: the device comes first, then its Apps node.
    links.push(groups.has(edge.source_id) ? [target, source] : [source, target]);
  }
  return links;
}

function flowLayout(placed: GraphNode[], nodes: GraphNode[], links: [string, string][]): Record<string, Point> {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 170 });
  graph.setDefaultEdgeLabel(() => ({}));
  placed.forEach((node) => graph.setNode(node.id, sizeOf(node, nodes)));
  links.forEach(([source, target]) => graph.setEdge(source, target));
  dagre.layout(graph);
  return Object.fromEntries(
    placed.map((node) => {
      const { x, y } = graph.node(node.id);
      const { width, height } = sizeOf(node, nodes);
      return [node.id, { x: x - width / 2, y: y - height / 2 }];
    }),
  );
}

const BRANCH = 250;
const SLOT = 150; // Room each node needs around its parent.
const CONE_BASE = 0.7; // Radians a non-root node fans its children across.
const CONE_PER_CHILD = 0.45;
const MAX_CONE = Math.PI * 1.5;
const WIDE_FAN = 12; // At this many children, they alternate between two rings to fit more.
const STAGGER = 130;
const ELLIPSE = 1.35; // Nodes are wider than tall, so rings are too.
const MARGIN = 26;
const COMPONENT_GAP = 170;
const ROW_WIDTH = 3200;

interface Tree {
  root: string;
  children: Map<string, string[]>;
  depth: Map<string, number>;
}

function spanningTree(start: string, neighbours: Map<string, Set<string>>, order: (a: string, b: string) => number): Tree {
  // Breadth-first, so each node hangs off the closest hub.
  const children = new Map<string, string[]>([[start, []]]);
  const depth = new Map([[start, 0]]);
  const queue = [start];
  for (let i = 0; i < queue.length; i++) {
    const current = queue[i];
    const next = [...(neighbours.get(current) ?? [])]
      .filter((id) => !depth.has(id))
      .sort((a, b) => (neighbours.get(b)!.size - neighbours.get(a)!.size) || order(a, b));
    for (const id of next) {
      depth.set(id, depth.get(current)! + 1);
      children.set(id, []);
      children.get(current)!.push(id);
      queue.push(id);
    }
  }
  // Similar types sit together around their hub.
  children.forEach((list) => list.sort(order));
  return { root: start, children, depth };
}

const RELAX_ROUNDS = 200;
const RELAX_LENGTH = 230; // Distance one link should span, before allowing for busy ends.
const HUB_DEGREE = 6; // Links beyond this lengthen a node's lines, so its ring has room.

/**
 * Re-places a group so every pair of nodes sits about as far apart as the links between them
 * (stress majorization), counting every link rather than just the tree's. Without it, a node linked
 * to several hubs stays in whichever star it was hung from, and its other lines cross the canvas.
 */
function relax(positions: Map<string, Point>, links: [string, string][]) {
  const ids = [...positions.keys()];
  const n = ids.length;
  const index = new Map(ids.map((id, i) => [id, i]));
  const adjacent = ids.map(() => new Set<number>());
  for (const [a, b] of links) {
    if (!index.has(a) || !index.has(b)) continue;
    adjacent[index.get(a)!].add(index.get(b)!);
    adjacent[index.get(b)!].add(index.get(a)!);
  }
  // A tree is already drawn well as stars, so only groups with extra links are re-placed.
  const linkCount = adjacent.reduce((sum, set) => sum + set.size, 0) / 2;
  if (n < 4 || linkCount <= n - 1) return;

  const span = (i: number, j: number) =>
    RELAX_LENGTH * Math.max(1, Math.sqrt(Math.max(adjacent[i].size, adjacent[j].size) / HUB_DEGREE));
  // Shortest weighted distances between all pairs.
  const target = ids.map((_, source) => {
    const distance = new Array(n).fill(Infinity);
    const done = new Array(n).fill(false);
    distance[source] = 0;
    for (let round = 0; round < n; round++) {
      let current = -1;
      for (let i = 0; i < n; i++) if (!done[i] && (current < 0 || distance[i] < distance[current])) current = i;
      if (current < 0 || distance[current] === Infinity) break;
      done[current] = true;
      adjacent[current].forEach((next) => {
        distance[next] = Math.min(distance[next], distance[current] + span(current, next));
      });
    }
    return distance;
  });

  // Worked in a space squashed sideways, since nodes are wider than tall.
  const xs = ids.map((id) => positions.get(id)!.x / ELLIPSE);
  const ys = ids.map((id) => positions.get(id)!.y);
  for (let round = 0; round < RELAX_ROUNDS; round++) {
    for (let i = 0; i < n; i++) {
      let [sumX, sumY, sumW] = [0, 0, 0];
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const want = target[i][j];
        const w = 1 / (want * want);
        const dx = xs[i] - xs[j];
        const dy = ys[i] - ys[j];
        const d = Math.hypot(dx, dy) || 1;
        sumX += w * (xs[j] + (want * dx) / d);
        sumY += w * (ys[j] + (want * dy) / d);
        sumW += w;
      }
      xs[i] = sumX / sumW;
      ys[i] = sumY / sumW;
    }
  }
  ids.forEach((id, i) => positions.set(id, { x: xs[i] * ELLIPSE, y: ys[i] }));
}

/** Lays one connected group out as branching stars from its busiest node. Positions are centres. */
function radialPositions(tree: Tree, sizes: Map<string, Size>, links: [string, string][]): Map<string, Point> {
  const weight = new Map<string, number>();
  const weigh = (id: string): number => {
    const total = tree.children.get(id)!.reduce((sum, child) => sum + weigh(child), 0);
    weight.set(id, Math.max(1, total));
    return weight.get(id)!;
  };
  weigh(tree.root);

  const positions = new Map<string, Point>();
  // Children fan out around the direction their parent grew in, sized by how much hangs off each.
  const place = (id: string, at: Point, heading: number, isRoot: boolean) => {
    positions.set(id, at);
    const children = tree.children.get(id)!;
    if (children.length === 0) return;
    const cone = isRoot ? Math.PI * 2 : Math.min(MAX_CONE, CONE_BASE + children.length * CONE_PER_CHILD);
    const wide = children.length >= WIDE_FAN;
    const distance = Math.max(BRANCH, (children.length * SLOT * (wide ? 0.6 : 1)) / cone);
    const total = children.reduce((sum, child) => sum + weight.get(child)!, 0);
    let cursor = heading - cone / 2;
    children.forEach((child, index) => {
      const slice = (cone * weight.get(child)!) / total;
      const angle = cursor + slice / 2;
      const r = distance + (wide && index % 2 === 1 ? STAGGER : 0);
      place(child, { x: at.x + Math.cos(angle) * r * ELLIPSE, y: at.y + Math.sin(angle) * r }, angle, false);
      cursor += slice;
    });
  };
  place(tree.root, { x: 0, y: 0 }, -Math.PI / 2, true);
  relax(positions, links);

  // Branches can still meet, so nudge apart anything touching.
  const ids = [...positions.keys()];
  for (let pass = 0; pass < 300; pass++) {
    let moved = false;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = positions.get(ids[i])!;
        const b = positions.get(ids[j])!;
        const overlapX = (sizes.get(ids[i])!.width + sizes.get(ids[j])!.width) / 2 + MARGIN - Math.abs(a.x - b.x);
        const overlapY = (sizes.get(ids[i])!.height + sizes.get(ids[j])!.height) / 2 + MARGIN - Math.abs(a.y - b.y);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        const alongX = overlapX < overlapY;
        const push = (alongX ? overlapX : overlapY) / 2;
        const sign = alongX ? Math.sign(b.x - a.x) || 1 : Math.sign(b.y - a.y) || 1;
        if (alongX) {
          a.x -= sign * push;
          b.x += sign * push;
        } else {
          a.y -= sign * push;
          b.y += sign * push;
        }
      }
    }
    if (!moved) break;
  }
  return positions;
}

function starLayout(placed: GraphNode[], nodes: GraphNode[], links: [string, string][]): Record<string, Point> {
  const neighbours = new Map(placed.map((node) => [node.id, new Set<string>()]));
  for (const [a, b] of links) {
    neighbours.get(a)?.add(b);
    neighbours.get(b)?.add(a);
  }
  const sizes = new Map(placed.map((node) => [node.id, sizeOf(node, nodes)]));
  const byId = new Map(placed.map((node) => [node.id, node]));
  const order = (a: string, b: string) => {
    const left = byId.get(a)!;
    const right = byId.get(b)!;
    return left.type.localeCompare(right.type) || left.name.localeCompare(right.name);
  };

  // Each connected group grows from its busiest node. Lone nodes are gathered at the end.
  const seen = new Set<string>();
  const groups: { positions: Map<string, Point>; left: number; top: number; width: number; height: number }[] = [];
  const hubsFirst = [...neighbours.keys()].sort((a, b) => neighbours.get(b)!.size - neighbours.get(a)!.size || order(a, b));
  for (const id of hubsFirst) {
    if (seen.has(id)) continue;
    const tree = spanningTree(id, neighbours, order);
    tree.depth.forEach((_, member) => seen.add(member));
    const positions = radialPositions(tree, sizes, links);
    let [left, top, right, bottom] = [Infinity, Infinity, -Infinity, -Infinity];
    positions.forEach((point, member) => {
      const { width, height } = sizes.get(member)!;
      left = Math.min(left, point.x - width / 2);
      right = Math.max(right, point.x + width / 2);
      top = Math.min(top, point.y - height / 2);
      bottom = Math.max(bottom, point.y + height / 2);
    });
    groups.push({ positions, left, top, width: right - left, height: bottom - top });
  }

  // Rows scale with the biggest group, so smaller groups sit beside it rather than far below.
  const rowWidth = Math.max(ROW_WIDTH, Math.max(...groups.map((group) => group.width)) * 1.9);
  const result: Record<string, Point> = {};
  let [x, y, rowHeight] = [0, 0, 0];
  for (const group of groups) {
    if (x > 0 && x + group.width > rowWidth) {
      x = 0;
      y += rowHeight + COMPONENT_GAP;
      rowHeight = 0;
    }
    group.positions.forEach((point, id) => {
      const { width, height } = sizes.get(id)!;
      result[id] = { x: x + point.x - group.left - width / 2, y: y + point.y - group.top - height / 2 };
    });
    x += group.width + COMPONENT_GAP;
    rowHeight = Math.max(rowHeight, group.height);
  }
  return result;
}

export function autoLayout(nodes: GraphNode[], edges: GraphEdge[], mode: LayoutMode = "star"): Record<string, Point> {
  const placed = nodes.filter((node) => !node.parent_id);
  const links = topLevelLinks(nodes, edges);
  return mode === "star" ? starLayout(placed, nodes, links) : flowLayout(placed, nodes, links);
}
