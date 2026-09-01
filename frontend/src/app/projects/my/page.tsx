"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderKanban, Loader2, Plus, Trash2 } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiEntity, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function statusLabel(value: unknown) {
  const key = String(value || "");
  const labels: Record<string, string> = {
    draft: "Draft",
    not_synced: "Chưa sync KG",
    syncing: "Đang sync KG",
    synced_unverified: "KG unverified",
    synced_verified: "KG verified",
    sync_failed: "Sync lỗi",
    merge_required: "Cần review",
    unverified: "Chưa xác thực",
    verified: "Đã xác thực",
  };
  return labels[key] || key || "Không rõ";
}

function relationLabel(value: unknown) {
  const key = String(value || "");
  const labels: Record<string, string> = {
    owner: "Dự án của bạn",
    owner_entity: "Hồ sơ phụ trách",
    linked_entity_participation: "Liên quan hồ sơ",
  };
  return labels[key] || "Liên quan hồ sơ";
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

export default function MyProjectsPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [projects, setProjects] = useState<ApiEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState("");

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/auth/login");
      return;
    }
    if (!user) return;
    api
      .myProjects()
      .then((response) => setProjects(response.data))
      .catch((err) => setError(err instanceof Error ? err.message : "Không tải được project"))
      .finally(() => setLoading(false));
  }, [isLoading, router, user]);

  async function handleDeleteProject(project: ApiEntity) {
    const confirmed = window.confirm(
      `Remove project "${project.name}"?\n\nDự án sẽ bị ẩn khỏi danh sách của bạn và bị vô hiệu hóa khỏi gợi ý.`,
    );
    if (!confirmed) return;
    setDeletingId(project.id);
    setError("");
    try {
      await api.deleteMyProject(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xóa được project");
    } finally {
      setDeletingId("");
    }
  }

  return (
    <div className="min-h-svh bg-background">
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
              <FolderKanban className="h-7 w-7" />
              My Projects
            </h1>
            <p className="mt-2 text-muted-foreground">
              Dự án do bạn tạo và dự án liên quan đến hồ sơ expert/enterprise/funder đang liên kết.
            </p>
          </div>
          <Link href="/projects/create">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Tạo dự án
            </Button>
          </Link>
        </header>

        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : error ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-rose-700">{error}</div>
        ) : projects.length === 0 ? (
          <div className="rounded-md border p-8 text-center">
            <div className="text-lg font-semibold">Chưa có dự án nào</div>
            <p className="mt-2 text-sm text-muted-foreground">Tạo dự án đầu tiên để bắt đầu luồng demo người dùng.</p>
            <Link href="/projects/create">
              <Button className="mt-4">Tạo dự án</Button>
            </Link>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((project) => (
              <Card key={project.id} className="rounded-md">
                <CardHeader>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary" className="rounded-md">
                        {statusLabel(project.metadata?.status ?? "draft")}
                      </Badge>
                      <Badge variant="outline" className="rounded-md">
                        {statusLabel(project.metadata?.kg_sync_status ?? "not_synced")}
                      </Badge>
                      <Badge variant="outline" className="rounded-md">
                        {relationLabel(project.metadata?.my_project_relation)}
                      </Badge>
                      <Badge variant="outline" className={`rounded-md ${embeddingBadge(project.metadata?.embedding_status).className}`}>
                        {embeddingBadge(project.metadata?.embedding_status).label}
                      </Badge>
                    </div>
                    <span className="text-xs text-muted-foreground">{project.id}</span>
                  </div>
                  <CardTitle className="line-clamp-2 text-lg">{project.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="line-clamp-3 text-sm text-muted-foreground">{project.summary || "Chưa có tóm tắt."}</p>
                  <div className="mt-3 grid gap-1 text-xs text-muted-foreground">
                    <div>Verification: {statusLabel(project.metadata?.entity_verification_status ?? "unverified")}</div>
                    <div>Scope: {String(project.metadata?.participation_scope ?? "owner_only")}</div>
                    {project.metadata?.linked_entity_role ? (
                      <div>Vai trò liên kết: {String(project.metadata.linked_entity_role)}</div>
                    ) : null}
                    <div>
                      Embedding: {embeddingBadge(project.metadata?.embedding_status).label}
                      {project.metadata?.embedding && typeof project.metadata.embedding === "object"
                        ? ` / signal ${String((project.metadata.embedding as Record<string, unknown>).signal ?? "unknown")}`
                        : ""}
                    </div>
                    <div>Trust: {Math.round(Number(project.metadata?.trust_weight ?? 0.5) * 100)}%</div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link href={`/projects/${project.id}/overview`}>
                      <Button size="sm" variant="outline">
                        Overview
                      </Button>
                    </Link>
                    <Link href={`/graph/neighbors?type=project&id=${project.id}`}>
                      <Button size="sm" variant="outline">
                        Graph
                      </Button>
                    </Link>
                    {project.metadata?.can_delete ? (
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={deletingId === project.id}
                        onClick={() => handleDeleteProject(project)}
                      >
                        {deletingId === project.id ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="mr-2 h-4 w-4" />
                        )}
                        Remove
                      </Button>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
