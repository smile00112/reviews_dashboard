"use client";

import { useState } from "react";
import type { Review, ReviewStatus } from "@/lib/types";
import { patchReview } from "@/lib/api";

const PLATFORM_TAG: Record<string, { label: string; cls: string }> = {
  yandex: { label: "Я", cls: "bg-[#fc3f1d]/15 text-[#ff6b4d]" },
  google: { label: "G", cls: "bg-[#4285f4]/15 text-[#7ab0ff]" },
  gis2: { label: "2Г", cls: "bg-[#2dbe64]/15 text-[#4fd786]" },
};

function stars(rating: number): string {
  return "★".repeat(rating) + "☆".repeat(5 - rating);
}

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const h = Math.floor(ms / 3_600_000);
  if (h < 1) return "меньше часа назад";
  if (h < 24) return `${h} ч назад`;
  const d = Math.floor(h / 24);
  return `${d} дн назад`;
}

function ageHours(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
}

function StatusBadge({ review }: { review: Review }) {
  if (review.status === "escalated")
    return <span className="rounded bg-bad/15 px-2 py-0.5 text-[10.5px] font-semibold text-bad">🔥 ЭСКАЛИРОВАНО</span>;
  if (review.status === "in_progress")
    return <span className="rounded bg-accent/15 px-2 py-0.5 text-[10.5px] font-semibold text-accent">В РАБОТЕ</span>;
  if (review.response_text)
    return <span className="rounded bg-good/15 px-2 py-0.5 text-[10.5px] font-semibold text-good">ОТВЕЧЕН</span>;
  return (
    <span className="rounded bg-bad/15 px-2 py-0.5 text-[10.5px] font-semibold text-bad">
      БЕЗ ОТВЕТА · {ageHours(review.first_seen_at)}ч
    </span>
  );
}

export function ReviewCard({
  review,
  onPatched,
  onAspect,
}: {
  review: Review;
  onPatched: (updated: Review) => void;
  onAspect: (category: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<string>(review.paid_cost?.toString() ?? "");

  async function patch(payload: Parameters<typeof patchReview>[1]) {
    setBusy(true);
    setError(null);
    try {
      onPatched(await patchReview(review.id, payload));
    } catch (e) {
      const status = (e as Error & { status?: number }).status;
      setError(
        status === 401 || status === 403
          ? "Нужны права администратора"
          : "Не удалось сохранить",
      );
    } finally {
      setBusy(false);
    }
  }

  const tag = review.platform ? PLATFORM_TAG[review.platform] : null;
  const negative = review.rating <= 3;

  return (
    <div
      className={`rounded-xl border bg-surface-1 p-4 ${
        review.status === "escalated" ? "border-bad/40" : review.response_text ? "border-border" : "border-bad/20"
      }`}
    >
      <div className="flex items-center justify-between gap-2 text-[12.5px]">
        <div className="flex items-center gap-2">
          <b>{review.author_name ?? "Аноним"}</b>
          <span className="text-text-faint">· {review.organization_name ?? "—"}</span>
          {tag && <span className={`rounded px-1.5 py-0.5 font-mono text-[10.5px] ${tag.cls}`}>{tag.label}</span>}
        </div>
        <span className="text-text-faint">{review.review_date_text ?? relTime(review.first_seen_at)}</span>
      </div>

      <div className={`mt-1.5 font-mono text-[13px] ${negative ? "text-bad" : "text-accent"}`}>
        {stars(review.rating)} {review.rating}.0
      </div>

      <p className="mt-2 text-[13.5px] leading-relaxed text-text">{review.review_text}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-text-dim">
        <StatusBadge review={review} />
        {review.sentiment_score !== null && (
          <span>
            Тональность:{" "}
            <b className={review.sentiment === "negative" ? "text-bad" : review.sentiment === "positive" ? "text-good" : ""}>
              {review.sentiment_score > 0 ? "+" : ""}
              {review.sentiment_score.toFixed(2)}
            </b>
          </span>
        )}
        {(review.problems?.length ?? 0) > 0 && (
          <span className="flex flex-wrap items-center gap-1">
            Аспекты:
            {review.problems!.map((p) => (
              <button
                key={p.category}
                type="button"
                onClick={() => onAspect(p.category)}
                className="rounded bg-surface-3 px-1.5 py-0.5 text-[10.5px] text-text-dim hover:text-text"
                title="Отфильтровать ленту по аспекту"
              >
                {p.category.replace(/_/g, " ")}
              </button>
            ))}
          </span>
        )}
      </div>

      {review.response_text && (
        <div className="mt-3 rounded-lg border-l-2 border-accent/50 bg-surface-2 p-3 text-[12.5px]">
          <div className="mb-1 flex justify-between text-[11px] text-text-faint">
            <span>↪ Ответ компании</span>
            {review.response_first_seen_at && <span>замечен {relTime(review.response_first_seen_at)}</span>}
          </div>
          <div className="text-text-dim">{review.response_text}</div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
        {review.status !== "in_progress" && review.status !== "escalated" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => patch({ status: "in_progress" })}
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-text-dim hover:text-text disabled:opacity-50"
          >
            В работу
          </button>
        )}
        {review.status !== "escalated" ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => patch({ status: "escalated" })}
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-text-dim hover:text-bad disabled:opacity-50"
          >
            🔥 Эскалировать
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => patch({ status: review.response_text ? "answered" : "new" })}
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-text-dim hover:text-text disabled:opacity-50"
          >
            ↩ Снять эскалацию
          </button>
        )}
        <label className="ml-1 inline-flex cursor-pointer items-center gap-1.5 text-text-dim">
          <input
            type="checkbox"
            checked={review.is_paid}
            disabled={busy}
            onChange={(e) => patch({ is_paid: e.target.checked })}
          />
          💎 Покупной
        </label>
        {review.is_paid && (
          <span className="inline-flex items-center gap-1 text-text-faint">
            <input
              type="number"
              min={0}
              value={cost}
              placeholder="₽"
              disabled={busy}
              onChange={(e) => setCost(e.target.value)}
              onBlur={() => {
                const parsed = cost === "" ? null : Number(cost);
                if (parsed !== review.paid_cost) patch({ paid_cost: parsed });
              }}
              className="w-20 rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[12px]"
            />
            ₽
          </span>
        )}
        {error && <span className="text-[11.5px] text-bad">{error}</span>}
      </div>
    </div>
  );
}
