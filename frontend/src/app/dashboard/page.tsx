"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  api,
  ApiEntity,
  EntityType,
  ExplanationResponse,
  getRecommendationExplanation,
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
  const router = useRouter();
  const [limit, setLimit] = useState("5");
  const [activeTargetType, setActiveTargetType] = useState<EntityType>("project");
  const [recommendationGroups, setRecommendationGroups] = useState<Partial<Record<EntityType, RecommendationItem[]>>>({});
  const [groupErrors, setGroupErrors] = useState<Partial<Record<EntityType, string>>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [selectedSource, setSelectedSource] = useState<ApiEntity | null>(null);
  const [adminSourceType, setAdminSourceType] = useState<EntityType>("project");
  const [adminSourceId, setAdminSourceId] = useState("");
  const [adminRecommendationMode, setAdminRecommendationMode] = useState<"public" | "personal">("public");
  const [selectedExplanation, setSelectedExplanation] = useState<RecommendationItem | null>(null);
  const [generatedExplanation, setGeneratedExplanation] = useState<ExplanationResponse["data"] | null>(null);
  const [isExplanationLoading, setIsExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState("");
  const [recommendationMode, setRecommendationMode] = useState<"public" | "personal">("public");

  useEffect(() => {
    if (user?.account_role === "admin" || user?.account_role === "root_admin") {
      router.replace("/admin");
    }
  }, [router, user?.account_role]);

  const isAdminUser = user?.account_role === "admin" || user?.account_role === "root_admin";
  const userSourceEntity = useMemo(() => getUserSourceEntity(user), [user]);
  const adminSourceEntity = useMemo<ApiEntity | null>(() => {
    const sourceId = adminSourceId.trim();
    if (!isAdminUser || !sourceId) return null;
    return {
      id: sourceId,
      name: `${getEntityOption(adminSourceType).label} ${sourceId}`,
      type: adminSourceType,
    };
  }, [adminSourceId, adminSourceType, isAdminUser]);
  const sourceEntity = adminSourceEntity ?? userSourceEntity;
  const activeRecommendationMode = adminSourceEntity ? adminRecommendationMode : "personal";
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
    setRecommendationMode(activeRecommendationMode);

    try {
      const settledResults = await Promise.allSettled(
        multiTargetTypes.map(async (targetType) => {
          const response = await api.recommend(
            sourceEntity.id,
            sourceEntity.type,
            targetType,
            Number(limit) || 5,
            activeRecommendationMode,
            activeRecommendationMode === "personal" ? user?.id : undefined,
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
    <div className="min-h-svh bg-[linear-gradient(180deg,#f8fafc_0%,#ffffff_44%,#f8fafc_100%)]">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-8 px-6 py-8">
        {/* Hero Section */}
        <section className="overflow-hidden rounded-[2rem] border border-slate-200/70 bg-white shadow-xl shadow-slate-200/70 lg:grid lg:grid-cols-[1.08fr_0.92fr]">
          <div className="relative overflow-hidden p-8 text-slate-950 md:p-10">
            
            <div className="relative z-10 flex flex-col justify-between h-full space-y-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700">
                  <GitFork className="h-3.5 w-3.5" /> PGPR Engine
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                  <Database className="h-3.5 w-3.5" /> Knowledge Graph
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-violet-100 bg-violet-50 px-3 py-1 text-xs font-bold text-violet-700">
                  <Sparkles className="h-3.5 w-3.5" /> Explainable AI
                </span>
              </div>
              <div className="space-y-4">
                <h1 className="max-w-2xl text-4xl font-black tracking-tight text-slate-950 md:text-5xl">Gợi ý hợp tác R&D dựa trên Knowledge Graph</h1>
                <p className="max-w-2xl text-base font-medium leading-7 text-slate-600">
                  Hệ thống dùng hồ sơ của bạn làm nguồn suy diễn, kết hợp PGPR, embedding và XAI để tìm project,
                  chuyên gia, doanh nghiệp hoặc quỹ tài trợ phù hợp.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Source</div>
                  <div className="mt-1 truncate text-sm font-extrabold text-slate-900">
                    {sourceEntity?.name ?? "Chưa liên kết hồ sơ"}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Mode</div>
                  <div className="mt-1 text-sm font-extrabold text-slate-900">{activeRecommendationMode}</div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Results</div>
                  <div className="mt-1 text-sm font-extrabold text-slate-900">{totalRecommendationCount} gợi ý</div>
                </div>
              </div>
            </div>
          </div>
          <div className="relative flex min-h-[300px] items-center justify-center overflow-hidden border-t border-slate-200 bg-slate-950 p-8 lg:border-l lg:border-t-0">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(34,211,238,0.20),transparent_30%),radial-gradient(circle_at_84%_78%,rgba(16,185,129,0.14),transparent_30%)]" />
            <div className="relative w-full max-w-md rounded-3xl border border-white/10 bg-white/10 p-6 shadow-2xl backdrop-blur">
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold uppercase tracking-wider text-cyan-200">Knowledge Graph</div>
                  <div className="mt-1 text-lg font-black text-white">Hybrid reasoning map</div>
                </div>
                <Badge className="rounded-full border-cyan-300/30 bg-cyan-400/10 px-3 py-1 text-cyan-100">Live</Badge>
              </div>
              <svg className="h-44 w-full" viewBox="0 0 360 180" role="img" aria-label="Knowledge graph preview">
                <line x1="72" y1="90" x2="174" y2="42" stroke="#67e8f9" strokeOpacity="0.55" strokeWidth="2" />
                <line x1="72" y1="90" x2="174" y2="136" stroke="#a7f3d0" strokeOpacity="0.55" strokeWidth="2" />
                <line x1="174" y1="42" x2="286" y2="82" stroke="#c4b5fd" strokeOpacity="0.55" strokeWidth="2" />
                <line x1="174" y1="136" x2="286" y2="82" stroke="#67e8f9" strokeOpacity="0.55" strokeWidth="2" />
                <line x1="174" y1="90" x2="286" y2="82" stroke="#fef3c7" strokeOpacity="0.5" strokeWidth="2" />
                <circle cx="72" cy="90" r="31" fill="#0f172a" stroke="#22d3ee" strokeWidth="3" />
                <text x="72" y="86" textAnchor="middle" fill="#e0f2fe" fontSize="11" fontWeight="700">Expert</text>
                <text x="72" y="102" textAnchor="middle" fill="#7dd3fc" fontSize="9">source</text>
                <circle cx="174" cy="42" r="24" fill="#111827" stroke="#34d399" strokeWidth="3" />
                <text x="174" y="46" textAnchor="middle" fill="#d1fae5" fontSize="10" fontWeight="700">Skill</text>
                <circle cx="174" cy="136" r="24" fill="#111827" stroke="#a78bfa" strokeWidth="3" />
                <text x="174" y="140" textAnchor="middle" fill="#ede9fe" fontSize="10" fontWeight="700">Topic</text>
                <circle cx="174" cy="90" r="20" fill="#111827" stroke="#fbbf24" strokeWidth="3" />
                <text x="174" y="94" textAnchor="middle" fill="#fef3c7" fontSize="9" fontWeight="700">XAI</text>
                <circle cx="286" cy="82" r="34" fill="#0f172a" stroke="#2dd4bf" strokeWidth="3" />
                <text x="286" y="78" textAnchor="middle" fill="#ccfbf1" fontSize="11" fontWeight="700">Project</text>
                <text x="286" y="95" textAnchor="middle" fill="#5eead4" fontSize="9">target</text>
              </svg>
              <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <div className="text-lg font-black text-white">PGPR</div>
                  <div className="text-[10px] font-semibold text-slate-400">Path score</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <div className="text-lg font-black text-white">XAI</div>
                  <div className="text-[10px] font-semibold text-slate-400">Evidence</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <div className="text-lg font-black text-white">KG</div>
                  <div className="text-[10px] font-semibold text-slate-400">Graph data</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Quick Links Section */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {entityOptions.map((option) => {
            const Icon = option.icon;
            let iconWrapperBg = "";
            let iconColor = "";
            
            if (option.type === "project") {
              iconWrapperBg = "bg-cyan-50 text-cyan-600 border-cyan-100";
              iconColor = "text-cyan-600";
            } else if (option.type === "expert") {
              iconWrapperBg = "bg-teal-50 text-teal-600 border-teal-100";
              iconColor = "text-teal-600";
            } else if (option.type === "funder") {
              iconWrapperBg = "bg-orange-50 text-orange-600 border-orange-100";
              iconColor = "text-orange-600";
            } else {
              iconWrapperBg = "bg-fuchsia-55 bg-fuchsia-50 text-fuchsia-600 border-fuchsia-100";
              iconColor = "text-fuchsia-600";
            }

            return (
              <Link href={`/search?type=${option.type}`} key={option.type}>
                <Card className="group h-full cursor-pointer overflow-hidden rounded-3xl border-slate-200/70 bg-white shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-slate-200/80">
                  <CardContent className="flex items-center justify-between gap-4 p-5">
                    <div className="flex items-center gap-4">
                      <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border ${iconWrapperBg} transition-transform duration-300 group-hover:scale-105`}>
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="font-extrabold tracking-tight text-slate-900 transition-colors group-hover:text-primary">{option.collectionLabel}</div>
                        <div className="mt-1 text-xs font-semibold text-slate-500">Duyệt dữ liệu và gợi ý chéo</div>
                      </div>
                    </div>
                    <ArrowRight className="h-4 w-4 text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-primary" />
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </section>

        {/* Workspace and Recommendations */}
        <section className="grid gap-6 lg:grid-cols-[400px_1fr]">
          {/* Workspace Panel */}
          <Card className="h-[860px] self-start overflow-hidden rounded-2xl border-slate-200/60 bg-white shadow-sm">
            <CardHeader className="border-b border-slate-100 bg-slate-50/40">
              <CardTitle className="text-base font-bold tracking-tight text-slate-800">Recommendation Workspace</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5 pt-5">
              <div className="rounded-xl border border-indigo-100/80 bg-indigo-50/30 p-4">
                <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">Source Profile Đang Dùng</div>
                {isAdminUser ? (
                  <div className="mt-3.5 rounded-xl border border-slate-150 bg-white p-4 shadow-sm">
                    <div className="mb-3.5 flex items-center justify-between gap-3">
                      <div>
                        <div className="text-xs font-bold text-slate-800">Admin Test Source</div>
                        <p className="mt-1 text-[10px] leading-relaxed text-slate-400">
                          Nhập source thủ công để chạy thử nghiệm các thuật toán PGPR.
                        </p>
                      </div>
                      <Badge variant="outline" className="rounded-md bg-slate-50 text-[10px] font-bold border-slate-200">
                        admin only
                      </Badge>
                    </div>
                    <div className="grid gap-3.5">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-bold text-slate-500">Source Type</Label>
                        <Select value={adminSourceType} onValueChange={(value) => setAdminSourceType(value as EntityType)}>
                          <SelectTrigger className="rounded-xl border-slate-200 h-9 text-xs font-semibold">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="rounded-xl">
                            {entityOptions.map((option) => (
                              <SelectItem key={option.type} value={option.type} className="text-xs rounded-lg">
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-bold text-slate-500">Source ID</Label>
                        <Input
                          value={adminSourceId}
                          onChange={(event) => setAdminSourceId(event.target.value)}
                          className="rounded-xl border-slate-200 h-9 text-xs font-medium"
                          placeholder="Ví dụ: prj_001, exp_001..."
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-bold text-slate-500">Chế độ Gợi ý</Label>
                        <Select
                          value={adminRecommendationMode}
                          onValueChange={(value) => setAdminRecommendationMode(value as "public" | "personal")}
                        >
                          <SelectTrigger className="rounded-xl border-slate-200 h-9 text-xs font-semibold">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="rounded-xl">
                            <SelectItem value="public" className="text-xs rounded-lg">Public mode</SelectItem>
                            <SelectItem value="personal" className="text-xs rounded-lg">Personal mode</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <p className="mt-3 text-[10px] leading-relaxed text-slate-400">
                      Bỏ trống Source ID để tự động quay lại linked profile của bạn.
                    </p>
                  </div>
                ) : null}
                {sourceEntity ? (
                  <div className="mt-3.5 space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-base font-bold text-slate-800 leading-snug tracking-tight">{sourceEntity.name}</div>
                        <div className="mt-1.5 break-all text-[11px] font-semibold text-indigo-500">ID: {sourceEntity.id}</div>
                      </div>
                      <Badge className="rounded-full px-2.5 py-0.5 text-[10px] font-bold bg-indigo-50 text-indigo-600 border-indigo-200" variant="outline">
                        {sourceEntity.type}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2.5 text-[11px]">
                      <div className="rounded-xl border border-slate-100 bg-white p-3 shadow-sm">
                        <div className="font-semibold text-slate-400">Scope</div>
                        <div className="mt-1 font-bold text-slate-700">
                          {user?.linked_entity?.participation_scope ?? "unknown"}
                        </div>
                      </div>
                      <div className="rounded-xl border border-slate-100 bg-white p-3 shadow-sm">
                        <div className="font-semibold text-slate-400">KG Status</div>
                        <div className="mt-1 font-bold text-slate-700">{user?.linked_entity?.kg_sync_status ?? "unknown"}</div>
                      </div>
                    </div>
                    <p className="text-[10px] leading-relaxed text-slate-500 font-medium">
                      {adminSourceEntity
                        ? "Đang sử dụng Source do Admin tùy chỉnh để phục vụ mục đích kiểm thử hệ thống."
                        : "Sử dụng tài khoản cá nhân đã xác thực, thuật toán tự động lọc và bảo vệ tính an toàn dữ liệu."}
                    </p>
                  </div>
                ) : (
                  <div className="mt-3.5 rounded-xl border border-amber-200 bg-amber-50/50 p-4 text-xs font-semibold text-amber-800 leading-relaxed">
                    {!user ? (
                      <div className="space-y-3">
                        <p>Chưa đăng nhập. Vui lòng đăng nhập để sử dụng tính năng recommendation.</p>
                        <Link href="/auth/login">
                          <Button size="sm" className="rounded-lg bg-amber-600 px-3 text-xs font-bold text-white hover:bg-amber-700">
                            Đăng nhập
                          </Button>
                        </Link>
                      </div>
                    ) : (
                      <p>Tài khoản chưa được liên kết hồ sơ. Hãy hoàn thiện thông tin tại trang Profile cá nhân.</p>
                    )}
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold text-slate-500">Số lượng kết quả hiển thị</Label>
                <Input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" className="rounded-xl border-slate-200 h-10 text-sm font-semibold" />
              </div>

              <Button 
                className="w-full gap-2 rounded-xl h-11 text-xs font-bold bg-gradient-to-r from-violet-600 to-indigo-600 text-white hover:from-violet-700 hover:to-indigo-700 transition-all duration-300 shadow-md shadow-indigo-100" 
                onClick={() => void runMultiRecommendation()} 
                disabled={isLoading || !sourceEntity}
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin text-white" /> : <Sparkles className="h-4 w-4 text-white" />}
                Gợi ý tất cả nhóm
              </Button>

              <Separator className="bg-slate-100" />

              <div className="grid gap-2">
                {multiTargetTypes.map((type) => {
                  const option = getEntityOption(type);
                  const count = recommendationGroups[type]?.length ?? 0;
                  const Icon = option.icon;
                  const isSelected = activeTargetType === type;
                  return (
                    <Button
                      key={type}
                      type="button"
                      variant={isSelected ? "default" : "outline"}
                      className={`justify-between h-10 rounded-xl px-4 text-xs font-bold transition-all duration-300 border-slate-200 ${
                        isSelected 
                          ? "bg-primary text-white shadow-md shadow-indigo-100" 
                          : "bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-800"
                      }`}
                      onClick={() => setActiveTargetType(type)}
                    >
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4" />
                        {option.collectionLabel}
                      </span>
                      <Badge variant={isSelected ? "secondary" : "outline"} className={`rounded-md px-2 py-0.5 text-[10px] font-bold border-transparent ${
                        isSelected 
                          ? "bg-white/20 text-white" 
                          : "bg-slate-100 text-slate-600"
                      }`}>
                        {count}
                      </Badge>
                    </Button>
                  );
                })}
              </div>

              <Separator className="bg-slate-100" />

              {sourceEntity ? (
                <div className="grid gap-2.5">
                  <Link href={`/graph/neighbors?type=${sourceEntity.type}&id=${sourceEntity.id}`} className="w-full">
                    <Button variant="outline" className="w-full justify-between h-10 rounded-xl text-xs font-semibold border-slate-200 hover:bg-slate-50 text-slate-600">
                      Xem Ego Neighbor Graph cá nhân
                      <ArrowRight className="h-4 w-4 text-slate-400" />
                    </Button>
                  </Link>
                  <Link href={`/search?type=${activeTargetType}`} className="w-full">
                    <Button variant="outline" className="w-full justify-between h-10 rounded-xl text-xs font-semibold border-slate-200 hover:bg-slate-50 text-slate-600">
                      Duyệt & lọc thực thể riêng lẻ
                      <ArrowRight className="h-4 w-4 text-slate-400" />
                    </Button>
                  </Link>
                </div>
              ) : null}
            </CardContent>
          </Card>

          {/* Recommendations Content */}
          <Card className="flex h-[860px] flex-col overflow-hidden rounded-2xl border-slate-200/60 bg-white shadow-sm">
            <CardHeader className="shrink-0 border-b border-slate-100 bg-slate-50/20 pb-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <CardTitle className="text-lg font-bold tracking-tight text-slate-800">{getEntityOption(activeTargetType).collectionLabel} Recommendations</CardTitle>
                  <p className="mt-1 text-xs font-medium text-slate-400">
                    Bảng gợi ý xếp hạng tương quan. Bấm nút "Giải thích chi tiết" để chạy động giải thích XAI.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={recommendationMode === "personal" ? "secondary" : "outline"} className="rounded-full px-3 py-0.5 text-[10px] font-bold border-slate-200/60">
                    {recommendationMode} mode
                  </Badge>
                  <Badge variant="outline" className="rounded-full px-3 py-0.5 text-[10px] font-bold bg-slate-50 border-slate-200 text-slate-600">
                    {totalRecommendationCount} tổng kết quả
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-y-auto pr-3 pt-6">
              {recommendationError ? (
                <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4 text-xs font-semibold text-rose-700 leading-relaxed">
                  {recommendationError}
                </div>
              ) : recommendations.length === 0 ? (
                <div className="flex min-h-[360px] flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-slate-250 p-6 text-center bg-slate-50/20">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
                    <Search className="h-5 w-5" />
                  </div>
                  <div className="space-y-1 max-w-sm">
                    <div className="text-sm font-bold text-slate-700">Chưa có kết quả gợi ý</div>
                    <div className="text-xs text-slate-400 leading-relaxed font-medium">
                      Nhấp nút "Gợi ý tất cả nhóm" tại bảng Workspace để bắt đầu lập lịch suy diễn PGPR.
                    </div>
                    {groupErrors[activeTargetType] ? (
                      <div className="mt-3.5 text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 rounded-xl p-3">{groupErrors[activeTargetType]}</div>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {recommendations.map((item, index) => (
                    <div key={`${item.id}-${index}`} className="rounded-2xl border border-slate-200/60 bg-white p-5 transition-all duration-300 premium-card-hover relative overflow-hidden">
                      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
                        <div className="min-w-0 space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className="rounded-md bg-slate-50 text-[10px] font-bold border-slate-200/80 text-slate-600 px-2 py-0.5">
                              Hạng #{index + 1}
                            </Badge>
                            <Badge className="rounded-md bg-indigo-50 text-[10px] font-bold border-indigo-150 text-indigo-600 px-2 py-0.5" variant="outline">
                              {item.type ?? activeTargetType}
                            </Badge>
                          </div>
                          <Link
                            href={`/entities/${item.type ?? activeTargetType}/${item.id}`}
                            className="block text-base font-bold text-slate-800 leading-snug tracking-tight hover:text-primary hover:underline transition-colors"
                          >
                            {item.name || item.id}
                          </Link>
                          <div className="text-[11px] font-semibold text-slate-400">ID thực thể: {item.id}</div>
                        </div>
                        <div className="flex md:justify-end shrink-0">
                          <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 text-right shadow-sm min-w-[90px] h-fit">
                            <div className="text-[9px] font-extrabold uppercase tracking-wider text-slate-400">Score</div>
                            <div className="text-lg font-extrabold text-indigo-600 mt-0.5">
                              {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* XAI Preview Card */}
                      <div className="mt-4 rounded-xl bg-gradient-to-r from-slate-50 to-indigo-50/20 p-4 border border-slate-100/80">
                        <div className="mb-2 flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">
                          <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
                          AI-Generated Preview (XAI)
                        </div>
                        <p className="text-xs leading-relaxed text-slate-500 font-medium">{getXaiPreview(item)}</p>
                      </div>

                      <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px] font-bold text-slate-400">
                        {item.scoring_method ? (
                          <Badge
                            className={`rounded-md px-2 py-0.5 border-transparent text-[10px] ${
                              item.scoring_method === "pgpr_policy" || item.scoring_method === "hybrid_embedding_path"
                                ? "bg-violet-50 text-violet-600"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {item.scoring_method === "pgpr_policy"
                              ? "PGPR Policy Network"
                              : item.scoring_method === "cypher_fallback"
                                ? "Neo4j Cypher Fallback"
                                : item.scoring_method === "hybrid_embedding_path"
                                  ? "Hybrid Path + Embedding"
                                  : item.scoring_method === "hybrid_embedding"
                                    ? "Hybrid Embedding"
                                    : item.scoring_method}
                          </Badge>
                        ) : null}
                        {item.evidence_level ? (
                          <Badge variant="outline" className="rounded-md border-slate-200 text-slate-500 px-2 py-0.5">
                            Minh chứng: {item.evidence_level}
                          </Badge>
                        ) : null}
                        {item.cold_start ? (
                          <Badge className="rounded-md border-transparent bg-amber-50 text-amber-600 px-2 py-0.5">
                            Cold-start
                          </Badge>
                        ) : null}
                        {item.embedding_status ? (
                          <Badge variant="outline" className="rounded-md border-slate-200 text-slate-500 px-2 py-0.5">
                            Embedding: {item.embedding_status}
                          </Badge>
                        ) : null}
                        {item.uses_provisional_data ? (
                          <Badge className="rounded-md border-transparent bg-rose-50 text-rose-600 px-2 py-0.5">
                            Hồ sơ chưa duyệt (Unverified)
                          </Badge>
                        ) : null}
                        <Badge variant="outline" className="rounded-md border-slate-200 text-slate-500 gap-1 px-2 py-0.5">
                          <Network className="h-3 w-3 text-slate-400" />
                          {item.reasoning_paths?.length ?? 0} paths
                        </Badge>
                        {typeof item.path_diversity === "number" ? (
                          <Badge variant="outline" className="rounded-md border-slate-200 text-slate-500 px-2 py-0.5">
                            Đa dạng: {item.path_diversity}
                          </Badge>
                        ) : null}
                      </div>

                      {item.recommendation_message ? (
                        <p className="mt-3 text-[11px] font-semibold text-amber-600 bg-amber-50/50 border border-amber-100 rounded-xl p-2.5">{item.recommendation_message}</p>
                      ) : null}
                      {item.fallback_reason ? (
                        <p className="mt-3 text-[11px] font-semibold text-amber-600 bg-amber-50/50 border border-amber-100 rounded-xl p-2.5">{item.fallback_reason}</p>
                      ) : null}

                      <div className="mt-4 flex flex-wrap gap-2 pt-2 border-t border-slate-100">
                        <Button 
                          variant="default" 
                          size="sm" 
                          className="rounded-xl px-4 text-xs font-bold shadow-md shadow-indigo-50/50" 
                          onClick={() => void openDetailedExplanation(item)}
                        >
                          Giải thích chi tiết
                        </Button>
                        {selectedSource ? (
                          <Link href={`/entities/${item.type ?? activeTargetType}/${item.id}`}>
                            <Button variant="outline" size="sm" className="rounded-xl px-4 text-xs font-bold border-slate-200 hover:bg-slate-50 text-slate-600">
                              Xem chi tiết hồ sơ
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
        <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-6xl overflow-x-hidden overflow-y-auto rounded-2xl border-slate-200 shadow-xl bg-white p-6 md:p-8">
          <DialogHeader className="pb-4 border-b border-slate-150">
            <DialogTitle className="text-xl font-bold tracking-tight text-slate-800 flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-indigo-500" />
              Giải thích Chi tiết (XAI Engine)
            </DialogTitle>
            <DialogDescription className="text-xs font-medium text-slate-400 mt-1">
              Phân tích vết đường dẫn suy luận đồ thị (KG Reasoning Paths) tạo sinh đề xuất.
            </DialogDescription>
          </DialogHeader>

          {selectedExplanation ? (
            <div className="min-w-0 space-y-6 pt-6">
              {/* Destination Card */}
              <div className="rounded-2xl border border-indigo-50 bg-indigo-50/20 p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">Thực thể Đề xuất</div>
                    <div className="text-lg font-bold tracking-tight text-slate-800">{selectedExplanation.name || selectedExplanation.id}</div>
                    <div className="text-xs font-semibold text-slate-400">ID: {selectedExplanation.id}</div>
                  </div>
                  <div className="rounded-xl border border-indigo-100 bg-white p-3 shadow-sm text-right shrink-0 h-fit">
                    <div className="text-[9px] font-extrabold uppercase tracking-wider text-slate-400">Độ tin cậy gợi ý</div>
                    <div className="text-base font-extrabold text-indigo-600 mt-0.5">
                      {typeof selectedExplanation.score === "number" ? (selectedExplanation.score * 100).toFixed(1) : "N/A"}%
                    </div>
                  </div>
                </div>
              </div>

              {/* Cache status info bar */}
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-slate-150 p-4 bg-slate-50/40">
                <div className="space-y-0.5">
                  <div className="text-xs font-bold text-slate-700">Trạng thái XAI Model</div>
                  <div className="text-[11px] font-medium text-slate-400 leading-relaxed">
                    {isExplanationLoading
                      ? "Đang lập biểu đồ suy diễn và gọi XAI Model..."
                      : generatedExplanation?._cache?.hit
                        ? "Dữ liệu truy xuất trực tiếp từ Cache, giảm độ trễ phản hồi."
                        : generatedExplanation
                          ? "Mô hình đã sinh cấu trúc giải thích mới và ghi vào hệ thống Cache."
                          : "Đang chờ sinh cấu trúc..."}
                  </div>
                  {generatedExplanation?._cache?.key ? (
                    <div className="text-[10px] font-semibold text-slate-400 font-mono break-all mt-1 bg-white border rounded-md px-2 py-0.5">
                      Cache-key: {generatedExplanation._cache.key}
                    </div>
                  ) : null}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-xl h-9 text-xs font-bold border-slate-200 hover:bg-slate-50 text-slate-600 shrink-0"
                  onClick={() => void regenerateExplanation()}
                  disabled={isExplanationLoading}
                >
                  {isExplanationLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin text-slate-500" /> : null}
                  Tạo lại giải thích
                </Button>
              </div>

              {/* Natural Language Explanation block */}
              <section className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Info className="h-4 w-4 text-slate-400" />
                  Mô tả giải thích tự nhiên
                </h3>
                <div className="rounded-2xl border border-slate-200/60 p-5 bg-white shadow-sm leading-relaxed">
                  {isExplanationLoading ? (
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-400 py-4">
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                      Mô hình AI đang phân tích dữ liệu, vui lòng đợi trong giây lát...
                    </div>
                  ) : explanationError ? (
                    <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4 text-xs font-semibold text-rose-700">
                      {explanationError}
                    </div>
                  ) : generatedExplanation?.natural_language ? (
                    <XaiTextBlock text={generatedExplanation.natural_language} />
                  ) : (
                    <XaiTextBlock text={getRecommendationExplanation(selectedExplanation)} />
                  )}
                </div>
              </section>

              {/* Confidence gauges */}
              {generatedExplanation?.confidence ? (
                <section className="min-w-0 space-y-2.5">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4 text-slate-400" />
                    Đánh giá độ tin cậy thành phần
                  </h3>
                  <ConfidenceBlock confidence={generatedExplanation.confidence} />
                </section>
              ) : null}

              {/* Reasoning paths list */}
              {selectedExplanation.reasoning_paths?.length ? (
                <section className="space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <Network className="h-4 w-4 text-slate-400" />
                    Bản đồ đường dẫn lập luận đồ thị (Reasoning Paths)
                  </h3>
                  <div className="min-w-0 space-y-3">
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
