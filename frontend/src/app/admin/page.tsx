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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/lib/auth";
import { AdminEntityRow, AdminUserRow, api, EntityType } from "@/lib/api";

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

export default function AdminPage() {
  const { user, isLoading: authLoading } = useAuth();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rows, setRows] = useState<AdminEntityRow[]>([]);
  const [adminUsers, setAdminUsers] = useState<AdminUserRow[]>([]);
  const [auditLogs, setAuditLogs] = useState<Record<string, unknown>[]>([]);
  const [kgFilter, setKgFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
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
    ])
      .then(([entitiesRes, logsRes]) => {
        setRows(entitiesRes.data ?? []);
        setAuditLogs(logsRes.data ?? []);
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "Khong tai duoc du lieu admin");
      })
      .finally(() => setIsLoading(false));
  }, [authLoading, user, canAdmin, kgFilter, typeFilter]);

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

        <Card id="review-queue" className="admin-scroll-reveal scroll-mt-24 rounded-md bg-white">
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
    </div>
  );
}
