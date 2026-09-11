"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface SectionTabsProps {
  tabs: { key: string; label: string }[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
  size?: "sm" | "md";
}

/**
 * Tab strip that collapses into a `<select>` on small screens
 * (per acceptance: tabs → select/drawer on mobile).
 */
export function SectionTabs({
  tabs,
  value,
  onChange,
  className,
  size = "sm",
}: SectionTabsProps) {
  return (
    <div className={className}>
      {/* Desktop: segmented control */}
      <div className="hidden md:flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1 w-fit max-w-full">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-150",
              size === "md" ? "px-4 py-2" : "",
              value === tab.key
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            aria-pressed={value === tab.key}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Mobile: select */}
      <div className="md:hidden">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border bg-card px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Section"
        >
          {tabs.map((tab) => (
            <option key={tab.key} value={tab.key}>
              {tab.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}