"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface BurstSegment {
  startSample: number;
  endSample: number;
  startTimeS: number;
  endTimeS: number;
  peakPowerDb: number;
  meanPowerDb: number;
  confidence?: number;
}

/**
 * Gantt-style strip of bursts across the recording's time axis.
 * Empty when no bursts were detected.
 */
export function BurstTimeline({
  bursts,
  durationS,
  className,
}: {
  bursts: BurstSegment[];
  durationS?: number | null;
  className?: string;
}) {
  const total = durationS && durationS > 0 ? durationS
    : bursts.length > 0
      ? Math.max(...bursts.map((b) => b.endTimeS))
      : null;

  if (!total || total <= 0) {
    return (
      <div className={cn("rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground", className)}>
        No bursts detected in this window.
      </div>
    );
  }

  const relPower = bursts.map((b) => {
    const min = Math.min(...bursts.map((x) => x.peakPowerDb));
    const max = Math.max(...bursts.map((x) => x.peakPowerDb));
    const range = max - min || 1;
    return ((b.peakPowerDb - min) / range) * 0.7 + 0.3;
  });

  return (
    <div className={cn("space-y-2", className)}>
      <div className="relative h-10 w-full rounded-md border bg-card overflow-hidden">
        {/* time gridlines */}
        {Array.from({ length: 8 }, (_, i) => (
          <div
            key={i}
            className="absolute top-0 bottom-0 w-px bg-muted/40"
            style={{ left: `${(i / 7) * 100}%` }}
          />
        ))}
        {/* burst segments */}
        {bursts.map((b, i) => {
          const left = (b.startTimeS / total) * 100;
          const width = Math.max(0.5, ((b.endTimeS - b.startTimeS) / total) * 100);
          return (
            <div
              key={i}
              className="absolute top-1/2 -translate-y-1/2 rounded-sm bg-primary/60 hover:bg-primary/90 transition-colors duration-150 cursor-help"
              style={{ left: `${left}%`, width: `${width}%`, height: "60%" }}
              title={`Burst ${i + 1}: ${b.startTimeS.toFixed(3)}s–${b.endTimeS.toFixed(3)}s · ${b.peakPowerDb.toFixed(1)} dB`}
            />
          );
        })}
      </div>
      <div className="flex items-center justify-between text-[10px] font-mono text-muted-foreground">
        <span>0s</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-sm bg-primary/60" />
          {bursts.length} bursts
        </span>
        <span>{total.toFixed(2)}s</span>
      </div>
    </div>
  );
}