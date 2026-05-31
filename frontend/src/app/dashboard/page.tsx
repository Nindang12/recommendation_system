"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Building2,
  Database,
  GitFork,
  GraduationCap,
  Info,
  Loader2,
  Network,
  Search,
  Sparkles,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  api,
  ApiEntity,
  EntityType,
  ExplanationResponse,
  getRecommendationExplanation,
  HealthResponse,
  RecommendationItem,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const entityOptions: Array<{ type: EntityType; label: string; collectionLabel: string; icon: typeof GraduationCap }> = [
  { type: "project", label: "Project", collectionLabel: "Projects", icon: GraduationCap },
  { type: "expert", label: "Expert", collectionLabel: "Experts", icon: UserCheck },
  { type: "funder", label: "Funder", collectionLabel: "Funders", icon: TrendingUp },
  { type: "enterprise", label: "Enterprise", collectionLabel: "Enterprises", icon: Building2 },
];

const multiTargetTypes: EntityType[] = ["project", "expert", "enterprise", "funder"];

function getEntityOption(type: EntityType) {
  return entityOptions.find((option) => option.type === type) ?? entityOptions[0];
}

function getUserSourceEntity(user: ReturnType<typeof useAuth>["user"]): ApiEntity | null {
  const linked = user?.linked_entity;
  const linkedType = linked?.type?.toLowerCase() as EntityType | undefined;
  if (!linked?.id || !linkedType || !multiTargetTypes.includes(linkedType)) return null;

  return {
    id: linked.id,
    name: linked.name || user?.full_name || linked.id,
    type: linkedType,
  };
}

