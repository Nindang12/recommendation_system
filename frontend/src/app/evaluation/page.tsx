"use client";

import { useEffect, useState } from "react";
import { AlertCircle, BarChart3, Loader2 } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, EvaluationSummaryResponse } from "@/lib/api";

function formatMetric(value: number | null) {
  return value === null || value === undefined ? "Chưa có" : value.toFixed(3);
}

export default function EvaluationPage() {
  const [summary, setSummary] = useState<EvaluationSummaryResponse["data"] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .evaluationSummary()
      .then((response) => setSummary(response.data))
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Không tải được evaluation"))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="min-h-svh bg-background">
      <Navbar />
      <main className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6">
        <div>
          <Badge variant="outline" className="mb-2 rounded-md">
            Evaluation
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight">Baseline vs PGPR</h1>
          <p className="mt-2 text-muted-foreground">
            Trang này là MVP summary. Pipeline metric đầy đủ vẫn cần làm trong `backend/evaluation/`.
          </p>
        </div>

        {isLoading ? (
          <div className="flex min-h-[360px] items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Đang tải evaluation summary...
          </div>
        ) : error ? (
          <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            <AlertCircle className="mt-0.5 h-4 w-4" />
            {error}
          </div>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-3">
              <Card className="rounded-md">
                <CardHeader>
                  <CardTitle className="text-lg">Smoke tests</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {summary?.smoke_tests.passed ?? "?"}/{summary?.smoke_tests.total ?? "?"}
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">Policy API smoke test artifact.</p>
                </CardContent>
              </Card>
              <Card className="rounded-md md:col-span-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <BarChart3 className="h-4 w-4" />
                    Status
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-6 text-muted-foreground">{summary?.note}</p>
                </CardContent>
              </Card>
            </section>

            <Card className="rounded-md">
              <CardHeader>
                <CardTitle className="text-lg">Metric table</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Method</TableHead>
                      <TableHead>Precision@5</TableHead>
                      <TableHead>Recall@5</TableHead>
                      <TableHead>NDCG@5</TableHead>
                      <TableHead>HitRate@5</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary?.metrics.map((row) => (
                      <TableRow key={row.method}>
                        <TableCell className="font-medium">{row.method}</TableCell>
                        <TableCell>{formatMetric(row.precision_at_5)}</TableCell>
                        <TableCell>{formatMetric(row.recall_at_5)}</TableCell>
                        <TableCell>{formatMetric(row.ndcg_at_5)}</TableCell>
                        <TableCell>{formatMetric(row.hit_rate_at_5)}</TableCell>
                        <TableCell>
                          <Badge variant={row.status === "smoke_pass" ? "secondary" : "outline"} className="rounded-md">
                            {row.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
