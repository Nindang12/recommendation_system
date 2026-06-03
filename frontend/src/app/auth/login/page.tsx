"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Database, Loader2, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const loggedInUser = await login(email, password);
      const isAdmin = loggedInUser.account_role === "admin" || loggedInUser.account_role === "root_admin";
      router.push(isAdmin ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dang nhap that bai");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-svh bg-background p-4">
      <div className="mx-auto grid min-h-svh max-w-6xl items-center gap-10 lg:grid-cols-[1fr_420px]">
        <section className="hidden lg:block">
          <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Database className="h-6 w-6" />
          </div>
          <h1 className="max-w-2xl text-5xl font-bold tracking-tight">R&D Recommendation Workspace</h1>
          <p className="mt-4 max-w-xl text-muted-foreground">
            Dang nhap de quan ly du an nghien cuu, tao project moi va chay goi y PGPR/XAI tren knowledge graph.
          </p>
        </section>

        <section className="rounded-md border bg-card p-6 shadow-sm">
          <div className="mb-6">
            <h2 className="text-2xl font-bold">Dang nhap</h2>
            <p className="mt-1 text-sm text-muted-foreground">Truy cap dashboard va workspace ca nhan.</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Mat khau</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogIn className="mr-2 h-4 w-4" />}
              Dang nhap
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-muted-foreground">
            Chua co tai khoan?{" "}
            <Link href="/auth/register" className="font-semibold text-foreground hover:underline">
              Dang ky
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
