"use client";

import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { LocateFixed, Minus, Plus, RotateCcw } from "lucide-react";
import { GraphEdgeItem, GraphNodeItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type PositionedNode = GraphNodeItem & {
  x: number;
  y: number;
};

type DragState = {
  nodeId: string;
  pointerId: number;
  moved: boolean;
  lastX: number;
  lastY: number;
} | null;

const WIDTH = 1500;
const HEIGHT = 1000;

const typeStyle: Record<string, { fill: string; stroke: string; badge: string }> = {
  Project: {
    fill: "#67e8f9",
    stroke: "#0891b2",
    badge: "bg-cyan-100 border-cyan-200 text-cyan-900",
  },
  Expert: {
    fill: "#99f6e4",
    stroke: "#0f766e",
    badge: "bg-teal-100 border-teal-200 text-teal-900",
  },
  Funder: {
    fill: "#fed7aa",
    stroke: "#ea580c",
    badge: "bg-orange-100 border-orange-200 text-orange-900",
  },
  Enterprise: {
    fill: "#f0abfc",
    stroke: "#a21caf",
    badge: "bg-fuchsia-100 border-fuchsia-200 text-fuchsia-900",
  },
  Location: {
    fill: "#fbcfe8",
    stroke: "#be185d",
    badge: "bg-pink-100 border-pink-200 text-pink-900",
  },
  ResearchDirection: {
    fill: "#bfdbfe",
    stroke: "#2563eb",
    badge: "bg-blue-100 border-blue-200 text-blue-900",
  },
  ResearchTopic: {
    fill: "#fdba74",
    stroke: "#ea580c",
    badge: "bg-orange-100 border-orange-200 text-orange-900",
  },
  Skill: {
    fill: "#bbf7d0",
    stroke: "#16a34a",
    badge: "bg-green-100 border-green-200 text-green-900",
  },
  Industry: {
    fill: "#fde68a",
    stroke: "#ca8a04",
    badge: "bg-yellow-100 border-yellow-200 text-yellow-900",
  },
  Dataset: {
    fill: "#ddd6fe",
    stroke: "#7c3aed",
    badge: "bg-violet-100 border-violet-200 text-violet-900",
  },
  Product: {
    fill: "#fecaca",
    stroke: "#dc2626",
    badge: "bg-red-100 border-red-200 text-red-900",
  },
};

const fallbackStyle = {
  fill: "#e2e8f0",
  stroke: "#64748b",
  badge: "bg-slate-100 border-slate-200 text-slate-900",
};

function styleFor(type: string) {
  return typeStyle[type] ?? fallbackStyle;
}

function relationLabel(value: string) {
  return value.replace(/_/g, " ");
}

function shortLabel(value: string, max = 22) {
  return value.length > max ? `${value.slice(0, max - 3)}...` : value;
}

function nodeRadius(node: GraphNodeItem, isMainNode: boolean) {
  const length = node.label.length;
  if (isMainNode) return Math.min(58, Math.max(42, 34 + length * 0.45));
  return Math.min(48, Math.max(30, 24 + length * 0.38));
}

function wrapNodeLabel(label: string, radius: number) {
  const maxChars = Math.max(7, Math.floor(radius / 3.3));
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];

  for (const word of words) {
    const last = lines[lines.length - 1];
    if (!last) {
      lines.push(word);
      continue;
    }
    if (`${last} ${word}`.length <= maxChars) {
      lines[lines.length - 1] = `${last} ${word}`;
    } else {
      lines.push(word);
    }
  }

  const fallbackLines = words.length ? lines : [label];
  return fallbackLines.slice(0, 3).map((line, index) => {
    if (index === 2 && fallbackLines.length > 3) return `${shortLabel(line, maxChars - 1)}...`;
    return shortLabel(line, maxChars);
  });
}

