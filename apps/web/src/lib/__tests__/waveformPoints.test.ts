import { describe, it, expect } from "vitest";
import { waveformPoints } from "@/lib/utils";

describe("waveformPoints — data-driven thumbnail geometry", () => {
  it("produces distinct paths for distinct signals", () => {
    const tone = Array.from({ length: 800 }, (_, i) => Math.sin(i * 0.05));
    const sweep = Array.from({ length: 800 }, (_, i) =>
      Math.sin(i * 0.015 * Math.sin(i * 0.001))
    );
    expect(waveformPoints(tone)).not.toBe(waveformPoints(sweep));
  });

  it("flattens a statically-varying amplitude profile, not a constant line", () => {
    const ramp = Array.from({ length: 400 }, (_, i) => i);
    const points = waveformPoints(ramp, 96, 40);
    const ys = points.split(" ").map((p) => Number(p.split(",")[1]));
    expect(Math.max(...ys)).toBeGreaterThan(Math.min(...ys));
  });

  it("returns empty for empty samples", () => {
    expect(waveformPoints([])).toBe("");
  });
});