"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
// import AppShell from "@/components/layout/AppShell";
import { listExecutions } from "@/lib/api";
import type { AgentExecution } from "@/types/api";
import { severityColor, statusColor } from "@/lib/status";

export default function ApprovalsPage() {
  const [rows, setRows] = useState<AgentExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listExecutions({ status: "waiting_human", limit: 50 });
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Pending Approvals</h2>
          <p className="text-sm text-slate-400">Human-in-the-loop queue</p>
        </div>
        <button
          onClick={load}
          className="rounded-lg border border-white/10 px-3 py-1.5 text-sm hover:bg-white/5"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="text-slate-400">Loading...</p>}
      {error && <p className="text-rose-300">{error}</p>}

      {!loading && rows.length === 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-8 text-slate-400">
          No cases waiting for human approval.
        </div>
      )}

      <div className="space-y-3">
        {rows.map((row) => {
          const event = row.event_payload || {};
          return (
            <Link
              key={row.thread_id}
              href={`/executions/${row.thread_id}`}
              className="block rounded-2xl border border-white/10 bg-white/5 p-4 transition hover:bg-white/10"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-0.5 text-xs ${statusColor(row.status)}`}>
                  {row.status}
                </span>
                <span className={`rounded-full px-2.5 py-0.5 text-xs ${severityColor(event.severity)}`}>
                  {event.severity || "n/a"}
                </span>
                <span className="text-sm text-slate-300">{event.order_number}</span>
              </div>
              <p className="mt-2 text-sm text-slate-200">
                {event.exception_type} · confidence {row.confidence ?? "—"}
              </p>
              <p className="mt-1 line-clamp-2 text-sm text-slate-400">
                {event.description}
              </p>
            </Link>
          );
        })}
      </div>
    </>
  );
}