function propertyPreview(value: unknown) {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return new Intl.DateTimeFormat("vi-VN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(parsed);
    }
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function countBy<T extends string>(values: T[]) {
  return values.reduce<Record<string, number>>((acc, item) => {
    acc[item] = (acc[item] ?? 0) + 1;
    return acc;
  }, {});
}

function initialLayout(nodes: GraphNodeItem[], edges: GraphEdgeItem[]) {
  const visibleNodes = nodes.slice(0, 90);
  if (visibleNodes.length === 0) return [];

  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }

  const sorted = [...visibleNodes].sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0));
  const center = sorted[0];
  const rest = sorted.slice(1);
  const outerRadius = Math.min(WIDTH, HEIGHT) * 0.42;
  const innerRadius = outerRadius * 0.58;
  const middleRadius = outerRadius * 0.78;

  const positioned = sorted.map((node, index) => {
    if (node.id === center.id) {
      return { ...node, x: WIDTH / 2, y: HEIGHT / 2 };
    }

    const restIndex = rest.findIndex((item) => item.id === node.id);
    const angle = (restIndex / Math.max(rest.length, 1)) * Math.PI * 2 - Math.PI / 2 + (restIndex % 2) * 0.08;
    const ring = restIndex % 3 === 0 ? innerRadius : restIndex % 3 === 1 ? middleRadius : outerRadius;
    return {
      ...node,
      x: WIDTH / 2 + Math.cos(angle) * ring,
      y: HEIGHT / 2 + Math.sin(angle) * ring,
    };
  });

  return relaxLayout(positioned, edges);
}

