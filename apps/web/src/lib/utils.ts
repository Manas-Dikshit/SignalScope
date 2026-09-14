import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export type FileFormat = "wav" | "raw_iq" | "sigmf";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function inferFormatFromFilename(name: string): FileFormat {
  const lower = name.toLowerCase();
  if (lower.endsWith(".sigmf-meta") || lower.endsWith(".sigmf-data") || lower.endsWith(".json")) {
    return "sigmf";
  }
  if (lower.endsWith(".wav")) return "wav";
  return "raw_iq";
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(1)} ms`;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}m ${s}s`;
}

export function formatFrequency(hz: number): string {
  if (hz >= 1e9) return `${(hz / 1e9).toFixed(2)} GHz`;
  if (hz >= 1e6) return `${(hz / 1e6).toFixed(2)} MHz`;
  if (hz >= 1e3) return `${(hz / 1e3).toFixed(2)} kHz`;
  return `${hz.toFixed(0)} Hz`;
}

export function downsample(arr: number[], maxPoints: number): number[] {
  if (arr.length <= maxPoints) return arr;
  const step = arr.length / maxPoints;
  const result: number[] = [];
  for (let i = 0; i < maxPoints; i++) {
    result.push(arr[Math.floor(i * step)]);
  }
  return result;
}

export function downsamplePair(
  x: number[],
  y: number[],
  maxPoints: number
): { x: number[]; y: number[] } {
  if (x.length <= maxPoints) return { x, y };
  const step = x.length / maxPoints;
  const rx: number[] = [];
  const ry: number[] = [];
  for (let i = 0; i < maxPoints; i++) {
    const idx = Math.floor(i * step);
    rx.push(x[idx]);
    ry.push(y[idx]);
  }
  return { x: rx, y: ry };
}

/**
 * SVG polyline points for a real sample array, normalized to the thumb box
 * with a small margin around the vertical range.
 */
export function waveformPoints(samples: number[], width = 96, height = 40): string {
  if (samples.length === 0) return "";
  const pts = downsample(samples, Math.max(8, Math.floor(width / 2)));
  let min = Infinity;
  let max = -Infinity;
  for (const v of pts) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const span = max - min || 1;
  const mid = height / 2;
  return pts
    .map((v, i) => {
      const x = (i / (pts.length - 1)) * width;
      const y = mid - ((v - (min + span / 2)) / span) * (height - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/* ── Proof payload helpers ─────────────────────────────────────────── */

/**
 * Any payload a backend estimate can attach as drill-down proof: M-th power
 * spectra, symbol-clock spectra, run-length histograms, or free-form dicts.
 */
export type ProofPayload = Record<string, unknown>;

/** Flatten a proof payload's spectrum sections into a readable summary line. */
export function summarizeEstimate(payload: ProofPayload | null | undefined): string {
  if (!payload || typeof payload !== "object") return "";
  const lines: string[] = [];
  const evidence = Array.isArray(payload.evidence) ? (payload.evidence as unknown[]) : [];
  for (const e of evidence) {
    if (typeof e === "string") lines.push(e);
  }
  for (const [key, value] of Object.entries(payload)) {
    if (key === "evidence" || key === "warnings" || key === "alternatives") continue;
    if (value && typeof value === "object" && "peakiness" in (value as object)) {
      const p = value as { peakiness: number };
      lines.push(
        `${key.replaceAll("_", " ")} spectrum peak sharpness ${(p.peakiness * 100).toFixed(1)}%`
      );
    } else if (typeof value === "number") {
      lines.push(`${key.replaceAll("_", " ")}: ${value}`);
    } else if (typeof value === "string") {
      lines.push(`${key.replaceAll("_", " ")}: ${value}`);
    }
  }
  return lines.join(". ") ? `${lines.join(". ")}.` : "";
}

/** Trigger a client-side download of a payload as JSON — used by ProofPanel. */
export function downloadJSON(payload: ProofPayload, filename: string): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
