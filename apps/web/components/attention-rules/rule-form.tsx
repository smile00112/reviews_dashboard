"use client";

import { useState } from "react";
import type {
  AttentionRule,
  AttentionRuleCreatePayload,
  AttentionRuleType,
  AttentionScopeType,
  AttentionSeverity,
  Company,
  Organization,
} from "@/lib/types";
import { RULE_TYPE_LABEL } from "./rules-table";

// Дефолты параметров = сиды бэкенда.
const PARAM_DEFAULTS: Record<AttentionRuleType, Record<string, number>> = {
  unanswered_overdue: { hours: 24 },
  fresh_negative: { window_hours: 2, max_rating: 2 },
  escalated: {},
  rating_drop: { threshold: -0.2, top: 3 },
  aspect_spike: { min_recent: 3, top: 3 },
};

const PARAM_FIELDS: Record<AttentionRuleType, { key: string; label: string; step?: string }[]> = {
  unanswered_overdue: [{ key: "hours", label: "Часов без ответа" }],
  fresh_negative: [
    { key: "window_hours", label: "Окно, часов" },
    { key: "max_rating", label: "Макс. рейтинг (звёзд)" },
  ],
  escalated: [],
  rating_drop: [
    { key: "threshold", label: "Порог падения (отрицательный)", step: "0.05" },
    { key: "top", label: "Максимум точек в списке" },
  ],
  aspect_spike: [
    { key: "min_recent", label: "Мин. упоминаний за 7 дней" },
    { key: "top", label: "Максимум аспектов в списке" },
  ],
};

export function RuleForm({
  companies,
  organizations,
  initial,
  onSubmit,
  onCancel,
}: {
  companies: Company[];
  organizations: Organization[];
  initial: AttentionRule | null;
  onSubmit: (payload: AttentionRuleCreatePayload) => Promise<void>;
  onCancel: () => void;
}) {
  const [ruleType, setRuleType] = useState<AttentionRuleType>(initial?.rule_type ?? "unanswered_overdue");
  const [name, setName] = useState(initial?.name ?? "");
  const [severity, setSeverity] = useState<AttentionSeverity>(initial?.severity ?? "warn");
  const [scopeType, setScopeType] = useState<AttentionScopeType>(initial?.scope_type ?? "global");
  const [companyId, setCompanyId] = useState(initial?.company_id ?? "");
  const [orgIds, setOrgIds] = useState<string[]>(initial?.organization_ids ?? []);
  const [params, setParams] = useState<Record<string, number>>(
    initial?.params ?? PARAM_DEFAULTS[initial?.rule_type ?? "unanswered_overdue"],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function switchType(next: AttentionRuleType) {
    setRuleType(next);
    setParams(PARAM_DEFAULTS[next]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onSubmit({
        rule_type: ruleType,
        name: name.trim() || null,
        severity,
        params,
        scope_type: scopeType,
        company_id: scopeType === "company" ? companyId || null : null,
        organization_ids: scopeType === "organizations" ? orgIds : [],
      });
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        status === 401 || status === 403
          ? "Нужны права администратора"
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-border bg-surface-2 p-4" data-testid="rule-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Тип правила
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={ruleType}
            onChange={(e) => switchType(e.target.value as AttentionRuleType)}
            disabled={initial !== null}
            data-testid="rule-type"
          >
            {(Object.keys(RULE_TYPE_LABEL) as AttentionRuleType[]).map((t) => (
              <option key={t} value={t}>{RULE_TYPE_LABEL[t]}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Название (необязательно)
          <input
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            data-testid="rule-name"
          />
        </label>
      </div>

      {PARAM_FIELDS[ruleType].length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {PARAM_FIELDS[ruleType].map((field) => (
            <label key={field.key} className="block text-xs">
              {field.label}
              <input
                type="number"
                step={field.step ?? "1"}
                className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
                value={params[field.key] ?? ""}
                onChange={(e) => setParams({ ...params, [field.key]: Number(e.target.value) })}
                data-testid={`param-${field.key}`}
              />
            </label>
          ))}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Серьёзность
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={severity}
            onChange={(e) => setSeverity(e.target.value as AttentionSeverity)}
            data-testid="rule-severity"
          >
            <option value="urgent">срочно</option>
            <option value="warn">внимание</option>
            <option value="info">инфо</option>
          </select>
        </label>
        <label className="block text-xs">
          Скоуп
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={scopeType}
            onChange={(e) => setScopeType(e.target.value as AttentionScopeType)}
            data-testid="rule-scope"
          >
            <option value="global">Вся сеть</option>
            <option value="company">Компания</option>
            <option value="organizations">Организации</option>
          </select>
        </label>
      </div>

      {scopeType === "company" && (
        <label className="block text-xs">
          Компания
          <select
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
            data-testid="rule-company"
          >
            <option value="">— выберите —</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
      )}

      {scopeType === "organizations" && (
        <label className="block text-xs">
          Организации (Ctrl/Cmd — несколько)
          <select
            multiple
            size={Math.min(8, Math.max(3, organizations.length))}
            className="mt-1 w-full rounded border border-border bg-transparent px-2 py-1.5"
            value={orgIds}
            onChange={(e) => setOrgIds(Array.from(e.target.selectedOptions, (o) => o.value))}
            data-testid="rule-orgs"
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>{o.name ?? o.id}</option>
            ))}
          </select>
        </label>
      )}

      {error && <div className="text-xs text-bad">{error}</div>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
          data-testid="rule-submit"
        >
          {initial ? "Сохранить" : "Создать правило"}
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-border px-3 py-1.5 text-xs">
          Отмена
        </button>
      </div>
    </form>
  );
}
