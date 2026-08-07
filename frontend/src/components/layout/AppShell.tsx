"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, isAuthenticated } from "@/lib/auth";
import { getMe } from "@/lib/api";
import type { UserResponse } from "@/types/api";

const nav = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/approvals", label: "Approvals" },
  { href: "/executions", label: "Executions" },
  { href: "/simulate", label: "Simulate" },
  { href: "/erp/orders", label: "ERP Orders" },
];

// Module cache so shell does not flash on route changes
let cachedUser: UserResponse | null = null;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserResponse | null>(cachedUser);
  const [ready, setReady] = useState<boolean>(!!cachedUser);

  useEffect(() => {
    if (!isAuthenticated()) {
      cachedUser = null;
      router.replace("/login");
      return;
    }

    if (cachedUser) {
      setUser(cachedUser);
      setReady(true);
      return;
    }

    getMe()
      .then((u) => {
        cachedUser = u;
        setUser(u);
      })
      .catch(() => {
        cachedUser = null;
        clearToken();
        router.replace("/login");
      })
      .finally(() => setReady(true));
  }, [router]);

  function logout() {
    cachedUser = null;
    clearToken();
    router.replace("/login");
  }

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-slate-950 text-slate-300">
        Loading console...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-7xl">
        <aside className="w-64 border-r border-white/10 bg-slate-950/80 p-4">
          <div className="mb-8">
            <div className="flex items-center gap-3">
              <div className="relative flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-400/30 bg-gradient-to-br from-cyan-500/20 via-sky-500/10 to-emerald-500/10 shadow-[0_0_24px_rgba(34,211,238,0.25)]">
                <div className="absolute inset-0 rounded-xl bg-cyan-400/5 blur-sm" />
                <span className="relative text-sm font-black tracking-tight text-cyan-200">
                  OF
                </span>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-300/80">
                  OpsForge
                </p>
                <h1 className="truncate text-base font-semibold tracking-tight text-white">
                  Operations Console
                </h1>
              </div>
            </div>
            <p className="mt-3 text-[12px] leading-relaxed text-slate-400">
              Autonomous exception investigation
              <span className="text-slate-600"> · </span>
              human-in-the-loop approval
            </p>
            <div className="mt-4 h-px w-full bg-gradient-to-r from-cyan-400/40 via-white/10 to-transparent" />
          </div>

          <nav className="space-y-1">
            {nav.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  prefetch
                  className={`block rounded-lg px-3 py-2 text-sm transition ${
                    active
                      ? "bg-cyan-500/15 text-cyan-300 shadow-[inset_0_0_0_1px_rgba(34,211,238,0.2)]"
                      : "text-slate-300 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="flex-1">
          <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
            <div>
              <p className="text-sm text-slate-400">Signed in as</p>
              <p className="font-medium">{user?.email}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-sm text-slate-200 transition hover:bg-white/5"
            >
              Logout
            </button>
          </header>
          <main className="p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}