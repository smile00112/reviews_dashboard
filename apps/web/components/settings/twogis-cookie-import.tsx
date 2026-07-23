"use client";

import { useState } from "react";
import { importTwogisSessionCookies } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";

interface TwogisCookieImportProps {
  onImported: (session: SessionInfo) => void;
}

export function TwogisCookieImport({ onImported }: TwogisCookieImportProps) {
  const [open, setOpen] = useState(false);
  const [cookies, setCookies] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleImport() {
    setBusy(true);
    setError(null);
    try {
      const session = await importTwogisSessionCookies(cookies);
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
        data-testid="twogis-cookie-import-open"
      >
        Сохранить токен вручную
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded border border-border p-3">
      <div className="text-xs font-medium">Ручной импорт сессии 2ГИС</div>
      <ol className="list-decimal space-y-1 pl-4 text-xs text-text-dim">
        <li>Откройте account.2gis.com/orgs/ в браузере, где вы авторизованы.</li>
        <li>
          F12 → вкладка <span className="text-text">Network</span> → обновите страницу → кликните любой запрос к{" "}
          <span className="text-text">api.account.2gis.com</span> → в <span className="text-text">Request Headers</span>{" "}
          найдите строку <span className="text-text">authorization</span> и скопируйте её значение целиком.
        </li>
        <li>
          Вставьте сюда — подойдёт как вся строка <span className="text-text">Bearer …</span>, так и сам токен.
        </li>
      </ol>
      <p className="text-xs text-text-dim">
        Кабинет 2ГИС авторизуется токеном (Authorization: Bearer), а не куками. Токен недолговечный — если «Проверить»
        покажет «устарела», возьмите свежий тем же способом.
      </p>
      <textarea
        value={cookies}
        onChange={(e) => setCookies(e.target.value)}
        rows={4}
        spellCheck={false}
        placeholder="Bearer a4a92e92cfceb011112dff456130a4fbdf138d49"
        className="w-full rounded border border-border bg-bg px-2 py-1 font-mono text-[11px]"
        data-testid="twogis-cookie-input"
      />
      {error && (
        <div className="text-xs text-bad" data-testid="twogis-cookie-error">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleImport}
          disabled={busy || cookies.trim().length === 0}
          className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
          data-testid="twogis-cookie-submit"
        >
          Сохранить токен
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
