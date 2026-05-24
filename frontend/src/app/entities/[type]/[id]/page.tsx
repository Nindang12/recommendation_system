"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  GitBranch,
  GraduationCap,
  Loader2,
  Sparkles,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { api, ApiEntity, EntityType, getRecommendationExplanation, RecommendationItem } from "@/lib/api";

const typeLabels: Record<EntityType, string> = {
  project: "Project",
  expert: "Expert",
  funder: "Funder",
  enterprise: "Enterprise",
};

const typeIcons = {
  project: GraduationCap,
  expert: UserCheck,
  funder: TrendingUp,
  enterprise: Building2,
};

const targetOptions: EntityType[] = ["expert", "funder", "enterprise", "project"];

function formatLabel(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPrimitive(value: unknown) {
  if (value === null || value === undefined || value === "") return "Chua co du lieu";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "boolean") return value ? "Co" : "Khong";
  return String(value);
}

function MetadataValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">Chua co du lieu</span>;

    const allPrimitive = value.every((item) => typeof item !== "object" || item === null);

    if (allPrimitive) {
      return (
        <div className="flex flex-wrap gap-1.5">
          {value.map((item, index) => (
            <Badge key={index} variant="secondary" className="max-w-full rounded-md whitespace-normal text-left">
              {formatPrimitive(item)}
            </Badge>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div key={index} className="rounded-md border bg-secondary/30 p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Item {index + 1}
            </div>
            {typeof item === "object" && item !== null ? (
              <MetadataValue value={item} depth={depth + 1} />
            ) : (
              <span className="break-words">{formatPrimitive(item)}</span>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-muted-foreground">Chua co du lieu</span>;

    return (
      <div className={depth === 0 ? "space-y-3" : "space-y-2 rounded-md bg-secondary/40 p-3"}>
        {entries.map(([childKey, childValue]) => (
          <MetadataRow key={childKey} label={formatLabel(childKey)} value={childValue} depth={depth + 1} />
        ))}
      </div>
    );
  }

  return <span className="break-words">{formatPrimitive(value)}</span>;
}

function MetadataRow({ label, value, depth = 0 }: { label: string; value: unknown; depth?: number }) {
  const isNestedObject = typeof value === "object" && value !== null && !Array.isArray(value);
  const isComplexArray = Array.isArray(value) && value.some((item) => typeof item === "object" && item !== null);

  if (isNestedObject || isComplexArray) {
    return (
      <div className="space-y-2">
        <div className="text-xs font-semibold text-muted-foreground">{label}</div>
        <MetadataValue value={value} depth={depth} />
      </div>
    );
  }

  return (
    <div className="grid gap-1 sm:grid-cols-[180px_minmax(0,1fr)] sm:gap-4">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="min-w-0 text-sm font-medium leading-relaxed [overflow-wrap:anywhere]">
        <MetadataValue value={value} depth={depth} />
      </div>
    </div>
  );
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

export default function EntityDetailPage({ params }: { params: Promise<{ type: string; id: string }> }) {
  const { type, id } = use(params);
  const entityType = type as EntityType;
  const Icon = typeIcons[entityType] ?? GitBranch;
  const [entity, setEntity] = useState<ApiEntity | null>(null);
  const [targetType, setTargetType] = useState<EntityType>(entityType === "project" ? "expert" : "project");
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [isEntityLoading, setIsEntityLoading] = useState(true);
  const [isRecommendationLoading, setIsRecommendationLoading] = useState(false);
  const [error, setError] = useState("");
  const [recommendationError, setRecommendationError] = useState("");

  useEffect(() => {
    setIsEntityLoading(true);
    setError("");
    api
      .getEntity(entityType, id)
      .then((result) => setEntity(result.data))
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Khong tai duoc entity"))
      .finally(() => setIsEntityLoading(false));
  }, [entityType, id]);

  async function runRecommendation() {
    if (!entity) return;

    setIsRecommendationLoading(true);
    setRecommendationError("");
    setRecommendations([]);

    try {
      const result = await api.recommend(entity.id, entity.type, targetType, 5);
      setRecommendations(normalizeRecommendations(result));
    } catch (requestError) {
      setRecommendationError(
        requestError instanceof Error ? requestError.message : "Khong chay duoc recommendation cho entity nay",
      );
    } finally {
      setIsRecommendationLoading(false);
    }
  }

  return (
    <div className="min-h-svh bg-background">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6">
        <Link
          href="/search"
          className="inline-flex w-fit items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Quay lai entity browser
        </Link>

        {error ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
        ) : isEntityLoading || !entity ? (
          <div className="flex min-h-[420px] items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Dang tai chi tiet entity...
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
            <section className="space-y-4">
              <Card className="rounded-md">
                <CardContent className="space-y-5 p-6">
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-md bg-secondary">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <Badge variant="outline" className="rounded-md">
                        {typeLabels[entity.type] ?? entity.type}
                      </Badge>
                      <div className="mt-1 text-sm text-muted-foreground">ID: {entity.id}</div>
                    </div>
                  </div>

                  <div>
                    <h1 className="text-3xl font-bold tracking-tight md:text-4xl">{entity.name || entity.id}</h1>
                    <p className="mt-3 max-w-3xl text-muted-foreground">
                      {entity.summary || "Entity nay chua co summary trong backend response."}
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card className="rounded-md">
                <CardHeader>
                  <CardTitle className="text-lg">Metadata</CardTitle>
                </CardHeader>
                <CardContent>
                  {entity.metadata && Object.keys(entity.metadata).length > 0 ? (
                    <div className="space-y-4">
                      {Object.entries(entity.metadata).map(([key, value]) => (
                        <div key={key} className="overflow-hidden rounded-md border bg-background p-4">
                          <div className="mb-4 border-b pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {formatLabel(key)}
                          </div>
                          <div className="min-w-0 text-sm">
                            <MetadataValue value={value} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                      API chua tra ve metadata cho entity nay.
                    </div>
                  )}
                </CardContent>
              </Card>
            </section>

            <aside className="space-y-4">
              <Card className="rounded-md">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Sparkles className="h-4 w-4" />
                    Goi y tu entity nay
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <div className="text-sm font-medium">Target type</div>
                    <Select value={targetType} onValueChange={(value) => setTargetType(value as EntityType)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {targetOptions.map((option) => (
                          <SelectItem key={option} value={option}>
                            {typeLabels[option]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <Button className="w-full gap-2" onClick={() => void runRecommendation()} disabled={isRecommendationLoading}>
                    {isRecommendationLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    Chay recommendation
                  </Button>

                  <Separator />

                  {recommendationError ? (
                    <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                      {recommendationError}
                    </div>
                  ) : recommendations.length === 0 ? (
                    <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                      Chua co ket qua. Bam nut tren de goi PGPR API.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {recommendations.map((item, index) => (
                        <div key={`${item.id}-${index}`} className="rounded-md border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-xs font-semibold text-muted-foreground">Rank #{index + 1}</div>
                              <Link
                                href={`/entities/${item.type ?? targetType}/${item.id}`}
                                className="mt-1 block font-semibold hover:underline"
                              >
                                {item.name || item.id}
                              </Link>
                            </div>
                            <Badge variant="secondary" className="rounded-md">
                              {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
                            </Badge>
                          </div>
                          {getRecommendationExplanation(item) ? (
                            <p className="mt-2 line-clamp-3 whitespace-pre-line text-sm text-muted-foreground">
                              {getRecommendationExplanation(item)}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
