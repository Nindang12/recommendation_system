
'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Activity, BarChart3, ClipboardList, Compass, FolderKanban, GitBranch, History, LayoutDashboard, LogIn, LogOut, Network, Plus, Shield, ShieldCheck, User, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';

const navItems = [
  { label: 'Entities', href: '/search', icon: Compass },
  { label: 'My Projects', href: '/projects/my', icon: FolderKanban },
  { label: 'Graph', href: '/graph/neighbors', icon: Network },
  { label: 'Evaluation', href: '/evaluation', icon: BarChart3 },
];

const adminNavItems = [
  { label: 'Review Queue', href: '/admin#review-queue', icon: ClipboardList },
  { label: 'Admin Users', href: '/admin#admin-users', icon: Users },
  { label: 'Audit Log', href: '/admin#audit-log', icon: History },
];

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const canOpenAdmin = user?.account_role === "admin" || user?.account_role === "root_admin";
  const isAdminRoute = pathname?.startsWith('/admin');
  const visibleNavItems = isAdminRoute ? adminNavItems : navItems;

  return (
    <nav className="sticky top-0 z-50 w-full border-b bg-background/95 shadow-sm backdrop-blur">
      <div className="mx-auto grid min-h-16 max-w-7xl grid-cols-[minmax(220px,280px)_1fr_auto] items-center gap-4 px-4">
        <Link href={isAdminRoute ? "/admin" : "/dashboard"} className="flex min-w-0 items-center gap-3 py-2">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
              {isAdminRoute ? <ShieldCheck className="h-5 w-5" /> : <GitBranch className="h-5 w-5" />}
            </div>
            <div className="min-w-0 leading-tight">
              <span className="block truncate text-base font-bold">{isAdminRoute ? 'Admin Console' : 'R&D Recommendation'}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {isAdminRoute ? 'Data governance + KG review' : 'PGPR + Knowledge Graph'}
              </span>
            </div>
          </Link>

          <div className="hidden min-w-0 items-center gap-1 overflow-x-auto md:flex">
            {visibleNavItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "inline-flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-secondary",
                  pathname === item.href || (isAdminRoute && item.href.startsWith('/admin'))
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            ))}
          </div>

        <div className="hidden items-center justify-end gap-2 sm:flex">
          {user ? (
            <>
              {canOpenAdmin && !isAdminRoute ? (
                <Link href="/admin" className="inline-flex items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium hover:bg-secondary">
                  <Shield className="h-4 w-4" />
                  Admin
                </Link>
              ) : null}
              <Link href="/profile" className="inline-flex max-w-[150px] items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium hover:bg-secondary">
                <User className="h-4 w-4" />
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
          <div className="hidden max-w-[170px] items-center gap-2 text-sm text-muted-foreground xl:flex">
            <Activity className="h-4 w-4 text-emerald-600" />
            <span className="truncate">FastAPI: localhost:8000</span>
          </div>
        </div>
      </div>
    </nav>
  );
}
