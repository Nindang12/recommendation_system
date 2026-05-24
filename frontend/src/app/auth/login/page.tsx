
'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Database } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      router.push('/dashboard');
    }, 1000);
  };

  return (
    <div className="min-h-svh flex items-center justify-center p-4 bg-background">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center p-3 bg-black text-white mb-4">
            <Database className="w-8 h-8" />
          </div>
          <h1 className="text-4xl font-headline font-bold tracking-tighter">KNOWLEDGE NEXUS</h1>
          <p className="text-muted-foreground">Access the global knowledge graph</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="email">Email Address</Label>
            <Input id="email" type="email" placeholder="name@example.com" required className="border-black focus-visible:ring-black" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
              <Button variant="link" className="px-0 font-normal h-auto text-muted-foreground">Forgot password?</Button>
            </div>
            <Input id="password" type="password" required className="border-black focus-visible:ring-black" />
          </div>
          <Button type="submit" className="w-full h-12 text-lg font-bold" disabled={loading}>
            {loading ? "Authenticating..." : "SIGN IN"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{' '}
          <Link href="/auth/register" className="text-black font-bold hover:underline">
            Register now
          </Link>
        </p>
      </div>
    </div>
  );
}
