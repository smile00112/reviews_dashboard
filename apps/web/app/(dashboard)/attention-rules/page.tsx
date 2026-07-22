"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createAttentionRule,
  deleteAttentionRule,
  listAttentionRules,
  listCompanies,
  listOrganizations,
  restartAttentionRule,
  updateAttentionRule,
} from "@/lib/api";
import type { AttentionRule, AttentionRuleCreatePayload, Company, Organization } from "@/lib/types";
import { RuleForm } from "@/components/attention-rules/rule-form";
import { RulesTable } from "@/components/attention-rules/rules-table";

export default function AttentionRulesPage() {
  const [rules, setRules] = useState<AttentionRule[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [editing, setEditing] = useState<AttentionRule | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextRules, nextCompanies, nextOrgs] = await Promise.all([
      listAttentionRules(),
      listCompanies(),
      listOrganizations(),
    ]);
    setRules(nextRules);
    setCompanies(nextCompanies);
    setOrganizations(nextOrgs);
  }, []);

  useEffect(() => {
    refresh().catch((err) => setPageError((err as Error).message));
  }, [refresh]);

  async function handleSubmit(payload: AttentionRuleCreatePayload) {
    if (editing) {
      // rule_type менять нельзя — собираем update-пейлоад явно (без деструктуризации,
      // чтобы не ловить no-unused-vars на выброшенном поле).
      await updateAttentionRule(editing.id, {
        name: payload.name,
        severity: payload.severity,
        params: payload.params,
        scope_type: payload.scope_type,
        company_id: payload.company_id,
        organization_ids: payload.organization_ids,
        period_days: payload.period_days,
      });
    } else {
      await createAttentionRule(payload);
    }
    setFormOpen(false);
    setEditing(null);
    await refresh();
  }

  async function handleToggle(rule: AttentionRule, enabled: boolean) {
    setPageError(null);
    try {
      await updateAttentionRule(rule.id, { is_enabled: enabled });
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setPageError(status === 401 || status === 403 ? "Нужны права администратора" : (err as Error).message);
    }
  }

  async function handleDelete(rule: AttentionRule) {
    if (!window.confirm("Удалить правило?")) return;
    setPageError(null);
    try {
      await deleteAttentionRule(rule.id);
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setPageError(status === 401 || status === 403 ? "Нужны права администратора" : (err as Error).message);
    }
  }

  async function handleRestart(rule: AttentionRule) {
    setPageError(null);
    try {
      await restartAttentionRule(rule.id);
      await refresh();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setPageError(status === 401 || status === 403 ? "Нужны права администратора" : (err as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Правила внимания</h1>
          <p className="text-sm text-text-dim">
            Управляют блоком «Требуют внимания» на обзоре сети
          </p>
        </div>
        <button
          className="rounded bg-accent px-3 py-2 text-xs font-semibold text-black"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          data-testid="rule-create"
        >
          + Новое правило
        </button>
      </div>

      {pageError && <div className="text-sm text-bad">{pageError}</div>}

      {formOpen && (
        <RuleForm
          key={editing?.id ?? "new"}
          companies={companies}
          organizations={organizations}
          initial={editing}
          onSubmit={handleSubmit}
          onCancel={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}

      <RulesTable
        rules={rules}
        companies={companies}
        organizations={organizations}
        onToggle={handleToggle}
        onEdit={(rule) => {
          setEditing(rule);
          setFormOpen(true);
        }}
        onDelete={handleDelete}
        onRestart={handleRestart}
      />
    </div>
  );
}
