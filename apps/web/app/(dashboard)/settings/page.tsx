"use client";

import { useEffect, useState } from "react";
import { getSettings } from "@/lib/api";
import type { Settings } from "@/lib/types";
import { SettingsForm } from "@/components/settings/settings-form";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch((err) => setError((err as Error).message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Настройки</h1>
        <p className="text-sm text-text-dim">Параметры дашборда</p>
      </div>

      {error && <div className="text-sm text-bad">{error}</div>}
      {settings && <SettingsForm initial={settings} />}
    </div>
  );
}
