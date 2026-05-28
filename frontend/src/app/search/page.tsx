"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Building2, Database, GraduationCap, Loader2, Search, Sparkles, TrendingUp, UserCheck } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiEntity, entityCollections, EntityType, getRecommendationExplanation, RecommendationItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const tabs: Array<{ type: EntityType; label: string; icon: typeof GraduationCap }> = [
  { type: "project", label: "Projects", icon: GraduationCap },
  { type: "expert", label: "Experts", icon: UserCheck },
  { type: "funder", label: "Funders", icon: TrendingUp },
  { type: "enterprise", label: "Enterprises", icon: Building2 },
];

type ActiveType = EntityType | "all";

function getUserSourceEntity(user: ReturnType<typeof useAuth>["user"]): ApiEntity | null {
  const linked = user?.linked_entity;
  const linkedType = linked?.type?.toLowerCase() as EntityType | undefined;
  if (!linked?.id || !linkedType || !entityCollections[linkedType]) return null;

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

function SearchPageContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const requestedType = searchParams.get("type") as ActiveType | null;
  const initialType = requestedType && (requestedType === "all" || entityCollections[requestedType as EntityType])
    ? requestedType
    : "all";
  const [activeType, setActiveType] = useState<ActiveType>(initialType);
  const [query, setQuery] = useState("");
  const [entities, setEntities] = useState<ApiEntity[]>([]);
  const [count, setCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [recommendTarget, setRecommendTarget] = useState<ApiEntity | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [isRecommendLoading, setIsRecommendLoading] = useState(false);
  const [recommendError, setRecommendError] = useState("");

  const activeCollection = useMemo(() => (activeType === "all" ? "all entities" : entityCollections[activeType]), [activeType]);
  const sourceEntity = useMemo(() => getUserSourceEntity(user), [user]);
  const targetEvaluation = useMemo(
    () => recommendations.find((item) => item.id === recommendTarget?.id),
    [recommendTarget?.id, recommendations],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsLoading(true);
      setError("");
      const request =
        activeType === "all"
          ? Promise.all(tabs.map((tab) => api.listEntities(entityCollections[tab.type], query, 12, 1)))
          : api.listEntities(entityCollections[activeType], query, 36, 1).then((result) => [result]);

      request
        .then((results) => {
          const nextEntities = results.flatMap((result) => result.data ?? []);
          const nextCount = results.reduce((total, result) => total + (result.count ?? result.data?.length ?? 0), 0);
          setEntities(nextEntities);
          setCount(nextCount);
        })
        .catch((requestError) => {
          setEntities([]);
          setCount(0);
          setError(requestError instanceof Error ? requestError.message : "Khong tai duoc entity");
        })
        .finally(() => setIsLoading(false));
    }, 250);

    return () => window.clearTimeout(timer);
  }, [activeType, query]);

  async function recommendEntity(entity: ApiEntity) {
    if (!sourceEntity) {
      setRecommendError("Tai khoan hien tai chua co linked entity de lam source recommendation.");
      setRecommendTarget(entity);
      setRecommendations([]);
      return;
    }

    setRecommendTarget(entity);
    setRecommendations([]);
    setRecommendError("");
    setIsRecommendLoading(true);

    try {
      const response = await api.recommendEntity(
        sourceEntity.id,
        sourceEntity.type,
        entity.id,
        entity.type,
        "personal",
        user?.id,
      );
      setRecommendations(normalizeRecommendations(response));
    } catch (requestError) {
      setRecommendError(requestError instanceof Error ? requestError.message : "Goi recommendation that bai");
    } finally {
      setIsRecommendLoading(false);
    }
  }

  return (
    <div className="min-h-svh bg-background">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <Badge variant="outline" className="mb-3 gap-1 rounded-md">
              <Database className="h-3.5 w-3.5" />
              Entity browser
            </Badge>
            <h1 className="text-3xl font-bold tracking-tight">Duyet du lieu MongoDB</h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              Xem tat ca entity trong he thong va chay recommendation tu ho so dang dang nhap toi tung nhom entity.
            </p>
          </div>
          <Link href="/dashboard">
            <Button variant="outline">Ve dashboard</Button>
          </Link>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
          <Tabs value={activeType} onValueChange={(value) => setActiveType(value as ActiveType)}>
            <TabsList className="grid h-auto grid-cols-2 gap-2 bg-transparent p-0 md:grid-cols-5">
              <TabsTrigger
                value="all"
                className="gap-2 rounded-md border data-[state=active]:border-primary data-[state=active]:bg-secondary"
              >
                <Database className="h-4 w-4" />
                Tat ca
              </TabsTrigger>
              {tabs.map((tab) => (
                <TabsTrigger
                  key={tab.type}
                  value={tab.type}
                  className="gap-2 rounded-md border data-[state=active]:border-primary data-[state=active]:bg-secondary"
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-9"
              placeholder="Search theo name, title hoac id..."
            />
          </div>
        </div>

        <div className="flex items-center justify-between border-b pb-3">
          <div className="text-sm text-muted-foreground">
            Dang xem <span className="font-semibold text-foreground">{activeCollection}</span>
            {sourceEntity ? (
              <span> | Source: {sourceEntity.name} ({sourceEntity.type})</span>
            ) : null}
          </div>
          <Badge variant="secondary" className="rounded-md">
            {count} entities
          </Badge>
        </div>

        {recommendTarget ? (
          <Card className="rounded-md">
            <CardContent className="space-y-4 p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase text-muted-foreground">Recommend entity</div>
                  <h2 className="mt-1 text-xl font-semibold">{recommendTarget.name || recommendTarget.id}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Source la {sourceEntity ? `${sourceEntity.name} (${sourceEntity.type})` : "linked entity cua user"}.
                    Backend se danh gia truc tiep source nay voi entity dang chon.
                  </p>
                </div>
                <Badge variant={targetEvaluation?.matched_requested_entity ? "default" : "outline"} className="rounded-md">
                  {targetEvaluation?.matched_requested_entity
                    ? `Co trong top recommendation #${targetEvaluation.matched_rank ?? "?"}`
                    : "Target-specific evaluation"}
                </Badge>
              </div>

              {recommendError ? (
                <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{recommendError}</div>
              ) : isRecommendLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Dang chay PGPR recommendation...
                </div>
              ) : recommendations.length > 0 ? (
                <div className="grid gap-3">
                  {recommendations.map((item, index) => {
                    const isTarget = item.id === recommendTarget.id;
                    return (
                      <div
                        key={`${item.id}-${index}`}
                        className={`rounded-md border p-3 ${isTarget ? "border-primary bg-secondary/60" : "bg-background"}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className="rounded-md">
                                {item.matched_requested_entity ? `Rank #${item.matched_rank ?? index + 1}` : "Direct evaluation"}
                              </Badge>
                              {isTarget ? <Badge className="rounded-md">Selected entity</Badge> : null}
                            </div>
                            <Link
                              href={`/entities/${item.type ?? recommendTarget.type}/${item.id}`}
                              className="mt-2 block font-semibold hover:underline"
                            >
                              {item.name || item.id}
                            </Link>
                            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                              {getRecommendationExplanation(item) || "Chua co XAI preview."}
                            </p>
                          </div>
                          <div className="shrink-0 rounded-md border bg-secondary/50 px-2 py-1 text-sm font-semibold">
                            {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        {error ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
        ) : isLoading ? (
          <div className="flex min-h-[360px] items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Dang tai du lieu...
          </div>
        ) : entities.length === 0 ? (
          <div className="flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-md border border-dashed text-center">
            <Database className="h-8 w-8 text-muted-foreground" />
            <div>
              <div className="font-semibold">Khong co du lieu phu hop</div>
              <div className="text-sm text-muted-foreground">Thu doi tu khoa hoac chon loai entity khac.</div>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {entities.map((entity) => (
              <Card key={`${entity.type}-${entity.id}`} className="h-full rounded-md transition-colors hover:border-primary">
                <CardContent className="flex h-full flex-col gap-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Badge variant="outline" className="mb-2 rounded-md">
                        {entity.type}
                      </Badge>
                      <h2 className="line-clamp-2 text-lg font-semibold">{entity.name || entity.id}</h2>
                    </div>
                  </div>
                  <p className="line-clamp-3 text-sm text-muted-foreground">
                    {entity.summary || "Chua co summary trong API response."}
                  </p>
                  <div className="mt-auto break-all text-xs text-muted-foreground">ID: {entity.id}</div>
                  <div className="flex flex-wrap gap-2 pt-2">
                    <Button
                      type="button"
                      size="sm"
                      className="gap-2"
                      onClick={() => void recommendEntity(entity)}
                      disabled={isRecommendLoading}
                    >
                      <Sparkles className="h-4 w-4" />
                      Recommend entity
                    </Button>
                    <Link href={`/entities/${entity.type}/${entity.id}`}>
                      <Button type="button" size="sm" variant="outline" className="gap-2">
                        Chi tiet
                        <ArrowRight className="h-4 w-4" />
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

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-svh bg-background">
          <Navbar />
          <main className="mx-auto flex min-h-[420px] max-w-7xl items-center justify-center px-4 py-6 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Dang tai entity browser...
          </main>
        </div>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}
