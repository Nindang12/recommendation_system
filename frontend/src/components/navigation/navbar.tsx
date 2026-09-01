
'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import type { MouseEvent } from 'react';
import { Activity, BarChart3, ClipboardList, Compass, FolderKanban, GitBranch, History, LayoutDashboard, LogIn, LogOut, Network, Plus, Shield, ShieldCheck, User, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { API_BASE_URL } from '@/lib/api';

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
  const apiDisplayUrl = API_BASE_URL.replace(/^https?:\/\//, '');
  const handleAdminNavClick = (event: MouseEvent<HTMLAnchorElement>, href: string) => {
    if (!isAdminRoute || !href.startsWith('/admin#')) return;

    event.preventDefault();
    const hash = href.split('#')[1] ?? '';
    window.history.replaceState(null, '', `/admin#${hash}`);
    window.dispatchEvent(new CustomEvent('admin-tab-change', { detail: { hash: `#${hash}` } }));
  };

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-slate-200/60 bg-white/75 shadow-sm backdrop-blur-lg">
      <div className="mx-auto grid min-h-16 max-w-7xl grid-cols-[minmax(220px,280px)_1fr_auto] items-center gap-4 px-6">
        <Link href={isAdminRoute ? "/admin" : "/dashboard"} className="flex min-w-0 items-center gap-3 py-2 group">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-500 text-white shadow-md shadow-indigo-200 transition-all duration-300 group-hover:scale-105 group-hover:shadow-indigo-300">
              {isAdminRoute ? <ShieldCheck className="h-5 w-5" /> : <GitBranch className="h-5 w-5" />}
            </div>
            <div className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-bold tracking-tight text-slate-800 transition-colors group-hover:text-primary">{isAdminRoute ? 'Admin Console' : 'R&D Recommendation'}</span>
              <span className="block truncate text-[11px] font-medium text-slate-400">
                {isAdminRoute ? 'Data governance + KG review' : 'PGPR + Knowledge Graph'}
              </span>
            </div>
          </Link>

          <div className="hidden min-w-0 items-center gap-1.5 overflow-x-auto md:flex">
            {visibleNavItems.map((item) => {
              const isActive = pathname === item.href || (isAdminRoute && item.href.startsWith('/admin'));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={(event) => handleAdminNavClick(event, item.href)}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold tracking-wide transition-all duration-300",
                    isActive
                      ? "bg-primary/10 text-primary border border-primary/10"
                      : "text-slate-500 hover:text-primary hover:bg-slate-50 border border-transparent"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </div>

        <div className="hidden items-center justify-end gap-3.5 sm:flex">
          {user ? (
            <>
              {canOpenAdmin && !isAdminRoute ? (
                <Link href="/admin" className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold text-slate-600 transition-colors hover:text-primary hover:bg-slate-50 border border-transparent">
                  <Shield className="h-4 w-4" />
                  Admin
                </Link>
              ) : null}
              <Link href="/profile" className="inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-600 transition-colors hover:text-primary hover:bg-slate-50 border border-slate-200">
                <User className="h-4 w-4" />
              </Link>
              <Button
                variant="outline"
                size="sm"
                className="h-9 px-4 text-xs font-semibold rounded-lg border-slate-200 hover:bg-slate-50"
                onClick={() => {
                  logout();
                  router.push('/auth/login');
                }}
              >
                <LogOut className="mr-2 h-4 w-4 text-slate-500" />
                Logout
              </Button>
            </>
          ) : (
            <Link href="/auth/login">
              <Button size="sm" className="h-9 px-4 text-xs font-semibold rounded-lg">
                <LogIn className="mr-2 h-4 w-4" />
                Login
              </Button>
            </Link>
          )}
          <div className="hidden items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500 xl:flex">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="truncate">FastAPI: {apiDisplayUrl}</span>
          </div>
        </div>
      </div>
    </nav>
  );
}


