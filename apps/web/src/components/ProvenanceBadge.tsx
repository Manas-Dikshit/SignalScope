import * as React from "react";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

const SOURCE_CONFIG: Record<
  Source,
  { icon: string; label: string; color: string }
> = {
  metadata: { icon: "📄", label: "metadata (exact)", color: "text-blue-400" },
  user_supplied: {
    icon: "✍️",
    label: "user supplied (exact)",
    color: "text-purple-400",
  },
  measured: {
    icon: "📏",
    label: "measured (exact)",
    color: "text-green-400",
  },
  estimated: { icon: "🧮", label: "estimated", color: "text-amber-400" },
  hypothesis: { icon: "🔎", label: "hypothesis", color: "text-orange-400" },
  unknown: { icon: "❓", label: "unknown", color: "text-gray-400" },
};

function confidenceColor(confidence: number | null | undefined): string {
  if (confidence == null) return "";
  if (confidence >= 0.7) return "text-green-400";
  if (confidence >= 0.4) return "text-yellow-400";
  return "text-red-400";
}

function confidenceBg(confidence: number | null | undefined): string {
  if (confidence == null) return "";
  if (confidence >= 0.7) return "bg-green-500/10 border-green-500/30";
  if (confidence >= 0.4) return "bg-yellow-500/10 border-yellow-500/30";
  return "bg-red-500/10 border-red-500/30";
}

export function SourceBadge({ source }: { source: Source }) {
  const config = SOURCE_CONFIG[source];
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs", config.color)}>
      <span>{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
}

export function ConfidenceDot({ confidence }: { confidence: number | null }) {
  if (confidence === null) return null;
  let color = "bg-red-500";
  if (confidence >= 0.7) color = "bg-green-500";
  else if (confidence >= 0.4) color = "bg-yellow-500";
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <span className={cn("h-2 w-2 rounded-full", color)} />
      <span className={confidenceColor(confidence)}>
        {confidence.toFixed(2)}
      </span>
    </span>
  );
}

export function ProvenanceBadge({
  source,
  confidence,
  className,
}: {
  source: Source;
  confidence?: number | null;
  className?: string;
}) {
  const config = SOURCE_CONFIG[source];
  const isExact = source === "metadata" || source === "user_supplied" || source === "measured";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        isExact
          ? "bg-blue-500/10 border-blue-500/30"
          : confidenceBg(confidence),
        config.color,
        className
      )}
    >
      <span>{config.icon}</span>
      <span>{config.label}</span>
      {confidence !== null && confidence !== undefined && (
        <ConfidenceDot confidence={confidence} />
      )}
    </span>
  );
}

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
      ? "unknown"
      : typeof value === "number"
      ? value.toLocaleString(undefined, { maximumFractionDigits: 4 })
      : String(value);

  const unitStr = unit ? ` ${unit}` : "";

  return (
    <div className="rounded-lg border bg-card p-4 space-y-2">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold">
        {formattedValue}
        {unitStr}
      </div>
      <ProvenanceBadge source={source} confidence={confidence} />

      {warnings && warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="text-xs text-yellow-400">
              ⚠️ {w}
            </div>
          ))}
        </div>
      )}

      {evidence && evidence.length > 0 && (
        <div>
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showEvidence ? "▾ Hide" : "▸ Show"} evidence ({evidence.length})
          </button>
          {showEvidence && (
            <ul className="mt-1 space-y-0.5 pl-2 text-xs text-muted-foreground">
              {evidence.map((e, i) => (
                <li key={i}>• {e}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {alternatives && alternatives.length > 0 && (
        <div>
          <button
            onClick={() => setShowAlternatives(!showAlternatives)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showAlternatives ? "▾ Hide" : "▸ Show"} alternatives (
            {alternatives.length})
          </button>
          {showAlternatives && (
            <div className="mt-1 space-y-2 pl-2">
              {alternatives.map((alt, i) => (
                <div key={i} className="text-xs">
                  <span className="font-medium">
                    {typeof alt.value === "number"
                      ? alt.value.toLocaleString(undefined, {
                          maximumFractionDigits: 4,
                        })
                      : String(alt.value)}
                  </span>
                  {alt.confidence !== null && alt.confidence !== undefined && (
                    <span className="ml-1">
                      — <ConfidenceDot confidence={alt.confidence} />
                    </span>
                  )}
                  {alt.evidence && alt.evidence.length > 0 && (
                    <ul className="mt-0.5 text-muted-foreground">
                      {alt.evidence.map((ev, j) => (
                        <li key={j}>  {ev}</li>
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
