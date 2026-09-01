"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Loader2, Network } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { SimpleGraph } from "@/components/graph/simple-graph";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, EntityType, GraphNeighborsResponse } from "@/lib/api";

function NeighborGraphContent() {
  const params = useSearchParams();
  const [entityType, setEntityType] = useState<EntityType>((params.get("type") as EntityType) || "project");
  const [entityId, setEntityId] = useState(params.get("id") || "prj_001");
  const [depth, setDepth] = useState("1");
  const [graph, setGraph] = useState<GraphNeighborsResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadGraph() {
    setIsLoading(true);
    setError("");
    setGraph(null);
    try {
      const response = await api.graphNeighbors(entityType, entityId, Number(depth) || 1, 80);
      setGraph(response.data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Khong tai duoc neighbor graph");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadGraph();
  }, []);

  return (
    <div className="min-h-svh bg-background">
      <Navbar />
      <main className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6">
        <Link href="/dashboard" className="inline-flex w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Ve dashboard
        </Link>

        <div>
          <Badge variant="outline" className="mb-2 rounded-md">
            Graph neighbors
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight">Neighbor graph visualization</h1>
          <p className="mt-2 text-muted-foreground">Goi API neighbors va ve ego graph quanh mot entity.</p>
        </div>

        <Card className="rounded-md">
          <CardContent className="grid gap-3 p-4 md:grid-cols-[180px_1fr_120px_auto] md:items-end">
            <div className="space-y-2">
              <Label>Entity type</Label>
              <Select value={entityType} onValueChange={(value) => setEntityType(value as EntityType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="project">Project</SelectItem>
                  <SelectItem value="expert">Expert</SelectItem>
                  <SelectItem value="funder">Funder</SelectItem>
                  <SelectItem value="enterprise">Enterprise</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Entity ID</Label>
              <Input value={entityId} onChange={(event) => setEntityId(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Depth</Label>
              <Input value={depth} onChange={(event) => setDepth(event.target.value)} inputMode="numeric" />
            </div>
            <Button onClick={() => void loadGraph()} disabled={isLoading}>
              {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Load graph
            </Button>
          </CardContent>
        </Card>

        <Card className="rounded-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Network className="h-4 w-4" />
              Graph result
            </CardTitle>
          </CardHeader>
          <CardContent>
            {error ? (
              <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
            ) : isLoading ? (
              <div className="flex min-h-[320px] items-center justify-center gap-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                Dang tai graph...
              </div>
            ) : (
              <SimpleGraph nodes={graph?.nodes ?? []} edges={graph?.edges ?? []} />
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

export default function NeighborGraphPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-svh bg-background">
          <Navbar />
          <main className="mx-auto flex min-h-[420px] max-w-7xl items-center justify-center px-4 py-6 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Dang tai graph page...
          </main>
        </div>
      }
    >
      <NeighborGraphContent />
    </Suspense>
  );
}