function relaxLayout(nodes: PositionedNode[], edges: GraphEdgeItem[]) {
  const indexById = new Map(nodes.map((node, index) => [node.id, index]));
  const positions = nodes.map((node, index) => ({
    ...node,
    fixed: index === 0,
    radius: nodeRadius(node, index === 0),
  }));

  const linkedEdges = edges
    .map((edge) => ({
      sourceIndex: indexById.get(edge.source),
      targetIndex: indexById.get(edge.target),
    }))
    .filter((edge): edge is { sourceIndex: number; targetIndex: number } => (
      edge.sourceIndex !== undefined && edge.targetIndex !== undefined
    ));

  for (let iteration = 0; iteration < 260; iteration += 1) {
    const alpha = 1 - iteration / 260;

    for (let i = 0; i < positions.length; i += 1) {
      for (let j = i + 1; j < positions.length; j += 1) {
        const a = positions[i];
        const b = positions[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const minimum = a.radius + b.radius + 34;

        if (distance < minimum) {
          const push = ((minimum - distance) / distance) * 0.56 * alpha;
          const offsetX = dx * push;
          const offsetY = dy * push;

          if (!a.fixed) {
            a.x -= offsetX;
            a.y -= offsetY;
          }
          if (!b.fixed) {
            b.x += offsetX;
            b.y += offsetY;
          }
        }
      }
    }

    for (const edge of linkedEdges) {
      const source = positions[edge.sourceIndex];
      const target = positions[edge.targetIndex];
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const ideal = source.radius + target.radius + 150;
      const pull = ((distance - ideal) / distance) * 0.018 * alpha;
      const offsetX = dx * pull;
      const offsetY = dy * pull;

      if (!source.fixed) {
        source.x += offsetX;
        source.y += offsetY;
      }
      if (!target.fixed) {
        target.x -= offsetX;
        target.y -= offsetY;
      }
    }

    for (let i = 1; i < positions.length; i += 1) {
      const node = positions[i];
      const dx = WIDTH / 2 - node.x;
      const dy = HEIGHT / 2 - node.y;
      node.x += dx * 0.003 * alpha;
      node.y += dy * 0.003 * alpha;
      node.x = Math.max(node.radius + 18, Math.min(WIDTH - node.radius - 18, node.x));
      node.y = Math.max(node.radius + 26, Math.min(HEIGHT - node.radius - 32, node.y));
    }
  }

  return positions.map(({ fixed, radius, ...node }) => node);
}

function resolveDragCollisions(nodes: PositionedNode[], draggedNodeId: string) {
  const next = nodes.map((node) => ({ ...node }));

  for (let iteration = 0; iteration < 8; iteration += 1) {
    let changed = false;

    for (let i = 0; i < next.length; i += 1) {
      for (let j = i + 1; j < next.length; j += 1) {
        const a = next[i];
        const b = next[j];
        const aRadius = nodeRadius(a, i === 0);
        const bRadius = nodeRadius(b, j === 0);
        const minimum = aRadius + bRadius + 18;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.hypot(dx, dy);

        if (distance === 0) {
          dx = 1;
          dy = 0;
          distance = 1;
        }

        if (distance < minimum) {
          const overlap = minimum - distance;
          const nx = dx / distance;
          const ny = dy / distance;
          const aIsDragged = a.id === draggedNodeId;
          const bIsDragged = b.id === draggedNodeId;

          if (aIsDragged && !bIsDragged) {
            b.x += nx * overlap;
            b.y += ny * overlap;
          } else if (bIsDragged && !aIsDragged) {
            a.x -= nx * overlap;
            a.y -= ny * overlap;
          } else {
            a.x -= nx * overlap * 0.5;
            a.y -= ny * overlap * 0.5;
            b.x += nx * overlap * 0.5;
            b.y += ny * overlap * 0.5;
          }

          changed = true;
        }
      }
    }

    for (let i = 0; i < next.length; i += 1) {
      const radius = nodeRadius(next[i], i === 0);
      next[i].x = Math.max(radius + 18, Math.min(WIDTH - radius - 18, next[i].x));
      next[i].y = Math.max(radius + 26, Math.min(HEIGHT - radius - 32, next[i].y));
    }

    if (!changed) break;
  }

  return next;
}

function buildNeighborMap(edges: GraphEdgeItem[]) {
  const map = new Map<string, Set<string>>();
  for (const edge of edges) {
    if (!map.has(edge.source)) map.set(edge.source, new Set());
    if (!map.has(edge.target)) map.set(edge.target, new Set());
    map.get(edge.source)?.add(edge.target);
    map.get(edge.target)?.add(edge.source);
  }
  return map;
}

function screenToSvg(svg: SVGSVGElement, event: PointerEvent<SVGElement>) {
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  return point.matrixTransform(matrix.inverse());
}

export function SimpleGraph({ nodes, edges }: { nodes: GraphNodeItem[]; edges: GraphEdgeItem[] }) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [positionedNodes, setPositionedNodes] = useState<PositionedNode[]>([]);
  const [dragging, setDragging] = useState<DragState>(null);
  const [zoom, setZoom] = useState(1);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    const layout = initialLayout(nodes, edges);
    setPositionedNodes(layout);
    setSelectedNodeId(layout[0]?.id ?? null);
    setZoom(1);
  }, [nodes, edges]);

  const nodeById = useMemo(
    () => new Map<string, PositionedNode>(positionedNodes.map((node) => [node.id, node])),
    [positionedNodes],
  );

  const visibleEdges = useMemo(
    () =>
      edges
        .map((edge) => ({
          ...edge,
          sourceNode: nodeById.get(edge.source),
          targetNode: nodeById.get(edge.target),
        }))
        .filter((edge) => edge.sourceNode && edge.targetNode)
        .slice(0, 220),
    [edges, nodeById],
  );

  const nodeCounts = useMemo(() => countBy(nodes.map((node) => node.type)), [nodes]);
  const edgeCounts = useMemo(() => countBy(edges.map((edge) => edge.type)), [edges]);
  const neighborMap = useMemo(() => buildNeighborMap(edges), [edges]);
  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) : positionedNodes[0];
  const viewWidth = WIDTH / zoom;
  const viewHeight = HEIGHT / zoom;
  const viewX = (WIDTH - viewWidth) / 2;
  const viewY = (HEIGHT - viewHeight) / 2;

  function startDrag(event: PointerEvent<SVGGElement>, nodeId: string) {
    const node = nodeById.get(nodeId);
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging({
      nodeId,
      pointerId: event.pointerId,
      moved: false,
      lastX: node?.x ?? 0,
      lastY: node?.y ?? 0,
    });
  }

  function moveDrag(event: PointerEvent<SVGSVGElement>) {
    if (!dragging || !svgRef.current) return;
    const next = screenToSvg(svgRef.current, event);
    if (!next) return;

    const deltaX = next.x - dragging.lastX;
    const deltaY = next.y - dragging.lastY;
    const directNeighbors = neighborMap.get(dragging.nodeId) ?? new Set<string>();
    const secondHopNeighbors = new Set<string>();
    for (const neighborId of directNeighbors) {
      for (const secondHopId of neighborMap.get(neighborId) ?? []) {
        if (secondHopId !== dragging.nodeId && !directNeighbors.has(secondHopId)) {
          secondHopNeighbors.add(secondHopId);
        }
      }
    }

    setDragging((current) => (current ? { ...current, moved: true, lastX: next.x, lastY: next.y } : current));
    setPositionedNodes((current) => {
      const moved = current.map((node, index) => {
        if (node.id !== dragging.nodeId) {
          const followFactor = directNeighbors.has(node.id) ? 0.28 : secondHopNeighbors.has(node.id) ? 0.09 : 0;
          if (followFactor === 0) return node;

          const radius = nodeRadius(node, index === 0);
          return {
            ...node,
            x: Math.max(radius + 18, Math.min(WIDTH - radius - 18, node.x + deltaX * followFactor)),
            y: Math.max(radius + 26, Math.min(HEIGHT - radius - 32, node.y + deltaY * followFactor)),
          };
        }

        const radius = nodeRadius(node, index === 0);
        return {
          ...node,
          x: Math.max(radius + 18, Math.min(WIDTH - radius - 18, next.x)),
          y: Math.max(radius + 26, Math.min(HEIGHT - radius - 32, next.y)),
        };
      });

      return resolveDragCollisions(moved, dragging.nodeId);
    });
  }

  function endDrag() {
    setDragging(null);
  }

  function selectNode(nodeId: string) {
    if (dragging?.moved) return;
    setSelectedNodeId(nodeId);
  }

  if (nodes.length === 0) {
    return (
      <div className="flex min-h-[340px] items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
        Khong co graph data de hien thi.
      </div>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <div className="overflow-hidden rounded-md border bg-[#f8fafc]">
        <div className="flex items-center justify-between border-b bg-white px-3 py-2">
          <div className="text-sm font-semibold">Graph result</div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setZoom((value) => Math.min(2.2, value + 0.2))}>
              <Plus className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setZoom((value) => Math.max(0.7, value - 0.2))}>
              <Minus className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setPositionedNodes(initialLayout(nodes, edges))}>
              <RotateCcw className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setZoom(1)}>
              <LocateFixed className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <svg
          ref={svgRef}
          viewBox={`${viewX} ${viewY} ${viewWidth} ${viewHeight}`}
          role="img"
          className="h-[650px] w-full touch-none select-none"
          onPointerMove={moveDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
              <path d="M0,0 L0,6 L7,3 z" fill="#94a3b8" />
            </marker>
          </defs>

          {visibleEdges.map((edge) => {
            const source = edge.sourceNode as PositionedNode;
            const target = edge.targetNode as PositionedNode;
            const midX = (source.x + target.x) / 2;
            const midY = (source.y + target.y) / 2;

            return (
              <g key={edge.id}>
                <line
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke="#94a3b8"
                  strokeWidth="1.2"
                  markerEnd="url(#arrowhead)"
                />
                <text x={midX} y={midY - 5} textAnchor="middle" className="fill-slate-500 text-[8px]">
                  {shortLabel(relationLabel(edge.type), 24)}
                </text>
              </g>
            );
          })}

          {positionedNodes.map((node, index) => {
            const style = styleFor(node.type);
            const radius = nodeRadius(node, index === 0);
            const labelLines = wrapNodeLabel(node.label, radius);
            const fontSize = Math.max(8, Math.min(12, radius / 4));
            const isSelected = selectedNodeId === node.id;

            return (
              <g
                key={node.id}
                className="cursor-grab active:cursor-grabbing"
                onPointerDown={(event) => startDrag(event, node.id)}
                onClick={() => selectNode(node.id)}
              >
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={radius}
                  fill={style.fill}
                  stroke={isSelected ? "#111827" : style.stroke}
                  strokeWidth={isSelected ? "4" : "2.5"}
                />
                <text x={node.x} y={node.y - ((labelLines.length - 1) * fontSize) / 2 + 3} textAnchor="middle" className="pointer-events-none fill-slate-900 font-bold">
                  {labelLines.map((line, lineIndex) => (
                    <tspan key={`${line}-${lineIndex}`} x={node.x} dy={lineIndex === 0 ? 0 : fontSize + 2} style={{ fontSize }}>
                      {line}
                    </tspan>
                  ))}
                </text>
                <text
                  x={node.x}
                  y={node.y + radius + 13}
                  textAnchor="middle"
                  className="pointer-events-none fill-slate-500 text-[9px]"
                >
                  {node.type}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <aside className="rounded-md border bg-white p-4">
        <h3 className="text-lg font-semibold">Results overview</h3>

        <div className="mt-4 space-y-3">
          <div>
            <div className="mb-2 text-sm text-muted-foreground">Nodes ({nodes.length})</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(nodeCounts).map(([type, count]) => (
                <Badge key={type} variant="outline" className={styleFor(type).badge}>
                  {type} ({count})
                </Badge>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm text-muted-foreground">Relationships ({edges.length})</div>
            <div className="flex max-h-[280px] flex-wrap gap-2 overflow-y-auto pr-1">
              {Object.entries(edgeCounts).map(([type, count]) => (
                <Badge key={type} variant="secondary" className="rounded-md">
                  {type} ({count})
                </Badge>
              ))}
            </div>
          </div>
        </div>

        {selectedNode ? (
          <div className="mt-4 rounded-md border bg-secondary/30 p-3">
            <div className="text-sm font-semibold">Selected node</div>
            <div className="mt-2 space-y-2">
              <div>
                <div className="text-xs text-muted-foreground">Label</div>
                <div className="break-words text-sm font-medium">{selectedNode.label}</div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-xs text-muted-foreground">Type</div>
                  <Badge variant="outline" className={styleFor(selectedNode.type).badge}>
                    {selectedNode.type}
                  </Badge>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">ID</div>
                  <div className="break-all text-xs">{selectedNode.id}</div>
                </div>
              </div>
              {selectedNode.properties && Object.keys(selectedNode.properties).length > 0 ? (
                <div className="max-h-[220px] space-y-2 overflow-y-auto border-t pt-2">
                  {Object.entries(selectedNode.properties).slice(0, 16).map(([key, value]) => (
                    <div key={key} className="rounded-md bg-background p-2 text-xs">
                      <div className="break-words text-muted-foreground">{key}</div>
                      <div className="mt-1 whitespace-pre-wrap break-words font-medium leading-5">
                        {propertyPreview(value)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="mt-4 rounded-md bg-secondary/50 p-3 text-xs leading-5 text-muted-foreground">
          Click node de xem thong tin. Keo node de sap xep lai graph. Dung +/- de zoom. Nut reset se dua layout ve trang thai ban dau.
        </div>
      </aside>
    </div>
  );
}
