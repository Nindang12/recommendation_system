
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Compass, Database, GitBranch, LayoutDashboard } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Entities', href: '/search', icon: Compass },
];

export function Navbar() {
  const pathname = usePathname();

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

        <div className="hidden items-center gap-2 text-sm text-muted-foreground sm:flex">
          <Activity className="h-4 w-4 text-emerald-600" />
          FastAPI: localhost:8000
        </div>
      </div>
    </nav>
  );
}
