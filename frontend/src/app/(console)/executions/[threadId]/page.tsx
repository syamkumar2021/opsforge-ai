"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
// import AppShell from "@/components/layout/AppShell";
import LifecycleStepper from "@/components/executions/LifecycleStepper";
import { decideExecution, getExecution } from "@/lib/api";
import type { AgentExecution } from "@/types/api";
import { severityColor, statusColor } from "@/lib/status";

function EmailDeliveryCard({ data }: { data: AgentExecution }) {
  const status = (data?.status || "").toLowerCase();
  const hitl = data?.notification_result?.hitl_alert;
  const finalMail = data?.notification_result?.final_email;
  const item = status === "waiting_human" ? hitl : finalMail || hitl;

  if (!item) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">
        No email notification yet.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm">
      <h3 className="mb-2 font-medium text-white">Email notification</h3>
      <p className="text-slate-300">Type: {item.type || "email"}</p>
      <p className="text-slate-300">Status: {item.status || "n/a"}</p>
      <p className="text-slate-300">
        To: {Array.isArray(item.to) ? item.to.join(", ") : item.to || "n/a"}
      </p>
      <p className="text-slate-300">Subject: {item.subject || "n/a"}</p>
      <p className="text-slate-300">Sent at: {item.sent_at || "n/a"}</p>
      {item.error && <p className="mt-2 text-rose-300">Error: {item.error}</p>}
      <p className="mt-3 text-xs text-slate-500">
        Full email content is available in Mailpit: http://localhost:8025
      </p>
    </div>
  );
}

export default function ExecutionDetailPage() {
  const params = useParams<{ threadId: string }>();
  const threadId = params.threadId;

  const [data, setData] = useState<AgentExecution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState(
    "Vendor evidence reviewed. Proceed with recommended action."
  );
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const row = await getExecution(threadId);
      setData((prev) => {
        if (
          prev?.human_decision &&
          !row.human_decision &&
          (row.status || "").toLowerCase() !== "completed" &&
          (row.status || "").toLowerCase() !== "failed"
        ) {
          return {
            ...row,
            human_decision: prev.human_decision,
            human_notes: prev.human_notes ?? row.human_notes,
          };
        }
        return row;
      });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load execution");
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 1000);
    return () => clearInterval(t);
  }, [threadId]);

  const waiting = (data?.status || "").toLowerCase() === "waiting_human";

  async function onDecide(decision: "approved" | "rejected") {
    setBusy(true);
    try {
      setData((prev) =>
        prev
          ? {
              ...prev,
              human_decision: decision,
              human_notes: notes,
            }
          : prev
      );

      const updated = await decideExecution(threadId, { decision, notes });
      setData(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <>
        <p className="text-slate-400">{error || "Loading case..."}</p>
      </>
    );
  }

  const event = data.event_payload || {};
  const order = data.research_data?.order || {};
  const browser = data.browser_evidence || {};
  const decision = data.integration_result?.decision || {};

  const rawStatus = (data.status || "pending").toLowerCase();
  const hasPlan = Array.isArray(data.plan) && data.plan.length > 0;
  const hasResearch =
    !!data.research_data && Object.keys(data.research_data).length > 0;
  const hasBrowser =
    !!data.browser_evidence && Object.keys(data.browser_evidence).length > 0;
  const hasIntegration =
    !!data.integration_result && Object.keys(data.integration_result).length > 0;

  // Lifecycle status: show running while agents work (even if API still says pending)
  let statusForStepper = rawStatus;
  if (rawStatus === "pending" || rawStatus === "running") {
    statusForStepper = "running";
  }
  if (
    rawStatus === "waiting_human" ||
    rawStatus === "completed" ||
    rawStatus === "failed"
  ) {
    statusForStepper = rawStatus;
  }

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">
            Case {event.order_number || threadId.slice(0, 8)}
          </h2>
          <p className="text-sm text-slate-400">
            {event.exception_type} · {event.description}
          </p>
        </div>
        <div className="flex gap-2">
          <span className={`rounded-full border px-2.5 py-1 text-xs ${statusColor(data.status)}`}>
            {data.status}
          </span>
          <span className={`rounded-full px-2.5 py-1 text-xs ${severityColor(event.severity)}`}>
            {event.severity || "n/a"}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <LifecycleStepper
            status={statusForStepper}
            humanDecision={data.human_decision}
            hasPlan={hasPlan}
            hasResearch={hasResearch}
            hasBrowser={hasBrowser}
            hasIntegration={hasIntegration}
          />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <h3 className="mb-2 font-medium">ERP Evidence</h3>
              <p className="text-sm text-slate-300">Found: {String(order.found ?? "—")}</p>
              <p className="text-sm text-slate-300">Status: {order.status || "—"}</p>
              <p className="text-sm text-slate-300">Customer: {order.customer_email || "—"}</p>
              <p className="text-sm text-slate-300">
                Amount: {order.total_amount ?? "—"} {order.currency || ""}
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <h3 className="mb-2 font-medium">Portal Evidence</h3>
              <p className="text-sm text-slate-300">Status: {browser.portal_status || "—"}</p>
              <p className="text-sm text-slate-300">Tracking: {browser.tracking_number || "—"}</p>
              <p className="text-sm text-slate-300">ETA: {browser.eta || "—"}</p>
              <p className="text-sm text-slate-300">Success: {String(browser.success ?? "—")}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <h3 className="mb-2 font-medium">Policy Decision</h3>
            <p className="text-sm text-cyan-200">
              {decision.reason || data.notification_result?.hitl_alert?.subject || "—"}
            </p>
            <div className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-3">
              <p>Action: {decision.action || "—"}</p>
              <p>Recommended: {decision.recommended_erp_status || "—"}</p>
              <p>Confidence: {data.confidence ?? decision.confidence ?? "—"}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <h3 className="mb-2 font-medium">Investigation Plan</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
              {(data.plan || []).map((p) => (
                <li key={p}>{p}</li>
              ))}
              {(!data.plan || data.plan.length === 0) && <li>No plan yet</li>}
            </ul>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <h3 className="mb-2 font-medium">Final Report</h3>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-sm text-slate-300">
              {data.report || "Report will appear after completion."}
            </pre>
          </div>

          <EmailDeliveryCard data={data} />
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <h3 className="mb-3 font-medium">Human Decision</h3>
            {waiting ? (
              <>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="min-h-28 w-full rounded-xl border border-white/10 bg-slate-950/70 p-3 text-sm outline-none ring-cyan-400/30 focus:ring-2"
                />
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button
                    disabled={busy}
                    onClick={() => onDecide("approved")}
                    className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
                  >
                    Approve
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => onDecide("rejected")}
                    className="rounded-xl bg-rose-500 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-400 disabled:opacity-60"
                  >
                    Reject
                  </button>
                </div>
              </>
            ) : (
              <div className="space-y-2 text-sm text-slate-300">
                <p>Decision: {data.human_decision || "—"}</p>
                <p>Notes: {data.human_notes || "—"}</p>
                <p>Approved by: {data.approved_by || "—"}</p>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
            <h3 className="mb-2 font-medium text-white">Agents executed</h3>
            <p>{(data.agents_executed || []).join(" → ") || "—"}</p>
            <p className="mt-3 text-xs text-slate-500">Thread: {data.thread_id}</p>
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
              {error}
            </div>
          )}

          {data.error && (
            <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
              {data.error}
            </div>
          )}
        </div>
      </div>
    </>
  );
}