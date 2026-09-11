"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";

interface RankedItem {
  label: string;
  confidence: number | null;
  evidence?: string[];
}

export function RankedBars({
  items,
  title,
  className,
}: {
  items: RankedItem[];
  title?: string;
  className?: string;
}) {
  const [expandedIdx, setExpandedIdx] = React.useState<number | null>(null);
  const sorted = [...items].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));

  return (
    <div className={cn("space-y-3", className)}>
      {title && (
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
          {title}
        </span>
      )}
      {sorted.map((item, i) => {
        const pct = Math.round((item.confidence ?? 0) * 100);
        const isExpanded = expandedIdx === i;

        return (
          <div key={i} className="space-y-1.5">
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground font-mono w-5 text-right shrink-0">
                {i + 1}.
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium font-mono">{item.label}</span>
                  <span className="text-xs font-mono text-muted-foreground tabular-nums">
                    {pct}%
                  </span>
                </div>
                <div className="ranked-track">
                  <div
                    className={cn(
                      "ranked-fill",
                      i === 0 ? "bg-primary" : i === 1 ? "bg-secondary" : "bg-muted-foreground/50"
                    )}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
              {item.evidence && item.evidence.length > 0 && (
                <button
                  onClick={() => setExpandedIdx(isExpanded ? null : i)}
                  className="shrink-0 p-1 text-muted-foreground hover:text-foreground transition-colors duration-150"
                  aria-label={isExpanded ? "Collapse evidence" : "Expand evidence"}
                >
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 transition-transform duration-150",
                      isExpanded && "rotate-180"
                    )}
                  />
                </button>
              )}
            </div>
            {isExpanded && item.evidence && item.evidence.length > 0 && (
              <ul className="ml-8 space-y-0.5 text-xs text-muted-foreground animate-fade-in">
                {item.evidence.map((e, j) => (
                  <li key={j}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
