"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  GitMerge,
  Info,
  Loader2,
  Network,
  Search,
  Shield,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  UserCog,
  Users,
} from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/lib/auth";
import {
  ApiEntity,
  AdminEntityRow,
  AdminGovernanceReviewRow,
  AdminOrphanRow,
  AdminUserRow,
  api,
  CanonicalTaxonomyResponse,
  EmbeddingJobRow,
  EmbeddingPipelineStatus,
  EntityType,
  ExplanationResponse,
  getRecommendationExplanation,
  HealthResponse,
  RecommendationItem,
} from "@/lib/api";

gsap.registerPlugin(ScrollTrigger);

const KG_FILTERS = [
  { value: "all", label: "Tất cả trạng thái KG" },
  { value: "sync_failed", label: "Lỗi đồng bộ (sync_failed)" },
  { value: "merge_required", label: "Cần gộp (merge_required)" },
  { value: "synced_unverified", label: "Đã đồng bộ - Chưa xác thực (synced_unverified)" },
  { value: "not_synced", label: "Chưa đồng bộ (not_synced)" },
  { value: "verified", label: "Đã xác thực (synced_verified)" },
  { value: "rejected", label: "Bị từ chối (rejected)" },
  { value: "disabled", label: "Vô hiệu hóa (disabled)" },
];

const TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: "all", label: "Tất cả loại" },
  { value: "expert", label: "Chuyên gia" },
  { value: "enterprise", label: "Doanh nghiệp" },
  { value: "funder", label: "Nhà tài trợ" },
  { value: "project", label: "Dự án" },
];

const REVIEW_STATUS_FILTERS = [
  { value: "all", label: "Tất cả trạng thái review" },
  { value: "needs_more_info", label: "Cần thêm thông tin (needs_more_info)" },
  { value: "merge_required", label: "Cần gộp (merge_required)" },
  { value: "pending_review", label: "Chờ duyệt (pending_review)" },
  { value: "rejected", label: "Bị từ chối (rejected)" },
  { value: "verified", label: "Đã xác thực (verified)" },
];

const QUALITY_FILTERS = [
  { value: "all", label: "Tất cả mức chất lượng" },
  { value: "poor", label: "Kém" },
  { value: "fair", label: "Trung bình" },
  { value: "good", label: "Tốt" },
  { value: "excellent", label: "Xuất sắc" },
];

const ADMIN_TEST_ENTITY_OPTIONS: Array<{ value: EntityType; label: string }> = [
  { value: "project", label: "Dự án" },
  { value: "expert", label: "Chuyên gia" },
  { value: "enterprise", label: "Doanh nghiệp" },
  { value: "funder", label: "Nhà tài trợ" },
];

const ENTITY_ROWS_PER_PAGE = 6;
type AdminTab = "overview" | "governance" | "entities" | "embedding" | "audit";

function tabFromHash(hash: string): AdminTab | null {
  const normalized = hash.replace("#", "");
  if (normalized === "review-queue") return "governance";
  if (normalized === "admin-users" || normalized === "audit-log") return "audit";
  if (normalized === "entity-review" || normalized === "entities") return "entities";
  if (normalized === "embedding" || normalized === "embedding-workers") return "embedding";
  if (normalized === "overview" || normalized === "system-test") return "overview";
  return null;
}