function statusTone(value?: string) {
  if (!value) return "bg-slate-100 text-slate-700";
  const normalized = value.toLowerCase();
  if (["connected", "ready", "ok"].some((item) => normalized.includes(item))) {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
  if (normalized.includes("optional")) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-rose-50 text-rose-700 border-rose-200";
}

function normalizeRecommendations(response: unknown): RecommendationItem[] {
  const payload = response as {
    data?: RecommendationItem[] | { recommendations?: RecommendationItem[] };
    recommendations?: RecommendationItem[];
  };

  if (Array.isArray(payload.recommendations)) return payload.recommendations;
  if (Array.isArray(payload.data)) return payload.data;
  if (payload.data && !Array.isArray(payload.data) && Array.isArray(payload.data.recommendations)) {
    return payload.data.recommendations;
  }
  return [];
}

function cleanXaiText(text: string) {
  return text.replace(/\*\*/g, "").replace(/```/g, "").trim();
}

function getXaiPreview(item: RecommendationItem) {
  const text = cleanXaiText(getRecommendationExplanation(item));
  if (!text) return "Chua co explanation tu backend.";

  const firstUsefulLine = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0);

  if (!firstUsefulLine) return "Chua co explanation tu backend.";
  return firstUsefulLine.length > 170 ? `${firstUsefulLine.slice(0, 170)}...` : firstUsefulLine;
}

function XaiTextBlock({ text }: { text: string }) {
  const lines = cleanXaiText(text)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return <p className="text-sm text-muted-foreground">Chua co noi dung giai thich.</p>;
  }

  return (
    <div className="space-y-3">
      {lines.map((line, index) => (
        <p key={`${line}-${index}`} className="text-sm leading-6 text-foreground">
          {line}
        </p>
      ))}
    </div>
  );
}

function formatJsonBlock(value: unknown) {
  if (!value) return "";
  return JSON.stringify(value, null, 2);
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function ConfidenceBlock({ confidence }: { confidence: Record<string, unknown> }) {
  const total = asNumber(confidence.total);
  const level = asString(confidence.level);
  const interpretation = asString(confidence.interpretation);
  const components =
    confidence.components && typeof confidence.components === "object"
      ? (confidence.components as Record<string, unknown>)
      : {};

  const percent = total !== null ? Math.round(total * 100) : null;
  const componentEntries = Object.entries(components);

  return (
    <div className="min-w-0 overflow-hidden rounded-md border bg-background p-4">
      <div className="grid gap-4 md:grid-cols-[180px_1fr]">
        <div className="rounded-md bg-secondary/50 p-4 text-center">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Confidence</div>
          <div className="mt-2 text-3xl font-bold">{percent !== null ? `${percent}%` : "N/A"}</div>
        </div>

        <div className="space-y-3">
          {level ? (
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Muc do</div>
              <div className="mt-1 font-semibold">{level}</div>
            </div>
          ) : null}

          {interpretation ? (
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Dien giai</div>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{interpretation}</p>
            </div>
          ) : null}
        </div>
      </div>

      {componentEntries.length > 0 ? (
        <div className="mt-4 space-y-3">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Thanh phan diem</div>
          <div className="grid gap-2 md:grid-cols-3">
            {componentEntries.map(([key, value]) => {
              const numericValue = asNumber(value);
              return (
                <div key={key} className="rounded-md border bg-secondary/30 p-3">
                  <div className="text-xs text-muted-foreground">{humanizeRelation(key)}</div>
                  <div className="mt-1 text-lg font-semibold">
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
  if (typeof path === "string") {
    return path.split("->").map((part) => part.trim()).filter(Boolean);
  }

  if (path && typeof path === "object") {
    const record = path as Record<string, unknown>;
    if (Array.isArray(record.relations)) {
      return record.relations.map((part) => String(part));
    }
    if (typeof record.path === "string") {
      return record.path.split("->").map((part) => part.trim()).filter(Boolean);
    }
  }

  return [];
}

function getPathScore(path: unknown) {
  if (path && typeof path === "object") {
    const score = (path as Record<string, unknown>).score;
    if (typeof score === "number") return score;
  }
  return null;
}

function getPathLength(path: unknown, parts: string[]) {
  if (path && typeof path === "object") {
    const record = path as Record<string, unknown>;
    const length = record.length ?? record.path_length;
    if (typeof length === "number") return length;
  }
  return parts.length;
}

type PathNodeView = {
  role: "Source" | "Evidence" | "Target";
  label: string;
  subtitle: string;
};

function getPathNodeLabels(path: unknown, relationCount: number) {
  if (path && typeof path === "object") {
    const record = path as Record<string, unknown>;
    const entities = record.entities ?? record.entity_names ?? record.nodes;
    if (Array.isArray(entities) && entities.length >= 2) {
      return entities.map((entity) => {
        if (entity && typeof entity === "object") {
          const node = entity as Record<string, unknown>;
          return String(node.name ?? node.label ?? node.id ?? "Node");
        }
        return String(entity);
      });
    }
  }

  const labels = ["Source"];
  for (let index = 1; index < relationCount; index += 1) {
    labels.push(`Evidence ${index}`);
  }
  labels.push("Target");
  return labels;
}

function compactNodeLabel(value: string, max = 18) {
  return value.length > max ? `${value.slice(0, Math.max(1, max - 3))}...` : value;
}

function buildPathNodes(
  path: unknown,
  relationCount: number,
  source: ApiEntity | null,
  target: RecommendationItem,
): PathNodeView[] {
  const labels = getPathNodeLabels(path, relationCount);
  const sourcePathLabel = labels[0] && labels[0] !== "Source" ? labels[0] : "";
  const targetPathLabel =
    labels[labels.length - 1] && labels[labels.length - 1] !== "Target" ? labels[labels.length - 1] : "";
  const sourceLabel = sourcePathLabel || source?.name || source?.id || "Source";
  const targetLabel = targetPathLabel || target.name || target.id || "Target";
  const evidenceLabels = labels.slice(1, Math.max(1, labels.length - 1));

  return [
    {
      role: "Source",
      label: sourceLabel,
      subtitle: source ? `${source.type}: ${source.id}` : "source entity",
    },
    ...Array.from({ length: Math.max(relationCount - 1, 0) }).map((_, evidenceIndex) => ({
      role: "Evidence" as const,
      label: evidenceLabels[evidenceIndex] || `Evidence ${evidenceIndex + 1}`,
      subtitle: "intermediate node",
    })),
    {
      role: "Target",
      label: targetLabel,
      subtitle: `${target.type || "target"}: ${target.id}`,
    },
  ];
}

function ReasoningPathCard({
  path,
  index,
  source,
  target,
}: {
  path: unknown;
  index: number;
  source: ApiEntity | null;
  target: RecommendationItem;
}) {
  const parts = getPathParts(path);
  const score = getPathScore(path);
  const length = getPathLength(path, parts);
  const pathNodes = buildPathNodes(path, parts.length, source, target);
  const graphWidth = Math.max(620, pathNodes.length * 170 + Math.max(pathNodes.length - 1, 0) * 120);
  const nodeGap = graphWidth / Math.max(pathNodes.length, 1);
  const nodeY = 78;
  const nodeRadius = 38;

  return (
    <div className="rounded-md border bg-background p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold">Path {index + 1}</div>
        <div className="flex flex-wrap gap-2">
          {score !== null ? (
            <Badge variant="secondary" className="rounded-md">
              Score {(score * 100).toFixed(1)}%
            </Badge>
          ) : null}
          <Badge variant="outline" className="rounded-md">
            Length {length}
          </Badge>
        </div>
      </div>

      {parts.length > 0 ? (
        <div className="w-full max-w-full overflow-x-auto overflow-y-hidden rounded-md bg-slate-50 p-4">
          <svg
            viewBox={`0 0 ${graphWidth} 170`}
            className="h-[170px] max-w-none shrink-0"
            style={{ width: `${graphWidth}px` }}
            role="img"
          >
            <defs>
              {parts.map((_, partIndex) => (
                <marker
                  key={partIndex}
                  id={`kg-path-arrow-${index}-${partIndex}`}
                  markerWidth="9"
                  markerHeight="9"
                  refX="8"
                  refY="4"
                  orient="auto"
                >
                  <path d="M0,0 L0,8 L8,4 z" fill="#64748b" />
                </marker>
              ))}
            </defs>

            {parts.map((part, partIndex) => {
              const fromX = nodeGap / 2 + partIndex * nodeGap;
              const toX = nodeGap / 2 + (partIndex + 1) * nodeGap;
              const lineStart = fromX + nodeRadius + 12;
              const lineEnd = toX - nodeRadius - 12;
              const labelX = (lineStart + lineEnd) / 2;

              return (
                <g key={`${part}-${partIndex}`}>
                  <rect
                    x={labelX - 56}
                    y={nodeY - 48}
                    width="112"
                    height="24"
                    rx="4"
                    className="fill-white stroke-slate-200"
                  />
                  <text x={labelX} y={nodeY - 32} textAnchor="middle" className="fill-slate-700 text-[11px] font-semibold">
                    {compactNodeLabel(humanizeRelation(part), 20)}
                  </text>
                  <line
                    x1={lineStart}
                    y1={nodeY}
                    x2={lineEnd}
                    y2={nodeY}
                    stroke="#64748b"
                    strokeWidth="1.6"
                    markerEnd={`url(#kg-path-arrow-${index}-${partIndex})`}
                  />
                </g>
              );
            })}

            {pathNodes.map((node, nodeIndex) => {
              const x = nodeGap / 2 + nodeIndex * nodeGap;
              const isSource = node.role === "Source";
              const isTarget = node.role === "Target";

              return (
                <g key={`${node.role}-${nodeIndex}`} className="group cursor-help">
                  <title>{`${node.role}: ${node.label} (${node.subtitle})`}</title>
                  <circle
                    cx={x}
                    cy={nodeY}
                    r={nodeRadius}
                    className={
                      isSource
                        ? "fill-cyan-100 stroke-cyan-700"
                        : isTarget
                          ? "fill-emerald-100 stroke-emerald-700"
                          : "fill-white stroke-slate-400"
                    }
                    strokeWidth="2.4"
                  />
                  <text x={x} y={nodeY - 7} textAnchor="middle" className="fill-slate-900 text-[11px] font-bold">
                    {node.role}
                  </text>
                  <text x={x} y={nodeY + 8} textAnchor="middle" className="fill-slate-900 text-[10px] font-semibold">
                    {compactNodeLabel(node.label, 14)}
                  </text>
                  <text x={x} y={nodeY + 56} textAnchor="middle" className="fill-slate-500 text-[10px]">
                    {compactNodeLabel(node.subtitle, 24)}
                  </text>
                  <g className="pointer-events-none opacity-0 transition-opacity group-hover:opacity-100">
                    <rect
                      x={x - 120}
                      y={nodeY - 76}
                      width="240"
                      height="36"
                      rx="5"
                      className="fill-slate-950 stroke-slate-700"
                    />
                    <text
                      x={x}
                      y={nodeY - 54}
                      textAnchor="middle"
                      className="fill-white text-[11px] font-semibold"
                    >
                      {compactNodeLabel(node.label, 34)}
                    </text>
                  </g>
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <pre className="whitespace-pre-wrap break-words text-sm">{formatJsonBlock(path)}</pre>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState("");
  const [limit, setLimit] = useState("5");
  const [activeTargetType, setActiveTargetType] = useState<EntityType>("project");
  const [recommendationGroups, setRecommendationGroups] = useState<Partial<Record<EntityType, RecommendationItem[]>>>({});
  const [groupErrors, setGroupErrors] = useState<Partial<Record<EntityType, string>>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [selectedSource, setSelectedSource] = useState<ApiEntity | null>(null);
  const [selectedExplanation, setSelectedExplanation] = useState<RecommendationItem | null>(null);
  const [generatedExplanation, setGeneratedExplanation] = useState<ExplanationResponse["data"] | null>(null);
  const [isExplanationLoading, setIsExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState("");
  const [recommendationMode, setRecommendationMode] = useState<"public" | "personal">("public");

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((error) => setHealthError(error instanceof Error ? error.message : "Khong ket noi duoc backend"));
  }, []);

  const healthServices = useMemo(() => Object.entries(health?.services ?? {}), [health]);
  const sourceEntity = useMemo(() => getUserSourceEntity(user), [user]);
  const recommendations = recommendationGroups[activeTargetType] ?? [];
  const totalRecommendationCount = useMemo(
    () => Object.values(recommendationGroups).reduce((total, items) => total + (items?.length ?? 0), 0),
    [recommendationGroups],
  );

  async function runMultiRecommendation() {
    if (!sourceEntity) {
      setRecommendationError("Tai khoan hien tai chua co linked entity de lam source recommendation.");
      return;
    }

    setIsLoading(true);
    setRecommendationError("");
    setGroupErrors({});
    setRecommendationGroups({});
    setSelectedSource(sourceEntity);
    setRecommendationMode("personal");

    try {
      const settledResults = await Promise.allSettled(
        multiTargetTypes.map(async (targetType) => {
          const response = await api.recommend(
            sourceEntity.id,
            sourceEntity.type,
            targetType,
            Number(limit) || 5,
            "personal",
            user?.id,
          );
          return [targetType, normalizeRecommendations(response)] as const;
        }),
      );

      const nextGroups: Partial<Record<EntityType, RecommendationItem[]>> = {};
      const nextErrors: Partial<Record<EntityType, string>> = {};

      settledResults.forEach((result, index) => {
        const targetType = multiTargetTypes[index];
        if (result.status === "fulfilled") {
          nextGroups[targetType] = result.value[1];
        } else {
          nextGroups[targetType] = [];
          nextErrors[targetType] = result.reason instanceof Error ? result.reason.message : "Goi recommendation that bai";
        }
      });

      setRecommendationGroups(nextGroups);
      setGroupErrors(nextErrors);
      setActiveTargetType(multiTargetTypes.find((type) => (nextGroups[type]?.length ?? 0) > 0) ?? "project");
    } catch (error) {
      setRecommendationError(error instanceof Error ? error.message : "Goi recommendation that bai");
    } finally {
      setIsLoading(false);
    }
  }

  async function requestDetailedExplanation(item: RecommendationItem, forceRefresh = false) {
    const source = selectedSource ?? sourceEntity;
    if (!source) {
      setExplanationError("Khong tim thay source entity cua tai khoan hien tai.");
      return;
    }
    const mode = "auto";
    const resolvedTargetType = item.type ?? activeTargetType;

    setExplanationError("");
    setGeneratedExplanation(null);
    setIsExplanationLoading(true);
    try {
      const response = await api.explain(item, source, resolvedTargetType, mode, forceRefresh);
      const explanation = response.data ?? undefined;
      setGeneratedExplanation(explanation ?? null);
    } catch (error) {
      setExplanationError(error instanceof Error ? error.message : "Khong tao duoc giai thich XAI");
    } finally {
      setIsExplanationLoading(false);
    }
  }

  async function openDetailedExplanation(item: RecommendationItem) {
    setSelectedExplanation(item);
    setGeneratedExplanation(null);
    setExplanationError("");
    await requestDetailedExplanation(item);
  }

  async function regenerateExplanation() {
    if (!selectedExplanation) return;
    await requestDetailedExplanation(selectedExplanation, true);
  }

  return (
    <div className="min-h-svh bg-background">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6">
        <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="outline" className="gap-1 rounded-md">
                <GitFork className="h-3.5 w-3.5" />
                PGPR runtime
              </Badge>
              <Badge variant="outline" className="gap-1 rounded-md">
                <Database className="h-3.5 w-3.5" />
                MongoDB + Neo4j
              </Badge>
              <Badge variant="outline" className="gap-1 rounded-md">
                <Sparkles className="h-3.5 w-3.5" />
                XAI explanations
              </Badge>
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight md:text-4xl">Dashboard goi y R&D ca nhan</h1>
              <p className="mt-2 max-w-3xl text-muted-foreground">
                He thong tu dung ho so dang dang nhap lam source, chay multi recommendation mot luot cho project,
                expert, enterprise va funder.
              </p>
            </div>
          </div>

          <Card className="rounded-md">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="h-4 w-4" />
                System health
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {healthError ? (
                <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                  <AlertCircle className="mt-0.5 h-4 w-4" />
                  <span>{healthError}</span>
                </div>
              ) : !health ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Dang kiem tra backend...
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">API status</span>
                    <Badge className={statusTone(health.status)} variant="outline">
                      {health.status}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {healthServices.map(([name, value]) => (
                      <div key={name} className="rounded-md border p-3">
                        <div className="text-xs uppercase text-muted-foreground">{name}</div>
                        <div className="mt-1 text-sm font-semibold">{value}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          {entityOptions.map((option) => (
            <Link href={`/search?type=${option.type}`} key={option.type}>
              <Card className="h-full rounded-md transition-colors hover:border-primary">
                <CardContent className="flex items-center gap-3 p-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
                    <option.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="font-semibold">{option.collectionLabel}</div>
                    <div className="text-sm text-muted-foreground">Browse & recommend</div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-[420px_1fr]">
          <Card className="rounded-md">
            <CardHeader>
              <CardTitle className="text-lg">Multi recommendation workspace</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border bg-secondary/30 p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Source dang dung</div>
                {sourceEntity ? (
                  <div className="mt-3 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-lg font-semibold leading-snug">{sourceEntity.name}</div>
                        <div className="mt-1 break-all text-xs text-muted-foreground">ID: {sourceEntity.id}</div>
                      </div>
                      <Badge variant="secondary" className="rounded-md">
                        {sourceEntity.type}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-md border bg-background p-2">
                        <div className="text-muted-foreground">Scope</div>
                        <div className="mt-1 font-semibold">
                          {user?.linked_entity?.participation_scope ?? "unknown"}
                        </div>
                      </div>
                      <div className="rounded-md border bg-background p-2">
                        <div className="text-muted-foreground">KG status</div>
                        <div className="mt-1 font-semibold">{user?.linked_entity?.kg_sync_status ?? "unknown"}</div>
                      </div>
                    </div>
                    <p className="text-xs leading-5 text-muted-foreground">
                      Source nay thuoc tai khoan hien tai nen recommendation chay o personal mode.
                    </p>
                  </div>
                ) : (
                  <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    Tai khoan chua co linked entity. Hay hoan thien profile hoac dang nhap bang expert/enterprise/funder
                    da duoc tao.
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <Label>Limit moi nhom</Label>
                <Input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" />
              </div>

              <Button className="w-full gap-2" onClick={() => void runMultiRecommendation()} disabled={isLoading || !sourceEntity}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Goi y tat ca nhom
              </Button>

              <Separator />

              <div className="grid gap-2">
                {multiTargetTypes.map((type) => {
                  const option = getEntityOption(type);
                  const count = recommendationGroups[type]?.length ?? 0;
                  const Icon = option.icon;
                  return (
                    <Button
                      key={type}
                      type="button"
                      variant={activeTargetType === type ? "default" : "outline"}
                      className="justify-between"
                      onClick={() => setActiveTargetType(type)}
                    >
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4" />
                        {option.collectionLabel}
                      </span>
                      <Badge variant={activeTargetType === type ? "secondary" : "outline"} className="rounded-md">
                        {count}
                      </Badge>
                    </Button>
                  );
                })}
              </div>

              <Separator />

              {sourceEntity ? (
                <div className="grid gap-2">
                  <Link href={`/graph/neighbors?type=${sourceEntity.type}&id=${sourceEntity.id}`}>
                    <Button variant="outline" className="w-full justify-between">
                      Xem neighbor graph cua toi
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Link href={`/search?type=${activeTargetType}`}>
                    <Button variant="outline" className="w-full justify-between">
                      Duyet entities de recommend rieng
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </Link>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="rounded-md">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-lg">{getEntityOption(activeTargetType).collectionLabel} recommendations</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Ket qua theo source la entity dang dang nhap. Bam giai thich chi tiet de xem XAI day du.
                  </p>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <Badge variant={recommendationMode === "personal" ? "secondary" : "outline"} className="rounded-md">
                    {recommendationMode} mode
                  </Badge>
                  <Badge variant="outline" className="rounded-md">
                    {totalRecommendationCount} tong ket qua
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {recommendationError ? (
                <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {recommendationError}
                </div>
              ) : recommendations.length === 0 ? (
                <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-md border border-dashed text-center">
                  <Search className="h-8 w-8 text-muted-foreground" />
                  <div>
                    <div className="font-semibold">Chua co ket qua</div>
                    <div className="text-sm text-muted-foreground">
                      Bam "Goi y tat ca nhom" de chay PGPR theo ho so dang nhap.
                    </div>
                    {groupErrors[activeTargetType] ? (
                      <div className="mt-2 max-w-xl text-xs text-rose-700">{groupErrors[activeTargetType]}</div>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {recommendations.map((item, index) => (
                    <div key={`${item.id}-${index}`} className="rounded-md border bg-background p-4 transition-colors hover:border-primary/60">
                      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
                        <div className="min-w-0">
                          <div className="mb-1 flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className="rounded-md">
                              Rank #{index + 1}
                            </Badge>
                            <Badge variant="secondary" className="rounded-md">
                              {item.type ?? activeTargetType}
                            </Badge>
                          </div>
                          <Link
                            href={`/entities/${item.type ?? activeTargetType}/${item.id}`}
                            className="block text-lg font-semibold leading-snug hover:underline"
                          >
                            {item.name || item.id}
                          </Link>
                          <div className="mt-1 text-xs text-muted-foreground">ID: {item.id}</div>
                        </div>
                        <div className="flex md:justify-end">
                          <div className="rounded-md border bg-secondary/60 px-3 py-2 text-right">
                            <div className="text-xs text-muted-foreground">Score</div>
                            <div className="text-base font-bold">
                              {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 rounded-md bg-secondary/40 p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                          <Info className="h-3.5 w-3.5" />
                          XAI preview
                        </div>
                        <p className="text-sm leading-6 text-muted-foreground">{getXaiPreview(item)}</p>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        {item.scoring_method ? (
                          <Badge
                            variant={
                              item.scoring_method === "pgpr_policy" ||
                              item.scoring_method === "hybrid_embedding_path"
                                ? "default"
                                : "secondary"
                            }
                            className="rounded-md"
                          >
                            {item.scoring_method === "pgpr_policy"
                              ? "PGPR policy"
                              : item.scoring_method === "cypher_fallback"
                                ? "Cypher fallback"
                                : item.scoring_method === "hybrid_embedding_path"
                                  ? "Hybrid path+embedding"
                                  : item.scoring_method === "hybrid_embedding"
                                    ? "Hybrid embedding"
                                    : item.scoring_method}
                          </Badge>
                        ) : null}
                        {item.evidence_level ? (
                          <Badge variant="outline" className="rounded-md">
                            Evidence {item.evidence_level}
                          </Badge>
                        ) : null}
                        {item.cold_start ? (
                          <Badge variant="outline" className="rounded-md border-amber-300 text-amber-800">
                            Cold-start
                          </Badge>
                        ) : null}
                        {item.embedding_status ? (
                          <Badge variant="outline" className="rounded-md">
                            Embedding {item.embedding_status}
                          </Badge>
                        ) : null}
                        {item.data_quality_level ? (
                          <Badge variant="outline" className="rounded-md">
                            Data {item.data_quality_level}
                          </Badge>
                        ) : null}
                        {item.uses_provisional_data ? (
                          <Badge variant="outline" className="rounded-md border-amber-300 text-amber-800">
                            Unverified
                          </Badge>
                        ) : null}
                        <Badge variant="outline" className="rounded-md gap-1">
                          <Network className="h-3 w-3" />
                          {item.reasoning_paths?.length ?? 0} paths
                        </Badge>
                        {typeof item.path_diversity === "number" ? (
                          <Badge variant="outline" className="rounded-md">
                            Diversity {item.path_diversity}
                          </Badge>
                        ) : null}
                      </div>
                      {item.recommendation_message ? (
                        <p className="mt-2 text-xs text-amber-800">{item.recommendation_message}</p>
                      ) : null}
                      {item.fallback_reason ? (
                        <p className="mt-2 text-xs text-amber-800">{item.fallback_reason}</p>
                      ) : null}

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button variant="default" size="sm" onClick={() => void openDetailedExplanation(item)}>
                          Giai thich chi tiet
                        </Button>
                        {selectedSource ? (
                          <Link href={`/entities/${item.type ?? activeTargetType}/${item.id}`}>
                            <Button variant="outline" size="sm">
                              Xem chi tiet
                            </Button>
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </main>

      <Dialog
        open={Boolean(selectedExplanation)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedExplanation(null);
            setGeneratedExplanation(null);
            setExplanationError("");
            setIsExplanationLoading(false);
          }
        }}
      >
        <DialogContent className="max-h-[88vh] w-[calc(100vw-2rem)] max-w-[calc(100vw-2rem)] overflow-x-hidden overflow-y-auto rounded-md lg:max-w-6xl xl:max-w-7xl">
          <DialogHeader>
            <DialogTitle>Giai thich XAI chi tiet</DialogTitle>
            <DialogDescription>
              Ly do PGPR de xuat entity nay, kem reasoning paths neu backend tra ve.
            </DialogDescription>
          </DialogHeader>

          {selectedExplanation ? (
            <div className="min-w-0 space-y-5">
              <div className="rounded-md border bg-secondary/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold uppercase text-muted-foreground">Recommendation</div>
                    <div className="mt-1 text-lg font-semibold">{selectedExplanation.name || selectedExplanation.id}</div>
                    <div className="mt-1 text-xs text-muted-foreground">ID: {selectedExplanation.id}</div>
                  </div>
                  <Badge className="rounded-md" variant="secondary">
                    Score{" "}
                    {typeof selectedExplanation.score === "number" ? selectedExplanation.score.toFixed(3) : "N/A"}
                  </Badge>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
                <div>
                  <div className="text-sm font-semibold">Trang thai explanation</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {isExplanationLoading
                      ? "Dang request API explanations..."
                      : generatedExplanation?._cache?.hit
                        ? "Service layer tra ve tu cache, khong sinh lai XAI."
                        : generatedExplanation
                          ? "Service layer vua sinh moi XAI va luu cache."
                          : "Chua co explanation."}
                  </div>
                  {generatedExplanation?._cache?.key ? (
                    <div className="mt-1 break-all text-[11px] text-muted-foreground">
                      Cache key: {generatedExplanation._cache.key}
                    </div>
                  ) : null}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void regenerateExplanation()}
                  disabled={isExplanationLoading}
                >
                  {isExplanationLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Tao lai giai thich
                </Button>
              </div>

              <section className="space-y-3">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  XAI explanation tu API /api/v1/explanations
                </h3>
                <div className="rounded-md border p-4">
                  {isExplanationLoading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Dang goi model XAI de tao giai thich...
                    </div>
                  ) : explanationError ? (
                    <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                      {explanationError}
                    </div>
                  ) : generatedExplanation?.natural_language ? (
                    <XaiTextBlock text={generatedExplanation.natural_language} />
                  ) : (
                    <XaiTextBlock text={getRecommendationExplanation(selectedExplanation)} />
                  )}
                </div>
              </section>

              {generatedExplanation?.confidence ? (
                <section className="min-w-0 space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Confidence
                  </h3>
                  <ConfidenceBlock confidence={generatedExplanation.confidence} />
                </section>
              ) : null}

              {selectedExplanation.reasoning_paths?.length ? (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Reasoning paths
                  </h3>
                  <div className="min-w-0 space-y-2">
                    {selectedExplanation.reasoning_paths.map((path, index) => (
                      <ReasoningPathCard
                        key={index}
                        path={path}
                        index={index}
                        source={selectedSource}
                        target={selectedExplanation}
                      />
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
