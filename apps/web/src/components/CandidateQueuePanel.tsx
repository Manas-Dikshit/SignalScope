"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { candidatesApi } from "@/lib/api";
import type { CandidatePriority } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChevronDown, Star } from "lucide-react";

const SUBSCORES: { key: "novelty" | "repeatability" | "plausibility" | "feasibility"; label: string }[] = [
  { key: "novelty", label: "Novelty" },
  { key: "repeatability", label: "Repeat" },
  { key: "plausibility", label: "Plausible" },
  { key: "feasibility", label: "Follow-up" },
];

function SubScore({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const unknown = Math.round(value * 100) === 50; // neutral 0.5 marker
  return (
    <div className="flex items-center gap-1.5" title={`${label}: ${pct}%`}>
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <div className="h-1.5 w-10 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${unknown ? "bg-muted-foreground/40" : "bg-primary"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function CandidateRow({ candidate, rank }: { candidate: CandidatePriority; rank: number }) {
  const [expanded, setExpanded] = React.useState(false);
  return (
    <div className="space-y-1.5 px-4 py-3 transition-colors duration-150 hover:bg-muted/40">
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground font-mono w-5 text-right shrink-0">
          {rank}.
        </span>
        <Link
          href={`/projects/${candidate.project_id}`}
          className="min-w-0 flex-1 text-sm font-medium font-mono truncate hover:text-primary hover:underline"
        >
          {candidate.project_name}
        </Link>
        {candidate.rare_signal && (
          <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
            <Star className="h-3 w-3" /> rare
          </span>
        )}
        <span className="text-xs font-mono text-muted-foreground tabular-nums">
          {candidate.composite.toFixed(0)}%
        </span>
        {candidate.reasons.length > 0 && (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="shrink-0 p-1 text-muted-foreground hover:text-foreground transition-colors duration-150"
            aria-label={expanded ? "Collapse reasoning" : "Expand reasoning"}
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-150 ${expanded ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>
      <div className="ml-8 flex flex-wrap gap-x-4 gap-y-1">
        {SUBSCORES.map(({ key, label }) => (
          <SubScore key={key} label={label} value={candidate[key]} />
        ))}
      </div>
      {expanded && (
        <ul className="ml-8 space-y-0.5 text-xs text-muted-foreground animate-fade-in">
          {candidate.reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CandidateQueuePanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["candidates"],
    queryFn: candidatesApi.prioritized,
  });

  return (
    <Card className="reveal reveal-delay-2 border-primary/20">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base font-display font-semibold">
          Candidate queue
        </CardTitle>
        <span className="text-xs text-muted-foreground">
          ranked by novelty · repeatability · plausibility · follow-up
        </span>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-24 rounded-lg border bg-card shimmer" />
        ) : error ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Candidate ranking is unavailable right now.
          </div>
        ) : data && data.candidates.length > 0 ? (
          <div className="divide-y divide-border rounded-lg border">
            {data.candidates.map((candidate, i) => (
              <CandidateRow key={candidate.project_id} candidate={candidate} rank={i + 1} />
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No analysed candidates yet. Run parameter estimation on a project to
            queue it here.
          </div>
        )}
        {data && data.candidates.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            A triage heuristic over stored DSP evidence — never an identification.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
