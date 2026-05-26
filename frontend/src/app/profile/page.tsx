"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Save, User } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, UserProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { researchTopicOptions } from "@/lib/research-topics";

function statusLabel(value?: string) {
  const labels: Record<string, string> = {
    email_unverified: "Email chua xac thuc",
    email_verified: "Email da xac thuc",
    unverified: "Chua xac thuc",
    pending_review: "Cho duyet",
    verified: "Da xac thuc",
    rejected: "Bi tu choi",
    not_synced: "Chua sync KG",
    syncing: "Dang sync KG",
    synced_unverified: "Da sync, chua xac thuc",
    synced_verified: "Da sync va verified",
    merge_required: "Can kiem tra trung",
    sync_failed: "Sync loi",
    sync_partial: "Sync chua hoan tat",
    disabled: "Da vo hieu hoa",
  };
  return labels[value || ""] || value || "Khong ro";
}

export default function ProfilePage() {
  const router = useRouter();
  const { user, isLoading, refresh } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!isLoading && !user) router.push("/auth/login");
    if (user) setProfile(user);
  }, [isLoading, router, user]);

  async function handleSave() {
    if (!profile) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await api.updateMe(profile);
      setProfile(response.data);
      await refresh();
      setMessage("Da luu profile.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Luu profile that bai");
    } finally {
      setSaving(false);
    }
  }

  function toggleTopic(topic: string, checked: boolean | "indeterminate") {
    if (!profile) return;
    const current = profile.research_interests ?? [];
    setProfile({
      ...profile,
      research_interests:
        checked === true ? Array.from(new Set([...current, topic])) : current.filter((item) => item !== topic),
    });
  }

  function updateCustomTopics(value: string) {
    if (!profile) return;
    setProfile({
      ...profile,
      custom_research_topics: value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  if (isLoading || !profile) {
    return (
      <div className="min-h-svh bg-background">
        <Navbar />
        <div className="flex h-[60vh] items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-svh bg-background">
      <Navbar />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <User className="h-8 w-8" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Trang ca nhan</h1>
              <p className="text-muted-foreground">Thong tin nay dung cho project va goi y ca nhan hoa sau nay.</p>
            </div>
          </div>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Luu thay doi
          </Button>
        </header>

        <section className="mb-6 grid gap-4 rounded-md border bg-card p-5 md:grid-cols-4">
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground">Account</div>
            <Badge variant="secondary" className="mt-2 rounded-md">
              {statusLabel(profile.account_verification_status)}
            </Badge>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground">Entity</div>
            <Badge variant="secondary" className="mt-2 rounded-md">
              {statusLabel(profile.linked_entity?.entity_verification_status)}
            </Badge>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground">Knowledge Graph</div>
            <Badge variant="outline" className="mt-2 rounded-md">
              {statusLabel(profile.linked_entity?.kg_sync_status)}
            </Badge>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-muted-foreground">Trust weight</div>
            <div className="mt-2 text-2xl font-bold">{Math.round((profile.linked_entity?.trust_weight ?? 1) * 100)}%</div>
          </div>
          <div className="md:col-span-4">
            <div className="grid gap-3 text-sm md:grid-cols-3">
              <div>
                <span className="text-muted-foreground">Linked entity: </span>
                <span className="font-medium">{profile.linked_entity?.name || profile.linked_entity?.id || "Chua co"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Scope: </span>
                <span className="font-medium">{profile.linked_entity?.participation_scope || "public"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Match: </span>
                <span className="font-medium">{profile.linked_entity?.match_status || "existing"}</span>
              </div>
            </div>
            {profile.linked_entity?.kg_sync_status === "synced_unverified" ? (
              <p className="mt-3 rounded-md border bg-secondary/40 p-3 text-sm text-muted-foreground">
                Ho so cua ban da duoc dua vao Knowledge Graph o trang thai chua xac thuc. Ban co the dung de nhan goi y ca nhan,
                nhung ket qua co the thay doi sau khi duoc duyet.
              </p>
            ) : null}
            {(profile.linked_entity?.duplicate_candidates?.length ?? 0) > 0 ? (
              <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                He thong phat hien ho so co kha nang trung voi data da co. Can admin review/merge truoc khi public rong rai.
              </p>
            ) : null}
          </div>
        </section>

        <section className="grid gap-6 rounded-md border bg-card p-6 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Ho ten / ten don vi</Label>
            <Input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Username</Label>
            <Input value={profile.username ?? ""} onChange={(e) => setProfile({ ...profile, username: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input value={profile.email} disabled />
          </div>
          <div className="space-y-2">
            <Label>Vai tro</Label>
            <Select value={profile.role ?? "expert"} onValueChange={(value) => setProfile({ ...profile, role: value })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="expert">Chuyen gia / Nha nghien cuu</SelectItem>
                <SelectItem value="enterprise">Doanh nghiep</SelectItem>
                <SelectItem value="funder">Nha tai tro</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>To chuc</Label>
            <Input value={profile.organization ?? ""} onChange={(e) => setProfile({ ...profile, organization: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>So dien thoai</Label>
            <Input value={profile.phone ?? ""} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Dia chi</Label>
            <Input value={profile.address ?? ""} onChange={(e) => setProfile({ ...profile, address: e.target.value })} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <div>
              <Label>Chủ đề nghiên cứu</Label>
              <p className="mt-1 text-xs text-muted-foreground">
                Danh mục cố định của hệ thống để dữ liệu profile đồng nhất với KG/recommendation pipeline.
              </p>
            </div>
            <div className="grid gap-2 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-3">
              {researchTopicOptions.map((topic) => (
                <label key={topic.value} className="flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm hover:bg-secondary">
                  <Checkbox
                    checked={(profile.research_interests ?? []).includes(topic.value)}
                    onCheckedChange={(checked) => toggleTopic(topic.value, checked)}
                  />
                  {topic.label}
                </label>
              ))}
              <label className="flex items-center gap-2 rounded-md p-2 text-sm text-muted-foreground">
                <Checkbox checked={(profile.custom_research_topics ?? []).length > 0} disabled />
                Khác
              </label>
            </div>
            <div className="space-y-2">
              <Label>Chủ đề nghiên cứu khác</Label>
              <Input
                value={(profile.custom_research_topics ?? []).join(", ")}
                onChange={(e) => updateCustomTopics(e.target.value)}
                placeholder="Ví dụ: Federated Learning, Digital Twin"
              />
              <p className="text-xs text-muted-foreground">
                Chủ đề khác được lưu riêng để mapping/duyệt trước khi đưa vào Neo4j.
              </p>
            </div>
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Mo ta ngan</Label>
            <Textarea value={profile.bio ?? ""} onChange={(e) => setProfile({ ...profile, bio: e.target.value })} rows={5} />
          </div>
          {message ? <div className="rounded-md border bg-secondary/50 p-3 text-sm md:col-span-2">{message}</div> : null}
        </section>
      </main>
    </div>
  );
}
