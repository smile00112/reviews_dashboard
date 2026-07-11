"use client";

import { useState } from "react";
import { createOrganization, updateOrganization } from "@/lib/api";
import type { Organization, ScrapeMode } from "@/lib/types";
import { ModeSelect } from "./mode-select";

interface BranchFormProps {
  companyId: string;
  branch?: Organization | null;
  onSaved: () => void;
  onClose: () => void;
}

const fieldLabel = "mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-text-faint";
const fieldInput =
  "w-full rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[13.5px] text-text outline-none focus:border-accent";

// "" / "1,5" → number | null. Accepts comma or dot decimals.
function numOrNull(value: string): number | null {
  const trimmed = value.trim().replace(",", ".");
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isNaN(n) ? null : n;
}

// Display a nullable numeric field as an editable string.
function numStr(value: number | null | undefined): string {
  return value == null ? "" : String(value);
}

// One platform's editable metrics. Rating/review inputs hide when their setter is null
// (Yandex — those come from the scraper); rating_count is always editable.
function PlatformFields({
  title,
  url,
  onUrl,
  urlPlaceholder,
  rating,
  onRating,
  reviewCount,
  onReviewCount,
  ratingCount,
  onRatingCount,
}: {
  title: string;
  url?: string;
  onUrl?: (v: string) => void;
  urlPlaceholder?: string;
  rating: string | null;
  onRating: ((v: string) => void) | null;
  reviewCount: string | null;
  onReviewCount: ((v: string) => void) | null;
  ratingCount: string;
  onRatingCount: (v: string) => void;
}) {
  return (
    <div className="mb-3">
      <div className="mb-1.5 text-[12px] font-medium text-text-dim">{title}</div>
      {onUrl && (
        <input
          value={url ?? ""}
          onChange={(e) => onUrl(e.target.value)}
          placeholder={urlPlaceholder}
          className={`${fieldInput} mb-2`}
        />
      )}
      <div className="grid grid-cols-3 gap-2">
        {onRating ? (
          <input
            value={rating ?? ""}
            onChange={(e) => onRating(e.target.value)}
            inputMode="decimal"
            placeholder="Рейтинг"
            className={fieldInput}
          />
        ) : (
          <div className="flex items-center px-1 text-[11px] text-text-faint">Рейтинг: скрейпер</div>
        )}
        {onReviewCount ? (
          <input
            value={reviewCount ?? ""}
            onChange={(e) => onReviewCount(e.target.value)}
            inputMode="numeric"
            placeholder="Отзывов"
            className={fieldInput}
          />
        ) : (
          <div className="flex items-center px-1 text-[11px] text-text-faint">Отзывов: скрейпер</div>
        )}
        <input
          value={ratingCount}
          onChange={(e) => onRatingCount(e.target.value)}
          inputMode="numeric"
          placeholder="Оценок"
          className={fieldInput}
        />
      </div>
    </div>
  );
}

