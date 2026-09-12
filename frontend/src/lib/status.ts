export function statusColor(status?: string) {
  switch ((status || "").toLowerCase()) {
    case "pending":
      return "bg-slate-500/20 text-slate-300 border-slate-400/30";
    case "running":
      return "bg-sky-500/20 text-sky-300 border-sky-400/30";
    case "waiting_human":
      return "bg-amber-500/20 text-amber-300 border-amber-400/30";
    case "completed":
      return "bg-emerald-500/20 text-emerald-300 border-emerald-400/30";
    case "failed":
      return "bg-rose-500/20 text-rose-300 border-rose-400/30";
    default:
      return "bg-white/10 text-slate-300 border-white/10";
  }
}

export function severityColor(severity?: string) {
  switch ((severity || "").toLowerCase()) {
    case "low":
      return "bg-slate-500/20 text-slate-300";
    case "medium":
      return "bg-blue-500/20 text-blue-300";
    case "high":
      return "bg-orange-500/20 text-orange-300";
    case "critical":
      return "bg-rose-500/20 text-rose-300";
    default:
      return "bg-white/10 text-slate-300";
  }
}