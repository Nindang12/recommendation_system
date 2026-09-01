"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Building2, Info, Loader2, Network, Sparkles, TrendingUp, UserCheck } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { SimpleGraph } from "@/components/graph/simple-graph";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  EntityType,
  ExplanationResponse,
  getRecommendationExplanation,
  GraphNeighborsResponse,
  ProjectOverviewResponse,
  RecommendationItem,
} from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const groups = [
  { key: "experts", title: "Experts", type: "expert", icon: UserCheck },
  { key: "funders", title: "Funders", type: "funder", icon: TrendingUp },
  { key: "enterprises", title: "Enterprises", type: "enterprise", icon: Building2 },
  { key: "similar_projects", title: "Similar projects", type: "project", icon: Sparkles },
] as const;

type ExplanationState = {
  loadingKey?: string;
  error?: string;
  cache: Record<string, ExplanationResponse["data"]>;
};

const XAI_PRESENTATION_VERSION = "v5-xai-model";

function explanationKey(targetType: EntityType, entityId: string) {
  return `${XAI_PRESENTATION_VERSION}:${targetType}:${entityId}`;
}

function cleanXaiText(text: string) {
  return text.replace(/\*\*/g, "").replace(/```/g, "").trim();
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function XaiTextBlock({ text }: { text: string }) {
  const lines = cleanXaiText(text)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return <p className="text-sm text-muted-foreground">Chua co noi dung giai thich.</p>;
  return (
    <div className="min-w-0 space-y-3">
      {lines.map((line, index) => (
        <p key={`${line}-${index}`} className="break-words text-sm leading-6 text-foreground">
          {line}
        </p>
      ))}
    </div>
  );
}

function ConfidenceBlock({ confidence }: { confidence: Record<string, unknown> }) {
  const total = asNumber(confidence.total);
  const level = asString(confidence.level);
  const interpretation = asString(confidence.interpretation);
  const components =
    confidence.components && typeof confidence.components === "object"
      ? (confidence.components as Record<string, unknown>)
      : {};
  const componentEntries = Object.entries(components);

  return (
    <div className="min-w-0 overflow-hidden rounded-md border bg-background p-4">
      <div className="grid min-w-0 gap-4 md:grid-cols-[180px_minmax(0,1fr)]">
        <div className="rounded-md bg-secondary/50 p-4 text-center">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Confidence</div>
          <div className="mt-2 text-3xl font-bold">{total !== null ? `${Math.round(total * 100)}%` : "N/A"}</div>
        </div>

        <div className="min-w-0 space-y-3">
          {level ? (
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Mức độ</div>
              <div className="mt-1 break-words font-semibold">{level}</div>
            </div>
          ) : null}

          {interpretation ? (
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Diễn giải</div>
              <p className="mt-1 break-words text-sm leading-6 text-muted-foreground">{interpretation}</p>
            </div>
          ) : null}
        </div>
      </div>

      {componentEntries.length > 0 ? (
        <div className="mt-4 min-w-0 space-y-3">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Thành phần điểm</div>
          <div className="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {componentEntries.map(([key, value]) => {
              const numericValue = asNumber(value);
              return (
                <div key={key} className="min-w-0 rounded-md border bg-secondary/30 p-3">
                  <div className="break-words text-xs text-muted-foreground">{humanizeRelation(key)}</div>
                  <div className="mt-1 break-words text-lg font-semibold">
                    {numericValue !== null ? `${Math.round(numericValue * 100)}%` : String(value)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function humanizeRelation(value: string) {
  return value.replace(/_/g, " ").toLowerCase();
}

function getPathParts(path: unknown) {
  if (typeof path === "string") return path.split("->").map((part) => part.trim()).filter(Boolean);
  if (path && typeof path === "object") {
    const record = path as Record<string, unknown>;
    if (Array.isArray(record.relations)) return record.relations.map(String);
    if (typeof record.path === "string") return record.path.split("->").map((part) => part.trim()).filter(Boolean);
  }
  return [];
}

function getPathNodes(path: unknown, relationCount: number, source: ProjectOverviewResponse["source"], target: RecommendationItem) {
  let labels: string[] = [];
  if (path && typeof path === "object") {
    const record = path as Record<string, unknown>;
    const entities = record.entities ?? record.entity_names ?? record.nodes;
    if (Array.isArray(entities)) {
      labels = entities.map((entity) => {
        if (entity && typeof entity === "object") {
          const node = entity as Record<string, unknown>;
          return String(node.name ?? node.label ?? node.id ?? "Node");
        }
        return String(entity);
      });
    }
  }
  return Array.from({ length: relationCount + 1 }).map((_, index) => ({
    role: index === 0 ? "Source" : index === relationCount ? "Target" : `Evidence ${index}`,
    label:
      labels[index] ||
      (index === 0 ? source.name || source.id : index === relationCount ? target.name || target.id : `Evidence ${index}`),
    subtitle:
      index === 0
        ? `${source.type}: ${source.id}`
        : index === relationCount
          ? `${target.type || "target"}: ${target.id}`
          : "intermediate node",
  }));
}

function compactLabel(value: string, max = 18) {
  return value.length > max ? `${value.slice(0, Math.max(1, max - 3))}...` : value;
}

function ReasoningPathCard({
  path,
  index,
  source,
  target,
}: {
  path: unknown;
  index: number;
  source: ProjectOverviewResponse["source"];
  target: RecommendationItem;
}) {
  const relations = getPathParts(path);
  const nodes = getPathNodes(path, relations.length, source, target);
  const record = path && typeof path === "object" ? (path as Record<string, unknown>) : {};
  const score = typeof record.score === "number" ? record.score : null;
  const length = typeof record.length === "number" ? record.length : typeof record.path_length === "number" ? record.path_length : relations.length;
  const graphWidth = Math.max(720, nodes.length * 190 + Math.max(nodes.length - 1, 0) * 110);
  const gap = graphWidth / Math.max(nodes.length, 1);
  const nodeY = 88;
  const radius = 42;

  return (
    <div className="min-w-0 overflow-hidden rounded-md border border-slate-200 bg-white p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="text-lg font-bold">Path {index + 1}</div>
        <div className="flex gap-2">
          {score !== null ? <Badge variant="secondary">Score {(score * 100).toFixed(1)}%</Badge> : null}
          <Badge variant="outline">Length {String(length)}</Badge>
        </div>
      </div>
      {relations.length ? (
        <div className="w-full max-w-full overflow-x-auto overflow-y-hidden rounded-md bg-slate-50 p-4">
          <svg
            viewBox={`0 0 ${graphWidth} 190`}
            className="h-[190px] max-w-none shrink-0"
            style={{ width: `${graphWidth}px` }}
            role="img"
          >
            <defs>
              {relations.map((_, relationIndex) => (
                <marker key={relationIndex} id={`overview-arrow-${index}-${relationIndex}`} markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto">
                  <path d="M0,0 L0,8 L8,4 z" fill="#64748b" />
                </marker>
              ))}
            </defs>
            {relations.map((relation, relationIndex) => {
              const fromX = gap / 2 + relationIndex * gap;
              const toX = gap / 2 + (relationIndex + 1) * gap;
              const start = fromX + radius + 12;
              const end = toX - radius - 12;
              const middle = (start + end) / 2;
              return (
                <g key={`${relation}-${relationIndex}`}>
                  <rect x={middle - 65} y={nodeY - 55} width="130" height="28" rx="6" fill="white" stroke="#dbe3ef" />
                  <text x={middle} y={nodeY - 37} textAnchor="middle" className="fill-slate-700 text-[11px] font-semibold">
                    {compactLabel(humanizeRelation(relation), 22)}
                  </text>
                  <line x1={start} y1={nodeY} x2={end} y2={nodeY} stroke="#64748b" strokeWidth="1.8" markerEnd={`url(#overview-arrow-${index}-${relationIndex})`} />
                </g>
              );
            })}
            {nodes.map((node, nodeIndex) => {
              const x = gap / 2 + nodeIndex * gap;
              const sourceNode = nodeIndex === 0;
              const targetNode = nodeIndex === nodes.length - 1;
              return (
                <g key={`${node.role}-${nodeIndex}`} className="group cursor-help">
                  <title>{`${node.role}: ${node.label} (${node.subtitle})`}</title>
                  <circle cx={x} cy={nodeY} r={radius} fill={sourceNode ? "#cffafe" : targetNode ? "#d1fae5" : "#fff"} stroke={sourceNode ? "#0e7490" : targetNode ? "#047857" : "#94a3b8"} strokeWidth="2.5" />
                  <text x={x} y={nodeY - 8} textAnchor="middle" className="fill-slate-900 text-[11px] font-bold">{node.role}</text>
                  <text x={x} y={nodeY + 9} textAnchor="middle" className="fill-slate-900 text-[10px] font-semibold">{compactLabel(node.label, 15)}</text>
                  <text x={x} y={nodeY + 65} textAnchor="middle" className="fill-slate-500 text-[10px]">{compactLabel(node.subtitle, 25)}</text>
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
          Path nay chua co du quan he de hien thi thanh so do.
        </div>
      )}
    </div>
  );
}

