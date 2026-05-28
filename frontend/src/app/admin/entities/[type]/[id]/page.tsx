"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  DatabaseZap,
  GitMerge,
  Loader2,
  RotateCw,
  ShieldAlert,
} from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, EntityType } from "@/lib/api";

gsap.registerPlugin(ScrollTrigger);

const VALID_TYPES: EntityType[] = ["expert", "enterprise", "funder", "project"];

function statusClass(value?: unknown) {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized.includes("verified") && !normalized.includes("unverified")) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (normalized.includes("rejected") || normalized.includes("disabled") || normalized.includes("failed")) {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  if (normalized.includes("merge") || normalized.includes("not_synced") || normalized.includes("syncing")) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function display(value: unknown, fallback = "-") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function candidateId(candidate: unknown) {
  if (!candidate || typeof candidate !== "object") return "";
  return String((candidate as Record<string, unknown>).id ?? "");
}

function candidateName(candidate: unknown) {
  if (!candidate || typeof candidate !== "object") return "";
  const record = candidate as Record<string, unknown>;
  return String(record.name ?? record.title ?? record.id ?? "");
}

export default function AdminEntityDetailPage() {
  const params = useParams<{ type: string; id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const entityType = params.type as EntityType;
  const entityId = params.id;

  const [entity, setEntity] = useState<Record<string, unknown> | null>(null);
  const [reason, setReason] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const duplicateCandidates = Array.isArray(entity?.duplicate_candidates) ? entity.duplicate_candidates : [];

  useEffect(() => {
    const scope = rootRef.current;
    if (!scope) return;
    const context = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>(".admin-detail-reveal").forEach((element, index) => {
        gsap.fromTo(
          element,
          { y: 26, opacity: 0 },
          {
            y: 0,
            opacity: 1,
            delay: index * 0.04,
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
  }, [entity]);

  const loadEntity = () => {
    if (!VALID_TYPES.includes(entityType)) {
      setError("Loai entity khong hop le.");
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    api
      .adminGetEntity(entityType, entityId)
      .then((response) => setEntity((response.data as unknown as Record<string, unknown>) ?? null))
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Loi tai entity"))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadEntity();
  }, [entityType, entityId]);

  useEffect(() => {
    const targetFromUrl = searchParams.get("mergeTarget");
    if (targetFromUrl) {
      setMergeTargetId(targetFromUrl);
    }
  }, [searchParams]);

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
    setIsBusy(true);
    setMessage("");
    setError("");
    try {
      await action();
      setMessage(successMessage);
      loadEntity();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Thao tac that bai");
    } finally {
      setIsBusy(false);
    }
  };

  const onMerge = (event: FormEvent) => {
    event.preventDefault();
    if (!mergeTargetId.trim()) {
      setError("Nhap target entity ID de merge.");
      return;
    }
    void runAction(
      () => api.adminMergeEntity(entityType, entityId, mergeTargetId.trim(), reason),
      "Da merge entity.",
    );
  };

  return (
    <div ref={rootRef} className="min-h-svh bg-slate-50">
      <Navbar />
      <main className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6">
        <Button variant="ghost" size="sm" className="admin-detail-reveal w-fit" onClick={() => router.push("/admin")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Quay lai admin
        </Button>

        {isLoading ? (
          <div className="flex min-h-[260px] items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Dang tai entity...
          </div>
        ) : error && !entity ? (
          <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            <AlertCircle className="mt-0.5 h-4 w-4" />
            {error}
          </div>
        ) : entity ? (
          <>
            <section className="admin-detail-reveal rounded-md border bg-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <Badge variant="outline" className="mb-3 rounded-md">
                    {entityType}
                  </Badge>
                  <h1 className="text-3xl font-bold tracking-tight">{String(entity.name ?? entity.title ?? entityId)}</h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {entityType} / {entityId}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className={`rounded-md ${statusClass(entity.kg_sync_status)}`}>
                    KG: {display(entity.kg_sync_status)}
                  </Badge>
                  <Badge variant="outline" className={`rounded-md ${statusClass(entity.entity_verification_status)}`}>
                    Verify: {display(entity.entity_verification_status)}
                  </Badge>
                  <Badge variant="outline" className="rounded-md">
                    Scope: {display(entity.participation_scope)}
                  </Badge>
                </div>
              </div>
            </section>

            {message ? <p className="admin-detail-reveal text-sm text-emerald-700">{message}</p> : null}
            {error ? <p className="admin-detail-reveal text-sm text-rose-700">{error}</p> : null}

            <section className="grid gap-5 lg:grid-cols-[1fr_360px]">
              <div className="space-y-5">
                <Card className="admin-detail-reveal rounded-md bg-white">
                  <CardHeader>
                    <CardTitle>Thong tin entity</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-3 text-sm md:grid-cols-2">
                    {[
                      ["Email", entity.email],
                      ["Organization", entity.organization],
                      ["Visibility", entity.visibility],
                      ["Trust weight", entity.trust_weight],
                      ["Source", entity.source],
                      ["Owner user", entity.user_id ?? entity.owner_user_id],
                      ["Created", entity.created_at],
                      ["Updated", entity.updated_at],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="rounded-md border bg-slate-50 p-3">
                        <div className="text-xs uppercase text-muted-foreground">{String(label)}</div>
                        <div className="mt-1 break-words font-medium">{display(value)}</div>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {duplicateCandidates.length > 0 ? (
                  <Card className="admin-detail-reveal rounded-md bg-white">
                    <CardHeader>
                      <CardTitle>Duplicate candidates</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {duplicateCandidates.map((candidate, index) => {
                        const id = candidateId(candidate);
                        const name = candidateName(candidate);
                        const record = candidate as Record<string, unknown>;
                        return (
                          <div key={`${id}-${index}`} className="rounded-md border bg-slate-50 p-3">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <div className="font-semibold">{name || id}</div>
                                <div className="mt-1 text-xs text-muted-foreground">ID: {id}</div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {record.match_strength ? (
                                  <Badge variant="outline" className="rounded-md">
                                    {String(record.match_strength)}
                                  </Badge>
                                ) : null}
                                {record.similarity ? (
                                  <Badge variant="outline" className="rounded-md">
                                    Similarity {String(record.similarity)}
                                  </Badge>
                                ) : null}
                              </div>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Button
                                type="button"
                                size="sm"
                                variant="default"
                                className="gap-2"
                                onClick={() => setMergeTargetId(id)}
                                disabled={!id}
                              >
                                <GitMerge className="h-4 w-4" />
                                Chon lam target merge
                              </Button>
                              {id ? (
                                <Link href={`/entities/${entityType}/${id}`}>
                                  <Button type="button" size="sm" variant="outline">
                                    Xem entity cu
                                  </Button>
                                </Link>
                              ) : null}
                            </div>
                          </div>
                        );
                      })}
                    </CardContent>
                  </Card>
                ) : null}
              </div>

              <aside className="space-y-5">
                <Card className="admin-detail-reveal rounded-md bg-white">
                  <CardHeader>
                    <CardTitle>Ly do thao tac</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Textarea
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      rows={4}
                      placeholder="Nhap ly do de luu vao audit log"
                    />
                  </CardContent>
                </Card>

                <Card className="admin-detail-reveal rounded-md bg-white">
                  <CardHeader>
                    <CardTitle>Hanh dong quan tri</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-2">
                    <Button
                      className="justify-start gap-2"
                      disabled={isBusy}
                      onClick={() => void runAction(() => api.adminVerifyEntity(entityType, entityId, reason), "Da verify.")}
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      Verify entity
                    </Button>
                    <Button
                      className="justify-start gap-2"
                      variant="destructive"
                      disabled={isBusy}
                      onClick={() => void runAction(() => api.adminRejectEntity(entityType, entityId, reason), "Da reject.")}
                    >
                      <ShieldAlert className="h-4 w-4" />
                      Reject entity
                    </Button>
                    <Button
                      className="justify-start gap-2"
                      variant="outline"
                      disabled={isBusy}
                      onClick={() => void runAction(() => api.adminDisableKg(entityType, entityId, reason), "Da disable KG.")}
                    >
                      <DatabaseZap className="h-4 w-4" />
                      Disable KG
                    </Button>
                    <Button
                      className="justify-start gap-2"
                      variant="outline"
                      disabled={isBusy}
                      onClick={() => void runAction(() => api.adminRetryKgSync(entityType, entityId), "Da retry KG sync.")}
                    >
                      <RotateCw className="h-4 w-4" />
                      Retry KG sync
                    </Button>
                    <Link href={`/entities/${entityType}/${entityId}`}>
                      <Button className="w-full justify-start" variant="secondary">
                        Xem public profile
                      </Button>
                    </Link>
                  </CardContent>
                </Card>

                <Card className="admin-detail-reveal rounded-md bg-white">
                  <CardHeader>
                    <CardTitle>Merge entity</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={onMerge} className="space-y-3">
                      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
                        Merge se vo hieu hoa entity hien tai, chuyen user dang link voi entity nay sang target entity,
                        va luu audit log. Entity cu khong bi xoa khoi database.
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="merge-target">Target entity ID</Label>
                        <Input
                          id="merge-target"
                          value={mergeTargetId}
                          onChange={(event) => setMergeTargetId(event.target.value)}
                          placeholder="exp_001"
                        />
                      </div>
                      <Button type="submit" disabled={isBusy} className="w-full gap-2">
                        <GitMerge className="h-4 w-4" />
                        Merge vao target
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              </aside>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
