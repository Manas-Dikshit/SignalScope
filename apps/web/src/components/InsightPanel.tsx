"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { insightsApi, jobsApi } from "@/lib/api";
import type { AnalysisInsight } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { AlertTriangle, Bot, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

/* ──────────────────────────────────────────────────────────────────────
 * InsightPanel
 *
 * Shows the latest Gemma 4 analyst brief for a project. The AI output is
 * always labelled `ai_hypothesis`: it is a cited hypothesis over deterministic
 * DSP evidence, never a measured value. Numeric values in the summary are
 * substituted by the backend, not written by the model.
 * ──────────────────────────────────────────────────────────────────── */

export function InsightPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = React.useState<string | null>(null);

  const insightQuery = useQuery<AnalysisInsight>({
    queryKey: ["insight", projectId],
    queryFn: () => insightsApi.latest(projectId),
    retry: false,
  });

  const generateMutation = useMutation({
    mutationFn: () => insightsApi.generate(projectId),
    onSuccess: (job) => setJobId(job.id),
  });

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1500;
    },
  });

  const jobStatus = jobQuery.data?.status;

  React.useEffect(() => {
    if (jobStatus === "completed" || jobStatus === "failed") {
      queryClient.invalidateQueries({ queryKey: ["insight", projectId] });
      setJobId(null);
    }
  }, [jobStatus, projectId, queryClient]);

  const insight = insightQuery.data;
  const payload = insight?.response_json;
  const running = generateMutation.isPending || Boolean(jobId);
  const notGenerated =
    insightQuery.isError && insightQuery.error instanceof Error
      ? insightQuery.error.message
      : null;

  return (
    <Card className="reveal reveal-delay-3">
      <CardHeader>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 font-display text-base font-semibold">
              <Bot className="h-4 w-4 text-muted-foreground" />
              AI Analyst Brief
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Gemma 4 reasoning over the deterministic DSP evidence. Review the
              provenance before acting.
            </p>
          </div>
          <Button
            onClick={() => generateMutation.mutate()}
            disabled={running}
            variant="outline"
            className="shrink-0"
          >
            {running ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            {running ? "Reasoning..." : insight ? "Regenerate Brief" : "Generate AI Brief"}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {generateMutation.isError && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <span className="text-muted-foreground">
              {generateMutation.error instanceof Error
                ? generateMutation.error.message
                : "AI service unavailable."}
            </span>
          </div>
        )}

        {jobId && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {jobQuery.data?.current_stage ?? "queued"} —{" "}
            {Math.round(jobQuery.data?.progress_percent ?? 0)}%
          </div>
        )}

        {!insight && !generateMutation.isError && (
          <div className="py-6 text-center text-sm text-muted-foreground">
            {notGenerated
              ? "No AI brief yet. Generate one after running parameter estimation."
              : "Loading AI brief..."}
          </div>
        )}

        {insight && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <ProvenanceBadge source="ai_hypothesis" />
              <span className="text-[11px] font-mono text-muted-foreground">
                {insight.model_name} · prompt {insight.prompt_version}
              </span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium",
                  insight.status === "completed"
                    ? "bg-confidence-high/10 text-confidence-high"
                    : "bg-warning/10 text-warning"
                )}
              >
                {insight.status}
              </span>
            </div>

            {insight.error_message && (
              <div className="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm text-muted-foreground">
                {insight.error_message}
              </div>
            )}

            {payload?.summary && (
              <p className="text-sm leading-relaxed">{payload.summary}</p>
            )}

            {payload?.hypothesis && (
              <div className="rounded-lg border bg-card/50 p-3 space-y-1">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  AI hypothesis
                </div>
                <div className="font-mono text-sm font-semibold">
                  {payload.hypothesis.label}
                </div>
                {payload.hypothesis.confidence_note && (
                  <div className="text-xs text-muted-foreground">
                    {payload.hypothesis.confidence_note}
                  </div>
                )}
              </div>
            )}

            {payload?.anomalies && payload.anomalies.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Anomalies
                </div>
                <ul className="space-y-1">
                  {payload.anomalies.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                      <span className="text-muted-foreground">{a.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {payload?.recommended_actions && payload.recommended_actions.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Suggested next steps
                </div>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {payload.recommended_actions.map((a, i) => (
                    <li key={i}>
                      <span className="font-mono text-foreground">{a.action}</span>
                      {a.why ? ` — ${a.why}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {payload?.unknowns && payload.unknowns.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Unknowns
                </div>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {payload.unknowns.map((u, i) => (
                    <li key={i}>{u}</li>
                  ))}
                </ul>
              </div>
            )}

            {payload?.limitations && payload.limitations.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Limitations
                </div>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {payload.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            )}

            {payload?.citations && Object.keys(payload.citations).length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Citations
                </div>
                <ul className="space-y-1 text-xs font-mono text-muted-foreground">
                  {Object.entries(payload.citations).map(([key, ref]) => (
                    <li key={key}>
                      <span className="text-foreground">{key}</span> → {ref}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
