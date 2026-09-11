"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { confidenceTier, PALETTE } from "@/lib/tokens";
import type { Source } from "@/lib/types";

/* ──────────────────────────────────────────────────────────────────────
 * ConfidenceIndicator
 *
 * Two variants:
 *   bar   — horizontal magnitude bar (default, compact)
 *   radial — small SVG arc gauge (good for cards)
 *
 * Tier coloring: high(≥0.7) cyan, mid(≥0.4) violet, low(<0.4) muted.
 * Amber/red are NOT used — they are reserved for warnings/errors only.
 * ──────────────────────────────────────────────────────────────────── */

export function ConfidenceIndicator({
  confidence,
  variant = "bar",
  showLabel = true,
  className,
  size = "sm",
}: {
  confidence: number | null;
  variant?: "bar" | "radial";
  showLabel?: boolean;
  className?: string;
  size?: "sm" | "md";
}) {
  if (confidence === null) return null;

  const tier = confidenceTier(confidence);
  const tierColors = {
    high: "bg-confidence-high",
    mid: "bg-secondary",
    low: "bg-muted-foreground",
    none: "bg-muted",
  }[tier];

  if (variant === "radial") {
    return (
      <RadialGauge
        confidence={confidence}
        tier={tier}
        showLabel={showLabel}
        className={className}
        size={size}
      />
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className={cn("confidence-track", size === "md" ? "h-2" : "h-1.5")}>
        <div
          className={cn("confidence-fill", tierColors)}
          style={{ width: `${confidence * 100}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-mono tabular-nums text-muted-foreground whitespace-nowrap">
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}

function RadialGauge({
  confidence,
  tier,
  showLabel,
  className,
  size,
}: {
  confidence: number;
  tier: "high" | "mid" | "low" | "none";
  showLabel: boolean;
  className?: string;
  size: "sm" | "md";
}) {
  const dim = size === "md" ? 48 : 36;
  const strokeWidth = size === "md" ? 4 : 3;
  const r = (dim - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const arc = circumference * 0.75; // 270 degrees
  const fill = arc * confidence;
  const offset = arc - fill;

  const tierColor = {
    high: PALETTE.confidence.high,
    mid: PALETTE.secondary,
    low: PALETTE.mutedForeground,
    none: PALETTE.muted,
  }[tier];

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)}>
      <svg width={dim} height={dim} viewBox={`0 0 ${dim} ${dim}`}>
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={r}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={strokeWidth}
          strokeDasharray={`${arc} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(135, ${dim / 2}, ${dim / 2})`}
        />
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={r}
          fill="none"
          stroke={tierColor}
          strokeWidth={strokeWidth}
          strokeDasharray={`${fill} ${circumference}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(135, ${dim / 2}, ${dim / 2})`}
          className="transition-all duration-500 ease-out"
        />
      </svg>
      {showLabel && (
        <span className="absolute text-[9px] font-mono tabular-nums text-muted-foreground">
          {(confidence * 100).toFixed(0)}
        </span>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────
 * MetricCard
 *
 * Consistent card for a single numeric/string metric with:
 *   - Label (muted)
 *   - Value + unit (mono font, prominent)
 *   - Optional ConfidenceIndicator
 *   - Optional left-border accent color
 *   - Optional sparkline (tiny SVG polyline from an array of numbers)
 *   - Optional range bar showing where value sits between min–max
 * ──────────────────────────────────────────────────────────────────── */

export function MetricCard({
  label,
  value,
  unit,
  confidence,
  source,
  accent,
  sparkline,
  rangeMin,
  rangeMax,
  className,
}: {
  label: string;
  value: number | string | null;
  unit?: string | null;
  confidence?: number | null;
  source?: Source;
  accent?: "primary" | "secondary" | "destructive" | "warning";
  sparkline?: number[];
  rangeMin?: number;
  rangeMax?: number;
  className?: string;
}) {
  const accentBorder = {
    primary: "border-l-primary",
    secondary: "border-l-secondary",
    destructive: "border-l-destructive",
    warning: "border-l-warning",
  }[accent ?? "primary"];

  return (
    <div
      className={cn(
        "rounded-lg border border-l-[3px] bg-card p-4 space-y-2 transition-all duration-200",
        accentBorder,
        "hover:shadow-glow"
      )}
    >
      <div className="flex items-start justify-between">
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
          {label}
        </span>
        {source && <SourceChip source={source} />}
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-display font-semibold tracking-tight">
          {value === null ? (
            <span className="text-muted-foreground text-lg">—</span>
          ) : typeof value === "number" ? (
            value.toLocaleString(undefined, { maximumFractionDigits: 4 })
          ) : (
            value
          )}
        </span>
        {unit && (
          <span className="text-xs text-muted-foreground font-mono">{unit}</span>
        )}
      </div>

      {(confidence !== undefined || sparkline) && (
        <div className="flex items-center gap-3 pt-1">
          {confidence !== undefined && (
            <ConfidenceIndicator confidence={confidence} size="sm" />
          )}
          {sparkline && sparkline.length > 1 && (
            <MiniSparkline data={sparkline} className="flex-1" />
          )}
        </div>
      )}

      {rangeMin !== undefined && rangeMax !== undefined && value !== null && typeof value === "number" && (
        <div className="pt-1">
          <RangeBar value={value} min={rangeMin} max={rangeMax} />
        </div>
      )}
    </div>
  );
}

/* ── SourceChip ─────────────────────────────────────────────────────── */

function SourceChip({ source }: { source: Source }) {
  const config: Record<Source, { label: string; color: string }> = {
    metadata:      { label: "metadata", color: "bg-primary/10 text-primary" },
    user_supplied: { label: "user", color: "bg-secondary/10 text-secondary" },
    measured:      { label: "measured", color: "bg-confidence-high/10 text-confidence-high" },
    estimated:     { label: "estimated", color: "bg-secondary/10 text-secondary" },
    hypothesis:    { label: "hypothesis", color: "bg-muted-foreground/10 text-muted-foreground" },
    unknown:       { label: "unknown", color: "bg-muted text-muted-foreground" },
  };
  const c = config[source] ?? config.unknown;

  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium", c.color)}>
      {c.label}
    </span>
  );
}

/* ── MiniSparkline ──────────────────────────────────────────────────── */

function MiniSparkline({
  data,
  className,
}: {
  data: number[];
  className?: string;
}) {
  const w = 80;
  const h = 20;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("h-5 flex-shrink-0", className)} preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke="hsl(var(--primary))"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ── RangeBar ───────────────────────────────────────────────────────── */

function RangeBar({
  value,
  min,
  max,
}: {
  value: number;
  min: number;
  max: number;
}) {
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));

  return (
    <div className="relative h-1 w-full rounded-full bg-muted">
      <div
        className="absolute inset-y-0 left-0 rounded-full bg-primary transition-all duration-500 ease-out"
        style={{ width: `${pct}%` }}
      />
      <div
        className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-primary shadow-glow"
        style={{ left: `calc(${pct}% - 4px)` }}
      />
    </div>
  );
}
