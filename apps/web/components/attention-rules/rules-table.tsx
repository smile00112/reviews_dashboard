"use client";

import type { AttentionRule, AttentionRuleType, Company, Organization } from "@/lib/types";

export const RULE_TYPE_LABEL: Record<AttentionRuleType, string> = {
  unanswered_overdue: "Без ответа дольше порога",
  fresh_negative: "Свежий негатив",
  escalated: "Эскалированные отзывы",
  rating_drop: "Падение рейтинга",
  aspect_spike: "Рост негативного аспекта",
};

export const SEVERITY_LABEL: Record<string, string> = {
  urgent: "срочно",
  warn: "внимание",
  info: "инфо",
};

export function paramsSummary(rule: AttentionRule): string {
  const p = rule.params;
  switch (rule.rule_type) {
    case "unanswered_overdue":
      return `> ${p.hours ?? 24} ч без ответа`;
    case "fresh_negative":
      return `≤ ${p.max_rating ?? 2}★ за ${p.window_hours ?? 2} ч`;
    case "escalated":
      return "все эскалированные";
    case "rating_drop":
      return `Δ ≤ ${p.threshold ?? -0.2} · топ ${p.top ?? 3}`;
    case "aspect_spike":
      return `от ${p.min_recent ?? 3} упоминаний · топ ${p.top ?? 3}`;
  }
}

export function scopeSummary(
  rule: AttentionRule,
  companies: Company[],
  organizations: Organization[],
): string {
  if (rule.scope_type === "company") {
    const company = companies.find((c) => c.id === rule.company_id);
    return company ? `Компания: ${company.name}` : "Компания удалена";
  }
  if (rule.scope_type === "organizations") {
    const known = organizations.filter((o) => rule.organization_ids.includes(o.id));
    return `Организации: ${known.length || rule.organization_ids.length}`;
  }
  return "Вся сеть";
}

export function RulesTable({
  rules,
  companies,
  organizations,
  onToggle,
  onEdit,
  onDelete,
}: {
  rules: AttentionRule[];
  companies: Company[];
  organizations: Organization[];
  onToggle: (rule: AttentionRule, enabled: boolean) => void;
  onEdit: (rule: AttentionRule) => void;
  onDelete: (rule: AttentionRule) => void;
}) {
  if (rules.length === 0) {
    return <div className="py-10 text-center text-text-faint">Правил пока нет — создайте первое.</div>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-left text-xs uppercase text-text-faint">
          <th className="px-2 py-2">Тип</th>
          <th className="px-2 py-2">Название</th>
          <th className="px-2 py-2">Параметры</th>
          <th className="px-2 py-2">Скоуп</th>
          <th className="px-2 py-2">Серьёзность</th>
          <th className="px-2 py-2">Вкл</th>
          <th className="px-2 py-2" />
        </tr>
      </thead>
      <tbody>
        {rules.map((rule) => (
          <tr key={rule.id} className="border-b border-border/50" data-testid="rule-row">
            <td className="px-2 py-2 font-medium">{RULE_TYPE_LABEL[rule.rule_type]}</td>
            <td className="px-2 py-2 text-text-dim">{rule.name ?? "—"}</td>
            <td className="px-2 py-2 font-mono text-xs">{paramsSummary(rule)}</td>
            <td className="px-2 py-2">{scopeSummary(rule, companies, organizations)}</td>
            <td className="px-2 py-2">{SEVERITY_LABEL[rule.severity] ?? rule.severity}</td>
            <td className="px-2 py-2">
              <input
                type="checkbox"
                checked={rule.is_enabled}
                onChange={(e) => onToggle(rule, e.target.checked)}
                data-testid="rule-toggle"
              />
            </td>
            <td className="px-2 py-2 text-right">
              <button className="mr-2 text-xs text-accent" onClick={() => onEdit(rule)}>
                Изменить
              </button>
              <button className="text-xs text-bad" onClick={() => onDelete(rule)}>
                Удалить
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
