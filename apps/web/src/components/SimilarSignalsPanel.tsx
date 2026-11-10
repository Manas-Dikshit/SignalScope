"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Fingerprint, Loader2, Radar } from "lucide-react";
import { projectsApi } from "@/lib/api";
import type { SimilarSignals } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { formatFrequency } from "@/lib/utils";
import { cn } from "@/lib/utils";

/* ──────────────────────────────────────────────────────────────────────
 * SimilarSignalsPanel
 *
 * Rare-signal gallery. Shows nearest spectral neighbours from the analyst's own
 * fingerprinted projects. Distances are computed by the backend from stored,
 * versioned fingerprints; the panel never re-reads recordings and never claims
 * an identification. The AI brief explains novelty separately, as a hypothesis.
 * ──────────────────────────────────────────────────────────────────── */

export function SimilarSignalsPanel({ projectId }: { projectId: string }) {
  const query = useQuery<SimilarSignals>({
    queryKey: ["similar", projectId],
    queryFn: () => projectsApi.similar(projectId),
    retry: false,
  });

  const data = query.data;
  const errorMessage =
    query.isError && query.error instanceof Error ? query.error.message : null;

  return (
    <Card className="reveal reveal-delay-3">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-display text-base font-semibold">
          <Radar className="h-4 w-4 text-muted-foreground" />
          Rare-Signal Gallery
        </CardTitle>
        <p className="mt-1 text-xs text-muted-foreground">
          Nearest spectral neighbours from your own fingerprinted projects. A
          short distance means similar evidence, never an identification.
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {query.isLoading && (
          <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Comparing spectral fingerprints...
          </div>
        )}

        {errorMessage && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <span className="text-muted-foreground">
              {errorMessage.toLowerCase().includes("fingerprint")
                ? `${errorMessage} The gallery fills in as soon as parameter estimation runs.`
                : errorMessage}
            </span>
          </div>
        )}

        {data && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <ProvenanceBadge source="estimated" />
              <span className="text-[11px] font-mono text-muted-foreground">
                fingerprint v{data.fingerprint.version} ·{" "}
                {data.fingerprint.dimensions} dims
              </span>
              <RarityChip rare={data.rare_signal} />
            </div>

            {data.rare_signal === true && (
              <p className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-xs text-muted-foreground">
                No gallery recording is closer than the similarity threshold.
                This is a rare-signal <span className="font-medium text-foreground">candidate</span> —
                treat it as a lead to investigate, not a conclusion.
              </p>
            )}

            {data.neighbors.length === 0 ? (
              <div className="rounded-lg border bg-card/50 p-4 text-sm text-muted-foreground">
                {data.rare_signal === null
                  ? "No comparable gallery neighbours yet. Analyse more recordings to build the gallery before judging novelty."
                  : "No other project is close enough to list yet."}
              </div>
            ) : (
              <ul className="space-y-2">
                {data.neighbors.map((neighbor) => {
                  const beyondThreshold = neighbor.distance > data.threshold;
                  const width = Math.min(
                    100,
                    (neighbor.distance / Math.max(data.threshold, 0.001)) * 100
                  );
                  return (
                    <li
                      key={neighbor.project_id}
                      className="rounded-lg border bg-card/50 p-3 space-y-2"
                    >
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">
                            {neighbor.project_name}
                          </div>
                          <div className="truncate text-[11px] font-mono text-muted-foreground">
                            {neighbor.recording_filename}
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                          {neighbor.modulation && (
                            <span className="rounded-full border px-2 py-0.5 font-mono">
                              {neighbor.modulation}
                            </span>
                          )}
                          {neighbor.symbol_rate_hz != null && (
                            <span className="font-mono">
                              {formatFrequency(neighbor.symbol_rate_hz)} sym/s
                            </span>
                          )}
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 font-mono",
                              beyondThreshold
                                ? "bg-warning/10 text-warning"
                                : "bg-confidence-high/10 text-confidence-high"
                            )}
                          >
                            distance {neighbor.distance.toFixed(3)}
                          </span>
                        </div>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            beyondThreshold ? "bg-warning" : "bg-confidence-high"
                          )}
                          style={{ width: `${width}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            <div className="space-y-1 text-[11px] text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <Fingerprint className="h-3 w-3" />
                Rare-candidate threshold: {data.threshold.toFixed(2)} cosine
                distance
              </div>
              <p>{data.method}</p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function RarityChip({ rare }: { rare: boolean | null }) {
  const label =
    rare === true
      ? "Rare-signal candidate"
      : rare === false
        ? "Matches gallery"
        : "Gallery too small";
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[10px] font-medium",
        rare === true
          ? "bg-warning/10 text-warning"
          : rare === false
            ? "bg-confidence-high/10 text-confidence-high"
            : "bg-muted text-muted-foreground"
      )}
    >
      {label}
    </span>
  );
}
