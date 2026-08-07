"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@opsforge.ai");
  const [password, setPassword] = useState("OpsForge@123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-[radial-gradient(ellipse_at_top,_#0f172a_0%,_#020617_60%)] px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur-xl"
      >
        <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/80">OpsForge Console</p>
        <h1 className="mt-2 text-3xl font-semibold text-white">Sign in</h1>
        <p className="mt-2 text-sm text-slate-400">Use your OpsForge account to continue.</p>

        <div className="mt-8 space-y-4">
          <div>
            <label className="mb-1.5 block text-sm text-slate-300">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5 text-slate-100 outline-none ring-cyan-400/40 focus:ring-2"
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm text-slate-300">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2.5 text-slate-100 outline-none ring-cyan-400/40 focus:ring-2"
              required
            />
          </div>
        </div>

        {error && (
          <p className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mt-6 w-full rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-60"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}