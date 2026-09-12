/**
 * Design tokens — single source of truth for colors, spacing, motion,
 * and chart palette. Consumed by PlotlyChart, ConfidenceIndicator,
 * MetricCard, and any component needing raw hex/values outside Tailwind.
 */

export const PALETTE = {
  background: "#0B0F14",
  card: "#111827",
  border: "#1e293b",
  muted: "#475569",

  primary: "#22d3ee",
  primaryDim: "#0e7490",
  secondary: "#8b5cf6",
  secondaryDim: "#6d28d9",

  destructive: "#ef4444",
  warning: "#f59e0b",
  foreground: "#f0f9ff",
  mutedForeground: "#64748b",

  confidence: {
    high: "#10b981",
    mid: "#f59e0b",
    low: "#ef4444",
  },
} as const;

export const CHART_TRACE_COLORS = {
  primary: PALETTE.primary,
  secondary: PALETTE.secondary,
  accent: "#f59e0b",
  success: PALETTE.confidence.high,
  waveformI: PALETTE.primary,
  waveformQ: PALETTE.secondary,
  scatter: PALETTE.primary,
  constellation: PALETTE.confidence.high,
  psd: PALETTE.primary,
} as const;

export const CHART_WATERFALL_COLORSCALE: [number, string][] = [
  [0, "#0B0F14"],
  [0.15, "#164e63"],
  [0.4, "#0e7490"],
  [0.65, "#22d3ee"],
  [0.85, "#a5f3fc"],
  [1.0, "#ecfeff"],
];

export const MOTION = {
  durationFast: 150,
  durationNormal: 200,
  durationSlow: 300,
  easeOut: "cubic-bezier(0.16, 1, 0.3, 1)",
} as const;

export const SPACING = {
  card: "p-6",
  cardCompact: "p-4",
  section: "space-y-6",
  gridGap: "gap-4",
} as const;

/**
 * Elevation scale — three tiers of depth shadow on dark surfaces.
 * Consumed via Tailwind `shadow-elevation-{1|2|3}` (CSS vars).
 * e3 reserved for floating panels (modals, login card on hero).
 */
export const ELEVATION = {
  e1: "0 1px 2px hsl(217 40% 3% / 0.4), 0 1px 3px hsl(217 40% 3% / 0.25)",
  e2: "0 2px 6px hsl(217 40% 3% / 0.35), 0 10px 24px hsl(217 40% 3% / 0.28)",
  e3: "0 4px 12px hsl(217 40% 3% / 0.45), 0 28px 56px -12px hsl(217 40% 3% / 0.6)",
} as const;

/**
 * Procedural waveform-art colors — layered signal traces, glow, and the
 * blueprint grid on the analysis workspace. Keep cyan/violet only; amber/red
 * stay semantic.
 */
export const WAVEFORM_ART = {
  trace: PALETTE.primary,
  traceSoft: "#a5f3fc",
  traceViolet: PALETTE.secondary,
  glow: "rgba(34, 211, 238, 0.18)",
  glowViolet: "rgba(139, 92, 246, 0.16)",
  grid: "hsla(217, 18%, 62%, 0.08)",
  gridMajor: "hsla(217, 18%, 62%, 0.16)",
  corner: "hsla(187, 92%, 50%, 0.35)",
} as const;

export function confidenceColor(confidence: number | null): string {
  if (confidence === null) return PALETTE.mutedForeground;
  if (confidence >= 0.7) return PALETTE.confidence.high;
  if (confidence >= 0.4) return PALETTE.confidence.mid;
  return PALETTE.confidence.low;
}

export function confidenceTier(confidence: number | null): "high" | "mid" | "low" | "none" {
  if (confidence === null) return "none";
  if (confidence >= 0.7) return "high";
  if (confidence >= 0.4) return "mid";
  return "low";
}
