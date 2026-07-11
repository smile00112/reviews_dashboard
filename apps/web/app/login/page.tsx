"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/companies");
      router.refresh();
    } catch {
      // Non-revealing message (same for unknown email / wrong password).
      setError("Неверный email или пароль");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="flex items-center justify-center gap-2 font-display text-2xl font-semibold tracking-tight">
            <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_#d4ff3a]" />
            SERM Dashboard
          </div>
          <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-text-faint">
            Панель управления
          </div>
        </div>
        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-border bg-surface p-7"
        >
          <h1 className="mb-1 font-display text-xl font-medium">Вход</h1>
          <p className="mb-6 text-[13px] text-text-dim">Войдите, чтобы управлять организациями и филиалами.</p>

          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-text-faint">
            Email
          </label>
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mb-4 w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13.5px] text-text outline-none focus:border-accent"
            placeholder="admin@example.com"
          />

          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-text-faint">
            Пароль
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-5 w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13.5px] text-text outline-none focus:border-accent"
            placeholder="••••••••"
          />

          {error && <p className="mb-4 text-[13px] text-bad">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent px-4 py-2.5 text-[14px] font-semibold text-bg hover:bg-accent-dim disabled:opacity-50"
          >
            {loading ? "Вход…" : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
}