function hashFromTab(tab: AdminTab) {
  return {
    overview: "system-test",
    governance: "review-queue",
    entities: "entity-review",
    embedding: "embedding-workers",
    audit: "audit-log",
  }[tab];
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

function healthTone(value?: string) {
  const normalized = String(value ?? "").toLowerCase();
  if (["connected", "ready", "ok"].some((item) => normalized.includes(item))) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (normalized.includes("optional")) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-rose-200 bg-rose-50 text-rose-700";
}

function statusClass(value?: string | null) {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized.includes("verified") && !normalized.includes("unverified")) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (normalized.includes("rejected") || normalized.includes("disabled") || normalized.includes("failed")) {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  if (normalized.includes("merge") || normalized.includes("syncing") || normalized.includes("not_synced")) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  if (normalized.includes("unverified")) {
    return "border-sky-200 bg-sky-50 text-sky-700";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function compact(value: unknown, fallback = "-") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function cleanXaiText(text: string) {
  return text.replace(/\*\*/g, "").replace(/```/g, "").trim();
}

function getXaiPreview(item: RecommendationItem) {
  const text = cleanXaiText(getRecommendationExplanation(item));
  if (!text) return "Chưa có giải thích từ backend.";

  const firstUsefulLine = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0);

  if (!firstUsefulLine) return "Chưa có giải thích từ backend.";
  return firstUsefulLine.length > 170 ? `${firstUsefulLine.slice(0, 170)}...` : firstUsefulLine;
}

function XaiTextBlock({ text }: { text: string }) {
  const lines = cleanXaiText(text)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return <p className="text-sm text-muted-foreground">Chưa có nội dung giải thích.</p>;
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
              <div className="text-xs font-semibold uppercase text-muted-foreground">Mức độ</div>
              <div className="mt-1 font-semibold">{level}</div>
            </div>
          ) : null}

          {interpretation ? (
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Diễn giải</div>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{interpretation}</p>
            </div>
          ) : null}
        </div>
      </div>

      {componentEntries.length > 0 ? (
        <div className="mt-4 space-y-3">
          <div className="text-xs font-semibold uppercase text-muted-foreground">Thành phần điểm</div>
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
          <svg viewBox={`0 0 ${graphWidth} 170`} className="h-[170px] max-w-none shrink-0" style={{ width: `${graphWidth}px` }} role="img">
            <defs>
              {parts.map((_, partIndex) => (
                <marker
                  key={partIndex}
                  id={`admin-kg-path-arrow-${index}-${partIndex}`}
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
                  <rect x={labelX - 56} y={nodeY - 48} width="112" height="24" rx="4" className="fill-white stroke-slate-200" />
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
                    markerEnd={`url(#admin-kg-path-arrow-${index}-${partIndex})`}
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

function firstDuplicateCandidate(row: AdminEntityRow) {
  const candidates = row.duplicate_candidates ?? [];
  return candidates.length > 0 ? candidates[0] : null;
}

function parseUnmappedWarning(warning: string) {
  const match = warning.match(/^unmapped_(topic|skill|industry):(.+)$/);
  if (!match) return [];
  const taxonomyType = match[1] as "topic" | "skill" | "industry";
  return match[2]
    .split(",")
    .map((rawValue) => ({ taxonomyType, rawValue: rawValue.trim() }))
    .filter((item) => item.rawValue);
}

function orphanEntityType(row: AdminOrphanRow): EntityType | null {
  const label = String(row.labels?.[0] ?? "").toLowerCase();
  if (label === "project" || label === "expert" || label === "enterprise" || label === "funder") {
    return label;
  }
  return null;
}

function LimitSelector({ value, onChange, label = "Hiển thị" }: { value: number; onChange: (val: number) => void; label?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500 font-medium">
      <span>{label}:</span>
      <Select value={String(value)} onValueChange={(val) => onChange(Number(val))}>
        <SelectTrigger className="h-8 w-[72px] rounded-lg bg-white border-slate-200">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="10">10</SelectItem>
          <SelectItem value="15">15</SelectItem>
          <SelectItem value="25">25</SelectItem>
          <SelectItem value="50">50</SelectItem>
          <SelectItem value="100">100</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

export default function AdminPage() {
  const { user, isLoading: authLoading } = useAuth();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");
  const [tabLoading, setTabLoading] = useState(false);
  const [rows, setRows] = useState<AdminEntityRow[]>([]);
  const [governanceRows, setGovernanceRows] = useState<AdminGovernanceReviewRow[]>([]);
  const [governanceSummary, setGovernanceSummary] = useState<Record<string, unknown>>({});
  const [canonicalTaxonomy, setCanonicalTaxonomy] = useState<CanonicalTaxonomyResponse["data"] | null>(null);
  const [orphanRows, setOrphanRows] = useState<AdminOrphanRow[]>([]);
  const [selectedTaxonomyItem, setSelectedTaxonomyItem] = useState<{
    row: AdminGovernanceReviewRow;
    rawValue: string;
    taxonomyType: "topic" | "skill" | "industry";
  } | null>(null);
  const [taxonomyForm, setTaxonomyForm] = useState({ canonical_id: "", reason: "" });
  const [requestInfoItem, setRequestInfoItem] = useState<AdminGovernanceReviewRow | null>(null);
  const [requestInfoForm, setRequestInfoForm] = useState({ requested_fields: "", admin_note: "", reason: "" });
  const [orphanAction, setOrphanAction] = useState<{
    row: AdminOrphanRow;
    action: "mark" | "disable";
  } | null>(null);
  const [orphanReason, setOrphanReason] = useState("");
  const [adminUsers, setAdminUsers] = useState<AdminUserRow[]>([]);
  const [auditLogs, setAuditLogs] = useState<Record<string, unknown>[]>([]);
  const [pipeline, setPipeline] = useState<EmbeddingPipelineStatus | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [embeddingJobs, setEmbeddingJobs] = useState<EmbeddingJobRow[]>([]);
  const [embeddingBusy, setEmbeddingBusy] = useState(false);
  const [systemTestBusy, setSystemTestBusy] = useState(false);
  const [systemTestError, setSystemTestError] = useState("");
  const [systemSourceType, setSystemSourceType] = useState<EntityType>("project");
  const [systemSourceId, setSystemSourceId] = useState("prj_001");
  const [systemTargetType, setSystemTargetType] = useState<EntityType>("expert");
  const [systemLimit, setSystemLimit] = useState("5");
  const [systemMode, setSystemMode] = useState<"public" | "personal">("public");
  const [systemRecommendations, setSystemRecommendations] = useState<RecommendationItem[]>([]);
  const [systemRecommendationSource, setSystemRecommendationSource] = useState<ApiEntity | null>(null);
  const [selectedExplanation, setSelectedExplanation] = useState<RecommendationItem | null>(null);
  const [generatedExplanation, setGeneratedExplanation] = useState<ExplanationResponse["data"] | null>(null);
  const [isExplanationLoading, setIsExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState("");
  const [governanceBusy, setGovernanceBusy] = useState(false);
  const [kgFilter, setKgFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [entitySearch, setEntitySearch] = useState("");
  const [entityTotal, setEntityTotal] = useState(0);
  const [reviewStatusFilter, setReviewStatusFilter] = useState("all");
  const [qualityFilter, setQualityFilter] = useState("all");
  const [taxonomyFilter, setTaxonomyFilter] = useState("all");
  const [duplicateFilter, setDuplicateFilter] = useState("all");
  const [isLoading, setIsLoading] = useState(true);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [error, setError] = useState("");
  const [adminForm, setAdminForm] = useState({ email: "", password: "", full_name: "" });

  // Limit States for display constraints
  const [entityPage, setEntityPage] = useState(1);
  const [governanceLimit, setGovernanceLimit] = useState(15);
  const [orphanLimit, setOrphanLimit] = useState(15);
  const [embeddingLimit, setEmbeddingLimit] = useState(10);
  const [auditLimit, setAuditLimit] = useState(15);
  const [usersLimit, setUsersLimit] = useState(15);

  const canAdmin = user?.account_role === "admin" || user?.account_role === "root_admin";
  const isRootAdmin = user?.account_role === "root_admin";

  useEffect(() => {
    const applyHash = (hash = window.location.hash) => {
      const nextTab = tabFromHash(hash);
      if (nextTab) setActiveTab(nextTab);
    };

    const handleHashChange = () => applyHash();
    const handleAdminTabChange = (event: Event) => {
      const detail = (event as CustomEvent<{ hash?: string }>).detail;
      applyHash(detail?.hash ?? window.location.hash);
    };

    applyHash();
    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("admin-tab-change", handleAdminTabChange);
    return () => {
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("admin-tab-change", handleAdminTabChange);
    };
  }, []);

  const stats = useMemo(() => {
    const pending = rows.filter((row) =>
      ["synced_unverified", "merge_required", "sync_failed", "not_synced"].includes(String(row.kg_sync_status)),
    ).length;
    const rejected = rows.filter((row) => String(row.kg_sync_status).includes("rejected")).length;
    const verified = rows.filter((row) => String(row.kg_sync_status).includes("verified") && !String(row.kg_sync_status).includes("unverified")).length;
    const syncFailed = rows.filter((row) => String(row.kg_sync_status).includes("failed")).length;
    return { pending, rejected, verified, syncFailed, total: rows.length };
  }, [rows]);

  const entityTotalPages = Math.max(1, Math.ceil(entityTotal / ENTITY_ROWS_PER_PAGE));
  const entityPageNumbers = useMemo(() => {
    const start = Math.max(1, Math.min(entityPage - 1, Math.max(1, entityTotalPages - 2)));
    const end = Math.min(entityTotalPages, start + 2);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }, [entityPage, entityTotalPages]);

  useEffect(() => {
    setEntityPage(1);
  }, [entitySearch, typeFilter, kgFilter]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setError("Cần đăng nhập để mở trang admin.");
      setIsLoading(false);
      return;
    }
    if (!canAdmin) {
      setError("Tài khoản hiện tại không có quyền admin.");
      setIsLoading(false);
      return;
    }

    setTabLoading(true);
    setError("");

    const fetchers: Promise<any>[] = [];

    if (activeTab === "overview") {
      fetchers.push(
        api.health().then((res) => setHealth(res))
      );
      // Fetch 100 entities to calculate the dashboard overview stats
      fetchers.push(
        api.adminListEntities({ limit: 100 }).then((res) => {
          setRows(res.data ?? []);
        })
      );
    } else if (activeTab === "governance") {
      fetchers.push(
        api.adminGovernanceReviewQueue({
          entity_type: typeFilter === "all" ? undefined : (typeFilter as EntityType),
          review_status: reviewStatusFilter === "all" ? undefined : reviewStatusFilter,
          level: qualityFilter === "all" ? undefined : qualityFilter,
          has_unmapped_taxonomy: taxonomyFilter === "all" ? undefined : taxonomyFilter === "yes",
          has_duplicate_candidates: duplicateFilter === "all" ? undefined : duplicateFilter === "yes",
          limit: governanceLimit,
        }).then((res) => {
          setGovernanceRows(res.data ?? []);
          setGovernanceSummary(res.source_summary ?? {});
        })
      );
      fetchers.push(
        api.canonicalTaxonomy().then((res) => setCanonicalTaxonomy(res.data ?? null))
      );
      fetchers.push(
        api.adminListOrphans(orphanLimit).then((res) => setOrphanRows(res.data ?? []))
      );
    } else if (activeTab === "entities") {
      fetchers.push(
        api.adminListEntities({
          entity_type: typeFilter === "all" ? undefined : (typeFilter as EntityType),
          kg_sync_status: kgFilter === "all" ? undefined : kgFilter === "verified" ? "synced_verified" : kgFilter,
          search: entitySearch.trim() || undefined,
          limit: ENTITY_ROWS_PER_PAGE,
          page: entityPage,
        }).then((res) => {
          setRows(res.data ?? []);
          setEntityTotal(res.total ?? res.count ?? 0);
        })
      );
    } else if (activeTab === "embedding") {
      fetchers.push(
        api.adminEmbeddingPipelineStatus().then((res) => setPipeline(res.data ?? null))
      );
      fetchers.push(
        api.adminListEmbeddingJobs({ status: "failed", limit: embeddingLimit }).then((res) => setEmbeddingJobs(res.jobs ?? []))
      );
    } else if (activeTab === "audit") {
      fetchers.push(
        api.adminAuditLogs(auditLimit).then((res) => setAuditLogs(res.data ?? []))
      );
      if (isRootAdmin) {
        fetchers.push(
          api.adminListUsers(usersLimit).then((res) => setAdminUsers(res.data ?? []))
        );
      }
    }

    Promise.all(fetchers)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "Không tải được phân hệ dữ liệu admin");
      })
      .finally(() => {
        setTabLoading(false);
        setIsLoading(false);
      });
  }, [
    authLoading,
    user,
    canAdmin,
    activeTab,
    kgFilter,
    typeFilter,
    entitySearch,
    entityPage,
    reviewStatusFilter,
    qualityFilter,
    taxonomyFilter,
    duplicateFilter,
    governanceLimit,
    orphanLimit,
    embeddingLimit,
    auditLimit,
    usersLimit,
  ]);

  useEffect(() => {
    const scope = rootRef.current;
    if (!scope) return;
    const context = gsap.context(() => {
      gsap.fromTo(
        ".admin-reveal",
        { y: 28, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.65,
          ease: "power3.out",
          stagger: 0.08,
          scrollTrigger: {
            trigger: scope,
            start: "top 82%",
            once: true,
          },
        },
      );

      gsap.utils.toArray<HTMLElement>(".admin-scroll-reveal").forEach((element) => {
        gsap.fromTo(
          element,
          { y: 36, opacity: 0 },
          {
            y: 0,
            opacity: 1,
            duration: 0.55,
            ease: "power2.out",
            scrollTrigger: {
              trigger: element,
              start: "top 88%",
              once: true,
            },
          },
        );
      });
    }, scope);
    return () => context.revert();
  }, [rows.length, auditLogs.length, adminUsers.length]);

  const reloadAdminUsers = () => {
    if (!isRootAdmin) return;
    setIsUsersLoading(true);
    api
      .adminListUsers(usersLimit)
      .then((response) => setAdminUsers(response.data ?? []))
      .finally(() => setIsUsersLoading(false));
  };

  const createAdmin = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api.adminCreateAdmin(adminForm);
      setAdminForm({ email: "", password: "", full_name: "" });
      reloadAdminUsers();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không tạo được admin");
    }
  };

  const reloadEmbeddingPanel = async () => {
    if (!canAdmin) return;
    const [pipelineRes, jobsRes] = await Promise.all([
      api.adminEmbeddingPipelineStatus(),
      api.adminListEmbeddingJobs({ status: "failed", limit: 20 }),
    ]);
    setPipeline(pipelineRes.data ?? null);
    setEmbeddingJobs(jobsRes.jobs ?? []);
  };

  const retryFailedEmbeddings = async () => {
    setEmbeddingBusy(true);
    setError("");
    try {
      await api.adminRetryFailedEmbeddings({
        limit: 50,
        reason: "admin_console_retry",
        error_type: "temporary",
      });
      await reloadEmbeddingPanel();
      const logsRes = await api.adminAuditLogs(30);
      setAuditLogs(logsRes.data ?? []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thực hiện lại được embedding jobs");
    } finally {
      setEmbeddingBusy(false);
    }
  };

  const recomputeEmbedding = async (entityType: EntityType, entityId: string) => {
    setEmbeddingBusy(true);
    setError("");
    try {
      await api.adminRecomputeEmbedding(entityType, entityId, "admin_console_recompute");
      await reloadEmbeddingPanel();
      const logsRes = await api.adminAuditLogs(30);
      setAuditLogs(logsRes.data ?? []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không tái tính được embedding");
    } finally {
      setEmbeddingBusy(false);
    }
  };

  const reloadGovernance = async () => {
    const [governanceRes, orphanRes, logsRes] = await Promise.all([
      api.adminGovernanceReviewQueue({
        entity_type: typeFilter === "all" ? undefined : (typeFilter as EntityType),
        review_status: reviewStatusFilter === "all" ? undefined : reviewStatusFilter,
        level: qualityFilter === "all" ? undefined : qualityFilter,
        has_unmapped_taxonomy: taxonomyFilter === "all" ? undefined : taxonomyFilter === "yes",
        has_duplicate_candidates: duplicateFilter === "all" ? undefined : duplicateFilter === "yes",
        limit: 80,
      }),
      api.adminListOrphans(80),
      api.adminAuditLogs(30),
    ]);
    setGovernanceRows(governanceRes.data ?? []);
    setGovernanceSummary(governanceRes.source_summary ?? {});
    setOrphanRows(orphanRes.data ?? []);
    setAuditLogs(logsRes.data ?? []);
  };

  const submitTaxonomyAlias = async () => {
    if (!selectedTaxonomyItem) return;
    setGovernanceBusy(true);
    setError("");
    try {
      await api.adminMapTaxonomyAlias({
        taxonomy_type: selectedTaxonomyItem.taxonomyType,
        raw_value: selectedTaxonomyItem.rawValue,
        canonical_id: taxonomyForm.canonical_id,
        reason: taxonomyForm.reason,
      });
      setSelectedTaxonomyItem(null);
      setTaxonomyForm({ canonical_id: "", reason: "" });
      await reloadGovernance();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không mapping được taxonomy alias");
    } finally {
      setGovernanceBusy(false);
    }
  };

  const submitRequestMoreInfo = async () => {
    if (!requestInfoItem?.entity_type || !requestInfoItem.entity_id) return;
    const requestedFields = requestInfoForm.requested_fields
      .split(",")
      .map((field) => field.trim())
      .filter(Boolean);
    setGovernanceBusy(true);
    setError("");
    try {
      await api.adminRequestMoreInfo(requestInfoItem.entity_type, requestInfoItem.entity_id, {
        requested_fields: requestedFields,
        admin_note: requestInfoForm.admin_note,
        reason: requestInfoForm.reason,
      });
      setRequestInfoItem(null);
      setRequestInfoForm({ requested_fields: "", admin_note: "", reason: "" });
      await reloadGovernance();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không tạo được request yêu cầu thêm thông tin");
    } finally {
      setGovernanceBusy(false);
    }
  };

  const submitOrphanAction = async () => {
    if (!orphanAction) return;
    const entityType = orphanEntityType(orphanAction.row);
    const entityId = String(orphanAction.row.entity_id ?? "");
    if (!entityType || !entityId) return;
    setGovernanceBusy(true);
    setError("");
    try {
      if (orphanAction.action === "mark") {
        await api.adminMarkOrphanCleanupCandidate(entityType, entityId, orphanReason);
      } else {
        await api.adminDisableOrphanFromRecommendation(entityType, entityId, orphanReason);
      }
      setOrphanAction(null);
      setOrphanReason("");
      await reloadGovernance();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không xử lý được orphan");
    } finally {
      setGovernanceBusy(false);
    }
  };

  const changeRole = async (userId: string, action: "promote" | "demote") => {
    setError("");
    try {
      if (action === "promote") {
        await api.adminPromoteUser(userId);
      } else {
        await api.adminDemoteUser(userId);
      }
      reloadAdminUsers();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không cập nhật được quyền tài khoản");
    }
  };

  const runSystemRecommendationTest = async () => {
    const sourceId = systemSourceId.trim();
    if (!sourceId) {
      setSystemTestError("Cần nhập Source ID để test recommendation.");
      return;
    }

    setSystemTestBusy(true);
    setSystemTestError("");
    setSystemRecommendations([]);
    const sourceEntity: ApiEntity = {
      id: sourceId,
      name: `${ADMIN_TEST_ENTITY_OPTIONS.find((option) => option.value === systemSourceType)?.label ?? systemSourceType} ${sourceId}`,
      type: systemSourceType,
    };
    setSystemRecommendationSource(sourceEntity);
    try {
      const response = await api.recommend(
        sourceId,
        systemSourceType,
        systemTargetType,
        Number(systemLimit) || 5,
        systemMode,
        systemMode === "personal" ? user?.id : undefined,
      );
      setSystemRecommendations(normalizeRecommendations(response));
    } catch (requestError) {
      setSystemTestError(requestError instanceof Error ? requestError.message : "Không chạy được system test");
    } finally {
      setSystemTestBusy(false);
    }
  };

  const requestDetailedExplanation = async (item: RecommendationItem, forceRefresh = false) => {
    const sourceEntity =
      systemRecommendationSource ??
      (systemSourceId.trim()
        ? ({
            id: systemSourceId.trim(),
            name: `${ADMIN_TEST_ENTITY_OPTIONS.find((option) => option.value === systemSourceType)?.label ?? systemSourceType} ${systemSourceId.trim()}`,
            type: systemSourceType,
          } satisfies ApiEntity)
        : null);

    if (!sourceEntity) {
      setExplanationError("Không tìm thấy source để tạo giải thích XAI.");
      return;
    }

    setExplanationError("");
    setGeneratedExplanation(null);
    setIsExplanationLoading(true);
    try {
      const response = await api.explain(item, sourceEntity, item.type ?? systemTargetType, "llm", forceRefresh);
      setGeneratedExplanation(response.data ?? null);
    } catch (requestError) {
      setExplanationError(requestError instanceof Error ? requestError.message : "Không tạo được giải thích XAI");
    } finally {
      setIsExplanationLoading(false);
    }
  };

  const openDetailedExplanation = async (item: RecommendationItem) => {
    setSelectedExplanation(item);
    setGeneratedExplanation(null);
    setExplanationError("");
    await requestDetailedExplanation(item);
  };

  const regenerateExplanation = async () => {
    if (!selectedExplanation) return;
    await requestDetailedExplanation(selectedExplanation, true);
  };

  return (
    <div ref={rootRef} className="min-h-svh bg-slate-50">
      <Navbar />
      <main className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6">
        <section className="admin-reveal rounded-md border bg-white p-5">
          <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
            <div>
              <Badge variant="outline" className="mb-3 rounded-md gap-1">
                <Shield className="h-3 w-3" />
                Bảng điều khiển quản trị
              </Badge>
              <h1 className="text-3xl font-bold tracking-tight">Quản trị dữ liệu & Knowledge Graph</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                Kiểm soát entity mới, trạng thái đồng bộ KG, phát hiện bản sao và vết kiểm tra. Các thao tác xác thực, từ chối, vô hiệu hóa và gộp ảnh hưởng trực tiếp đến đề xuất khuyến nghị.
              </p>
            </div>
            <div className="grid min-w-[260px] grid-cols-2 gap-2 text-sm">
              <div className="rounded-md border bg-slate-50 p-3">
                <div className="text-xs uppercase text-muted-foreground">Tài khoản</div>
                <div className="mt-1 font-semibold">{user?.full_name || user?.email || "Khách"}</div>
              </div>
              <div className="rounded-md border bg-slate-50 p-3">
                <div className="text-xs uppercase text-muted-foreground">Vai trò</div>
                <div className="mt-1 font-semibold">{user?.account_role ?? "none"}</div>
              </div>
            </div>
          </div>
        </section>

        {!user && !authLoading ? (
          <div className="admin-reveal rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <Link href="/auth/login" className="font-medium underline">
              Đăng nhập
            </Link>{" "}
            để sử dụng trang admin.
          </div>
        ) : null}

        <section className="admin-reveal grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {[
            { label: "Tổng entity", value: stats.total, icon: DatabaseZap, tone: "bg-slate-900 text-white" },
            { label: "Cần duyệt", value: stats.pending, icon: Clock3, tone: "bg-amber-50 text-amber-800" },
            { label: "Đã xác thực", value: stats.verified, icon: CheckCircle2, tone: "bg-emerald-50 text-emerald-800" },
            { label: "Bị từ chối", value: stats.rejected, icon: AlertCircle, tone: "bg-rose-50 text-rose-800" },
            { label: "Đồng bộ lỗi", value: stats.syncFailed, icon: DatabaseZap, tone: "bg-orange-50 text-orange-800" },
          ].map((item) => (
            <Card key={item.label} className="rounded-md">
              <CardContent className="flex items-center justify-between p-4">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">{item.label}</div>
                  <div className="mt-1 text-2xl font-bold">{item.value}</div>
                </div>
                <div className={`flex h-10 w-10 items-center justify-center rounded-md ${item.tone}`}>
                  <item.icon className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>
          ))}
        </section>

        {/* Tab Navigation Taskbar */}
        <div className="admin-reveal grid grid-cols-2 md:grid-cols-5 gap-2 rounded-xl bg-slate-100 p-2 shadow-sm border border-slate-200/80">
          {[
            { id: "overview", label: "Tổng quan & Kiểm thử", icon: Activity },
            { id: "governance", label: "Chất lượng dữ liệu & Node côi", icon: GitMerge },
            { id: "entities", label: "Lưới thực thể", icon: DatabaseZap },
            { id: "embedding", label: "Embedding Workers", icon: Sparkles },
            { id: "audit", label: "Bảo mật & Nhật ký", icon: ShieldCheck },
          ].map((tab) => {
            const isSelected = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <Button
                key={tab.id}
                type="button"
                variant={isSelected ? "default" : "ghost"}
                className={`flex items-center justify-center gap-2 rounded-xl py-2 px-3 text-xs font-bold transition-all duration-300 ${
                  isSelected
                    ? "bg-primary text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-800 hover:bg-slate-200"
                }`}
                onClick={() => {
                  const nextTab = tab.id as AdminTab;
                  setActiveTab(nextTab);
                  window.history.replaceState(null, "", `/admin#${hashFromTab(nextTab)}`);
                }}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </Button>
            );
          })}
        </div>

        {tabLoading ? (
          <div className="flex min-h-[300px] flex-col items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm text-sm text-slate-400">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
            <span className="font-semibold text-slate-600">Đang tải cấu phần quản trị...</span>
          </div>
        ) : (
          <div className="space-y-5">
            {activeTab === "overview" && (
              <Card className="admin-scroll-reveal rounded-md bg-white">
                <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Activity className="h-5 w-5" />
                      System Health & Recommendation Test
                    </CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Theo doi trang thai backend, MongoDB, Neo4j, RabbitMQ va chay thu PGPR recommendation bang source/target thu cong.
                    </p>
                  </div>
                  <Badge variant="outline" className="rounded-md">
                    admin only
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <div className="rounded-md border bg-white p-3 text-sm shadow-sm">
                      <div className="text-xs uppercase text-muted-foreground">API status</div>
                      <div className={`mt-2 inline-flex rounded-md border px-2 py-1 text-xs font-semibold ${healthTone(health?.status)}`}>
                        {health?.status ?? "unknown"}
                      </div>
                    </div>
                    {Object.entries(health?.services ?? {}).map(([name, value]) => (
                      <div key={name} className="rounded-md border bg-white p-3 text-sm shadow-sm">
                        <div className="text-xs uppercase text-muted-foreground">{name}</div>
                        <div className={`mt-2 inline-flex rounded-md border px-2 py-1 text-xs font-semibold ${healthTone(String(value))}`}>
                          {String(value)}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="grid gap-4 rounded-md border bg-slate-50 p-4 lg:grid-cols-[1fr_auto]">
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                      <div className="space-y-2">
                        <Label>Source type</Label>
                        <Select value={systemSourceType} onValueChange={(value) => setSystemSourceType(value as EntityType)}>
                          <SelectTrigger className="rounded-md bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ADMIN_TEST_ENTITY_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>Source ID</Label>
                        <Input
                          value={systemSourceId}
                          onChange={(event) => setSystemSourceId(event.target.value)}
                          placeholder="prj_001 / exp_001..."
                          className="bg-white"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Target type</Label>
                        <Select value={systemTargetType} onValueChange={(value) => setSystemTargetType(value as EntityType)}>
                          <SelectTrigger className="rounded-md bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ADMIN_TEST_ENTITY_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>Mode</Label>
                        <Select value={systemMode} onValueChange={(value) => setSystemMode(value as "public" | "personal")}>
                          <SelectTrigger className="rounded-md bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="public">Public</SelectItem>
                            <SelectItem value="personal">Personal</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>Limit</Label>
                        <Input
                          value={systemLimit}
                          onChange={(event) => setSystemLimit(event.target.value)}
                          inputMode="numeric"
                          className="bg-white"
                        />
                      </div>
                    </div>
                    <div className="flex items-end">
                      <Button className="w-full gap-2 lg:w-auto" disabled={systemTestBusy} onClick={() => void runSystemRecommendationTest()}>
                        {systemTestBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                        Test recommendation
                      </Button>
                    </div>
                  </div>

                  {systemTestError ? (
                    <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{systemTestError}</div>
                  ) : null}

                  <div className="rounded-md border">
                    <div className="flex items-center justify-between border-b px-3 py-2">
                      <div className="text-sm font-medium">Recommendation result</div>
                      <Badge variant="outline" className="rounded-md">
                        {systemRecommendations.length} ket qua
                      </Badge>
                    </div>
                    {systemRecommendations.length === 0 ? (
                      <div className="flex min-h-[160px] flex-col items-center justify-center gap-2 p-4 text-center text-sm text-muted-foreground">
                        <Search className="h-7 w-7" />
                        Chua co ket qua test.
                      </div>
                    ) : (
                      <div className="grid gap-3 p-3">
                        {systemRecommendations.map((item, index) => (
                          <div key={`${item.id}-${index}`} className="grid gap-4 rounded-md border bg-white p-4 md:grid-cols-[1fr_auto]">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge variant="outline" className="rounded-md">
                                  #{index + 1}
                                </Badge>
                                <Badge variant="secondary" className="rounded-md">
                                  {item.type ?? systemTargetType}
                                </Badge>
                                {item.scoring_method ? (
                                  <Badge variant="outline" className="rounded-md">
                                    {item.scoring_method}
                                  </Badge>
                                ) : null}
                                {item.evidence_level ? (
                                  <Badge variant="outline" className="rounded-md">
                                    {item.evidence_level}
                                  </Badge>
                                ) : null}
                                <Badge variant="outline" className="rounded-md gap-1">
                                  <Network className="h-3 w-3" />
                                  {item.reasoning_paths?.length ?? 0} paths
                                </Badge>
                              </div>
                              <div className="mt-2 font-semibold">{item.name || item.id}</div>
                              <div className="mt-1 break-all text-xs text-muted-foreground">ID: {item.id}</div>
                              <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{getXaiPreview(item)}</p>
                              {item.recommendation_message ? (
                                <p className="mt-3 rounded-md border border-amber-100 bg-amber-50 p-2 text-xs font-medium text-amber-700">
                                  {item.recommendation_message}
                                </p>
                              ) : null}
                              {item.fallback_reason ? (
                                <p className="mt-3 rounded-md border border-amber-100 bg-amber-50 p-2 text-xs font-medium text-amber-700">
                                  {item.fallback_reason}
                                </p>
                              ) : null}
                              <div className="mt-4 flex flex-wrap gap-2 border-t pt-3">
                                <Button
                                  size="sm"
                                  className="gap-2"
                                  onClick={() => void openDetailedExplanation(item)}
                                >
                                  <Sparkles className="h-4 w-4" />
                                  Giải thích chi tiết
                                </Button>
                                <Link href={`/entities/${item.type ?? systemTargetType}/${item.id}`}>
                                  <Button variant="outline" size="sm">
                                    Xem chi tiết hồ sơ
                                  </Button>
                                </Link>
                              </div>
                            </div>
                            <div className="rounded-md border bg-slate-50 px-3 py-2 text-right">
                              <div className="text-xs text-muted-foreground">Score</div>
                              <div className="text-lg font-bold">{typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {activeTab === "embedding" && (
              <Card className="admin-scroll-reveal rounded-md bg-white">
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle>Embedding pipeline</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Theo doi queue RabbitMQ, outbox va trang thai embedding. Model:{" "}
                      {pipeline?.model ?? "graphsage_lite_v1"} ({pipeline?.embedding_dimension ?? 128}d).
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" disabled={embeddingBusy} onClick={() => void reloadEmbeddingPanel()}>
                      Lam moi
                    </Button>
                    <Button size="sm" disabled={embeddingBusy} onClick={() => void retryFailedEmbeddings()}>
                      {embeddingBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                      Retry failed jobs
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <div className="rounded-md border bg-slate-50 p-3 text-sm">
                      <div className="text-xs uppercase text-muted-foreground">RabbitMQ</div>
                      <div className="mt-1 font-semibold">{pipeline?.rabbitmq ?? "-"}</div>
                    </div>
                    <div className="rounded-md border bg-slate-50 p-3 text-sm">
                      <div className="text-xs uppercase text-muted-foreground">Queue jobs</div>
                      <div className="mt-1 font-semibold">
                        {pipeline?.queues && typeof pipeline.queues === "object"
                          ? String((pipeline.queues["embedding.jobs"] as { messages?: number })?.messages ?? "-")
                          : "-"}
                      </div>
                    </div>
                    <div className="rounded-md border bg-slate-50 p-3 text-sm">
                      <div className="text-xs uppercase text-muted-foreground">DLQ</div>
                      <div className={`mt-1 font-semibold ${pipeline?.dlq?.alert ? "text-amber-800" : ""}`}>
                        {pipeline?.dlq?.messages ?? "-"}
                      </div>
                      {pipeline?.dlq?.alert ? (
                        <p className="mt-1 text-xs text-amber-800">Co message malformed trong DLQ — can kiem tra worker/logs.</p>
                      ) : null}
                    </div>
                    <div className="rounded-md border bg-slate-50 p-3 text-sm">
                      <div className="text-xs uppercase text-muted-foreground">Outbox pending</div>
                      <div className="mt-1 font-semibold">{pipeline?.outbox?.pending ?? "-"}</div>
                    </div>
                    <div className="rounded-md border bg-slate-50 p-3 text-sm">
                      <div className="text-xs uppercase text-muted-foreground">Workers alive</div>
                      <div className="mt-1 font-semibold">
                        {(pipeline?.worker_summary?.alive_count ?? 0) > 0
                          ? `${pipeline?.worker_summary?.alive_count ?? 0} alive`
                          : "none alive"}
                        {(pipeline?.worker_summary?.stale_count ?? 0) > 0
                          ? ` / ${pipeline?.worker_summary?.stale_count} stale`
                          : ""}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {pipeline?.worker_summary?.count ?? 0} worker(s), stale &gt;{" "}
                        {pipeline?.worker_summary?.stale_after_seconds ?? 120}s
                      </p>
                    </div>
                  </div>
                  {pipeline && (pipeline.worker_heartbeats?.length ?? 0) > 0 ? (
                    <div className="rounded-md border">
                      <div className="border-b px-3 py-2 text-sm font-medium">Worker heartbeats</div>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Worker</TableHead>
                            <TableHead>Liveness</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Last seen</TableHead>
                            <TableHead>Processed</TableHead>
                            <TableHead>Failed</TableHead>
                            <TableHead>Current job</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {pipeline.worker_heartbeats?.map((worker) => (
                            <TableRow key={worker.worker_id}>
                              <TableCell className="text-xs">{worker.worker_id}</TableCell>
                              <TableCell>
                                <Badge
                                  variant="outline"
                                  className={
                                    worker.liveness === "alive"
                                      ? "border-emerald-300"
                                      : worker.liveness === "stale"
                                        ? "border-amber-300"
                                        : "border-slate-300"
                                  }
                                >
                                  {worker.liveness ?? "unknown"}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs">{worker.status ?? "-"}</TableCell>
                              <TableCell className="text-xs">{compact(worker.last_seen_at)}</TableCell>
                              <TableCell>{worker.processed_count ?? 0}</TableCell>
                              <TableCell>{worker.failed_count ?? 0}</TableCell>
                              <TableCell className="text-xs">{compact(worker.current_job_id)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Chua co worker heartbeat. Chay `python -m workers.embedding_worker` de worker ghi trang thai.
                    </p>
                  )}
                  {pipeline?.entity_embedding_status ? (
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(pipeline.entity_embedding_status).map(([key, value]) => (
                        <Badge key={key} variant="outline" className="rounded-md">
                          {key}: {value}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  <div className="rounded-md border">
                    <div className="border-b px-3 py-2 text-sm font-medium">Failed / recent jobs</div>
                    {embeddingJobs.length === 0 ? (
                      <p className="p-3 text-sm text-muted-foreground">Khong co job failed trong outbox.</p>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Entity</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Error</TableHead>
                            <TableHead>Type</TableHead>
                            <TableHead />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {embeddingJobs.map((job) => (
                            <TableRow key={job.event_id ?? job.job_id}>
                              <TableCell className="text-xs">
                                {job.entity_type}/{job.entity_id}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className={statusClass(job.status)}>
                                  {job.status}
                                </Badge>
                              </TableCell>
                              <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                                {compact(job.last_error)}
                              </TableCell>
                              <TableCell className="text-xs">{compact((job as { error_type?: string }).error_type)}</TableCell>
                              <TableCell>
                                {job.entity_type && job.entity_id ? (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={embeddingBusy}
                                    onClick={() =>
                                      void recomputeEmbedding(job.entity_type as EntityType, String(job.entity_id))
                                    }
                                  >
                                    Recompute
                                  </Button>
                                ) : null}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {activeTab === "governance" && (
              <>
                <Card id="review-queue" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
                  <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
                    <div>
                      <CardTitle>Governance review queue</CardTitle>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Hang cho data quality: ho so thieu thong tin, can merge, taxonomy chua chuan hoa.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Select value={reviewStatusFilter} onValueChange={setReviewStatusFilter}>
                        <SelectTrigger className="w-[190px]">
                          <SelectValue placeholder="Review status" />
                        </SelectTrigger>
                        <SelectContent>
                          {REVIEW_STATUS_FILTERS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={qualityFilter} onValueChange={setQualityFilter}>
                        <SelectTrigger className="w-[160px]">
                          <SelectValue placeholder="Quality" />
                        </SelectTrigger>
                        <SelectContent>
                          {QUALITY_FILTERS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={taxonomyFilter} onValueChange={setTaxonomyFilter}>
                        <SelectTrigger className="w-[190px]">
                          <SelectValue placeholder="Taxonomy" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Tat ca taxonomy</SelectItem>
                          <SelectItem value="yes">Co unmapped taxonomy</SelectItem>
                          <SelectItem value="no">Khong unmapped taxonomy</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={duplicateFilter} onValueChange={setDuplicateFilter}>
                        <SelectTrigger className="w-[190px]">
                          <SelectValue placeholder="Duplicate" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Tat ca duplicate</SelectItem>
                          <SelectItem value="yes">Co duplicate candidate</SelectItem>
                          <SelectItem value="no">Khong duplicate candidate</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-2 md:grid-cols-4">
                      {[
                        ["total", (governanceSummary.total as number | undefined) ?? governanceRows.length],
                        ["poor", (governanceSummary.by_quality_level as Record<string, number> | undefined)?.poor ?? 0],
                        ["needs_more_info", (governanceSummary.by_review_status as Record<string, number> | undefined)?.needs_more_info ?? 0],
                        ["unmapped_taxonomy", (governanceSummary.unmapped_taxonomy_warnings as number | undefined) ?? 0],
                      ].map(([label, value]) => (
                        <div key={String(label)} className="rounded-md border bg-slate-50 p-3">
                          <div className="text-xs uppercase text-muted-foreground">{String(label)}</div>
                          <div className="mt-1 text-xl font-bold">{String(value)}</div>
                        </div>
                      ))}
                    </div>

                    {governanceRows.length === 0 ? (
                      <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                        Khong co item nao khop bo loc governance hien tai.
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Entity</TableHead>
                              <TableHead>Quality</TableHead>
                              <TableHead>Review</TableHead>
                              <TableHead>Warnings</TableHead>
                              <TableHead>Recommended action</TableHead>
                              <TableHead />
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {governanceRows.map((row) => {
                              const warnings = row.data_quality?.warnings ?? [];
                              const level = row.data_quality?.level ?? "-";
                              const score = typeof row.data_quality?.score === "number" ? row.data_quality.score : null;
                              return (
                                <TableRow key={`${row.entity_type}-${row.entity_id}`} className="align-top">
                                  <TableCell className="min-w-[280px]">
                                    <div className="font-semibold">{row.name || row.entity_id}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">
                                      {row.entity_type} / {row.entity_id}
                                    </div>
                                    <div className="mt-2 flex flex-wrap gap-1">
                                      {row.participation_scope === "owner_only" ? (
                                        <Badge variant="outline" className="rounded-md border-sky-200 bg-sky-50 text-sky-700">
                                          owner_only
                                        </Badge>
                                      ) : null}
                                      {row.entity_verification_status === "unverified" ? (
                                        <Badge variant="outline" className="rounded-md border-amber-200 bg-amber-50 text-amber-700">
                                          unverified
                                        </Badge>
                                      ) : null}
                                      {(row.unmapped_taxonomy_values?.length ?? 0) > 0 ? (
                                        <Badge variant="outline" className="rounded-md border-purple-200 bg-purple-50 text-purple-700">
                                          unmapped_taxonomy
                                        </Badge>
                                      ) : null}
                                    </div>
                                  </TableCell>
                                  <TableCell>
                                    <Badge variant="outline" className={`rounded-md ${statusClass(level)}`}>
                                      {level}
                                    </Badge>
                                    <div className="mt-1 text-2xl font-bold">
                                      {score === null ? "-" : `${Math.round(score * 100)}%`}
                                    </div>
                                  </TableCell>
                                  <TableCell>
                                    <Badge variant="outline" className={`rounded-md ${statusClass(row.review_status)}`}>
                                      {compact(row.review_status)}
                                    </Badge>
                                    {(row.duplicate_candidates_count ?? 0) > 0 ? (
                                      <div className="mt-2 text-xs text-amber-700">
                                        {row.duplicate_candidates_count} duplicate candidate(s)
                                      </div>
                                    ) : null}
                                  </TableCell>
                                  <TableCell className="min-w-[280px]">
                                    <div className="flex flex-wrap gap-1">
                                      {warnings.slice(0, 5).map((warning) => (
                                        <Badge key={warning} variant="outline" className="rounded-md">
                                          {warning}
                                        </Badge>
                                      ))}
                                      {warnings.length > 5 ? (
                                        <Badge variant="outline" className="rounded-md">
                                          +{warnings.length - 5}
                                        </Badge>
                                      ) : null}
                                    </div>
                                    {(row.data_quality?.missing_fields?.length ?? 0) > 0 ? (
                                      <div className="mt-2 text-xs text-muted-foreground">
                                        Missing: {row.data_quality?.missing_fields?.join(", ")}
                                      </div>
                                    ) : null}
                                  </TableCell>
                                  <TableCell className="text-sm">{compact(row.recommended_action)}</TableCell>
                                  <TableCell className="text-right">
                                    <div className="flex justify-end gap-2">
                                      {(row.unmapped_taxonomy_values?.length ?? 0) > 0
                                        ? row.unmapped_taxonomy_values
                                            ?.flatMap(parseUnmappedWarning)
                                            .slice(0, 1)
                                            .map((item) => (
                                              <Button
                                                key={`${item.taxonomyType}-${item.rawValue}`}
                                                size="sm"
                                                variant="outline"
                                                onClick={() => {
                                                  setSelectedTaxonomyItem({
                                                    row,
                                                    rawValue: item.rawValue,
                                                    taxonomyType: item.taxonomyType,
                                                  });
                                                  setTaxonomyForm({ canonical_id: "", reason: "" });
                                                }}
                                              >
                                                Map taxonomy
                                              </Button>
                                            ))
                                        : null}
                                      {row.review_status === "needs_more_info" && row.entity_type && row.entity_id ? (
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          onClick={() => {
                                            setRequestInfoItem(row);
                                            setRequestInfoForm({
                                              requested_fields: row.data_quality?.missing_fields?.join(", ") ?? "",
                                              admin_note: "",
                                              reason: "Entity is missing required recommendation fields",
                                            });
                                          }}
                                        >
                                          Request info
                                        </Button>
                                      ) : null}
                                      {row.entity_type && row.entity_id ? (
                                        <Link href={`/admin/entities/${row.entity_type}/${row.entity_id}`}>
                                          <Button size="sm" variant="outline">
                                            Review
                                          </Button>
                                        </Link>
                                      ) : null}
                                    </div>
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card id="orphan-cleanup" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
                  <CardHeader>
                    <CardTitle>Orphan cleanup candidates</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Node khong co relationship. Chi mark/disable khoi recommendation, khong physical delete.
                    </p>
                  </CardHeader>
                  <CardContent>
                    {orphanRows.length === 0 ? (
                      <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                        Khong co orphan node trong graph.
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Node</TableHead>
                              <TableHead>KG</TableHead>
                              <TableHead>Visibility</TableHead>
                              <TableHead />
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {orphanRows.map((row) => {
                              const entityType = orphanEntityType(row);
                              return (
                                <TableRow key={`${row.labels?.join("-")}-${row.entity_id}`}>
                                  <TableCell>
                                    <div className="font-semibold">{row.name || row.entity_id}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">
                                      {row.labels?.join(", ") || "-"} / {row.entity_id}
                                    </div>
                                  </TableCell>
                                  <TableCell>
                                    <Badge variant="outline" className={`rounded-md ${statusClass(row.kg_sync_status)}`}>
                                      {compact(row.kg_sync_status)}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="text-sm">
                                    {compact(row.visibility)} / {compact(row.participation_scope)}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {entityType && row.entity_id ? (
                                      <div className="flex justify-end gap-2">
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          onClick={() => {
                                            setOrphanAction({ row, action: "mark" });
                                            setOrphanReason("");
                                          }}
                                        >
                                          Mark cleanup
                                        </Button>
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          onClick={() => {
                                            setOrphanAction({ row, action: "disable" });
                                            setOrphanReason("");
                                          }}
                                        >
                                          Disable recommendation
                                        </Button>
                                      </div>
                                    ) : (
                                      <span className="text-xs text-muted-foreground">Unsupported label</span>
                                    )}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </>
            )}

            {activeTab === "entities" && (
              <Card id="entity-review" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle>Entity review queue</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Loc entity theo ten, id, loai va KG status truoc khi xu ly. Mac dinh chi tai mot so luong gioi han.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Input
                      value={entitySearch}
                      onChange={(event) => setEntitySearch(event.target.value)}
                      placeholder="Tim ten, email hoac id..."
                      className="w-[240px]"
                    />
                    <Select value={typeFilter} onValueChange={setTypeFilter}>
                      <SelectTrigger className="w-[160px]">
                        <SelectValue placeholder="Loai entity" />
                      </SelectTrigger>
                      <SelectContent>
                        {TYPE_FILTERS.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={kgFilter} onValueChange={setKgFilter}>
                      <SelectTrigger className="w-[210px]">
                        <SelectValue placeholder="KG status" />
                      </SelectTrigger>
                      <SelectContent>
                        {KG_FILTERS.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setTypeFilter("expert");
                        setKgFilter("synced_unverified");
                        setEntitySearch("");
                      }}
                    >
                      Chua xac thuc
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setTypeFilter("all");
                        setKgFilter("all");
                        setEntitySearch("");
                      }}
                    >
                      Reset
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="flex min-h-[240px] items-center justify-center gap-2 text-muted-foreground">
                      <Loader2 className="h-5 w-5 animate-spin" />
                      Dang tai queue...
                    </div>
                  ) : error ? (
                    <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                      <AlertCircle className="mt-0.5 h-4 w-4" />
                      {error}
                    </div>
                  ) : rows.length === 0 ? (
                    <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                      Khong co entity nao khop bo loc hien tai.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Entity</TableHead>
                            <TableHead>KG sync</TableHead>
                            <TableHead>Verification</TableHead>
                            <TableHead>Duplicate</TableHead>
                            <TableHead>Scope</TableHead>
                            <TableHead>Trust</TableHead>
                            <TableHead />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {rows.map((row) => (
                            <TableRow key={`${row.entity_type}-${row.entity_id}`} className="align-top">
                              <TableCell className="min-w-[320px]">
                                <div className="font-semibold">{row.name || row.entity_id}</div>
                                <div className="mt-1 text-xs text-muted-foreground">
                                  {row.entity_type} / {row.entity_id}
                                </div>
                                {row.sync_error ? (
                                  <div className="mt-2 max-w-md rounded-md bg-rose-50 px-2 py-1 text-xs text-rose-700">
                                    {String(row.sync_error)}
                                  </div>
                                ) : null}
                                {row.merged_into ? (
                                  <div className="mt-2 max-w-md rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
                                    Da merge vao {row.merged_into}
                                  </div>
                                ) : null}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className={`rounded-md ${statusClass(row.kg_sync_status)}`}>
                                  {compact(row.kg_sync_status)}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge
                                  variant="outline"
                                  className={`rounded-md ${statusClass(row.entity_verification_status)}`}
                                >
                                  {compact(row.entity_verification_status)}
                                </Badge>
                              </TableCell>
                              <TableCell className="min-w-[220px] text-sm">
                                {(row.duplicate_candidates?.length ?? 0) > 0 ? (
                                  <div className="space-y-1">
                                    <Badge variant="outline" className="rounded-md border-amber-200 bg-amber-50 text-amber-700">
                                      {row.duplicate_candidates?.length} candidate
                                    </Badge>
                                    {firstDuplicateCandidate(row) ? (
                                      <div className="text-xs text-muted-foreground">
                                        {String(firstDuplicateCandidate(row)?.name ?? firstDuplicateCandidate(row)?.id ?? "")}
                                      </div>
                                    ) : null}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-sm">{compact(row.participation_scope)}</TableCell>
                              <TableCell className="text-sm">
                                {typeof row.trust_weight === "number" ? row.trust_weight.toFixed(2) : "-"}
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex justify-end gap-2">
                                  {firstDuplicateCandidate(row)?.id ? (
                                    <Link
                                      href={`/admin/entities/${row.entity_type}/${row.entity_id}?mergeTarget=${encodeURIComponent(
                                        String(firstDuplicateCandidate(row)?.id),
                                      )}`}
                                    >
                                      <Button size="sm" variant="default" className="gap-1">
                                        <GitMerge className="h-3.5 w-3.5" />
                                        Merge
                                      </Button>
                                    </Link>
                                  ) : null}
                                  <Link href={`/admin/entities/${row.entity_type}/${row.entity_id}`}>
                                    <Button size="sm" variant="outline">
                                      Review
                                    </Button>
                                  </Link>
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                        <div className="text-sm text-muted-foreground">
                          Page {entityPage} / {entityTotalPages} - hien {rows.length} trong tong {entityTotal} entity
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={entityPage <= 1}
                            onClick={() => setEntityPage((page) => Math.max(1, page - 1))}
                          >
                            Truoc
                          </Button>
                          {entityPageNumbers.map((pageNumber) => (
                            <Button
                              key={pageNumber}
                              type="button"
                              variant={entityPage === pageNumber ? "default" : "outline"}
                              size="sm"
                              onClick={() => setEntityPage(pageNumber)}
                            >
                              Page {pageNumber}
                            </Button>
                          ))}
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={entityPage >= entityTotalPages}
                            onClick={() => setEntityPage((page) => Math.min(entityTotalPages, page + 1))}
                          >
                            Sau
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {activeTab === "audit" && (
              <>
                {isRootAdmin && (
                  <Card id="admin-users" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
                    <CardHeader>
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-900 text-white">
                          <ShieldCheck className="h-5 w-5" />
                        </div>
                        <div>
                          <CardTitle>Root admin controls</CardTitle>
                          <p className="mt-1 text-sm text-muted-foreground">Tao admin moi va cap quyen cho user hien co.</p>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-5">
                      <form onSubmit={createAdmin} className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
                        <div className="space-y-1">
                          <Label>Email admin moi</Label>
                          <Input
                            value={adminForm.email}
                            onChange={(event) => setAdminForm((prev) => ({ ...prev, email: event.target.value }))}
                            placeholder="admin@example.com"
                            type="email"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label>Ho ten</Label>
                          <Input
                            value={adminForm.full_name}
                            onChange={(event) => setAdminForm((prev) => ({ ...prev, full_name: event.target.value }))}
                            placeholder="Admin name"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label>Mat khau</Label>
                          <Input
                            value={adminForm.password}
                            onChange={(event) => setAdminForm((prev) => ({ ...prev, password: event.target.value }))}
                            placeholder="Admin@123456"
                            type="password"
                          />
                        </div>
                        <Button className="self-end gap-2" type="submit">
                          <UserCog className="h-4 w-4" />
                          Tao admin
                        </Button>
                      </form>

                      {isUsersLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Dang tai users...
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>User</TableHead>
                                <TableHead>Business role</TableHead>
                                <TableHead>Account role</TableHead>
                                <TableHead />
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {adminUsers.map((adminUser) => {
                                const id = String(adminUser._id ?? adminUser.id ?? "");
                                const accountRole = String(adminUser.account_role ?? "user");
                                return (
                                  <TableRow key={id}>
                                    <TableCell>
                                      <div className="font-medium">{adminUser.full_name || adminUser.email}</div>
                                      <div className="text-xs text-muted-foreground">{adminUser.email}</div>
                                    </TableCell>
                                    <TableCell>{adminUser.role ?? "expert"}</TableCell>
                                    <TableCell>
                                      <Badge className={`rounded-md ${statusClass(accountRole)}`} variant="outline">
                                        {accountRole}
                                      </Badge>
                                    </TableCell>
                                    <TableCell className="space-x-2 text-right">
                                      {accountRole === "user" ? (
                                        <Button size="sm" variant="outline" onClick={() => void changeRole(id, "promote")}>
                                          Promote admin
                                        </Button>
                                      ) : accountRole === "admin" ? (
                                        <Button size="sm" variant="outline" onClick={() => void changeRole(id, "demote")}>
                                          Demote user
                                        </Button>
                                      ) : null}
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                <Card id="audit-log" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-100">
                        <Users className="h-5 w-5" />
                      </div>
                      <div>
                        <CardTitle>Audit log gan day</CardTitle>
                        <p className="mt-1 text-sm text-muted-foreground">Theo doi thao tac quan tri de phuc vu audit.</p>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    {auditLogs.length === 0 ? (
                      <p className="text-muted-foreground">Chua co audit log.</p>
                    ) : (
                      auditLogs.map((log, index) => (
                        <div key={String(log._id ?? index)} className="relative rounded-md border bg-slate-50 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="font-medium">
                              {String(log.action ?? "action")} - {String(log.entity_type ?? "")}/{String(log.entity_id ?? "")}
                            </div>
                            <Badge variant="outline" className="rounded-md">
                              {String(log.created_at ?? "").slice(0, 19)}
                            </Badge>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">Admin {String(log.admin_user_id ?? "")}</div>
                          {log.reason ? <div className="mt-2 text-xs">{String(log.reason)}</div> : null}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        )}
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
        <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-6xl overflow-x-hidden overflow-y-auto rounded-2xl border-slate-200 bg-white p-6 shadow-xl md:p-8">
          <DialogHeader className="border-b border-slate-200 pb-4">
            <DialogTitle className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-800">
              <Sparkles className="h-5 w-5 text-indigo-500" />
              Giải thích Chi tiết (XAI Engine)
            </DialogTitle>
            <DialogDescription className="mt-1 text-xs font-medium text-slate-500">
              Phân tích vết đường dẫn suy luận Knowledge Graph tạo sinh đề xuất recommendation.
            </DialogDescription>
          </DialogHeader>

          {selectedExplanation ? (
            <div className="min-w-0 space-y-6 pt-6">
              <div className="rounded-2xl border border-indigo-50 bg-indigo-50/20 p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">Thực thể đề xuất</div>
                    <div className="text-lg font-bold tracking-tight text-slate-800">{selectedExplanation.name || selectedExplanation.id}</div>
                    <div className="text-xs font-semibold text-slate-500">ID: {selectedExplanation.id}</div>
                  </div>
                  <div className="h-fit shrink-0 rounded-xl border border-indigo-100 bg-white p-3 text-right shadow-sm">
                    <div className="text-[9px] font-extrabold uppercase tracking-wider text-slate-500">Độ tin cậy gợi ý</div>
                    <div className="mt-0.5 text-base font-extrabold text-indigo-600">
                      {typeof selectedExplanation.score === "number" ? (selectedExplanation.score * 100).toFixed(1) : "N/A"}%
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-slate-50/50 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-0.5">
                  <div className="text-xs font-bold text-slate-700">Trạng thái XAI Model</div>
                  <div className="text-[11px] font-medium leading-relaxed text-slate-500">
                    {isExplanationLoading
                      ? "Đang lập biểu đồ suy diễn và gọi XAI Model..."
                      : generatedExplanation?._cache?.hit
                        ? "Dữ liệu truy xuất từ cache."
                        : generatedExplanation
                          ? "Mô hình đã sinh cấu trúc giải thích mới."
                          : "Đang chờ sinh cấu trúc..."}
                  </div>
                  {generatedExplanation?._cache?.key ? (
                    <div className="mt-1 break-all rounded-md border bg-white px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-500">
                      Cache-key: {generatedExplanation._cache.key}
                    </div>
                  ) : null}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 shrink-0 text-xs font-bold"
                  onClick={() => void regenerateExplanation()}
                  disabled={isExplanationLoading}
                >
                  {isExplanationLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin text-slate-500" /> : null}
                  Tạo lại giải thích
                </Button>
              </div>

              <section className="space-y-2">
                <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
                  <Info className="h-4 w-4 text-slate-400" />
                  Mô tả giải thích tự nhiên
                </h3>
                <div className="rounded-2xl border border-slate-200/60 bg-white p-5 leading-relaxed shadow-sm">
                  {isExplanationLoading ? (
                    <div className="flex items-center gap-2 py-4 text-xs font-medium text-slate-500">
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

              {generatedExplanation?.confidence ? (
                <section className="min-w-0 space-y-2.5">
                  <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
                    <TrendingUp className="h-4 w-4 text-slate-400" />
                    Đánh giá độ tin cậy thành phần
                  </h3>
                  <ConfidenceBlock confidence={generatedExplanation.confidence} />
                </section>
              ) : null}

              {selectedExplanation.reasoning_paths?.length ? (
                <section className="space-y-3">
                  <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
                    <Network className="h-4 w-4 text-slate-400" />
                    Bản đồ đường dẫn lập luận đồ thị (Reasoning Paths)
                  </h3>
                  <div className="min-w-0 space-y-3">
                    {selectedExplanation.reasoning_paths.map((path, index) => (
                      <ReasoningPathCard
                        key={index}
                        path={path}
                        index={index}
                        source={systemRecommendationSource}
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

      <Dialog open={Boolean(selectedTaxonomyItem)} onOpenChange={(open) => !open && setSelectedTaxonomyItem(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Map taxonomy alias</DialogTitle>
            <DialogDescription>
              Them alias vao taxonomy. He thong chi ghi mapping va audit log, khong rewrite entity hang loat.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-2">
              <Label>Taxonomy type</Label>
              <Input value={selectedTaxonomyItem?.taxonomyType ?? ""} disabled />
            </div>
            <div className="grid gap-2">
              <Label>Raw value</Label>
              <Input value={selectedTaxonomyItem?.rawValue ?? ""} disabled />
            </div>
            <div className="grid gap-2">
              <Label>Canonical value</Label>
              <Select
                value={taxonomyForm.canonical_id}
                onValueChange={(value) => setTaxonomyForm((prev) => ({ ...prev, canonical_id: value }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Chon canonical id" />
                </SelectTrigger>
                <SelectContent>
                  {(
                    selectedTaxonomyItem?.taxonomyType === "topic"
                      ? canonicalTaxonomy?.topics
                      : selectedTaxonomyItem?.taxonomyType === "skill"
                        ? canonicalTaxonomy?.skills
                        : canonicalTaxonomy?.industries
                  )?.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.label} ({item.id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Reason</Label>
              <Textarea
                value={taxonomyForm.reason}
                onChange={(event) => setTaxonomyForm((prev) => ({ ...prev, reason: event.target.value }))}
                placeholder="Vi sao raw value nay nen map vao canonical value da chon?"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedTaxonomyItem(null)}>
              Cancel
            </Button>
            <Button
              disabled={governanceBusy || !taxonomyForm.canonical_id || !taxonomyForm.reason.trim()}
              onClick={() => void submitTaxonomyAlias()}
            >
              Save alias
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(requestInfoItem)} onOpenChange={(open) => !open && setRequestInfoItem(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request more information</DialogTitle>
            <DialogDescription>
              Tao request de user bo sung cac truong dang thieu. Request nay duoc luu de profile co the hien warning.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-2">
              <Label>Entity</Label>
              <Input value={`${requestInfoItem?.entity_type ?? ""}/${requestInfoItem?.entity_id ?? ""}`} disabled />
            </div>
            <div className="grid gap-2">
              <Label>Requested fields, separated by comma</Label>
              <Input
                value={requestInfoForm.requested_fields}
                onChange={(event) => setRequestInfoForm((prev) => ({ ...prev, requested_fields: event.target.value }))}
                placeholder="research_topics, skills_or_technology, location"
              />
            </div>
            <div className="grid gap-2">
              <Label>Admin note</Label>
              <Textarea
                value={requestInfoForm.admin_note}
                onChange={(event) => setRequestInfoForm((prev) => ({ ...prev, admin_note: event.target.value }))}
                placeholder="Huong dan ngan gon cho user"
              />
            </div>
            <div className="grid gap-2">
              <Label>Reason</Label>
              <Textarea
                value={requestInfoForm.reason}
                onChange={(event) => setRequestInfoForm((prev) => ({ ...prev, reason: event.target.value }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRequestInfoItem(null)}>
              Cancel
            </Button>
            <Button
              disabled={governanceBusy || !requestInfoForm.requested_fields.trim() || !requestInfoForm.reason.trim()}
              onClick={() => void submitRequestMoreInfo()}
            >
              Create request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(orphanAction)} onOpenChange={(open) => !open && setOrphanAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {orphanAction?.action === "disable" ? "Disable orphan from recommendation" : "Mark cleanup candidate"}
            </DialogTitle>
            <DialogDescription>
              Yeu cau reason bat buoc. Hanh dong nay khong physical delete node.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-2">
              <Label>Node</Label>
              <Input
                value={`${orphanAction?.row.labels?.[0] ?? ""}/${orphanAction?.row.entity_id ?? ""}`}
                disabled
              />
            </div>
            <div className="grid gap-2">
              <Label>Reason</Label>
              <Textarea
                value={orphanReason}
                onChange={(event) => setOrphanReason(event.target.value)}
                placeholder="Vi sao node nay la cleanup candidate?"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOrphanAction(null)}>
              Cancel
            </Button>
            <Button disabled={governanceBusy || !orphanReason.trim()} onClick={() => void submitOrphanAction()}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
