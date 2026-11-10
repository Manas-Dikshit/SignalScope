import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SimilarSignalsPanel } from "@/components/SimilarSignalsPanel";
import { projectsApi } from "@/lib/api";
import type { SimilarSignals } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  projectsApi: {
    similar: vi.fn(),
  },
}));

const mockedSimilar = vi.mocked(projectsApi.similar);

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SimilarSignalsPanel projectId="project-1" />
    </QueryClientProvider>
  );
}

const RARE_RESULT: SimilarSignals = {
  project_id: "project-1",
  fingerprint: {
    version: "1",
    dimensions: 22,
    features: { spectral_flatness: 0.2 },
    created_at: "2026-11-10T00:00:00",
  },
  neighbors: [
    {
      project_id: "project-2",
      project_name: "Known QPSK burst",
      recording_filename: "known.wav",
      modulation: "QPSK",
      symbol_rate_hz: 125000,
      distance: 0.81,
      similarity: 0.19,
    },
  ],
  nearest_distance: 0.81,
  threshold: 0.35,
  rare_signal: true,
  method: "Cosine distance over stored fingerprints. Not an identification.",
  evidence: [],
};

beforeEach(() => {
  mockedSimilar.mockReset();
});

describe("SimilarSignalsPanel", () => {
  it("flags a rare-signal candidate and lists neighbours", async () => {
    mockedSimilar.mockResolvedValue(RARE_RESULT);
    renderPanel();

    expect(await screen.findByText("Known QPSK burst")).toBeTruthy();
    expect(screen.getAllByText(/rare-signal candidate/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/distance 0\.810/)).toBeTruthy();
    expect(screen.getByText(/not a conclusion/i)).toBeTruthy();
    expect(screen.getByText("estimated")).toBeTruthy();
  });

  it("does not claim rarity when the gallery is too small", async () => {
    mockedSimilar.mockResolvedValue({
      ...RARE_RESULT,
      neighbors: [],
      nearest_distance: null,
      rare_signal: null,
    });
    renderPanel();

    expect(await screen.findByText("Gallery too small")).toBeTruthy();
    expect(
      screen.getByText(/Analyse more recordings to build the gallery/i)
    ).toBeTruthy();
  });

  it("explains a missing fingerprint instead of failing", async () => {
    mockedSimilar.mockRejectedValue(
      new Error("No fingerprint for this project yet. Run parameter estimation first.")
    );
    renderPanel();

    expect(
      await screen.findByText(/gallery fills in as soon as parameter estimation runs/i)
    ).toBeTruthy();
  });
});
