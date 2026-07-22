"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createRole,
  deleteRole,
  getPermissionCatalog,
  getRoles,
  updateRole,
  updateRoleGrants,
} from "@/lib/api";
import type { PermissionCatalog, PermissionItem, Role } from "@/lib/types";

export function RolesManager() {
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // roleId -> Set of granted permission keys (local, editable copy)
  const [draft, setDraft] = useState<Record<string, Set<string>>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cat, rs] = await Promise.all([getPermissionCatalog(), getRoles()]);
      setCatalog(cat);
      setRoles(rs);
      const d: Record<string, Set<string>> = {};
      for (const r of rs) {
        if (!r.is_system) d[r.id] = new Set(r.permissions);
      }
      setDraft(d);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = useMemo(() => {
    const out: Record<string, boolean> = {};
    for (const r of roles) {
      if (r.is_system) continue;
      const cur = draft[r.id];
      if (!cur) continue;
      const orig = new Set(r.permissions);
      out[r.id] = cur.size !== orig.size || [...cur].some((k) => !orig.has(k));
    }
    return out;
  }, [roles, draft]);

  function toggle(roleId: string, key: string) {
    setDraft((prev) => {
      const next = new Set(prev[roleId] ?? []);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { ...prev, [roleId]: next };
    });
  }

  async function save(role: Role) {
    setSavingId(role.id);
    setError(null);
    try {
      const updated = await updateRoleGrants(role.id, [...(draft[role.id] ?? [])]);
      setRoles((rs) => rs.map((r) => (r.id === role.id ? updated : r)));
      setDraft((d) => ({ ...d, [role.id]: new Set(updated.permissions) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSavingId(null);
    }
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    setError(null);
    try {
      await createRole({ name });
      setNewName("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleRename(role: Role) {
    const name = window.prompt("Новое название роли", role.name);
    if (!name || name.trim() === role.name) return;
    setError(null);
    try {
      const updated = await updateRole(role.id, { name: name.trim() });
      setRoles((rs) => rs.map((r) => (r.id === role.id ? updated : r)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleDelete(role: Role) {
    if (!window.confirm(`Удалить роль «${role.name}»?`)) return;
    setError(null);
    try {
      await deleteRole(role.id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (loading) return <p className="text-text-faint">Загрузка…</p>;
  if (!catalog) return <p className="text-bad">{error ?? "Не удалось загрузить"}</p>;

  const groups: { title: string; items: PermissionItem[] }[] = [
    { title: "Страницы", items: catalog.pages },
    { title: "Действия", items: catalog.actions },
  ];

  return (
    <div className="space-y-4">
      {error && <div className="text-sm text-bad">{error}</div>}

      <div className="flex flex-wrap items-end gap-2">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Название новой роли"
          className="rounded border border-border bg-surface px-3 py-2 text-sm"
          data-testid="new-role-name"
        />
        <button
          type="button"
          onClick={handleCreate}
          disabled={!newName.trim()}
          className="rounded bg-accent px-3 py-2 text-xs font-semibold text-black disabled:opacity-50"
          data-testid="create-role"
        >
          Создать роль
        </button>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-2">
              <th className="sticky left-0 z-10 bg-surface-2 px-3 py-2 text-left font-medium">Право</th>
              {roles.map((r) => (
                <th key={r.id} className="px-3 py-2 text-center align-bottom">
                  <div className="font-semibold">{r.name}</div>
                  <div className="text-[11px] text-text-faint">
                    {r.user_count} польз.
                  </div>
                  {!r.is_system && (
                    <div className="mt-1 flex justify-center gap-1.5 text-[11px]">
                      <button type="button" onClick={() => handleRename(r)} className="text-accent hover:underline">
                        ✎
                      </button>
                      <button type="button" onClick={() => handleDelete(r)} className="text-bad hover:underline">
                        🗑
                      </button>
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <FragmentGroup
                key={group.title}
                title={group.title}
                items={group.items}
                roles={roles}
                draft={draft}
                onToggle={toggle}
                colSpan={roles.length + 1}
              />
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-border bg-surface-2">
              <td className="px-3 py-2 text-text-faint">Сохранить изменения</td>
              {roles.map((r) => (
                <td key={r.id} className="px-3 py-2 text-center">
                  {r.is_system ? (
                    <span className="text-[11px] text-text-faint">системная</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => save(r)}
                      disabled={!dirty[r.id] || savingId === r.id}
                      className="rounded bg-accent px-2.5 py-1 text-[11px] font-semibold text-black disabled:opacity-40"
                      data-testid={`save-role-${r.slug}`}
                    >
                      {savingId === r.id ? "…" : "Сохранить"}
                    </button>
                  )}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function FragmentGroup({
  title,
  items,
  roles,
  draft,
  onToggle,
  colSpan,
}: {
  title: string;
  items: PermissionItem[];
  roles: Role[];
  draft: Record<string, Set<string>>;
  onToggle: (roleId: string, key: string) => void;
  colSpan: number;
}) {
  return (
    <>
      <tr className="bg-surface">
        <td colSpan={colSpan} className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          {title}
        </td>
      </tr>
      {items.map((item) => (
        <tr key={item.key} className="border-b border-border/60">
          <td className="sticky left-0 z-10 bg-surface px-3 py-1.5 text-text-dim">{item.label}</td>
          {roles.map((r) => {
            const checked = r.is_system || (draft[r.id]?.has(item.key) ?? false);
            return (
              <td key={r.id} className="px-3 py-1.5 text-center">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={r.is_system}
                  onChange={() => onToggle(r.id, item.key)}
                  aria-label={`${r.name}: ${item.label}`}
                />
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
