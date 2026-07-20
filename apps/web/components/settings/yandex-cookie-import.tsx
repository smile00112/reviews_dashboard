"use client";

import { useState } from "react";
import { importSessionCookies } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";

interface YandexCookieImportProps {
  onImported: (session: SessionInfo) => void;
}

export function YandexCookieImport({ onImported }: YandexCookieImportProps) {
  const [open, setOpen] = useState(false);
  const [cookies, setCookies] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleImport() {
    setBusy(true);
    setError(null);
    try {
      const session = await importSessionCookies(cookies);
      onImported(session);
      setCookies("");
      setOpen(false);
    } catch (err) {
      setError((err as Error).message || "Не удалось импортировать куки");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-text-dim underline underline-offset-2"
        data-testid="yandex-cookie-import-open"
      >
        Сохранить куки вручную
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded border border-border p-3">
      <div className="text-xs font-medium">Ручной импорт сессии</div>
      <ol className="list-decimal space-y-1 pl-4 text-xs text-text-dim">
        <li>Откройте yandex.ru в браузере, где вы авторизованы.</li>
        <li>
          F12 → вкладка <span className="text-text">Network</span> → обновите страницу → кликните любой запрос к
          yandex.ru → в <span className="text-text">Request Headers</span> найдите строку{" "}
          <span className="text-text">Cookie</span> и скопируйте её целиком.
        </li>
        <li>Вставьте сюда. Главное — чтобы внутри был Session_id.</li>
      </ol>
      <p className="text-xs text-text-dim">
        Через консоль не получится: Session_id помечен HttpOnly, и document.cookie его не видит.
      </p>
      <textarea
        value={cookies}
        onChange={(e) => setCookies(e.target.value)}
        rows={5}
        spellCheck={false}
        placeholder="Session_id=3:1234...; yandexuid=...; i=..."
        className="w-full rounded border border-border bg-bg px-2 py-1 font-mono text-[11px]"
        data-testid="yandex-cookie-input"
      />
      {error && (
        <div className="text-xs text-bad" data-testid="yandex-cookie-error">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleImport}
          disabled={busy || cookies.trim().length === 0}
          className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
          data-testid="yandex-cookie-submit"
        >
          Сохранить куки
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          disabled={busy}
          className="rounded border border-border px-3 py-1.5 text-xs disabled:opacity-50"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
