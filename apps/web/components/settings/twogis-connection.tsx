"use client";

import { useEffect, useState } from "react";
import { checkTwogisSession, getTwogisSession } from "@/lib/api";
import type { SessionInfo, SessionStatus } from "@/lib/types";
import { TwogisCookieImport } from "./twogis-cookie-import";

const STATUS_LABEL: Record<SessionStatus, string> = {
  missing: "Не подключено",
  valid: "Подключено",
  expired: "Сессия устарела",
  needs_manual_action: "Требуется ручной вход",
  pending: "Проверка…",
  awaiting_code: "Ожидает код подтверждения",
};

export function TwogisConnection() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getTwogisSession()
      .then(setSession)
      .catch((err) => setError((err as Error).message));
  }, []);

  async function handleCheck() {
    setError(null);
    setBusy(true);
    try {
      const info = await checkTwogisSession();
      setSession(info);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const status = session?.status ?? "missing";

  return (
    <div className="max-w-md space-y-3 rounded border border-border bg-surface p-4">
      <div>
        <h2 className="text-sm font-medium">Подключение к 2ГИС</h2>
        <p className="text-xs text-text-dim">
          Статус: <strong className="text-text">{STATUS_LABEL[status]}</strong>
        </p>
        {session?.last_checked_at && (
          <p className="text-xs text-text-dim">
            Последняя проверка: {new Date(session.last_checked_at).toLocaleString("ru-RU")}
          </p>
        )}
        {session?.message && status !== "valid" && (
          <p className="text-xs text-text-dim" data-testid="twogis-session-message">
            Причина: <span className="text-text">{session.message}</span>
          </p>
        )}
      </div>

      {error && <div className="text-sm text-bad">{error}</div>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleCheck}
          disabled={busy}
          className="rounded border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
          data-testid="twogis-check-session"
        >
          Проверить
        </button>
      </div>

      <TwogisCookieImport onImported={setSession} />
    </div>
  );
}
