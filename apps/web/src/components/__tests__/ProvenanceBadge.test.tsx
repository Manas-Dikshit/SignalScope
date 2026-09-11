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

describe("SourceBadge distinct rendering per source", () => {
  it("renders a distinct label for each of the 6 sources", () => {
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

    expect(metadata.textContent).not.toBe(userSupplied.textContent);
    expect(metadata.textContent).not.toBe(measured.textContent);
    expect(estimated.textContent).not.toBe(hypothesis.textContent);
    expect(hypothesis.textContent).not.toBe(unknown.textContent);
  });

  it("renders exact sources without a confidence dot", () => {
    render(<ProvenanceBadge source="metadata" confidence={0.99} />);
    const el = screen.getByText(/metadata \(exact\)/).closest("span");
    expect(el).not.toBeNull();
  });
});

describe("ConfidenceDot confidence tiers", () => {
  it("renders nothing when confidence is null", () => {
    const { container } = render(<ConfidenceDot confidence={null} />);
    expect(container.firstChild).toBeNull();
  });

  it.each([
    [0.9, "bg-confidence-high", "high"],
    [0.5, "bg-secondary", "mid"],
    [0.2, "bg-muted-foreground", "low"],
    [0.7, "bg-confidence-high", "high boundary"],
    [0.4, "bg-secondary", "mid boundary"],
  ])("confidence %s uses %s (%s)", (conf, expectedClass) => {
    const { container } = render(<ConfidenceDot confidence={conf} />);
    const dot = container.querySelector("span span");
    expect(dot).not.toBeNull();
    expect(dot!.className).toContain(expectedClass);
  });
});

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
    expect(badges.length).toBe(SOURCES.length);
  });
});