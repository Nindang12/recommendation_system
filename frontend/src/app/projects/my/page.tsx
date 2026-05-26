"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderKanban, Loader2, Plus } from "lucide-react";
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
    not_synced: "Chua sync KG",
    syncing: "Dang sync KG",
    synced_unverified: "KG unverified",
    synced_verified: "KG verified",
    sync_failed: "Sync loi",
    merge_required: "Can review",
    unverified: "Chua xac thuc",
    verified: "Da xac thuc",
  };
  return labels[key] || key || "Khong ro";
}

export default function MyProjectsPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [projects, setProjects] = useState<ApiEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/auth/login");
      return;
    }
    if (!user) return;
    api
      .myProjects()
      .then((response) => setProjects(response.data))
      .catch((err) => setError(err instanceof Error ? err.message : "Khong tai duoc project"))
      .finally(() => setLoading(false));
  }, [isLoading, router, user]);

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
            <p className="mt-2 text-muted-foreground">Danh sach project do ban tao trong he thong.</p>
          </div>
          <Link href="/projects/create">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Tao project
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
            <div className="text-lg font-semibold">Chua co project nao</div>
            <p className="mt-2 text-sm text-muted-foreground">Tao project dau tien de bat dau luong demo nguoi dung.</p>
            <Link href="/projects/create">
              <Button className="mt-4">Tao project</Button>
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
                    </div>
                    <span className="text-xs text-muted-foreground">{project.id}</span>
                  </div>
                  <CardTitle className="line-clamp-2 text-lg">{project.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="line-clamp-3 text-sm text-muted-foreground">{project.summary || "Chua co tom tat."}</p>
                  <div className="mt-3 grid gap-1 text-xs text-muted-foreground">
                    <div>Verification: {statusLabel(project.metadata?.entity_verification_status ?? "unverified")}</div>
                    <div>Scope: {String(project.metadata?.participation_scope ?? "owner_only")}</div>
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
