"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
// import AppShell from "@/components/layout/AppShell";
import { simulateEvent } from "@/lib/api";

const EXCEPTION_TYPES = [
  "vendor_status_mismatch",
  "shipping_delay",
  "inventory_shortage",
  "address_issue",
  "payment_failure",
  "other",
];

const SEVERITIES = ["low", "medium", "high", "critical"];

export default function SimulatePage() {
  const router = useRouter();
  const [orderNumber, setOrderNumber] = useState("ORD-10001");
  const [exceptionType, setExceptionType] = useState("vendor_status_mismatch");
  const [severity, setSeverity] = useState("high");
  const [description, setDescription] = useState(
    "ERP processing vs portal In Transit mismatch"
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await simulateEvent({
        order_number: orderNumber.trim(),
        exception_type: exceptionType,
        severity,
        description: description.trim(),
      });
      router.push(`/executions/${res.thread_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulate failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">Simulate Exception</h2>
        <p className="text-sm text-slate-400">
          Create an investigation event and open the live case view
        </p>
      </div>

      <form
        onSubmit={onSubmit}
        className="max-w-2xl space-y-4 rounded-2xl border border-white/10 bg-white/5 p-6"
      >
        <div>
          <label className="mb-1 block text-sm text-slate-300">Order number</label>
          <input
            value={orderNumber}
            onChange={(e) => setOrderNumber(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5 outline-none ring-cyan-400/30 focus:ring-2"
            required
            minLength={3}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm text-slate-300">Exception type</label>
            <select
              value={exceptionType}
              onChange={(e) => setExceptionType(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5"
            >
              {EXCEPTION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-300">Severity</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5"
            >
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm text-slate-300">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="min-h-28 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5 outline-none ring-cyan-400/30 focus:ring-2"
            required
            minLength={10}
          />
        </div>

        {error && (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
        >
          {loading ? "Submitting..." : "Simulate event"}
        </button>
      </form>
    </>
  );
}