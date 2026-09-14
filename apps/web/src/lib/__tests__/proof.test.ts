import { describe, it, expect } from "vitest";
import { formatFrequency, summarizeEstimate } from "@/lib/utils";

describe("formatFrequency", () => {
  it("formats Hz/kHz/MHz/GHz bands", () => {
    expect(formatFrequency(40)).toBe("40 Hz");
    expect(formatFrequency(40_000)).toBe("40.00 kHz");
    expect(formatFrequency(1_250_000)).toBe("1.25 MHz");
    expect(formatFrequency(1_250_000_000)).toBe("1.25 GHz");
  });
});

describe("summarizeEstimate", () => {
  it("renders evidence lines and spectrum peak sharpness", () => {
    const payload = {
      evidence: ["dominant tone at 4x symbol rate"],
      order_4: { freqs: [0, 0.25], power: [0.1, 1], peakiness: 0.85 },
      warnings: ["short capture"],
    };
    const summary = summarizeEstimate(payload);
    expect(summary).toContain("dominant tone at 4x symbol rate");
    expect(summary).toContain("85.0%");
    expect(summary).not.toContain("warnings:");
  });

  it("returns empty string for null/empty payloads", () => {
    expect(summarizeEstimate(null)).toBe("");
    expect(summarizeEstimate(undefined)).toBe("");
    expect(summarizeEstimate({})).toBe("");
    expect(summarizeEstimate("garbage" as unknown as Record<string, unknown>)).toBe("");
  });
});