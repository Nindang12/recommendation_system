"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Building2, Database, GraduationCap, Loader2, Search, TrendingUp, UserCheck } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiEntity, entityCollections, EntityType } from "@/lib/api";

const tabs: Array<{ type: EntityType; label: string; icon: typeof GraduationCap }> = [
  { type: "project", label: "Projects", icon: GraduationCap },
  { type: "expert", label: "Experts", icon: UserCheck },
  { type: "funder", label: "Funders", icon: TrendingUp },
  { type: "enterprise", label: "Enterprises", icon: Building2 },
];

function SearchPageContent() {
  const searchParams = useSearchParams();
  const initialType = (searchParams.get("type") as EntityType | null) ?? "project";
  const [activeType, setActiveType] = useState<EntityType>(initialType);
  const [query, setQuery] = useState("");
  const [entities, setEntities] = useState<ApiEntity[]>([]);
  const [count, setCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const activeCollection = useMemo(() => entityCollections[activeType], [activeType]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsLoading(true);
      setError("");
      api
        .listEntities(activeCollection, query, 24, 1)
        .then((result) => {
          setEntities(result.data ?? []);
          setCount(result.count ?? result.data?.length ?? 0);
        })
        .catch((requestError) => {
          setEntities([]);
          setCount(0);
          setError(requestError instanceof Error ? requestError.message : "Khong tai duoc entity");
        })
        .finally(() => setIsLoading(false));
    }, 250);

    return () => window.clearTimeout(timer);
  }, [activeCollection, query]);

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
              Tim project, expert, funder va enterprise de dung lam source cho luong recommendation.
            </p>
          </div>
          <Link href="/dashboard">
            <Button variant="outline">Ve dashboard</Button>
          </Link>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
          <Tabs value={activeType} onValueChange={(value) => setActiveType(value as EntityType)}>
            <TabsList className="grid h-auto grid-cols-2 gap-2 bg-transparent p-0 md:grid-cols-4">
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
          </div>
          <Badge variant="secondary" className="rounded-md">
            {count} entities
          </Badge>
        </div>

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
              <Link href={`/entities/${entity.type}/${entity.id}`} key={`${entity.type}-${entity.id}`}>
                <Card className="h-full rounded-md transition-colors hover:border-primary">
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
                    <div className="mt-auto text-xs text-muted-foreground">ID: {entity.id}</div>
                  </CardContent>
                </Card>
              </Link>
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