function embeddingBadge(value: unknown) {
  const status = String(value || "unknown");
  const labels: Record<string, string> = {
    ready: "Embedding ready",
    pending: "Embedding pending",
    queued: "Embedding queued",
    processing: "Embedding processing",
    stale: "Embedding stale",
    failed: "Embedding failed",
    skipped: "Embedding skipped",
  };
  const className =
    status === "ready"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : status === "failed" || status === "skipped"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
  return { label: labels[status] || `Embedding ${status}`, className };
}

function RecommendationList({
  items,
  type,
  source,
  explanations,
  onExplain,
}: {
  items: RecommendationItem[];
  type: EntityType;
  source?: ProjectOverviewResponse["source"];
  explanations: ExplanationState;
  onExplain: (item: RecommendationItem, targetType: EntityType) => void;
}) {
  if (!items?.length) {
    return <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">Khong co ket qua.</div>;
  }

  return (
    <div className="space-y-3">
      {items.map((item, index) => (
        <div className="rounded-md border p-3" key={`${item.id}-${index}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">Rank #{index + 1}</div>
              <div className="truncate font-semibold">{item.name || item.id}</div>
              <div className="text-xs text-muted-foreground">ID: {item.id}</div>
            </div>
            <Badge variant="secondary" className="rounded-md">
              {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
            </Badge>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link href={`/entities/${item.type ?? type}/${item.id}`}>Xem entity</Link>
            </Button>
            <Button
              size="sm"
              disabled={!source || explanations.loadingKey === explanationKey(type, item.id)}
              onClick={() => onExplain(item, type)}
            >
              {explanations.loadingKey === explanationKey(type, item.id) ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Giải thích chi tiết
            </Button>
          </div>

        </div>
      ))}
      {explanations.error ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{explanations.error}</div>
      ) : null}
    </div>
  );
}

export default function ProjectOverviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [overview, setOverview] = useState<ProjectOverviewResponse | null>(null);
  const [graph, setGraph] = useState<GraphNeighborsResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [explanations, setExplanations] = useState<ExplanationState>({ cache: {} });
  const [selectedExplanation, setSelectedExplanation] = useState<RecommendationItem | null>(null);
  const [selectedTargetType, setSelectedTargetType] = useState<EntityType>("expert");

  useEffect(() => {
    setIsLoading(true);
    setError("");
    Promise.allSettled([api.projectOverview(id), api.graphNeighbors("project", id, 1, 60)])
      .then(([overviewResult, graphResult]) => {
        if (overviewResult.status === "fulfilled") {
          setOverview(overviewResult.value);
        } else {
          setError(overviewResult.reason instanceof Error ? overviewResult.reason.message : "Khong tai duoc overview");
        }

        if (graphResult.status === "fulfilled") {
          setGraph(graphResult.value.data);
        }
      })
      .finally(() => setIsLoading(false));
  }, [id]);

  async function handleExplain(item: RecommendationItem, targetType: EntityType, forceRefresh = false) {
    const source = overview?.source;
    if (!source) return;
    const key = explanationKey(targetType, item.id);
    setSelectedExplanation(item);
    setSelectedTargetType(targetType);
    if (explanations.cache[key] && !forceRefresh) return;

    setExplanations((current) => ({ ...current, loadingKey: key, error: "" }));
    try {
      const response = await api.explain(item, source, targetType, "llm", forceRefresh);
      setExplanations((current) => ({
        cache: { ...current.cache, [key]: response.data },
        loadingKey: undefined,
        error: "",
      }));
    } catch (err) {
      setExplanations((current) => ({
        ...current,
        loadingKey: undefined,
        error: err instanceof Error ? err.message : "Khong tao duoc giai thich XAI",
      }));
    }
  }

  const selectedExplanationKey = selectedExplanation
    ? explanationKey(selectedTargetType, selectedExplanation.id)
    : "";
  const generatedExplanation = selectedExplanationKey ? explanations.cache[selectedExplanationKey] : undefined;

  return (
    <div className="min-h-svh bg-background">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6">
        <Link href="/dashboard" className="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Ve dashboard
        </Link>

        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <Badge variant="outline" className="mb-2 rounded-md">
              Project overview
            </Badge>
            <h1 className="text-3xl font-bold tracking-tight">{overview?.source?.name || id}</h1>
            <p className="mt-2 text-muted-foreground">
              Tong hop 4 nhom recommendation chinh cho mot project de demo nhanh.
            </p>
            {overview?.source?.metadata?.embedding_status ? (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                <Badge
                  variant="outline"
                  className={`rounded-md ${embeddingBadge(overview.source.metadata.embedding_status).className}`}
                >
                  {embeddingBadge(overview.source.metadata.embedding_status).label}
                </Badge>
                <span className="text-muted-foreground">
                  {overview.source.metadata.embedding_status === "ready"
                    ? "Embedding da san sang de hybrid recommendation su dung."
                    : "Embedding chua san sang, he thong se uu tien Cypher/PGPR fallback."}
                </span>
              </div>
            ) : null}
          </div>
          <Link href={`/entities/project/${id}`}>
            <Button variant="outline">Xem entity detail</Button>
          </Link>
        </div>

        {isLoading ? (
          <div className="flex min-h-[360px] items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Dang tai project overview...
          </div>
        ) : error ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
        ) : (
          <>
            <section className="grid gap-4 lg:grid-cols-2">
              {groups.map((group) => (
                <Card key={group.key} className="rounded-md">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <group.icon className="h-4 w-4" />
                      {group.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <RecommendationList
                      items={(overview?.data?.[group.key] as RecommendationItem[] | undefined) ?? []}
                      type={group.type}
                      source={overview?.source}
                      explanations={explanations}
                      onExplain={handleExplain}
                    />
                  </CardContent>
                </Card>
              ))}
            </section>

            <Card className="rounded-md">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Network className="h-4 w-4" />
                  Neighbor graph
                </CardTitle>
              </CardHeader>
              <CardContent>
                <SimpleGraph nodes={graph?.nodes ?? []} edges={graph?.edges ?? []} />
              </CardContent>
            </Card>
          </>
        )}
      </main>

      <Dialog
        open={Boolean(selectedExplanation)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedExplanation(null);
            setExplanations((current) => ({ ...current, error: "", loadingKey: undefined }));
          }
        }}
      >
        <DialogContent className="max-h-[90vh] w-[calc(100vw-1rem)] max-w-6xl overflow-x-hidden overflow-y-auto rounded-xl border-slate-200 bg-white p-4 shadow-xl sm:w-[calc(100vw-2rem)] sm:p-6 md:p-8">
          <DialogHeader className="min-w-0 border-b border-slate-200 pb-4 pr-8">
            <DialogTitle className="flex min-w-0 items-center gap-2 text-left text-lg font-bold tracking-tight text-slate-800 sm:text-xl">
              <Sparkles className="h-5 w-5 text-indigo-500" />
              Giải thích Chi tiết (XAI Engine)
            </DialogTitle>
            <DialogDescription className="break-words text-left text-xs font-medium leading-5 text-slate-500 sm:text-sm">
              Phân tích bằng chứng, độ tin cậy và reasoning paths tạo nên đề xuất.
            </DialogDescription>
          </DialogHeader>

          {selectedExplanation ? (
            <div className="min-w-0 space-y-6 pt-5">
              <div className="min-w-0 overflow-hidden rounded-md border border-indigo-100 bg-indigo-50/30 p-4 sm:p-5">
                <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="text-xs font-bold uppercase text-indigo-500">Thực thể đề xuất</div>
                    <div className="mt-1 break-words text-xl font-bold">{selectedExplanation.name || selectedExplanation.id}</div>
                    <div className="mt-1 break-all text-sm text-muted-foreground">ID: {selectedExplanation.id}</div>
                  </div>
                  <div className="h-fit shrink-0 rounded-md border bg-white p-3 text-left shadow-sm sm:text-right">
                    <div className="text-xs font-semibold uppercase text-muted-foreground">Điểm gợi ý</div>
                    <div className="mt-1 text-xl font-bold text-indigo-600">
                      {typeof selectedExplanation.score === "number"
                        ? `${(selectedExplanation.score * 100).toFixed(1)}%`
                        : "N/A"}
                    </div>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {selectedExplanation.scoring_method ? (
                    <Badge variant="outline">{selectedExplanation.scoring_method}</Badge>
                  ) : null}
                  {selectedExplanation.evidence_level ? (
                    <Badge variant="outline">Evidence: {selectedExplanation.evidence_level}</Badge>
                  ) : null}
                  {selectedExplanation.embedding_status ? (
                    <Badge variant="outline">Embedding: {selectedExplanation.embedding_status}</Badge>
                  ) : null}
                  {selectedExplanation.cold_start ? <Badge variant="outline">Cold-start</Badge> : null}
                </div>
              </div>

              <div className="flex min-w-0 flex-col gap-4 rounded-md border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="font-semibold">Trạng thái XAI Model</div>
                  <div className="mt-1 break-words text-sm leading-6 text-muted-foreground">
                    {explanations.loadingKey === selectedExplanationKey
                      ? "Đang tạo giải thích chi tiết..."
                      : generatedExplanation?._cache?.hit
                        ? "Đang hiển thị giải thích từ cache."
                        : generatedExplanation
                          ? "Giải thích mới đã được tạo."
                          : "Đang chờ kết quả giải thích."}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 shrink-0 self-start rounded-md text-xs font-bold sm:self-auto"
                  disabled={explanations.loadingKey === selectedExplanationKey}
                  onClick={() => void handleExplain(selectedExplanation, selectedTargetType, true)}
                >
                  {explanations.loadingKey === selectedExplanationKey ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Tạo lại giải thích
                </Button>
              </div>

              <section className="min-w-0 space-y-2">
                <h3 className="flex items-center gap-2 text-xs font-bold uppercase text-muted-foreground sm:text-sm">
                  <Info className="h-4 w-4" />
                  Mô tả giải thích tự nhiên
                </h3>
                <div className="min-w-0 overflow-hidden rounded-md border p-4 sm:p-5">
                  {explanations.loadingKey === selectedExplanationKey ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      XAI đang phân tích dữ liệu...
                    </div>
                  ) : explanations.error ? (
                    <div className="break-words rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                      {explanations.error}
                    </div>
                  ) : (
                    <XaiTextBlock
                      text={generatedExplanation?.natural_language || getRecommendationExplanation(selectedExplanation)}
                    />
                  )}
                </div>
              </section>

              {generatedExplanation?.confidence ? (
                <section className="min-w-0 space-y-2">
                  <h3 className="flex items-center gap-2 text-xs font-bold uppercase text-muted-foreground sm:text-sm">
                    <TrendingUp className="h-4 w-4" />
                    Đánh giá độ tin cậy
                  </h3>
                  <ConfidenceBlock confidence={generatedExplanation.confidence} />
                </section>
              ) : null}

              {selectedExplanation.reasoning_paths?.length ? (
                <section className="min-w-0 space-y-3">
                  <h3 className="flex items-center gap-2 text-xs font-bold uppercase text-muted-foreground sm:text-sm">
                    <Network className="h-4 w-4" />
                    Bản đồ đường dẫn lập luận đồ thị (Reasoning Paths)
                  </h3>
                  {selectedExplanation.reasoning_paths.map((path, index) => (
                    <ReasoningPathCard
                      key={index}
                      path={path}
                      index={index}
                      source={overview?.source ?? { id, type: "project", name: id }}
                      target={selectedExplanation}
                    />
                  ))}
                </section>
              ) : (
                <div className="break-words rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                  Đề xuất hiện chưa có reasoning path đầy đủ; kết quả có thể đang dựa trên embedding hoặc Cypher fallback.
                </div>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
