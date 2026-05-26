"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Building2, Loader2, Network, Sparkles, TrendingUp, UserCheck } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { SimpleGraph } from "@/components/graph/simple-graph";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, GraphNeighborsResponse, ProjectOverviewResponse, RecommendationItem } from "@/lib/api";

const groups = [
  { key: "experts", title: "Experts", type: "expert", icon: UserCheck },
  { key: "funders", title: "Funders", type: "funder", icon: TrendingUp },
  { key: "enterprises", title: "Enterprises", type: "enterprise", icon: Building2 },
  { key: "similar_projects", title: "Similar projects", type: "project", icon: Sparkles },
] as const;

function RecommendationList({ items, type }: { items: RecommendationItem[]; type: string }) {
  if (!items?.length) {
    return <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">Khong co ket qua.</div>;
  }

  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <Link href={`/entities/${item.type ?? type}/${item.id}`} key={`${item.id}-${index}`}>
          <div className="rounded-md border p-3 transition-colors hover:border-primary">
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
          </div>
        </Link>
      ))}
    </div>
  );
}

export default function ProjectOverviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [overview, setOverview] = useState<ProjectOverviewResponse | null>(null);
  const [graph, setGraph] = useState<GraphNeighborsResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

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
    </div>
  );
}
