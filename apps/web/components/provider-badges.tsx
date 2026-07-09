import type { Organization } from "@/lib/types";

interface BadgeSpec {
  label: string;
  href: string | null;
  title: string;
}

function Badge({ label, href, title }: BadgeSpec) {
  const base = "rounded px-1.5 py-0.5 text-xs font-medium";
  if (!href) {
    return (
      <span className={`${base} bg-slate-100 text-slate-400`} title={`${title}: нет ссылки`}>
        {label}
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`${base} bg-slate-800 text-white hover:bg-slate-900`}
      title={title}
    >
      {label}
    </a>
  );
}

export function ProviderBadges({ org }: { org: Organization }) {
  return (
    <div className="flex gap-1">
      <Badge label="Я" href={org.yandex_url} title="Яндекс Карты" />
      <Badge label="2ГИС" href={org.twogis_url} title="2ГИС" />
      <Badge label="G" href={org.google_url} title="Google Maps" />
    </div>
  );
}