export function BranchForm({ companyId, branch, onSaved, onClose }: BranchFormProps) {
  const editing = Boolean(branch);
  const [name, setName] = useState(branch?.name ?? "");
  const [city, setCity] = useState(branch?.city ?? "");
  const [url, setUrl] = useState(branch?.yandex_url ?? "");
  const [address, setAddress] = useState(branch?.address ?? "");
  const [mode, setMode] = useState<ScrapeMode>(branch?.preferred_scrape_mode ?? "public");
  // Yandex metrics (rating/review_count come from the scraper; rating_count is manual)
  const [yandexRatingCount, setYandexRatingCount] = useState(numStr(branch?.yandex_rating_count));
  // 2GIS metrics (fully manual)
  const [gis2Url, setGis2Url] = useState(branch?.gis2_url ?? "");
  const [gis2Rating, setGis2Rating] = useState(numStr(branch?.gis2_rating));
  const [gis2ReviewCount, setGis2ReviewCount] = useState(numStr(branch?.gis2_review_count));
  const [gis2RatingCount, setGis2RatingCount] = useState(numStr(branch?.gis2_rating_count));
  // Google metrics (fully manual)
  const [googleUrl, setGoogleUrl] = useState(branch?.google_url ?? "");
  const [googleRating, setGoogleRating] = useState(numStr(branch?.google_rating));
  const [googleReviewCount, setGoogleReviewCount] = useState(numStr(branch?.google_review_count));
  const [googleRatingCount, setGoogleRatingCount] = useState(numStr(branch?.google_rating_count));
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!city.trim()) {
      setError("Укажите город филиала");
      return;
    }
    if (!editing && !url.trim()) {
      setError("Укажите ссылку на карточку (URL)");
      return;
    }
    setLoading(true);
    setError(null);
    const platformMetrics = {
      yandex_rating_count: numOrNull(yandexRatingCount),
      gis2_url: gis2Url.trim() || null,
      gis2_rating: numOrNull(gis2Rating),
      gis2_review_count: numOrNull(gis2ReviewCount),
      gis2_rating_count: numOrNull(gis2RatingCount),
      google_url: googleUrl.trim() || null,
      google_rating: numOrNull(googleRating),
      google_review_count: numOrNull(googleReviewCount),
      google_rating_count: numOrNull(googleRatingCount),
    };
    try {
      if (editing && branch) {
        await updateOrganization(branch.id, {
          name: name.trim() || null,
          city: city.trim(),
          address: address.trim() || null,
          preferred_scrape_mode: mode,
          ...platformMetrics,
        });
      } else {
        await createOrganization({
          yandex_url: url.trim(),
          preferred_scrape_mode: mode,
          name: name.trim() || null,
          city: city.trim(),
          address: address.trim() || null,
          company_id: companyId,
          ...platformMetrics,
        });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить филиал");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-10 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-border bg-surface p-7">
        <h2 className="mb-1 font-display text-2xl font-medium">
          {editing ? "Редактировать филиал" : "Добавить филиал"}
        </h2>
        <p className="mb-6 text-[13px] text-text-dim">
          Филиал — точка на карте, для которой собираются отзывы.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className={fieldLabel}>Название точки</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Тверская, 17" className={fieldInput} />
          </div>

          <div className="mb-4 grid grid-cols-2 gap-4">
            <div>
              <label className={fieldLabel}>Город *</label>
              <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Москва" className={fieldInput} />
            </div>
            <div>
              <label className={fieldLabel}>Режим сбора</label>
              <ModeSelect value={mode} onChange={setMode} />
            </div>
          </div>

          <div className="mb-4">
            <label className={fieldLabel}>URL карточки Яндекс{editing ? "" : " *"}</label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={editing}
              placeholder="https://yandex.ru/maps/org/..."
              className={`${fieldInput} ${editing ? "opacity-60" : ""}`}
            />
            {editing && <p className="mt-1 text-[11px] text-text-faint">URL нельзя изменить после создания.</p>}
          </div>

          <div className="mb-4">
            <label className={fieldLabel}>Полный адрес</label>
            <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="ул. Тверская, д. 17" className={fieldInput} />
          </div>

          <div className="mb-4 border-t border-border pt-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
              Показатели по площадкам
            </p>

            <PlatformFields
              title="Яндекс"
              rating={null}
              onRating={null}
              reviewCount={null}
              onReviewCount={null}
              ratingCount={yandexRatingCount}
              onRatingCount={setYandexRatingCount}
            />
            <PlatformFields
              title="2ГИС"
              url={gis2Url}
              onUrl={setGis2Url}
              urlPlaceholder="https://2gis.ru/..."
              rating={gis2Rating}
              onRating={setGis2Rating}
              reviewCount={gis2ReviewCount}
              onReviewCount={setGis2ReviewCount}
              ratingCount={gis2RatingCount}
              onRatingCount={setGis2RatingCount}
            />
            <PlatformFields
              title="Google Maps"
              url={googleUrl}
              onUrl={setGoogleUrl}
              urlPlaceholder="https://maps.google.com/..."
              rating={googleRating}
              onRating={setGoogleRating}
              reviewCount={googleReviewCount}
              onReviewCount={setGoogleReviewCount}
              ratingCount={googleRatingCount}
              onRatingCount={setGoogleRatingCount}
            />
          </div>

          {error && <p className="mt-3 text-[13px] text-bad">{error}</p>}

          <div className="mt-6 flex justify-end gap-3 border-t border-border pt-5">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-[13px] font-medium text-text hover:bg-surface-3"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-accent px-4 py-2.5 text-[13px] font-semibold text-bg hover:bg-accent-dim disabled:opacity-50"
            >
              {loading ? "Сохранение…" : editing ? "Сохранить" : "Создать филиал"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
