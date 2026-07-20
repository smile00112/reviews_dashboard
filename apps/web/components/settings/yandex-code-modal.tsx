"use client";

import { useEffect, useRef, useState } from "react";

interface YandexCodeModalProps {
  onSubmit: (code: string) => Promise<void>;
  onCancel: () => void;
}

export function YandexCodeModal({ onSubmit, onCancel }: YandexCodeModalProps) {
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // The login is blocked on this code, so put the caret in the field rather
  // than making the operator click into it.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(code);
      // Left open on failure: a wrong code must show why, not just vanish.
    } catch (err) {
      setError((err as Error).message || "Не удалось отправить код");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-border bg-surface p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="yandex-code-title"
        data-testid="yandex-code-modal"
      >
        <div id="yandex-code-title" className="font-medium">
          Код подтверждения
        </div>
        <p className="mt-1 text-xs text-text-dim">
          Яндекс отправил код на ваше устройство. Введите его — вход ждёт этот код.
        </p>
        <input
          ref={inputRef}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={12}
          className="mt-3 w-full rounded border border-border bg-transparent px-2 py-1.5 text-center font-mono text-lg tracking-[0.4em]"
          data-testid="yandex-code-input"
        />
        {error && (
          <div className="mt-2 text-xs text-bad" data-testid="yandex-code-error">
            {error}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-border px-3 py-1.5 text-xs disabled:opacity-50"
            disabled={submitting}
            onClick={onCancel}
          >
            Отмена
          </button>
          <button
            type="submit"
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg disabled:opacity-50"
            disabled={submitting || code.length === 0}
            data-testid="yandex-code-submit"
          >
            Подтвердить
          </button>
        </div>
      </form>
    </div>
  );
}
