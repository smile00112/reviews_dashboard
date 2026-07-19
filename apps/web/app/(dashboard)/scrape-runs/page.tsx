"use client";

import { useEffect, useState } from "react";
import { listScrapeRuns } from "@/lib/api";
import type { ScrapeRun } from "@/lib/types";
import { ScrapeRunStatusTable } from "@/components/scrape-run-status";

export default function ScrapeRunsPage() {
  const [items, setItems] = useState<ScrapeRun[]>([]);

  useEffect(() => {
    listScrapeRuns()
      .then((data) => setItems(data.items))
      .catch(console.error);
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-4xl font-medium tracking-tight">История сборов</h1>
        <p className="mt-1.5 text-sm text-text-dim">Результаты сборов отзывов по всем площадкам</p>
      </div>
      <ScrapeRunStatusTable items={items} />
    </div>
  );
}
