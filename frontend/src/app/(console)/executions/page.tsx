"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
// import AppShell from "@/components/layout/AppShell";
import { listExecutions } from "@/lib/api";
import type { AgentExecution } from "@/types/api";
import { statusColor } from "@/lib/status";

export default function ExecutionsPage() {
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<AgentExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listExecutions({
        status: status || undefined,
        limit: 50,
      });
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load executions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [status]);

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Executions</h2>
          <p className="text-sm text-slate-400">Investigation history</p>
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="pending">pending</option>
          <option value="running">running</option>
          <option value="waiting_human">waiting_human</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
      </div>

      {loading && <p className="text-slate-400">Loading...</p>}
      {error && <p className="text-rose-300">{error}</p>}

      <div className="overflow-hidden rounded-2xl border border-white/10">
        <table className="min-w-full text-sm">
          <thead className="bg-white/5 text-left text-slate-400">
            <tr>
              <th className="px-4 py-3">Order</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Confidence</th>
              <th className="px-4 py-3">Started</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.thread_id} className="border-t border-white/10 hover:bg-white/5">
                <td className="px-4 py-3">
                  <Link className="text-cyan-300 hover:underline" href={`/executions/${row.thread_id}`}>
                    {row.event_payload?.order_number || row.thread_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${statusColor(row.status)}`}>
                    {row.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-300">
                  {row.event_payload?.exception_type || "—"}
                </td>
                <td className="px-4 py-3">{row.confidence ?? "—"}</td>
                <td className="px-4 py-3 text-slate-400">
                  {row.started_at ? new Date(row.started_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}