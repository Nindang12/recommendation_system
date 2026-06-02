"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  GitMerge,
  Loader2,
  Shield,
  ShieldCheck,
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
  AdminEntityRow,
  AdminGovernanceReviewRow,
  AdminOrphanRow,
  AdminUserRow,
  api,
  CanonicalTaxonomyResponse,
  EmbeddingJobRow,
  EmbeddingPipelineStatus,
  EntityType,
} from "@/lib/api";

gsap.registerPlugin(ScrollTrigger);

const KG_FILTERS = [
  { value: "all", label: "Tat ca KG status" },
  { value: "sync_failed", label: "sync_failed" },
  { value: "merge_required", label: "merge_required" },
  { value: "synced_unverified", label: "synced_unverified" },
  { value: "not_synced", label: "not_synced" },
  { value: "verified", label: "verified (synced_verified)" },
  { value: "rejected", label: "rejected" },
  { value: "disabled", label: "disabled" },
];

const TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: "all", label: "Tat ca loai" },
  { value: "expert", label: "Expert" },
  { value: "enterprise", label: "Enterprise" },
  { value: "funder", label: "Funder" },
  { value: "project", label: "Project" },
];

const REVIEW_STATUS_FILTERS = [
  { value: "all", label: "Tat ca review status" },
  { value: "needs_more_info", label: "needs_more_info" },
  { value: "merge_required", label: "merge_required" },
  { value: "pending_review", label: "pending_review" },
  { value: "rejected", label: "rejected" },
  { value: "verified", label: "verified" },
];

const QUALITY_FILTERS = [
  { value: "all", label: "Tat ca quality" },
  { value: "poor", label: "poor" },
  { value: "fair", label: "fair" },
  { value: "good", label: "good" },
  { value: "excellent", label: "excellent" },
];

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

