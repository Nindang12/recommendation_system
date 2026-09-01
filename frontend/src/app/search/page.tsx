"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Building2, ChevronLeft, ChevronRight, Database, GraduationCap, Loader2, Search, Sparkles, TrendingUp, UserCheck } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiEntity, EntityCollection, entityCollections, EntityType, ExplanationResponse, getRecommendationExplanation, RecommendationItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const tabs: Array<{ type: EntityType; label: string; icon: typeof GraduationCap }> = [
  { type: "project", label: "Projects", icon: GraduationCap },
  { type: "expert", label: "Experts", icon: UserCheck },
  { type: "funder", label: "Funders", icon: TrendingUp },
  { type: "enterprise", label: "Enterprises", icon: Building2 },
];

const ENTITY_PAGE_SIZE = 9;
const ENTITY_FETCH_LIMIT = 100;
const ENTITY_FETCH_PAGE_GUARD = 20;

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

function cleanXaiText(text: string) {
  return text.replace(/\*\*/g, "").replace(/```/g, "").trim();
}

function XaiTextBlock({ text }: { text: string }) {
  const lines = cleanXaiText(text)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return <p className="text-sm text-slate-500">Chưa có nội dung giải thích.</p>;
  }

  return (
    <div className="space-y-3">
      {lines.map((line, index) => (
        <p key={`${line}-${index}`} className="text-sm leading-6 text-slate-700">
          {line}
        </p>
      ))}
    </div>
  );
}

async function fetchAllFromCollection(collection: EntityCollection, search: string): Promise<ApiEntity[]> {
  const allItems: ApiEntity[] = [];
  let page = 1;
  let total = 0;

  while (page <= ENTITY_FETCH_PAGE_GUARD) {
    const result = await api.listEntities(collection, search, ENTITY_FETCH_LIMIT, page);
    const items = result.data ?? [];
    allItems.push(...items);
    total = result.count ?? allItems.length;

    if (items.length === 0 || allItems.length >= total || items.length < ENTITY_FETCH_LIMIT) {
      break;
    }

    page += 1;
  }

  return allItems;
}

function getPageNumbers(currentPage: number, totalPages: number): number[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
  return Array.from({ length: 5 }, (_, index) => start + index);
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
  const [entityPage, setEntityPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [recommendTargetType, setRecommendTargetType] = useState<EntityType>(
    initialType === "all" ? "project" : (initialType as EntityType),
  );
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [isRecommendLoading, setIsRecommendLoading] = useState(false);
  const [recommendError, setRecommendError] = useState("");
  const [selectedExplanation, setSelectedExplanation] = useState<RecommendationItem | null>(null);
  const [generatedExplanation, setGeneratedExplanation] = useState<ExplanationResponse["data"] | null>(null);
  const [isExplanationLoading, setIsExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState("");

  const activeCollection = useMemo(() => (activeType === "all" ? "all entities" : entityCollections[activeType]), [activeType]);
  const sourceEntity = useMemo(() => getUserSourceEntity(user), [user]);
  const totalEntityPages = Math.max(1, Math.ceil(count / ENTITY_PAGE_SIZE));
  const visibleEntities = useMemo(() => {
    const start = (entityPage - 1) * ENTITY_PAGE_SIZE;
    return entities.slice(start, start + ENTITY_PAGE_SIZE);
  }, [entities, entityPage]);
  const entityPageNumbers = useMemo(() => getPageNumbers(entityPage, totalEntityPages), [entityPage, totalEntityPages]);

  useEffect(() => {
    if (activeType !== "all") {
      setRecommendTargetType(activeType);
    }
  }, [activeType]);

  useEffect(() => {
    setEntityPage(1);
  }, [activeType, query]);

  useEffect(() => {
    if (entityPage > totalEntityPages) {
      setEntityPage(totalEntityPages);
    }
  }, [entityPage, totalEntityPages]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsLoading(true);
      setError("");
      const request =
        activeType === "all"
          ? Promise.all(tabs.map((tab) => fetchAllFromCollection(entityCollections[tab.type], query)))
          : fetchAllFromCollection(entityCollections[activeType], query).then((items) => [items]);

      request
        .then((results) => {
          const nextEntities = results.flat();
          setEntities(nextEntities);
          setCount(nextEntities.length);
        })
        .catch((requestError) => {
          setEntities([]);
          setCount(0);
          setError(requestError instanceof Error ? requestError.message : "Không tải được thực thể");
        })
        .finally(() => setIsLoading(false));
    }, 250);

    return () => window.clearTimeout(timer);
  }, [activeType, query]);

  const renderEntityPagination = () => {
    if (totalEntityPages <= 1 || isLoading || error || entities.length === 0) {
      return null;
    }

    const startItem = (entityPage - 1) * ENTITY_PAGE_SIZE + 1;
    const endItem = Math.min(entityPage * ENTITY_PAGE_SIZE, count);

    return (
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200/70 bg-white px-4 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="text-[11px] font-semibold text-slate-400">
          Hiển thị <span className="font-bold text-slate-700">{startItem}-{endItem}</span> trong{" "}
          <span className="font-bold text-slate-700">{count}</span> thực thể
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8 rounded-lg border-slate-200 text-slate-500"
            onClick={() => setEntityPage((page) => Math.max(1, page - 1))}
            disabled={entityPage === 1}
            aria-label="Trang trước"
            title="Trang trước"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>

          {entityPageNumbers[0] > 1 ? (
            <>
              <Button
                type="button"
                variant={entityPage === 1 ? "default" : "outline"}
                size="sm"
                className="h-8 min-w-8 rounded-lg px-2 text-xs font-bold"
                onClick={() => setEntityPage(1)}
              >
                1
              </Button>
              <span className="px-1 text-xs font-bold text-slate-300">...</span>
            </>
          ) : null}

          {entityPageNumbers.map((pageNumber) => (
            <Button
              key={pageNumber}
              type="button"
              variant={pageNumber === entityPage ? "default" : "outline"}
              size="sm"
              className="h-8 min-w-8 rounded-lg px-2 text-xs font-bold"
              onClick={() => setEntityPage(pageNumber)}
            >
              {pageNumber}
            </Button>
          ))}

          {entityPageNumbers[entityPageNumbers.length - 1] < totalEntityPages ? (
            <>
              <span className="px-1 text-xs font-bold text-slate-300">...</span>
              <Button
                type="button"
                variant={entityPage === totalEntityPages ? "default" : "outline"}
                size="sm"
                className="h-8 min-w-8 rounded-lg px-2 text-xs font-bold"
                onClick={() => setEntityPage(totalEntityPages)}
              >
                {totalEntityPages}
              </Button>
            </>
          ) : null}

          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8 rounded-lg border-slate-200 text-slate-500"
            onClick={() => setEntityPage((page) => Math.min(totalEntityPages, page + 1))}
            disabled={entityPage === totalEntityPages}
            aria-label="Trang sau"
            title="Trang sau"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  };

  async function recommendCurrentView() {
    if (!sourceEntity) {
      setRecommendError("Tài khoản hiện tại chưa có hồ sơ liên kết để làm nguồn gợi ý.");
      setRecommendations([]);
      return;
    }

    setRecommendations([]);
    setRecommendError("");
    setIsRecommendLoading(true);

    try {
      const response = await api.recommend(
        sourceEntity.id,
        sourceEntity.type,
        recommendTargetType,
        5,
        "personal",
        user?.id,
      );
      setRecommendations(normalizeRecommendations(response));
    } catch (requestError) {
      setRecommendError(requestError instanceof Error ? requestError.message : "Gọi gợi ý thất bại");
    } finally {
      setIsRecommendLoading(false);
    }
  }

  async function requestDetailedExplanation(item: RecommendationItem, forceRefresh = false) {
    if (!sourceEntity) {
      setExplanationError("Không tìm thấy thực thể nguồn của tài khoản hiện tại.");
      return;
    }

    setExplanationError("");
    setGeneratedExplanation(null);
    setIsExplanationLoading(true);

    try {
      const response = await api.explain(
        item,
        sourceEntity,
        item.type ?? recommendTargetType,
        "llm",
        forceRefresh,
      );
      setGeneratedExplanation(response.data ?? null);
    } catch (requestError) {
      setExplanationError(requestError instanceof Error ? requestError.message : "Không tạo được giải thích XAI");
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
    <div className="min-h-svh bg-slate-50/50">
      <Navbar />

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-slate-150 pb-5">
          <div className="space-y-2">
            <Badge className="gap-1 rounded-full bg-indigo-50 border-indigo-200 text-indigo-600 px-3 py-1 font-semibold text-xs" variant="outline">
              <Database className="h-3.5 w-3.5 text-indigo-500" />
              Entity Browser
            </Badge>
            <h1 className="text-3xl font-extrabold tracking-tight text-slate-800 font-headline">Duyệt Dữ liệu Khoa học</h1>
            <p className="max-w-2xl text-xs sm:text-sm text-slate-400 font-medium leading-relaxed">
              Truy cập toàn bộ cơ sở tri thức MongoDB và chạy trực tiếp thuật toán PGPR suy luận mối liên kết từ hồ sơ của bạn.
            </p>
          </div>
          <Link href="/dashboard">
            <Button variant="outline" className="rounded-xl border-slate-200 hover:bg-slate-50 hover:text-slate-800 text-xs font-semibold px-4 h-9 shadow-sm">
              Về Dashboard
            </Button>
          </Link>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_380px] items-center">
          <Tabs value={activeType} onValueChange={(value) => setActiveType(value as ActiveType)} className="w-full">
            <TabsList className="grid h-auto grid-cols-2 gap-2 bg-transparent p-0 md:grid-cols-5">
              <TabsTrigger
                value="all"
                className="gap-2 rounded-xl border border-slate-200 h-10 text-xs font-bold bg-white text-slate-600 transition-all duration-300 data-[state=active]:bg-primary data-[state=active]:text-white data-[state=active]:border-transparent data-[state=active]:shadow-md data-[state=active]:shadow-indigo-100"
              >
                <Database className="h-4 w-4" />
                Tất cả
              </TabsTrigger>
              {tabs.map((tab) => (
                <TabsTrigger
                  key={tab.type}
                  value={tab.type}
                  className="gap-2 rounded-xl border border-slate-200 h-10 text-xs font-bold bg-white text-slate-600 transition-all duration-300 data-[state=active]:bg-primary data-[state=active]:text-white data-[state=active]:border-transparent data-[state=active]:shadow-md data-[state=active]:shadow-indigo-100"
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="relative w-full">
            <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-10 rounded-xl border-slate-200 h-11 text-xs font-medium focus-visible:ring-indigo-500 shadow-sm"
              placeholder="Tìm kiếm theo tên, tiêu đề hoặc ID..."
            />
          </div>
        </div>

        <div className="flex items-center justify-between border-b border-slate-150 pb-4">
          <div className="text-xs font-semibold text-slate-400">
            Danh mục: <span className="font-bold text-slate-700 capitalize">{activeCollection}</span>
            {sourceEntity ? (
              <span className="hidden sm:inline"> | Source: <span className="font-bold text-indigo-500">{sourceEntity.name}</span> ({sourceEntity.type})</span>
            ) : null}
          </div>
          <Badge variant="secondary" className="rounded-md bg-slate-100 text-[10px] font-extrabold text-slate-600 px-2 py-0.5 border-transparent">
            {count} thực thể
          </Badge>
        </div>

        {/* Recommendation Launcher Card */}
        <Card className="rounded-2xl border-slate-200/60 shadow-sm bg-gradient-to-r from-violet-50/50 via-indigo-50/10 to-transparent overflow-hidden">
          <CardContent className="grid gap-5 p-6 lg:grid-cols-[1fr_auto] lg:items-center">
            <div className="space-y-3.5">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">Recommend Entity</div>
                <h2 className="mt-1 text-lg font-bold tracking-tight text-slate-800 font-headline">Gợi ý Thực thể Phù hợp</h2>
                <p className="mt-1.5 max-w-3xl text-xs leading-relaxed text-slate-500 font-medium">
                  Chạy giải thuật đồ thị tri thức PGPR để tìm kiếm các mối nối có xác suất liên quan lớn nhất từ tài khoản của bạn. Chọn loại đích đến (Target Type) dưới đây.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-[240px_1fr] md:items-center">
                <div className="space-y-1.5">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Chọn Target Type</div>
                  <Select value={recommendTargetType} onValueChange={(value) => setRecommendTargetType(value as EntityType)}>
                    <SelectTrigger className="rounded-xl border-slate-200 h-9.5 text-xs font-semibold bg-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl">
                      {tabs.map((tab) => (
                        <SelectItem key={tab.type} value={tab.type} className="text-xs rounded-lg">
                          {tab.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="text-xs font-semibold text-slate-400 self-end pb-1 leading-relaxed">
                  {sourceEntity ? (
                    <div className="flex items-center gap-1.5">
                      Đang liên kết hồ sơ: <span className="font-bold text-slate-700">{sourceEntity.name}</span>{" "}
                      <Badge variant="outline" className="rounded-full px-2 py-0.2 text-[9px] font-bold bg-indigo-50 text-indigo-600 border-indigo-200">
                        {sourceEntity.type}
                      </Badge>
                    </div>
                  ) : (
                    "Yêu cầu tài khoản có hồ sơ liên kết để kích hoạt thuật toán gợi ý."
                  )}
                </div>
              </div>
            </div>
            <Button
              type="button"
              className="gap-2 rounded-xl h-11 text-xs font-bold bg-gradient-to-r from-violet-600 to-indigo-600 text-white hover:from-violet-700 hover:to-indigo-700 transition-all duration-300 shadow-md shadow-indigo-100"
              onClick={() => void recommendCurrentView()}
              disabled={isRecommendLoading || !sourceEntity}
            >
              {isRecommendLoading ? <Loader2 className="h-4 w-4 animate-spin text-white" /> : <Sparkles className="h-4 w-4 text-white" />}
              Gợi ý {entityCollections[recommendTargetType]}
            </Button>
          </CardContent>
        </Card>

        {/* Recommendations Panel */}
        {recommendError || isRecommendLoading || recommendations.length > 0 ? (
          <Card className="rounded-2xl border-slate-200/60 shadow-sm bg-white overflow-hidden">
            <CardContent className="space-y-5 p-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between border-b border-slate-100 pb-4">
                <div>
                  <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">Recommendation Results</div>
                  <h2 className="mt-1 text-lg font-bold tracking-tight text-slate-800">Kết quả Đề xuất {entityCollections[recommendTargetType]}</h2>
                  <p className="mt-1 text-xs text-slate-400 font-medium">
                    Hệ thống đã xếp hạng mối tương quan tương đối từ hồ sơ {sourceEntity ? `${sourceEntity.name}` : "của bạn"}.
                  </p>
                </div>
                <Badge variant="secondary" className="rounded-full px-3 py-0.5 text-[10px] font-bold bg-slate-100 border-transparent text-slate-600">
                  {recommendations.length} kết quả
                </Badge>
              </div>

              {recommendError ? (
                <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4 text-xs font-semibold text-rose-700 leading-relaxed">{recommendError}</div>
              ) : isRecommendLoading ? (
                <div className="flex items-center justify-center gap-2 text-xs font-medium text-slate-400 py-10 bg-slate-50/20 rounded-xl border border-dashed">
                  <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                  Hệ thống PGPR đang thực hiện suy diễn vết đồ thị lập luận...
                </div>
              ) : recommendations.length > 0 ? (
                <div className="grid gap-3">
                  {recommendations.map((item, index) => {
                    return (
                      <div
                        key={`${item.id}-${index}`}
                        className="rounded-xl border border-slate-200/60 p-4 bg-white transition-all duration-300 premium-card-hover hover:border-indigo-300"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <div className="min-w-0 space-y-1.5">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className="rounded-md bg-slate-50 text-[10px] font-bold border-slate-200 text-slate-500 px-2 py-0.2">
                                Hạng #{index + 1}
                              </Badge>
                              {item.evidence_level ? <Badge className="rounded-md bg-indigo-50 text-[10px] font-bold border-indigo-200 text-indigo-600 px-2 py-0.2" variant="outline">{item.evidence_level}</Badge> : null}
                            </div>
                            <Link
                              href={`/entities/${item.type ?? recommendTargetType}/${item.id}`}
                              className="block font-bold text-slate-800 text-sm hover:text-primary hover:underline transition-colors"
                            >
                              {item.name || item.id}
                            </Link>
                            <p className="line-clamp-2 text-[11px] font-medium leading-relaxed text-slate-400">
                              {getRecommendationExplanation(item) || "Không có nội dung XAI tóm tắt."}
                            </p>
                          </div>
                          <div className="shrink-0 rounded-xl border border-slate-100 bg-slate-50/50 px-3 py-2 text-center shadow-sm min-w-[72px]">
                            <div className="text-[9px] font-extrabold uppercase tracking-wider text-slate-400">Score</div>
                            <div className="text-sm font-bold text-indigo-600 mt-0.5">
                              {typeof item.score === "number" ? item.score.toFixed(3) : "N/A"}
                            </div>
                          </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                          <Button
                            type="button"
                            size="sm"
                            className="gap-2 rounded-xl px-4 text-xs font-bold shadow-md shadow-indigo-50/50"
                            onClick={() => void openDetailedExplanation(item)}
                          >
                            <Sparkles className="h-3.5 w-3.5" />
                            Giải thích chi tiết
                          </Button>
                          <Link href={`/entities/${item.type ?? recommendTargetType}/${item.id}`}>
                            <Button type="button" size="sm" variant="outline" className="rounded-xl px-4 text-xs font-bold border-slate-200 hover:bg-slate-50 text-slate-600">
                              Xem chi tiết hồ sơ
                            </Button>
                          </Link>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        {renderEntityPagination()}

        {error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4 text-xs font-semibold text-rose-700">{error}</div>
        ) : isLoading ? (
          <div className="flex min-h-[360px] items-center justify-center gap-2 text-xs font-medium text-slate-400">
            <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
            Đang tải dữ liệu từ máy chủ MongoDB...
          </div>
        ) : entities.length === 0 ? (
          <div className="flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed p-6 text-center bg-slate-50/20">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
              <Database className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <div className="text-sm font-bold text-slate-700">Không tìm thấy dữ liệu</div>
              <div className="text-xs text-slate-400 leading-relaxed font-medium">Thay đổi từ khóa tìm kiếm hoặc chọn danh mục thực thể khác.</div>
            </div>
          </div>
        ) : (
          <>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {visibleEntities.map((entity) => {
              let typeBadgeClass = "";
              if (entity.type === "project") {
                typeBadgeClass = "bg-cyan-50 text-cyan-600 border-cyan-200/60";
              } else if (entity.type === "expert") {
                typeBadgeClass = "bg-teal-50 text-teal-600 border-teal-200/60";
              } else if (entity.type === "funder") {
                typeBadgeClass = "bg-orange-50 text-orange-600 border-orange-200/60";
              } else {
                typeBadgeClass = "bg-fuchsia-50 text-fuchsia-600 border-fuchsia-200/60";
              }

              return (
                <Card key={`${entity.type}-${entity.id}`} className="h-full rounded-2xl border-slate-200/60 shadow-sm bg-white overflow-hidden transition-all duration-300 premium-card-hover flex flex-col">
                  <CardContent className="flex h-full flex-col p-5 space-y-4">
                    <div className="space-y-2">
                      <Badge className={`rounded-full px-2.5 py-0.5 text-[9px] font-bold border ${typeBadgeClass}`} variant="outline">
                        {entity.type}
                      </Badge>
                      <h2 className="line-clamp-2 text-base font-bold leading-snug tracking-tight text-slate-800 group-hover:text-primary">{entity.name || entity.id}</h2>
                    </div>
                    <p className="line-clamp-3 text-xs leading-relaxed text-slate-400 font-medium">
                      {entity.summary || "Bản ghi chưa được cập nhật thông tin mô tả chi tiết."}
                    </p>
                    <div className="mt-auto pt-4 border-t border-slate-100 flex flex-col gap-2">
                      <div className="break-all text-[10px] font-semibold text-slate-400 font-mono">ID: {entity.id}</div>
                      <div className="flex gap-2 pt-1">
                        <Link href={`/entities/${entity.type}/${entity.id}`}>
                          <Button type="button" size="sm" variant="outline" className="gap-2 rounded-xl text-xs font-bold border-slate-200 hover:bg-slate-50 text-slate-600 h-8 px-4">
                            Xem Chi Tiết
                            <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                          </Button>
                        </Link>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
          {renderEntityPagination()}
          </>
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
        <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-4xl overflow-y-auto rounded-2xl border-slate-200 bg-white p-6 shadow-xl md:p-8">
          <DialogHeader className="border-b border-slate-100 pb-4">
            <DialogTitle className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-800">
              <Sparkles className="h-5 w-5 text-indigo-500" />
              Giải thích Chi tiết (XAI Engine)
            </DialogTitle>
            <DialogDescription className="mt-1 text-xs font-medium text-slate-400">
              Phân tích lý do hệ thống đề xuất thực thể này dựa trên reasoning path, score metadata và bằng chứng từ Knowledge Graph.
            </DialogDescription>
          </DialogHeader>

          {selectedExplanation ? (
            <div className="space-y-6 pt-6">
              <div className="rounded-2xl border border-indigo-50 bg-indigo-50/20 p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <div className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-500">Thực thể Đề xuất</div>
                    <div className="text-lg font-bold tracking-tight text-slate-800">{selectedExplanation.name || selectedExplanation.id}</div>
                    <div className="break-all text-xs font-semibold text-slate-400">ID: {selectedExplanation.id}</div>
                  </div>
                  <div className="h-fit shrink-0 rounded-xl border border-indigo-100 bg-white p-3 text-right shadow-sm">
                    <div className="text-[9px] font-extrabold uppercase tracking-wider text-slate-400">Score</div>
                    <div className="mt-0.5 text-base font-extrabold text-indigo-600">
                      {typeof selectedExplanation.score === "number" ? selectedExplanation.score.toFixed(3) : "N/A"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-4 rounded-xl border border-slate-150 bg-slate-50/40 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-0.5">
                  <div className="text-xs font-bold text-slate-700">Trạng thái XAI Model</div>
                  <div className="text-[11px] font-medium leading-relaxed text-slate-400">
                    {isExplanationLoading
                      ? "Đang gọi XAI Model để tạo giải thích chi tiết..."
                      : generatedExplanation?._cache?.hit
                        ? "Dữ liệu được truy xuất từ cache."
                        : generatedExplanation
                          ? "Mô hình đã sinh giải thích mới."
                          : "Đang chờ sinh giải thích."}
                  </div>
                  {generatedExplanation?._cache?.key ? (
                    <div className="mt-1 break-all rounded-md border bg-white px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-400">
                      Cache-key: {generatedExplanation._cache.key}
                    </div>
                  ) : null}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-9 shrink-0 rounded-xl border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50"
                  onClick={() => void regenerateExplanation()}
                  disabled={isExplanationLoading}
                >
                  {isExplanationLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin text-slate-500" /> : null}
                  Tạo lại giải thích
                </Button>
              </div>

              <section className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Mô tả giải thích tự nhiên</h3>
                <div className="rounded-2xl border border-slate-200/60 bg-white p-5 leading-relaxed shadow-sm">
                  {isExplanationLoading ? (
                    <div className="flex items-center gap-2 py-4 text-xs font-medium text-slate-400">
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

              {selectedExplanation.reasoning_paths?.length ? (
                <section className="space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Reasoning paths</h3>
                  <div className="space-y-2">
                    {selectedExplanation.reasoning_paths.slice(0, 5).map((path, index) => (
                      <pre key={index} className="max-h-40 overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] leading-5 text-slate-600">
                        {JSON.stringify(path, null, 2)}
                      </pre>
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
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
            Đang tải Entities Browser...
          </main>
        </div>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}
