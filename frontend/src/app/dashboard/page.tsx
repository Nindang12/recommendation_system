"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  api,
  ApiEntity,
  EntityType,
  ExplanationResponse,
  getRecommendationExplanation,
  getRecommendationVisualization,
  HealthResponse,
  RecommendationItem,
} from "@/lib/api";
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

const demoSources = [
  { id: "prj_001", type: "project" as EntityType, name: "Demo Project -> Expert", target: "expert" as EntityType },
  { id: "prj_001", type: "project" as EntityType, name: "Demo Project -> Funder", target: "funder" as EntityType },
  { id: "prj_001", type: "project" as EntityType, name: "Demo Project -> Enterprise", target: "enterprise" as EntityType },
];

function statusTone(value?: string) {
  if (!value) return "bg-slate-100 text-slate-700";
  const normalized = value.toLowerCase();
  if (["connected", "ready", "ok"].some((item) => normalized.includes(item))) {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
  if (normalized.includes("optional")) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-rose-50 text-rose-700 border-rose-200";
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
    <div className="rounded-md border bg-background p-4">
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

function ReasoningPathCard({ path, index }: { path: unknown; index: number }) {
  const parts = getPathParts(path);
  const score = getPathScore(path);
  const length = getPathLength(path, parts);

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
        <div className="flex flex-wrap items-center gap-2">
          {parts.map((part, partIndex) => (
            <div key={`${part}-${partIndex}`} className="flex items-center gap-2">
              <Badge variant="outline" className="rounded-md bg-secondary/40 px-2 py-1 text-xs">
                {humanizeRelation(part)}
              </Badge>
              {partIndex < parts.length - 1 ? <span className="text-muted-foreground">→</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <pre className="whitespace-pre-wrap break-words text-sm">{formatJsonBlock(path)}</pre>
      )}
    </div>
  );
}

function VisualizationBlock({ text }: { text: string }) {
  const cleaned = cleanXaiText(text)
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("=") && !line.toLowerCase().includes("reasoning paths visualization"));

  if (cleaned.length === 0) return null;

  return (
    <div className="space-y-2 rounded-md border bg-secondary/30 p-4">
      {cleaned.map((line, index) => {
        const isPathTitle = /^Path\s+\d+/i.test(line);
        return (
          <div
            key={`${line}-${index}`}
            className={isPathTitle ? "pt-2 text-sm font-semibold text-foreground first:pt-0" : "pl-3 text-sm text-muted-foreground"}
          >
            {line.replace(/[┌└├─>]/g, "").replace(/^\s+/, "")}
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState("");
  const [sourceType, setSourceType] = useState<EntityType>("project");
  const [targetType, setTargetType] = useState<EntityType>("expert");
  const [sourceId, setSourceId] = useState("prj_001");
  const [sourceName, setSourceName] = useState("prj_001");
  const [limit, setLimit] = useState("5");
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [selectedSource, setSelectedSource] = useState<ApiEntity | null>(null);
  const [selectedExplanation, setSelectedExplanation] = useState<RecommendationItem | null>(null);
  const [generatedExplanation, setGeneratedExplanation] = useState<ExplanationResponse["data"] | null>(null);
  const [isExplanationLoading, setIsExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState("");

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((error) => setHealthError(error instanceof Error ? error.message : "Khong ket noi duoc backend"));
  }, []);

  const healthServices = useMemo(() => Object.entries(health?.services ?? {}), [health]);

  async function runRecommendation(nextSourceId = sourceId, nextSourceType = sourceType, nextTargetType = targetType) {
    setIsLoading(true);
    setRecommendationError("");
    setRecommendations([]);

    const source: ApiEntity = {
      id: nextSourceId,
      name: sourceName || nextSourceId,
      type: nextSourceType,
    };

    setSelectedSource(source);

    try {
      const result = await api.recommend(nextSourceId, nextSourceType, nextTargetType, Number(limit) || 5);
      setRecommendations(normalizeRecommendations(result));
    } catch (error) {
      setRecommendationError(error instanceof Error ? error.message : "Goi recommendation that bai");
    } finally {
      setIsLoading(false);
    }
  }

  function applyDemo(demo: (typeof demoSources)[number]) {
    setSourceType(demo.type);
    setTargetType(demo.target);
    setSourceId(demo.id);
    setSourceName(demo.id);
    void runRecommendation(demo.id, demo.type, demo.target);
  }

  async function requestDetailedExplanation(item: RecommendationItem, forceRefresh = false) {
    const source: ApiEntity = selectedSource ?? {
      id: sourceId,
      name: sourceName || sourceId,
      type: sourceType,
    };
    const mode = "auto";
    const resolvedTargetType = item.type ?? targetType;

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
    <div className="min-h-svh bg-background">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6">
        <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="outline" className="gap-1 rounded-md">
                <GitFork className="h-3.5 w-3.5" />
                PGPR runtime
              </Badge>
              <Badge variant="outline" className="gap-1 rounded-md">
                <Database className="h-3.5 w-3.5" />
                MongoDB + Neo4j
              </Badge>
              <Badge variant="outline" className="gap-1 rounded-md">
                <Sparkles className="h-3.5 w-3.5" />
                XAI explanations
              </Badge>
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight md:text-4xl">Dashboard demo he thong goi y R&D</h1>
              <p className="mt-2 max-w-3xl text-muted-foreground">
                Giao dien tap trung vao luong bao ve do an: kiem tra backend, duyet entity, chay PGPR recommendation,
                xem score, explanation va reasoning paths.
              </p>
            </div>
          </div>

          <Card className="rounded-md">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="h-4 w-4" />
                System health
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {healthError ? (
                <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                  <AlertCircle className="mt-0.5 h-4 w-4" />
                  <span>{healthError}</span>
                </div>
              ) : !health ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Dang kiem tra backend...
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">API status</span>
                    <Badge className={statusTone(health.status)} variant="outline">
                      {health.status}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {healthServices.map(([name, value]) => (
                      <div key={name} className="rounded-md border p-3">
                        <div className="text-xs uppercase text-muted-foreground">{name}</div>
                        <div className="mt-1 text-sm font-semibold">{value}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          {entityOptions.map((option) => (
            <Link href={`/search?type=${option.type}`} key={option.type}>
              <Card className="h-full rounded-md transition-colors hover:border-primary">
                <CardContent className="flex items-center gap-3 p-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
                    <option.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="font-semibold">{option.collectionLabel}</div>
                    <div className="text-sm text-muted-foreground">Browse data</div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-[420px_1fr]">
          <Card className="rounded-md">
            <CardHeader>
              <CardTitle className="text-lg">Recommendation workspace</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>Source type</Label>
                  <Select value={sourceType} onValueChange={(value) => setSourceType(value as EntityType)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {entityOptions.map((option) => (
                        <SelectItem key={option.type} value={option.type}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Target type</Label>
                  <Select value={targetType} onValueChange={(value) => setTargetType(value as EntityType)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {entityOptions.map((option) => (
                        <SelectItem key={option.type} value={option.type}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Source ID</Label>
                <Input value={sourceId} onChange={(event) => setSourceId(event.target.value)} placeholder="prj_001" />
              </div>

              <div className="space-y-2">
                <Label>Limit</Label>
                <Input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" />
              </div>

              <Button className="w-full gap-2" onClick={() => void runRecommendation()} disabled={isLoading}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Chay PGPR recommendation
              </Button>

              <Separator />

              <div className="space-y-2">
                <div className="text-sm font-semibold">Quick demo</div>
                <div className="grid gap-2">
                  {demoSources.map((demo) => (
                    <Button
                      key={`${demo.id}-${demo.target}`}
                      variant="outline"
                      className="justify-between"
                      onClick={() => applyDemo(demo)}
                    >
                      {demo.name}
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-md">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-lg">Recommendation results</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Ket qua duoc rut gon de de doc. Bam giai thich chi tiet de xem XAI day du.
                  </p>
                </div>
                <Badge variant="outline" className="rounded-md">
                  {recommendations.length} ket qua
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {recommendationError ? (
                <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {recommendationError}
                </div>
              ) : recommendations.length === 0 ? (
                <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-md border border-dashed text-center">
                  <Search className="h-8 w-8 text-muted-foreground" />
                  <div>
                    <div className="font-semibold">Chua co ket qua</div>
                    <div className="text-sm text-muted-foreground">Nhap source ID hoac dung quick demo de goi backend.</div>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {recommendations.map((item, index) => (
                    <div key={`${item.id}-${index}`} className="rounded-md border bg-background p-4 transition-colors hover:border-primary/60">
                      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
                        <div className="min-w-0">
                          <div className="mb-1 flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className="rounded-md">
                              Rank #{index + 1}
                            </Badge>
                            <Badge variant="secondary" className="rounded-md">
                              {item.type ?? targetType}
                            </Badge>
                          </div>
                          <Link
                            href={`/entities/${item.type ?? targetType}/${item.id}`}
                            className="block text-lg font-semibold leading-snug hover:underline"
                          >
                            {item.name || item.id}
                          </Link>
                          <div className="mt-1 text-xs text-muted-foreground">ID: {item.id}</div>
                        </div>
                        <div className="flex md:justify-end">
                          <div className="rounded-md border bg-secondary/60 px-3 py-2 text-right">
                            <div className="text-xs text-muted-foreground">Score</div>
                            <div className="text-base font-bold">
                              {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 rounded-md bg-secondary/40 p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                          <Info className="h-3.5 w-3.5" />
                          XAI preview
                        </div>
                        <p className="text-sm leading-6 text-muted-foreground">{getXaiPreview(item)}</p>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="outline" className="rounded-md gap-1">
                          <Network className="h-3 w-3" />
                          {item.reasoning_paths?.length ?? 0} paths
                        </Badge>
                        {typeof item.path_diversity === "number" ? (
                          <Badge variant="outline" className="rounded-md">
                            Diversity {item.path_diversity}
                          </Badge>
                        ) : null}
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button variant="default" size="sm" onClick={() => void openDetailedExplanation(item)}>
                          Giai thich chi tiet
                        </Button>
                        {selectedSource ? (
                          <Link href={`/entities/${item.type ?? targetType}/${item.id}`}>
                            <Button variant="outline" size="sm">
                              Xem chi tiet
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
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto rounded-md">
          <DialogHeader>
            <DialogTitle>Giai thich XAI chi tiet</DialogTitle>
            <DialogDescription>
              Ly do PGPR de xuat entity nay, kem reasoning paths neu backend tra ve.
            </DialogDescription>
          </DialogHeader>

          {selectedExplanation ? (
            <div className="space-y-5">
              <div className="rounded-md border bg-secondary/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold uppercase text-muted-foreground">Recommendation</div>
                    <div className="mt-1 text-lg font-semibold">{selectedExplanation.name || selectedExplanation.id}</div>
                    <div className="mt-1 text-xs text-muted-foreground">ID: {selectedExplanation.id}</div>
                  </div>
                  <Badge className="rounded-md" variant="secondary">
                    Score{" "}
                    {typeof selectedExplanation.score === "number" ? selectedExplanation.score.toFixed(3) : "N/A"}
                  </Badge>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
                <div>
                  <div className="text-sm font-semibold">Trang thai explanation</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {isExplanationLoading
                      ? "Dang request API explanations..."
                      : generatedExplanation?._cache?.hit
                        ? "Service layer tra ve tu cache, khong sinh lai XAI."
                        : generatedExplanation
                          ? "Service layer vua sinh moi XAI va luu cache."
                          : "Chua co explanation."}
                  </div>
                  {generatedExplanation?._cache?.key ? (
                    <div className="mt-1 break-all text-[11px] text-muted-foreground">
                      Cache key: {generatedExplanation._cache.key}
                    </div>
                  ) : null}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void regenerateExplanation()}
                  disabled={isExplanationLoading}
                >
                  {isExplanationLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Tao lai giai thich
                </Button>
              </div>

              <section className="space-y-3">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  XAI explanation tu API /api/v1/explanations
                </h3>
                <div className="rounded-md border p-4">
                  {isExplanationLoading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Dang goi model XAI de tao giai thich...
                    </div>
                  ) : explanationError ? (
                    <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
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
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Confidence
                  </h3>
                  <ConfidenceBlock confidence={generatedExplanation.confidence} />
                </section>
              ) : null}

              {selectedExplanation.reasoning_paths?.length ? (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Reasoning paths
                  </h3>
                  <div className="space-y-2">
                    {selectedExplanation.reasoning_paths.map((path, index) => (
                      <ReasoningPathCard key={index} path={path} index={index} />
                    ))}
                  </div>
                </section>
              ) : null}

              {(generatedExplanation?.visualization || getRecommendationVisualization(selectedExplanation)) ? (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Visualization text
                  </h3>
                  <VisualizationBlock text={generatedExplanation?.visualization || getRecommendationVisualization(selectedExplanation)} />
                </section>
              ) : null}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