export default function AdminPage() {
  const { user, isLoading: authLoading } = useAuth();
  const rootRef = useRef<HTMLDivElement | null>(null);
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
  const [embeddingJobs, setEmbeddingJobs] = useState<EmbeddingJobRow[]>([]);
  const [embeddingBusy, setEmbeddingBusy] = useState(false);
  const [governanceBusy, setGovernanceBusy] = useState(false);
  const [kgFilter, setKgFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [reviewStatusFilter, setReviewStatusFilter] = useState("all");
  const [qualityFilter, setQualityFilter] = useState("all");
  const [taxonomyFilter, setTaxonomyFilter] = useState("all");
  const [duplicateFilter, setDuplicateFilter] = useState("all");
  const [isLoading, setIsLoading] = useState(true);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [error, setError] = useState("");
  const [adminForm, setAdminForm] = useState({ email: "", password: "", full_name: "" });
  const canAdmin = user?.account_role === "admin" || user?.account_role === "root_admin";
  const isRootAdmin = user?.account_role === "root_admin";

  const stats = useMemo(() => {
    const pending = rows.filter((row) =>
      ["synced_unverified", "merge_required", "sync_failed", "not_synced"].includes(String(row.kg_sync_status)),
    ).length;
    const rejected = rows.filter((row) => String(row.kg_sync_status).includes("rejected")).length;
    const verified = rows.filter((row) => String(row.kg_sync_status).includes("verified") && !String(row.kg_sync_status).includes("unverified")).length;
    const syncFailed = rows.filter((row) => String(row.kg_sync_status).includes("failed")).length;
    return { pending, rejected, verified, syncFailed, total: rows.length };
  }, [rows]);

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

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setError("Can dang nhap de mo trang admin.");
      setIsLoading(false);
      return;
    }
    if (!canAdmin) {
      setError("Tai khoan hien tai khong co quyen admin.");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError("");
    Promise.all([
      api.adminListEntities({
        entity_type: typeFilter === "all" ? undefined : (typeFilter as EntityType),
        kg_sync_status: kgFilter === "all" ? undefined : kgFilter === "verified" ? "synced_verified" : kgFilter,
        limit: 80,
      }),
      api.adminAuditLogs(30),
      api.adminEmbeddingPipelineStatus(),
      api.adminListEmbeddingJobs({ status: "failed", limit: 20 }),
      api.adminGovernanceReviewQueue({
        entity_type: typeFilter === "all" ? undefined : (typeFilter as EntityType),
        review_status: reviewStatusFilter === "all" ? undefined : reviewStatusFilter,
        level: qualityFilter === "all" ? undefined : qualityFilter,
        has_unmapped_taxonomy: taxonomyFilter === "all" ? undefined : taxonomyFilter === "yes",
        has_duplicate_candidates: duplicateFilter === "all" ? undefined : duplicateFilter === "yes",
        limit: 80,
      }),
      api.canonicalTaxonomy(),
      api.adminListOrphans(80),
    ])
      .then(([entitiesRes, logsRes, pipelineRes, jobsRes, governanceRes, taxonomyRes, orphanRes]) => {
        setRows(entitiesRes.data ?? []);
        setAuditLogs(logsRes.data ?? []);
        setPipeline(pipelineRes.data ?? null);
        setEmbeddingJobs(jobsRes.jobs ?? []);
        setGovernanceRows(governanceRes.data ?? []);
        setGovernanceSummary(governanceRes.source_summary ?? {});
        setCanonicalTaxonomy(taxonomyRes.data ?? null);
        setOrphanRows(orphanRes.data ?? []);
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "Khong tai duoc du lieu admin");
      })
      .finally(() => setIsLoading(false));
  }, [authLoading, user, canAdmin, kgFilter, typeFilter, reviewStatusFilter, qualityFilter, taxonomyFilter, duplicateFilter]);

  useEffect(() => {
    if (!isRootAdmin) return;
    setIsUsersLoading(true);
    api
      .adminListUsers(80)
      .then((response) => setAdminUsers(response.data ?? []))
      .catch(() => setAdminUsers([]))
      .finally(() => setIsUsersLoading(false));
  }, [isRootAdmin]);

  const reloadAdminUsers = () => {
    if (!isRootAdmin) return;
    setIsUsersLoading(true);
    api
      .adminListUsers(80)
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
      setError(requestError instanceof Error ? requestError.message : "Khong tao duoc admin");
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
      setError(requestError instanceof Error ? requestError.message : "Khong retry duoc embedding jobs");
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
      setError(requestError instanceof Error ? requestError.message : "Khong recompute duoc embedding");
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
      setError(requestError instanceof Error ? requestError.message : "Khong map duoc taxonomy alias");
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
      setError(requestError instanceof Error ? requestError.message : "Khong tao duoc request more information");
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
      setError(requestError instanceof Error ? requestError.message : "Khong xu ly duoc orphan");
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
      setError(requestError instanceof Error ? requestError.message : "Khong cap nhat duoc role");
    }
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
                Admin Console
              </Badge>
              <h1 className="text-3xl font-bold tracking-tight">Quan tri du lieu va Knowledge Graph</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                Kiem soat entity moi, trang thai sync KG, duplicate candidates va audit trail. Cac hanh dong verify,
                reject, disable va merge se anh huong truc tiep den recommendation.
              </p>
            </div>
            <div className="grid min-w-[260px] grid-cols-2 gap-2 text-sm">
              <div className="rounded-md border bg-slate-50 p-3">
                <div className="text-xs uppercase text-muted-foreground">Account</div>
                <div className="mt-1 font-semibold">{user?.full_name || user?.email || "Guest"}</div>
              </div>
              <div className="rounded-md border bg-slate-50 p-3">
                <div className="text-xs uppercase text-muted-foreground">Role</div>
                <div className="mt-1 font-semibold">{user?.account_role ?? "none"}</div>
              </div>
            </div>
          </div>
        </section>

        {!user && !authLoading ? (
          <div className="admin-reveal rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <Link href="/auth/login" className="font-medium underline">
              Dang nhap
            </Link>{" "}
            de su dung trang admin.
          </div>
        ) : null}

        <section className="admin-reveal grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {[
            { label: "Tong entity", value: stats.total, icon: DatabaseZap, tone: "bg-slate-900 text-white" },
            { label: "Can review", value: stats.pending, icon: Clock3, tone: "bg-amber-50 text-amber-800" },
            { label: "Verified", value: stats.verified, icon: CheckCircle2, tone: "bg-emerald-50 text-emerald-800" },
            { label: "Rejected", value: stats.rejected, icon: AlertCircle, tone: "bg-rose-50 text-rose-800" },
            { label: "Sync failed", value: stats.syncFailed, icon: DatabaseZap, tone: "bg-orange-50 text-orange-800" },
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

        <Card id="entity-review" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Entity review queue</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">Loc entity theo loai va KG status truoc khi xu ly.</p>
            </div>
            <div className="flex flex-wrap gap-2">
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
              </div>
            )}
          </CardContent>
        </Card>

        {isRootAdmin ? (
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
        ) : null}

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
      </main>

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
