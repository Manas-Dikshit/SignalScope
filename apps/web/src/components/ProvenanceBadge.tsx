"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ConfidenceIndicator } from "@/components/ConfidenceIndicator";
import { confidenceColor } from "@/lib/tokens";
import type { Source } from "@/lib/types";
import {
  FileText,
  PenLine,
  Ruler,
  Calculator,
  FlaskConical,
  CircleDashed,
  ChevronDown,
  AlertTriangle,
} from "lucide-react";

/* ── Source configuration ────────────────────────────────────────────── */

const SOURCE_CONFIG: Record<Source, {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  exact: boolean;
}> = {
  metadata:      { icon: FileText,       label: "metadata (exact)",      exact: true },
  user_supplied: { icon: PenLine,        label: "user supplied (exact)", exact: true },
  measured:      { icon: Ruler,          label: "measured (exact)",      exact: true },
  estimated:     { icon: Calculator,     label: "estimated",             exact: false },
  hypothesis:    { icon: FlaskConical,   label: "hypothesis",            exact: false },
  unknown:       { icon: CircleDashed,   label: "unknown",               exact: false },
};

/* ── SourceBadge ────────────────────────────────────────────────────── */

export function SourceBadge({ source, className }: { source: Source; className?: string }) {
  const config = SOURCE_CONFIG[source] ?? SOURCE_CONFIG.unknown;
  const Icon = config.icon;

  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs text-muted-foreground", className)}>
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span>{config.label}</span>
    </span>
  );
}

/* ── ConfidenceDot ──────────────────────────────────────────────────── */

export function ConfidenceDot({
  confidence,
  className,
}: {
  confidence: number | null;
  className?: string;
}) {
  if (confidence === null) return null;

  const tier = confidence >= 0.7 ? "high" : confidence >= 0.4 ? "mid" : "low";
  const dotColor = {
    high: "bg-confidence-high",
    mid: "bg-secondary",
    low: "bg-muted-foreground",
  }[tier];

  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span className={cn("h-2 w-2 rounded-full", dotColor)} />
      <span className="text-xs font-mono tabular-nums text-muted-foreground">
        {confidence.toFixed(2)}
      </span>
    </span>
  );
}

/* ── ProvenanceBadge ────────────────────────────────────────────────── */

export function ProvenanceBadge({
  source,
  confidence,
  className,
}: {
  source: Source;
  confidence?: number | null;
  className?: string;
}) {
  const config = SOURCE_CONFIG[source] ?? SOURCE_CONFIG.unknown;
  const Icon = config.icon;

  const tier = confidence !== null && confidence !== undefined
    ? confidence >= 0.7 ? "high" : confidence >= 0.4 ? "mid" : "low"
    : null;

  const borderColors = {
    high: "border-primary/30",
    mid: "border-secondary/30",
    low: "border-muted-foreground/20",
    null: "border-primary/20",
  };

  const bgColors = {
    high: "bg-primary/5",
    mid: "bg-secondary/5",
    low: "bg-muted/5",
    null: "bg-primary/5",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs",
        bgColors[tier ?? "null"],
        borderColors[tier ?? "null"],
        className
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="font-medium">{config.label.split(" ")[0]}</span>
      {!config.exact && tier && (
        <ConfidenceIndicator
          confidence={confidence!}
          variant="bar"
          showLabel={true}
          size="sm"
        />
      )}
      {config.exact && (
        <span className="text-[10px] font-medium text-primary/70 uppercase tracking-wider">exact</span>
      )}
    </span>
  );
}

/* ── EstimateCard ───────────────────────────────────────────────────── */

export function EstimateCard({
  label,
  value,
  unit,
  source,
  confidence,
  evidence,
  alternatives,
  warnings,
}: {
  label: string;
  value: number | string | null;
  unit?: string | null;
  source: Source;
  confidence?: number | null;
  evidence?: string[];
  alternatives?: { value: number | string | null; confidence?: number | null; evidence?: string[] }[];
  warnings?: string[];
}) {
  const [showEvidence, setShowEvidence] = React.useState(false);
  const [showAlternatives, setShowAlternatives] = React.useState(false);

  const formattedValue =
    value === null
      ? "—"
      : typeof value === "number"
        ? value.toLocaleString(undefined, { maximumFractionDigits: 4 })
        : String(value);

  const unitStr = unit ? ` ${unit}` : "";
  const tier = confidence !== null && confidence !== undefined
    ? confidence >= 0.7 ? "high" : confidence >= 0.4 ? "mid" : "low"
    : null;

  const accentBorder = tier === "high"
    ? "border-l-confidence-high"
    : tier === "mid"
      ? "border-l-secondary"
      : "border-l-muted-foreground/30";

  return (
    <div className={cn(
      "rounded-lg border border-l-[3px] bg-card p-4 space-y-2",
      accentBorder,
    )}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider leading-none">
          {label}
        </span>
        <SourceBadge source={source} />
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="text-xl font-display font-semibold tracking-tight">
          {formattedValue}
        </span>
        {unit && (
          <span className="text-xs text-muted-foreground font-mono">{unit}</span>
        )}
      </div>

      {confidence !== null && confidence !== undefined && (
        <ConfidenceIndicator confidence={confidence} variant="bar" size="sm" />
      )}

      {warnings && warnings.length > 0 && (
        <div className="space-y-1 pt-1">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-warning">
              <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {evidence && evidence.length > 0 && (
        <div className="pt-1">
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors duration-150"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform duration-150", showEvidence && "rotate-180")} />
            {showEvidence ? "Hide" : "Show"} evidence ({evidence.length})
          </button>
          {showEvidence && (
            <ul className="mt-1.5 space-y-0.5 pl-2 text-xs text-muted-foreground">
              {evidence.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {alternatives && alternatives.length > 0 && (
        <div className="pt-1">
          <button
            onClick={() => setShowAlternatives(!showAlternatives)}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors duration-150"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform duration-150", showAlternatives && "rotate-180")} />
            {showAlternatives ? "Hide" : "Show"} alternatives ({alternatives.length})
          </button>
          {showAlternatives && (
            <div className="mt-1.5 space-y-2 pl-2">
              {alternatives.map((alt, i) => (
                <div key={i} className="text-xs space-y-1">
                  <div className="font-medium font-mono">
                    {typeof alt.value === "number"
                      ? alt.value.toLocaleString(undefined, { maximumFractionDigits: 4 })
                      : String(alt.value)}
                  </div>
                  {alt.confidence !== null && alt.confidence !== undefined && (
                    <ConfidenceIndicator confidence={alt.confidence} size="sm" />
                  )}
                  {alt.evidence && alt.evidence.length > 0 && (
                    <ul className="text-muted-foreground space-y-0.5">
                      {alt.evidence.map((ev, j) => (
                        <li key={j}>{ev}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
