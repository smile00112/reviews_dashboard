import { RolesManager } from "@/components/settings/roles/roles-manager";

export default function RolesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Роли и доступ</h1>
        <p className="text-sm text-text-dim">
          Настройка доступа ролей к страницам и действиям. Роль «Администратор» имеет полный
          доступ и не редактируется.
        </p>
      </div>
      <RolesManager />
    </div>
  );
}
