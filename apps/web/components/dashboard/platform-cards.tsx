import type { PlatformCard } from "@/lib/types";

const META: Record<string, { name: string; logo: string; bg: string; fg: string }> = {
  yandex: { name: "Яндекс Бизнес", logo: "Я", bg: "#ffcc00", fg: "#000" },
  google: { name: "Google Business", logo: "G", bg: "#4285f4", fg: "#fff" },
  gis2: { name: "2ГИС", logo: "2", bg: "#2ecc71", fg: "#fff" },
};

const ORDER = ["yandex", "gis2", "google"];

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10.5px] font-semibold uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mt-1 font-mono text-base">{children}</div>
    </div>
  );
}

function na() {
  return <span className="text-text-faint">нет данных</span>;
}

function delta(v: number | null) {
  if (v === null || v === undefined) return <span className="text-text-faint">—</span>;
  const cls = v > 0 ? "text-good" : v < 0 ? "text-bad" : "text-text-faint";
  return <span className={cls}>{v > 0 ? "▲ +" : v < 0 ? "▼ " : "• "}{v}</span>;
}

export function PlatformCards({ cards }: { cards: PlatformCard[] }) {
  const byPlatform = Object.fromEntries(cards.map((c) => [c.platform, c]));
  return (
    <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
      {ORDER.map((key) => {
        const c = byPlatform[key];
        const m = META[key];
        if (!c) return null;
        return (
          <div key={key} className="rounded-2xl border border-border bg-surface p-5">
            <div className="mb-4 flex items-center gap-3 border-b border-border pb-3.5">
              <div
                className="flex h-10 w-10 items-center justify-center rounded-[10px] font-display text-xl font-bold"
                style={{ background: m.bg, color: m.fg }}
              >
                {m.logo}
              </div>
              <div>
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-text-faint">
                  {c.weighted_rating !== null ? `рейтинг ${c.weighted_rating}` : "нет данных"}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Ср. взвеш">{c.weighted_rating ?? na()}</Metric>
              <Metric label="Δ за период">{delta(c.rating_delta)}</Metric>
              <Metric label="Доля негатива">
                {c.negativity_percent !== null ? (
                  <span className="text-bad">{c.negativity_percent}%</span>
                ) : (
                  na()
                )}
              </Metric>
              <Metric label="Скорость ответа">
                {c.response_speed_hours !== null ? `${c.response_speed_hours} ч` : na()}
              </Metric>
            </div>
          </div>
        );
      })}
    </div>
  );
}
