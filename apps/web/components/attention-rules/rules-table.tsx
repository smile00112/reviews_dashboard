"use client";

import { Fragment, useState } from "react";
import type { AttentionRule, AttentionRuleType, Company, Organization } from "@/lib/types";
import { RuleHistory } from "./rule-history";

export const RULE_TYPE_LABEL: Record<AttentionRuleType, string> = {
  unanswered_overdue: "Без ответа",
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
      return `≥ ${p.min_count ?? 1} без ответа`;
    case "fresh_negative":
      return `≤ ${p.max_rating ?? 2}★ · ≥ ${p.min_count ?? 1}`;
    case "escalated":
      return `≥ ${p.min_count ?? 1} эскалированных`;
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

function StatusBadge({ rule }: { rule: AttentionRule }) {
  if (rule.is_latched) {
    const ends = new Date(rule.period_ends_at).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    return (
      <span title={`Период до ${ends}`} className="rounded bg-bad/15 px-2 py-0.5 text-xs text-bad">
        ● сработало · до {ends}
      </span>
    );
  }
  return <span className="rounded bg-surface-3 px-2 py-0.5 text-xs text-text-dim">○ ждёт</span>;
}

export function RulesTable({
  rules,
  companies,
  organizations,
  onToggle,
  onEdit,
  onDelete,
  onRestart,
}: {
  rules: AttentionRule[];
  companies: Company[];
  organizations: Organization[];
  onToggle: (rule: AttentionRule, enabled: boolean) => void;
  onEdit: (rule: AttentionRule) => void;
  onDelete: (rule: AttentionRule) => void;
  onRestart: (rule: AttentionRule) => void;
}) {
  const [openHistory, setOpenHistory] = useState<string | null>(null);

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
          <th className="px-2 py-2">Период</th>
          <th className="px-2 py-2">Статус</th>
          <th className="px-2 py-2">Вкл</th>
          <th className="px-2 py-2" />
        </tr>
      </thead>
      <tbody>
        {rules.map((rule) => (
          <Fragment key={rule.id}>
            <tr className="border-b border-border/50" data-testid="rule-row">
              <td className="px-2 py-2 font-medium">{RULE_TYPE_LABEL[rule.rule_type]}</td>
              <td className="px-2 py-2 text-text-dim">{rule.name ?? "—"}</td>
              <td className="px-2 py-2 font-mono text-xs">{paramsSummary(rule)}</td>
              <td className="px-2 py-2">{scopeSummary(rule, companies, organizations)}</td>
              <td className="px-2 py-2 tabular-nums">{rule.period_days} дн.</td>
              <td className="px-2 py-2" data-testid="rule-status">
                <StatusBadge rule={rule} />
              </td>
              <td className="px-2 py-2">
                <input
                  type="checkbox"
                  checked={rule.is_enabled}
                  onChange={(e) => onToggle(rule, e.target.checked)}
                  data-testid="rule-toggle"
                />
              </td>
              <td className="whitespace-nowrap px-2 py-2 text-right">
                <button
                  className="mr-2 text-xs text-accent"
                  onClick={() => onRestart(rule)}
                  data-testid="rule-restart"
                >
                  Перезапустить
                </button>
                <button
                  className="mr-2 text-xs text-text-dim"
                  onClick={() => setOpenHistory((cur) => (cur === rule.id ? null : rule.id))}
                  data-testid="rule-history-toggle"
                >
                  История
                </button>
                <button className="mr-2 text-xs text-accent" onClick={() => onEdit(rule)}>
                  Изменить
                </button>
                <button className="text-xs text-bad" onClick={() => onDelete(rule)}>
                  Удалить
                </button>
              </td>
            </tr>
            {openHistory === rule.id && (
              <tr className="border-b border-border/50 bg-surface-2/40">
                <td colSpan={8} className="px-2 py-3">
                  <RuleHistory ruleId={rule.id} />
                </td>
              </tr>
            )}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}
