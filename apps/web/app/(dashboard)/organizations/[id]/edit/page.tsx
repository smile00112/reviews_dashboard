"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getOrganization, updateOrganization } from "@/lib/api";
import type { Organization, ScrapeMode } from "@/lib/types";
import { ModeSelect } from "@/components/mode-select";
import { useCan } from "@/components/shell/user-context";

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

function numStr(value: number | null | undefined): string {
  return value == null ? "" : String(value);
}

export default function OrganizationEditPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const canManage = useCan("action:org.manage");

  const [org, setOrg] = useState<Organization | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Basic fields
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [address, setAddress] = useState("");
  const [mode, setMode] = useState<ScrapeMode>("public");
  const [isActive, setIsActive] = useState(true);
  // Yandex (rating/review_count come from the scraper; rating_count is manual)
  const [yandexRatingCount, setYandexRatingCount] = useState("");
  // 2GIS (fully manual)
  const [gis2Url, setGis2Url] = useState("");
  const [gis2Rating, setGis2Rating] = useState("");
  const [gis2ReviewCount, setGis2ReviewCount] = useState("");
  const [gis2RatingCount, setGis2RatingCount] = useState("");
  // Google (fully manual)
  const [googleUrl, setGoogleUrl] = useState("");
  const [googleRating, setGoogleRating] = useState("");
  const [googleReviewCount, setGoogleReviewCount] = useState("");
  const [googleRatingCount, setGoogleRatingCount] = useState("");

  useEffect(() => {
    if (!params.id) return;
    getOrganization(params.id)
      .then((o) => {
        setOrg(o);
        setName(o.name ?? "");
        setCity(o.city ?? "");
        setRegion(o.region ?? "");
        setAddress(o.address ?? "");
        setMode(o.preferred_scrape_mode);
        setIsActive(o.is_active);
        setYandexRatingCount(numStr(o.yandex_rating_count));
        setGis2Url(o.gis2_url ?? "");
        setGis2Rating(numStr(o.gis2_rating));
        setGis2ReviewCount(numStr(o.gis2_review_count));
        setGis2RatingCount(numStr(o.gis2_rating_count));
        setGoogleUrl(o.google_url ?? "");
        setGoogleRating(numStr(o.google_rating));
        setGoogleReviewCount(numStr(o.google_review_count));
        setGoogleRatingCount(numStr(o.google_rating_count));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить точку"));
  }, [params.id]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await updateOrganization(params.id, {
        name: name.trim() || null,
        city: city.trim() || null,
        region: region.trim() || null,
        address: address.trim() || null,
        preferred_scrape_mode: mode,
        is_active: isActive,
        yandex_rating_count: numOrNull(yandexRatingCount),
        gis2_url: gis2Url.trim() || null,
        gis2_rating: numOrNull(gis2Rating),
        gis2_review_count: numOrNull(gis2ReviewCount),
        gis2_rating_count: numOrNull(gis2RatingCount),
        google_url: googleUrl.trim() || null,
        google_rating: numOrNull(googleRating),
        google_review_count: numOrNull(googleReviewCount),
        google_rating_count: numOrNull(googleRatingCount),
      });
      router.push(`/organizations/${params.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить точку");
      setLoading(false);
    }
  }

  if (!org) {
    return (
      <p className="text-sm text-text-faint">{error ?? "Загрузка..."}</p>
    );
  }

  if (!canManage) {
    return (
      <div className="space-y-4">
        <Link href={`/organizations/${params.id}`} className="text-sm text-text-dim hover:text-accent">
          ← Назад к точке
        </Link>
        <p className="text-sm text-bad">Недостаточно прав для редактирования точки.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-5">
      <Link href={`/organizations/${params.id}`} className="text-sm text-text-dim hover:text-accent">
        ← Назад к точке
      </Link>
      <h1 className="font-display text-3xl font-medium tracking-tight">Редактировать точку</h1>

      <form onSubmit={handleSubmit} className="rounded-2xl border border-border bg-surface p-7">
        {/* Active toggle */}
        <label className="mb-5 flex items-center gap-3 rounded-lg border border-border bg-surface-2 px-4 py-3">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          <span>
            <span className="text-[13.5px] font-medium text-text">Точка активна</span>
            <span className="block text-[12px] text-text-faint">
              Неактивные точки исключаются из автоматического сбора отзывов (ночные задачи и «Собрать все»).
            </span>
          </span>
        </label>

        <div className="mb-4">
          <label className={fieldLabel}>Название точки</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Тверская, 17" className={fieldInput} />
        </div>

        <div className="mb-4 grid grid-cols-2 gap-4">
          <div>
            <label className={fieldLabel}>Город</label>
            <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Москва" className={fieldInput} />
          </div>
          <div>
            <label className={fieldLabel}>Регион</label>
            <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="Московская область" className={fieldInput} />
          </div>
        </div>

        <div className="mb-4">
          <label className={fieldLabel}>Полный адрес</label>
          <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="ул. Тверская, д. 17" className={fieldInput} />
        </div>

        <div className="mb-4">
          <label className={fieldLabel}>Режим сбора</label>
          <ModeSelect value={mode} onChange={setMode} />
        </div>

        <div className="mb-4">
          <label className={fieldLabel}>URL карточки Яндекс</label>
          <input value={org.yandex_url ?? ""} disabled className={`${fieldInput} opacity-60`} />
          <p className="mt-1 text-[11px] text-text-faint">URL нельзя изменить после создания.</p>
        </div>

        <div className="mb-2 border-t border-border pt-4">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
            Показатели по площадкам
          </p>

          <div className="mb-3">
            <div className="mb-1.5 text-[12px] font-medium text-text-dim">Яндекс</div>
            <div className="grid grid-cols-3 gap-2">
              <div className="flex items-center px-1 text-[11px] text-text-faint">Рейтинг: скрейпер</div>
              <div className="flex items-center px-1 text-[11px] text-text-faint">Отзывов: скрейпер</div>
              <input value={yandexRatingCount} onChange={(e) => setYandexRatingCount(e.target.value)} inputMode="numeric" placeholder="Оценок" className={fieldInput} />
            </div>
          </div>

          <div className="mb-3">
            <div className="mb-1.5 text-[12px] font-medium text-text-dim">2ГИС</div>
            <input value={gis2Url} onChange={(e) => setGis2Url(e.target.value)} placeholder="https://2gis.ru/..." className={`${fieldInput} mb-2`} />
            <div className="grid grid-cols-3 gap-2">
              <input value={gis2Rating} onChange={(e) => setGis2Rating(e.target.value)} inputMode="decimal" placeholder="Рейтинг" className={fieldInput} />
              <input value={gis2ReviewCount} onChange={(e) => setGis2ReviewCount(e.target.value)} inputMode="numeric" placeholder="Отзывов" className={fieldInput} />
              <input value={gis2RatingCount} onChange={(e) => setGis2RatingCount(e.target.value)} inputMode="numeric" placeholder="Оценок" className={fieldInput} />
            </div>
          </div>

          <div className="mb-3">
            <div className="mb-1.5 text-[12px] font-medium text-text-dim">Google Maps</div>
            <input value={googleUrl} onChange={(e) => setGoogleUrl(e.target.value)} placeholder="https://maps.google.com/..." className={`${fieldInput} mb-2`} />
            <div className="grid grid-cols-3 gap-2">
              <input value={googleRating} onChange={(e) => setGoogleRating(e.target.value)} inputMode="decimal" placeholder="Рейтинг" className={fieldInput} />
              <input value={googleReviewCount} onChange={(e) => setGoogleReviewCount(e.target.value)} inputMode="numeric" placeholder="Отзывов" className={fieldInput} />
              <input value={googleRatingCount} onChange={(e) => setGoogleRatingCount(e.target.value)} inputMode="numeric" placeholder="Оценок" className={fieldInput} />
            </div>
          </div>
        </div>

        {error && <p className="mt-3 text-[13px] text-bad">{error}</p>}

        <div className="mt-6 flex justify-end gap-3 border-t border-border pt-5">
          <Link
            href={`/organizations/${params.id}`}
            className="rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-[13px] font-medium text-text hover:bg-surface-3"
          >
            Отмена
          </Link>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-accent px-4 py-2.5 text-[13px] font-semibold text-bg hover:bg-accent-dim disabled:opacity-50"
          >
            {loading ? "Сохранение…" : "Сохранить"}
          </button>
        </div>
      </form>
    </div>
  );
}
