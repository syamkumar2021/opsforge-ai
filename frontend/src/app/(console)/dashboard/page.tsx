"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
// import AppShell from "@/components/layout/AppShell";
import { listExecutions } from "@/lib/api";
import type { AgentExecution } from "@/types/api";
import { statusColor } from "@/lib/status";

function StatCard({
  label,
  value,
  href,
}: {
  label: string;
  value: number;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-2xl border border-white/10 bg-white/5 p-5 transition hover:bg-white/10"
    >
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
    </Link>
  );
}

export default function DashboardPage() {
  const [rows, setRows] = useState<AgentExecution[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await listExecutions({ limit: 100 });
      setRows(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const counts = useMemo(() => {
    const base = {
      waiting_human: 0,
      running: 0,
      completed: 0,
      failed: 0,
      pending: 0,
    };
    for (const r of rows) {
      const s = (r.status || "").toLowerCase();
      if (s in base) base[s as keyof typeof base] += 1;
    }
    return base;
  }, [rows]);

  const recent = rows.slice(0, 8);

  return (
    <>
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">Operations Dashboard</h2>
        <p className="text-sm text-slate-400">Live exception investigation overview</p>
      </div>

      {error && <p className="mb-4 text-rose-300">{error}</p>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Waiting approval" value={counts.waiting_human} href="/approvals" />
        <StatCard label="Running" value={counts.running} href="/executions?status=running" />
        <StatCard label="Completed" value={counts.completed} href="/executions?status=completed" />
        <StatCard label="Failed" value={counts.failed} href="/executions?status=failed" />
      </div>

      <div className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-medium">Recent executions</h3>
          <Link href="/executions" className="text-sm text-cyan-300 hover:underline">
            View all
          </Link>
        </div>
        <div className="space-y-2">
          {recent.map((row) => (
            <Link
              key={row.thread_id}
              href={`/executions/${row.thread_id}`}
              className="flex items-center justify-between rounded-xl border border-white/5 bg-slate-950/40 px-3 py-2 hover:bg-white/5"
            >
              <div>
                <p className="text-sm text-slate-100">
                  {row.event_payload?.order_number || row.thread_id.slice(0, 8)}
                </p>
                <p className="text-xs text-slate-400">
                  {row.event_payload?.exception_type || "exception"}
                </p>
              </div>
              <span className={`rounded-full border px-2 py-0.5 text-xs ${statusColor(row.status)}`}>
                {row.status}
              </span>
            </Link>
          ))}
          {recent.length === 0 && (
            <p className="text-sm text-slate-400">No executions yet. Use Simulate to create one.</p>
          )}
        </div>
      </div>
    </>
  );
}