"use client";

import { BarChart3, FileText, Layers } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/evals", label: "Evals", icon: BarChart3 },
  { href: "/schemas", label: "Schemas", icon: Layers },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 border-r bg-sidebar text-sidebar-foreground md:flex md:flex-col">
        <Link
          href="/documents"
          className="flex items-center gap-2 px-5 py-4 font-semibold tracking-tight"
        >
          <span className="inline-block size-2.5 rounded-sm bg-primary" aria-hidden />
          fieldwise
        </Link>
        <nav className="flex flex-col gap-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>
        <p className="mt-auto px-5 py-4 text-xs text-muted-foreground">
          Schema-driven extraction with per-field evals.
        </p>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b px-4 py-2 md:hidden">
          <Link href="/documents" className="font-semibold">
            fieldwise
          </Link>
          <nav className="ml-auto flex gap-3 text-sm">
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(pathname.startsWith(href) && "font-medium")}
              >
                {label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
