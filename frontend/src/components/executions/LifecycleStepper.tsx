"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

const STEPS = ["pending", "running", "waiting_human", "completed"] as const;

function stepIndex(
  status?: string,
  humanDecision?: string | null,
  progress?: {
    hasPlan?: boolean;
    hasResearch?: boolean;
    hasBrowser?: boolean;
    hasIntegration?: boolean;
  }
): number {
  const s = (status || "pending").toLowerCase();
  const decision = (humanDecision || "").toLowerCase();

  if (s === "failed") return 1;
  if (s === "completed") return 3;
  if (s === "waiting_human") return 2;

  if (decision === "approved" || decision === "rejected") return 2;

  if (progress?.hasBrowser || progress?.hasIntegration) return 2;
  if (s === "running" || progress?.hasPlan || progress?.hasResearch) return 1;

  return 0;
}

export default function LifecycleStepper({
  status,
  humanDecision,
  hasPlan,
  hasResearch,
  hasBrowser,
  hasIntegration,
}: {
  status?: string;
  humanDecision?: string | null;
  hasPlan?: boolean;
  hasResearch?: boolean;
  hasBrowser?: boolean;
  hasIntegration?: boolean;
}) {
  const targetIdx = stepIndex(status, humanDecision, {
    hasPlan,
    hasResearch,
    hasBrowser,
    hasIntegration,
  });

  const rejected = (humanDecision || "").toLowerCase() === "rejected";
  const failed = (status || "").toLowerCase() === "failed";

  const ceilingRef = useRef(0);
  const [ceiling, setCeiling] = useState(0);

  useEffect(() => {
    const next = Math.max(ceilingRef.current, targetIdx);
    ceilingRef.current = next;
    setCeiling(next);
  }, [targetIdx]);

  const [visualIdx, setVisualIdx] = useState(0);

  useEffect(() => {
    if (visualIdx >= ceiling) return;

    // Single step forward → instant (running lights immediately)
    if (ceiling === visualIdx + 1) {
      setVisualIdx(ceiling);
      return;
    }

    // Multi-step jump → advance one-by-one, fast
    const t = setTimeout(() => {
      setVisualIdx((v) => Math.min(v + 1, ceiling));
    }, 160);
    return () => clearTimeout(t);
  }, [visualIdx, ceiling]);

  const activeIdx = visualIdx;

  const label = useMemo(() => {
    if (failed) return "failed";
    return (status || "pending").replaceAll("_", " ");
  }, [failed, status]);

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-5 shadow-[inset_0_0_30px_rgba(34,211,238,0.04)]">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="font-medium text-white">Execution lifecycle</h3>
        <span className="text-xs uppercase tracking-wider text-cyan-300/70">{label}</span>
      </div>

      <div className="flex items-center">
        {STEPS.map((step, idx) => {
          const done = !failed && idx < activeIdx;
          const active = !failed && idx === activeIdx;
          const isLast = idx === STEPS.length - 1;

          const showReject =
            isLast && rejected && (status || "").toLowerCase() === "completed";

          const showTick =
            done ||
            (isLast &&
              (status || "").toLowerCase() === "completed" &&
              !rejected &&
              activeIdx >= 3) ||
            (active && step === "waiting_human" && !!humanDecision);

          const lit = showTick || active || showReject;
          const segmentFilled = !failed && activeIdx > idx;

          return (
            <div key={step} className="flex min-w-0 flex-1 items-center last:flex-none">
              <div
                className={[
                  "relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-sm font-bold transition duration-300",
                  showReject
                    ? "border-rose-300/80 bg-rose-500/20 text-rose-100 shadow-[0_0_16px_rgba(251,113,133,0.55)]"
                    : lit
                    ? "border-cyan-200/90 bg-cyan-400/15 text-cyan-50 shadow-[0_0_18px_rgba(34,211,238,0.65)]"
                    : "border-white/20 bg-slate-950 text-slate-500",
                ].join(" ")}
              >
                {showReject ? "✕" : showTick ? "✓" : ""}
              </div>

              {!isLast && (
                <div className="relative mx-1 h-[2px] min-w-0 flex-1 overflow-hidden">
                  <div className="absolute inset-0 rounded-full bg-white/10" />
                  <motion.div
                    className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-cyan-300/80 via-sky-300/70 to-emerald-300/80 shadow-[0_0_10px_rgba(34,211,238,0.55)]"
                    initial={false}
                    animate={{ width: segmentFilled ? "100%" : "0%" }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-2 flex">
        {STEPS.map((step, idx) => (
          <div
            key={`${step}-label`}
            className={`flex-1 text-center text-[11px] capitalize ${
              idx <= activeIdx ? "text-cyan-200/90" : "text-slate-500"
            }`}
            style={idx === STEPS.length - 1 ? { flex: "0 0 2.25rem" } : undefined}
          >
            {step.replaceAll("_", " ")}
          </div>
        ))}
      </div>
    </div>
  );
}