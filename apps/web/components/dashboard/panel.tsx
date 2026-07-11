import type { ReactNode } from "react";

/** Shared dashboard panel wrapper matching the prototype .panel style. */
export function Panel({
  title,
  meta,
  children,
  action,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-[22px]">
      <div className="mb-[18px] flex items-center justify-between">
        <div>
          <div className="font-display text-lg font-medium tracking-tight">{title}</div>
          {meta && <div className="text-xs text-text-faint">{meta}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}
