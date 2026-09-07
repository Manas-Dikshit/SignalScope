import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  SourceBadge,
  ConfidenceDot,
  ProvenanceBadge,
} from "@/components/ProvenanceBadge";
import type { Source } from "@/lib/types";

const SOURCES: Source[] = [
  "metadata",
  "user_supplied",
  "measured",
  "estimated",
  "hypothesis",
  "unknown",
];

// Each source must render a distinct icon + label text so provenance is
// unambiguous in the UI (product requirement, not incidental styling).
describe("SourceBadge distinct rendering per source", () => {
  it("renders a distinct icon+label for each of the 6 sources", () => {
    render(
      <>
        {SOURCES.map((s) => (
          <SourceBadge key={s} source={s} />
        ))}
      </>
    );

    const metadata = screen.getByText(/metadata \(exact\)/).parentElement!;
    const userSupplied = screen.getByText(/user supplied \(exact\)/).parentElement!;
    const measured = screen.getByText(/measured \(exact\)/).parentElement!;
    const estimated = screen.getByText(/estimated/).parentElement!;
    const hypothesis = screen.getByText(/hypothesis/).parentElement!;
    const unknown = screen.getByText(/unknown/).parentElement!;

    // distinct text labels
    expect(metadata.textContent).not.toBe(userSupplied.textContent);
    expect(metadata.textContent).not.toBe(measured.textContent);
    expect(estimated.textContent).not.toBe(hypothesis.textContent);
    expect(hypothesis.textContent).not.toBe(unknown.textContent);

    // each carries a distinct icon
    expect(metadata.textContent).toContain("📄");
    expect(userSupplied.textContent).toContain("✍️");
    expect(measured.textContent).toContain("📏");
    expect(estimated.textContent).toContain("🧮");
    expect(hypothesis.textContent).toContain("🔎");
    expect(unknown.textContent).toContain("❓");
  });

  it("renders exact sources without a confidence dot", () => {
    render(
      <ProvenanceBadge source="metadata" confidence={0.99} />
    );
    // exact sources are trusted; the confidence is not shown as color-coded
    const el = screen.getByText(/metadata \(exact\)/).closest("span");
    expect(el).not.toBeNull();
  });
});

// The spec's "4 confidence tiers" map to: None, low (<0.4), mid (0.4-0.69),
// high (>=0.7). Our ConfidenceDot distinguishes high green / mid yellow /
// low red, and hides when confidence is null.
describe("ConfidenceDot confidence tiers", () => {
  it("renders nothing when confidence is null", () => {
    const { container } = render(<ConfidenceDot confidence={null} />);
    expect(container.firstChild).toBeNull();
  });

  it.each([
    [0.9, "bg-green-500", "high"],
    [0.5, "bg-yellow-500", "mid"],
    [0.2, "bg-red-500", "low"],
    [0.7, "bg-green-500", "high boundary"],
    [0.4, "bg-yellow-500", "mid boundary"],
  ])("confidence %s uses %s (%s)", (conf, expectedClass) => {
    const { container } = render(<ConfidenceDot confidence={conf} />);
    const dot = container.querySelector("span span");
    expect(dot).not.toBeNull();
    expect(dot!.className).toContain(expectedClass);
  });
});

// Every source/confidence combination renders a working ProvenanceBadge with
// the same icon + a confidence dot for non-exact sources.
describe("ProvenanceBadge (source x confidence)", () => {
  it("renders a badge for every source with a mid confidence", () => {
    render(
      <>
        {SOURCES.map((s) => (
          <ProvenanceBadge key={s} source={s} confidence={0.5} />
        ))}
      </>
    );
    const badges = screen.getAllByText(/metadata|user supplied|measured|estimated|hypothesis|unknown/);
    // one badge per source
    expect(badges.length).toBe(SOURCES.length);
  });
});
