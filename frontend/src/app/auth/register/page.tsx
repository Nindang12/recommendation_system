"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Loader2, TrendingUp, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { useAuth } from "@/lib/auth";
import { researchTopicOptions } from "@/lib/research-topics";

const roles = [
  { value: "expert", label: "Chuyen gia / Nha nghien cuu", icon: UserCheck },
  { value: "enterprise", label: "Doanh nghiep", icon: Building2 },
  { value: "funder", label: "Nha tai tro", icon: TrendingUp },
];

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [role, setRole] = useState("expert");
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [useCustomTopic, setUseCustomTopic] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function toggleTopic(topic: string, checked: boolean | "indeterminate") {
    setSelectedTopics((current) =>
      checked === true ? Array.from(new Set([...current, topic])) : current.filter((item) => item !== topic),
    );
  }

  async function handleRegister(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const password = String(form.get("password") || "");
    const confirmPassword = String(form.get("confirm_password") || "");
    if (password !== confirmPassword) {
      setError("Mat khau xac nhan khong khop");
      return;
    }

    setLoading(true);
    setError("");
    try {
      await register({
        email: String(form.get("email") || ""),
        password,
        full_name: String(form.get("full_name") || ""),
        username: String(form.get("username") || ""),
        role,
        organization: String(form.get("organization") || ""),
        phone: String(form.get("phone") || ""),
        address: String(form.get("address") || ""),
        bio: String(form.get("bio") || ""),
        research_interests: selectedTopics,
        custom_research_topics: useCustomTopic
          ? String(form.get("custom_research_topics") || "")
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
      });
      router.push("/profile");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dang ky that bai");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-svh bg-background px-4 py-8">
      <main className="mx-auto max-w-5xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Tao tai khoan nguoi dung</h1>
          <p className="mt-2 text-muted-foreground">
            Tai khoan dung de quan ly profile, tao project ca nhan va chay goi y tren he thong.
          </p>
        </div>

        <form onSubmit={handleRegister} className="grid gap-6 rounded-md border bg-card p-6 lg:grid-cols-[280px_1fr]">
          <aside className="space-y-3">
            <Label>Vai tro</Label>
            <div className="grid gap-2">
              {roles.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setRole(item.value)}
                  className={`flex items-center gap-3 rounded-md border p-3 text-left text-sm ${
                    role === item.value ? "border-primary bg-secondary font-semibold" : "hover:bg-secondary/60"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </button>
              ))}
            </div>
          </aside>

          <section className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="full_name">Ho ten / Ten don vi</Label>
              <Input id="full_name" name="full_name" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" name="username" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" name="email" type="email" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">So dien thoai</Label>
              <Input id="phone" name="phone" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Mat khau</Label>
              <Input id="password" name="password" type="password" required minLength={6} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm_password">Xac nhan mat khau</Label>
              <Input id="confirm_password" name="confirm_password" type="password" required minLength={6} />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="organization">To chuc</Label>
              <Input id="organization" name="organization" placeholder="Truong/Vien/Cong ty/Quy tai tro" />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="address">Dia chi</Label>
              <Input id="address" name="address" />
            </div>
            <div className="space-y-2 md:col-span-2">
              <div>
                <Label>Chủ đề nghiên cứu</Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Chọn từ danh mục chuẩn của hệ thống để thống nhất dữ liệu khi matching với Knowledge Graph.
                </p>
              </div>
              <div className="grid gap-2 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-3">
                {researchTopicOptions.map((topic) => (
                  <label key={topic.value} className="flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm hover:bg-secondary">
                    <Checkbox
                      checked={selectedTopics.includes(topic.value)}
                      onCheckedChange={(checked) => toggleTopic(topic.value, checked)}
                    />
                    {topic.label}
                  </label>
                ))}
                <label className="flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm hover:bg-secondary">
                  <Checkbox checked={useCustomTopic} onCheckedChange={(checked) => setUseCustomTopic(checked === true)} />
                  Khác
                </label>
              </div>
              {useCustomTopic ? (
                <div className="space-y-2">
                  <Label htmlFor="custom_research_topics">Chủ đề nghiên cứu khác</Label>
                  <Input
                    id="custom_research_topics"
                    name="custom_research_topics"
                    placeholder="Ví dụ: Federated Learning, Digital Twin"
                  />
                  <p className="text-xs text-muted-foreground">
                    Các chủ đề này sẽ được lưu riêng để admin/hệ thống map sang topic chuẩn trước khi đồng bộ Neo4j.
                  </p>
                </div>
              ) : null}
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="bio">Mo ta ngan</Label>
              <Textarea id="bio" name="bio" rows={4} />
            </div>
            {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 md:col-span-2">{error}</div> : null}
            <div className="flex flex-wrap items-center gap-3 md:col-span-2">
              <Button type="submit" disabled={loading}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Dang ky
              </Button>
              <Link href="/auth/login" className="text-sm text-muted-foreground hover:text-foreground">
                Da co tai khoan? Dang nhap
              </Link>
            </div>
          </section>
        </form>
      </main>
    </div>
  );
}
