"use client";

import * as React from "react";
import { cn, downloadJSON, type ProofPayload } from "@/lib/utils";
import { Eye, X, Download, FileJson2, AlertTriangle } from "lucide-react";

export type { ProofPayload };

/**
 * "View proof" drill-down behind a confidence-bearing estimate.
 *
 * - Trigger is a text-labeled button ("View proof") so the signal is obvious.
 * - Desktop (>375px): expands inline beneath the estimate.
 * - Mobile (≤375px): opens a fixed bottom sheet.
 * - Every section offers "Download JSON" so analysts can keep the raw payload.
 *
 * Renders whatever the backend attached: free-form evidence lines, M-th power /
 * symbol-clock spectra (as mini normalized polyline plots), run-length
 * histograms, and warnings.
 */
export function ProofPanel({
  title,
  payload,
  warnings,
  className,
}: {
  title: string;
  payload: ProofPayload | null | undefined;
  warnings?: string[];
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [sheet, setSheet] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    const mq = window.matchMedia("(max-width: 375px)");
    const update = () => setSheet(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [open]);

  if (!payload || Object.keys(payload).length === 0) return null;

  const sections = buildSections(payload);

  const trigger = (
    <button
      onClick={() => setOpen((v) => !v)}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      aria-expanded={open}
    >
      <Eye className="h-3 w-3" />
      {open ? "Hide proof" : "View proof"}
    </button>
  );

  const body = (
    <div className="space-y-2.5" data-testid="proof-body">
      {sections.length === 0 && (
        <div className="text-xs text-muted-foreground">No human-readable proof attached.</div>
      )}
      {sections.map((s, i) => (
        <div key={i} className="rounded-lg border bg-background/60 p-3 space-y-1.5">
          {s.label && (
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              {s.label}
            </div>
          )}
          {s.kind === "spectrum" && (
            <svg
              viewBox={`0 0 240 56`}
              className="h-14 w-full"
              preserveAspectRatio="none"
              role="img"
              aria-label={`${s.label} spectrum plot`}
            >
              <polyline
                points={pointsFrom(s.y, 240, 56)}
                fill="none"
                stroke="hsl(var(--primary))"
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </svg>
          )}
          {s.kind === "histogram" && (
            <div className="space-y-1">
              {s.y.slice(0, 12).map((v, j) => (
                <div key={j} className="flex items-center gap-2">
                  <span className="w-10 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
                    {s.x[j] ?? j + 1}
                  </span>
                  <div className="h-2 flex-1 rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-secondary"
                      style={{ width: `${Math.min(100, (Number(v) / maxOf(s.y)) * 100)}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 font-mono text-[10px] text-muted-foreground">
                    {Number(v)}
                  </span>
                </div>
              ))}
            </div>
          )}
          {s.kind === "text" && (
            <div className="font-mono text-[11px] leading-relaxed text-muted-foreground break-all">
              {s.text}
            </div>
          )}
        </div>
      ))}
      {warnings && warnings.length > 0 && (
        <div className="space-y-1 rounded-lg border border-warning/30 bg-warning/5 p-3">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-warning">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  if (sheet && open) {
    return (
      <>
        {trigger}
        <div className="fixed inset-x-0 bottom-0 z-50">
          <div className="mx-auto max-h-[70vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border bg-card p-4 shadow-elevation-1 animate-slide-up">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="text-sm font-semibold">{title}</div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => downloadJSON(payload, `${slug(title)}-proof.json`)}
                  className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
                >
                  <Download className="h-3 w-3" />
                  Download JSON
                </button>
                <button
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center rounded-md border p-1 text-muted-foreground hover:text-foreground"
                  aria-label="Close proof"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            {body}
          </div>
        </div>
      </>
    );
  }

  if (!open) return trigger;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2">
        {trigger}
        <button
          onClick={() => downloadJSON(payload, `${slug(title)}-proof.json`)}
          className="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <FileJson2 className="h-3 w-3" />
          Download JSON
        </button>
      </div>
      <div className="animate-fade-in">{body}</div>
    </div>
  );
}

type ProofSection =
  | { label: string; kind: "spectrum"; y: number[] }
  | { label: string; kind: "histogram"; x: number[]; y: number[] }
  | { label: string; kind: "text"; text: string };

function buildSections(payload: ProofPayload): ProofSection[] {
  const sections: ProofSection[] = [];
  const evidence = payload.evidence;
  if (Array.isArray(evidence) && evidence.length > 0) {
    (evidence as unknown[])
      .filter((e) => typeof e === "string")
      .forEach((e) => sections.push({ label: "Evidence", kind: "text", text: e as string }));
  }
  for (const [key, value] of Object.entries(payload)) {
    if (key === "evidence" || key === "warnings" || key === "alternatives") continue;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const o = value as Record<string, unknown>;
      if (Array.isArray(o.power) && (o.power as number[]).length > 0) {
        sections.push({
          label: key.replaceAll("_", " "),
          kind: "spectrum",
          y: o.power as number[],
        });
      } else if (Array.isArray(o.run_lengths) && Array.isArray(o.counts) && (o.counts as unknown[]).length > 0) {
        sections.push({
          label: `${key.replaceAll("_", " ")} (run-length histogram)`,
          kind: "histogram",
          x: o.run_lengths as number[],
          y: o.counts as number[],
        });
      } else {
        sections.push({
          label: key.replaceAll("_", " "),
          kind: "text",
          text: JSON.stringify(value),
        });
      }
    }
  }
  return sections;
}

function maxOf(arr: number[]): number {
  let m = 1;
  for (const v of arr) {
    if (Number.isFinite(v) && v > m) m = v;
  }
  return m;
}

function pointsFrom(y: number[], width: number, height: number): string {
  if (y.length === 0) return "";
  const step = Math.max(1, Math.floor(y.length / width));
  const sample = y.filter((_, i) => i % step === 0);
  if (sample.length < 2) return "";
  let min = Infinity;
  let max = -Infinity;
  for (const v of sample) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const span = max - min || 1;
  return sample
    .map((v, i) => {
      const x = (i / (sample.length - 1)) * width;
      const y2 = height - ((v - min) / span) * (height - 8) - 4;
      return `${x.toFixed(1)},${y2.toFixed(1)}`;
    })
    .join(" ");
}

function slug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}