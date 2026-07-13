import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Icon } from "../components/ui";

export default function Login() {
  const nav = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.login(username, password);
      nav("/overview");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Brand panel — vibrant, warm, not the usual navy */}
      <div className="hidden lg:flex flex-col justify-between p-12
                      bg-gradient-to-br from-brand-600 via-[#8B3FD9] to-[#C026D3] text-white">
        <div className="flex items-center gap-2.5">
          <span className="h-9 w-9 rounded-xl bg-white/15 grid place-items-center backdrop-blur">
            <Icon name="graph_3" className="text-[20px]" />
          </span>
          <p className="font-extrabold tracking-tight text-lg">SenseMinds 360</p>
        </div>

        <div className="max-w-md">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight">
            Reliability intelligence you can actually trust.
          </h1>
          <p className="mt-4 text-white/80 leading-relaxed">
            Deterministic engineering first. Learning second. Language last —
            every statement cited back to the evidence that produced it.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {["Explainable", "Reproducible", "No invented failures"].map((t) => (
              <span key={t}
                className="rounded-full bg-white/12 ring-1 ring-white/20 px-3 py-1 text-xs font-semibold backdrop-blur">
                {t}
              </span>
            ))}
          </div>
        </div>

        <p className="text-xs text-white/60">Laurus Labs · Visakhapatnam · 6 assets monitored</p>
      </div>

      {/* Form */}
      <div className="flex items-center justify-center p-6 sm:p-12">
        <form onSubmit={submit} className="w-full max-w-sm animate-rise">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <span className="h-9 w-9 rounded-xl bg-brand-600 text-white grid place-items-center">
              <Icon name="graph_3" className="text-[20px]" />
            </span>
            <p className="font-extrabold tracking-tight text-lg">SenseMinds 360</p>
          </div>

          <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
          <p className="text-sm text-ink-muted mt-1">Use your employee ID to continue.</p>

          <label className="block mt-7">
            <span className="eyebrow">Employee ID</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="mt-1.5 w-full rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm
                         outline-none transition-all focus:border-brand-400
                         focus:ring-4 focus:ring-brand-50"
            />
          </label>

          <label className="block mt-4">
            <span className="eyebrow">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="mt-1.5 w-full rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm
                         outline-none transition-all focus:border-brand-400
                         focus:ring-4 focus:ring-brand-50"
            />
          </label>

          {err && (
            <p className="mt-4 flex items-center gap-2 rounded-xl bg-crit-soft ring-1 ring-crit-ring
                          px-3 py-2 text-sm text-crit font-medium">
              <Icon name="error" className="text-[16px]" />
              {err}
            </p>
          )}

          <button className="btn-primary w-full mt-6" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
            {!busy && <Icon name="arrow_forward" className="text-[18px]" />}
          </button>
        </form>
      </div>
    </div>
  );
}
