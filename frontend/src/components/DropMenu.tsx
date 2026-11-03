import { useEffect } from "react";
import type { Catalog, DropMenuItem, GraphNode } from "../types";
import { CATEGORY_COLORS, categoryOf, FALLBACK_ICON, NODE_ICONS } from "../visuals";

interface Props {
  catalog: Catalog;
  source: GraphNode;
  x: number;
  y: number;
  onPick: (item: DropMenuItem) => void;
  onCancel: () => void;
}

const MENU_WIDTH = 270;
const ROW_HEIGHT = 32;

/** Shown when a connection is dragged from a node and dropped on empty canvas. */
export default function DropMenu({ catalog, source, x, y, onPick, onCancel }: Props) {
  const items = catalog.drop_menu[source.type] ?? [];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const left = Math.min(x, window.innerWidth - MENU_WIDTH - 12);
  const top = Math.max(12, Math.min(y, window.innerHeight - (items.length + 1) * ROW_HEIGHT - 40));

  return (
    <div className="menu-backdrop" onMouseDown={onCancel}>
      <div className="drop-menu glass" role="menu" style={{ left, top, width: MENU_WIDTH }} onMouseDown={(e) => e.stopPropagation()}>
        <h4 title={source.name}>Add to {source.name}</h4>
        {items.map((item) => {
          const Icon = NODE_ICONS[item.type] ?? FALLBACK_ICON;
          return (
            <button key={item.label} role="menuitem" onClick={() => onPick(item)}>
              <Icon size={14} style={{ color: CATEGORY_COLORS[categoryOf(catalog, item.type)] }} />
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
