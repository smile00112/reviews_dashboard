"use client";

import { useEffect, useRef, useState } from "react";
import { checkSession, getSession, loginYandex, submitSessionCode } from "@/lib/api";
import type { SessionInfo, SessionStatus } from "@/lib/types";
import { YandexCodeModal } from "./yandex-code-modal";
import { YandexCookieImport } from "./yandex-cookie-import";

const STATUS_LABEL: Record<SessionStatus, string> = {
  missing: "Не подключено",
  valid: "Подключено",
  expired: "Сессия устарела",
  needs_manual_action: "Требуется ручной вход",
  pending: "Выполняется вход…",
  awaiting_code: "Ожидает код подтверждения",
};

const POLL_INTERVAL_MS = 2000;

export function YandexConnection() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [dismissedCodePrompt, setDismissedCodePrompt] = useState(false);
  // The status stays awaiting_code until the background login picks the code
  // up, so without this the modal would sit there inviting a second submit —
  // which the API rejects with 409, the code having already been consumed.
  const [codeSubmitted, setCodeSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const loggedStepsRef = useRef(0);

  // Mirror the login trace into the browser console. The Playwright run
  // happens in a background task on the API, so this is the only place an
  // operator can watch it advance or see where it stopped.
  useEffect(() => {
    const steps = session?.progress ?? [];
    if (steps.length < loggedStepsRef.current) {
      loggedStepsRef.current = 0; // a new attempt reset the trace
    }
    for (let i = loggedStepsRef.current; i < steps.length; i += 1) {
      const { at, step, url } = steps[i];
      console.info(`[yandex-login] ${new Date(at).toLocaleTimeString("ru-RU")} ${step}`, url ?? "");
    }
    loggedStepsRef.current = steps.length;
  }, [session]);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const info = await getSession();
        setSession(info);
        if (info.status !== "pending" && info.status !== "awaiting_code") {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => {
    getSession()
      .then((info) => {
        setSession(info);
        if (info.status === "pending" || info.status === "awaiting_code") {
          startPolling();
        }
      })
      .catch((err) => setError((err as Error).message));
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleStartLogin() {
    setError(null);
    setBusy(true);
    setDismissedCodePrompt(false);
    setCodeSubmitted(false);
    try {
      await loginYandex();
      startPolling();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitCode(value: string) {
    // Throws on failure so the modal can keep itself open and show why.
    const info = await submitSessionCode(value);
    setSession(info);
    setCodeSubmitted(true);
    startPolling();
  }

  async function handleCheck() {
    setError(null);
    setBusy(true);
    try {
      const info = await checkSession();
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
        <h2 className="text-sm font-medium">Подключение к Яндексу</h2>
        <p className="text-xs text-text-dim">
          Статус: <strong className="text-text">{STATUS_LABEL[status]}</strong>
        </p>
        {session?.last_login_at && (
          <p className="text-xs text-text-dim">Последний вход: {new Date(session.last_login_at).toLocaleString("ru-RU")}</p>
        )}
        {session?.message && status !== "valid" && (
          <p className="text-xs text-text-dim" data-testid="yandex-session-message">
            Причина: <span className="text-text">{session.message}</span>
          </p>
        )}
      </div>

      {status === "awaiting_code" && codeSubmitted && (
        <p className="text-xs text-text-dim" data-testid="yandex-code-sent">
          Код отправлен, ждём ответа Яндекса…
        </p>
      )}

      {status === "awaiting_code" && dismissedCodePrompt && !codeSubmitted && (
        <button
          type="button"
          onClick={() => setDismissedCodePrompt(false)}
          className="rounded border border-accent px-3 py-1.5 text-xs font-semibold text-accent"
          data-testid="yandex-code-reopen"
        >
          Ввести код
        </button>
      )}

      {error && <div className="text-sm text-bad">{error}</div>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleStartLogin}
          disabled={busy || status === "pending" || status === "awaiting_code"}
          className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
          data-testid="yandex-start-login"
        >
          Начать авторизацию
        </button>
        <button
          type="button"
          onClick={handleCheck}
          disabled={busy || status === "pending" || status === "awaiting_code"}
          className="rounded border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
          data-testid="yandex-check-session"
        >
          Проверить
        </button>
      </div>

      <YandexCookieImport onImported={setSession} />

      {status === "awaiting_code" && !dismissedCodePrompt && !codeSubmitted && (
        <YandexCodeModal onSubmit={handleSubmitCode} onCancel={() => setDismissedCodePrompt(true)} />
      )}
    </div>
  );
}
