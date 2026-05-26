"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function CreateProjectPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [status, setStatus] = useState("draft");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isLoading && !user) router.push("/auth/login");
  }, [isLoading, router, user]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setSaving(true);
    setError("");
    try {
      const response = await api.createProject({
        title: String(form.get("title") || ""),
        summary: String(form.get("summary") || ""),
        description: String(form.get("description") || ""),
        field: String(form.get("field") || ""),
        status,
        budget: form.get("budget") ? Number(form.get("budget")) : null,
        trl: form.get("trl") ? Number(form.get("trl")) : null,
        location: String(form.get("location") || ""),
        keywords: String(form.get("keywords") || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
      router.push(`/projects/${response.data.id}/overview`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tao project that bai");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-svh bg-background">
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight">Tao project moi</h1>
          <p className="mt-2 text-muted-foreground">
            Project se duoc luu vao MongoDB va gan voi tai khoan hien tai. Sau nay co the day tiep vao KG/PGPR pipeline.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="grid gap-5 rounded-md border bg-card p-6 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="title">Ten project</Label>
            <Input id="title" name="title" required placeholder="AI trong chan doan hinh anh y te" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="summary">Tom tat</Label>
            <Textarea id="summary" name="summary" rows={3} required />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="description">Mo ta chi tiet</Label>
            <Textarea id="description" name="description" rows={6} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="field">Linh vuc</Label>
            <Input id="field" name="field" placeholder="Healthcare AI" />
          </div>
          <div className="space-y-2">
            <Label>Trang thai</Label>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="draft">Draft</SelectItem>
                <SelectItem value="proposed">Proposed</SelectItem>
                <SelectItem value="ongoing">Ongoing</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="budget">Ngan sach du kien</Label>
            <Input id="budget" name="budget" type="number" min="0" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="trl">TRL 1-9</Label>
            <Input id="trl" name="trl" type="number" min="1" max="9" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="location">Dia diem</Label>
            <Input id="location" name="location" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="keywords">Tu khoa</Label>
            <Input id="keywords" name="keywords" placeholder="AI, X-ray, Computer Vision" />
          </div>
          {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 md:col-span-2">{error}</div> : null}
          <div className="md:col-span-2">
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
              Tao project
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
}

