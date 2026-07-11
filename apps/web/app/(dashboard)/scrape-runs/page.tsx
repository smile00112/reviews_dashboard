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
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">История сборов</h1>
      <ScrapeRunStatusTable items={items} />
    </div>
  );
}
