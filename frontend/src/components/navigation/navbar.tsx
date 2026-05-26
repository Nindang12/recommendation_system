
'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Activity, BarChart3, Compass, FolderKanban, GitBranch, LayoutDashboard, LogIn, LogOut, Network, Plus, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';

const navItems = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Entities', href: '/search', icon: Compass },
  { label: 'My Projects', href: '/projects/my', icon: FolderKanban },
  { label: 'Create', href: '/projects/create', icon: Plus },
  { label: 'Graph', href: '/graph/neighbors', icon: Network },
  { label: 'Evaluation', href: '/evaluation', icon: BarChart3 },
];

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  return (
    <nav className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <div className="flex items-center gap-8">
          <Link href="/dashboard" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GitBranch className="h-5 w-5" />
            </div>
            <div className="leading-tight">
              <span className="block text-base font-bold">R&D Recommendation</span>
              <span className="block text-xs text-muted-foreground">PGPR + Knowledge Graph</span>
            </div>
          </Link>

          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-secondary",
                  pathname === item.href ? "bg-secondary text-foreground" : "text-muted-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="hidden items-center gap-2 sm:flex">
          {user ? (
            <>
              <Link href="/profile" className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-secondary">
                <User className="h-4 w-4" />
                {user.full_name || user.email}
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  logout();
                  router.push('/auth/login');
                }}
              >
                <LogOut className="mr-2 h-4 w-4" />
                Logout
              </Button>
            </>
          ) : (
            <Link href="/auth/login">
              <Button size="sm">
                <LogIn className="mr-2 h-4 w-4" />
                Login
              </Button>
            </Link>
          )}
          <div className="hidden items-center gap-2 text-sm text-muted-foreground xl:flex">
            <Activity className="h-4 w-4 text-emerald-600" />
            FastAPI: localhost:8000
          </div>
        </div>
      </div>
    </nav>
  );
}
