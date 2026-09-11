"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi, recordingsApi, jobsApi } from "@/lib/api";
import type { Recording, ParameterEstimate, Job, DeepAnalysis, BurstDetection } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { PlotlyChart, CHART_WATERFALL_COLORSCALE } from "@/components/PlotlyChart";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { MetricCard } from "@/components/ConfidenceIndicator";
import { RankedBars } from "@/components/RankedBar";
import { SectionTabs } from "@/components/SectionTabs";
import { BurstTimeline } from "@/components/BurstTimeline";
import { formatBytes, formatDuration, formatFrequency, downsamplePair } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { CHART_TRACE_COLORS } from "@/lib/tokens";
import { cn } from "@/lib/utils";
import {
  Loader2,
  AlertTriangle,
  Activity,
  SlidersHorizontal,
  Radio,
  Play,
  Plus,
  TrendingUp,
} from "lucide-react";
import type { Data } from "plotly.js-dist-min";

const FEATURE_RANGES: Record<string, { label: string; unit?: string; min: number; max: number }> = {
  occupied_bandwidth: { label: "Occupied Bandwidth", unit: "Hz", min: 0, max: 10_000_000 },
  peak_frequency: { label: "Peak Frequency", unit: "Hz", min: 0, max: 10_000_000 },
  spectral_centroid: { label: "Spectral Centroid", unit: "Hz", min: 0, max: 10_000_000 },
  spectral_flatness: { label: "Spectral Flatness", min: 0, max: 1 },
  crest_factor: { label: "Crest Factor", min: 0, max: 20 },
  zero_crossing_rate: { label: "Zero-Crossing Rate", min: 0, max: 1 },
  snr: { label: "Estimated SNR", unit: "dB", min: -10, max: 60 },
};

function WarningList({ warnings }: { warnings: string[] }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <ul className="space-y-1.5 rounded-lg border border-warning/30 bg-warning/5 p-3">
      {warnings.map((w, i) => (
        <li key={i} className="flex items-start gap-2 text-xs text-warning">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          <span>{w}</span>
        </li>
      ))}
    </ul>
  );
}

function MonoPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-card/50 p-3 space-y-2">
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <div className="font-mono text-xs break-all leading-relaxed">{children}</div>
    </div>
  );
}

export default function AnalysisWorkspacePage() {
  const params = useParams();
  const projectId = params.id as string;
  const { addToast } = useToast();
  const queryClient = useQueryClient();

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId),
  });

  const recordingId = project?.recording_id;

  const { data: recording, isLoading: recordingLoading } = useQuery({
    queryKey: ["recording", recordingId],
    queryFn: () => recordingsApi.get(recordingId!),
    enabled: !!recordingId,
  });

  const { data: preview, isLoading: previewLoading } = useQuery({
    queryKey: ["preview", recordingId],
    queryFn: () => recordingsApi.preview(recordingId!),
    enabled: !!recordingId,
  });

  const { data: parameters } = useQuery({
    queryKey: ["parameters", projectId],
    queryFn: () => projectsApi.parameters(projectId),
    enabled: !!projectId,
  });

  const { data: analysis, isError: analysisError } = useQuery({
    queryKey: ["analysis", projectId],
    queryFn: () => projectsApi.analysis(projectId),
    enabled: !!projectId,
  });

  const [roiStart, setRoiStart] = React.useState(0);
  const [roiEnd, setRoiEnd] = React.useState(100);
  const [activeTab, setActiveTab] = React.useState("waveform");
  const [analysisTab, setAnalysisTab] = React.useState("spectrum");

  const meta = recording?.metadata_entry;
  const totalSamples = recording?.total_samples ?? 0;
  const duration = recording?.duration_seconds ?? 0;
  const sampleRate = meta?.sample_rate ?? 1;

  React.useEffect(() => {
    if (preview) {
      setRoiStart(0);
      setRoiEnd(100);
    }
  }, [preview]);

  const n = preview?.preview_count ?? 0;
  const samplesReal = preview?.samples_real ?? [];
  const samplesImag = preview?.samples_imag ?? [];
  const timeArr = React.useMemo(() => {
    if (!sampleRate || n === 0) return [];
    return Array.from({ length: n }, (_, i) => i / sampleRate);
  }, [sampleRate, n]);

  const roiStartIdx = Math.floor((roiStart / 100) * n);
  const roiEndIdx = Math.ceil((roiEnd / 100) * n);

  const waveDown = downsamplePair(timeArr.slice(roiStartIdx, roiEndIdx), samplesReal.slice(roiStartIdx, roiEndIdx), 20000);
  const waveImagDown = downsamplePair(timeArr.slice(roiStartIdx, roiEndIdx), samplesImag.slice(roiStartIdx, roiEndIdx), 20000);
  const scatterDown = downsamplePair(samplesReal.slice(roiStartIdx, roiEndIdx), samplesImag.slice(roiStartIdx, roiEndIdx), 5000);

  const [activeJobId, setActiveJobId] = React.useState<string | null>(null);

  const { data: jobData } = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => jobsApi.get(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed" || !status) return false;
      return 2000;
    },
  });

  React.useEffect(() => {
    if (jobData?.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["parameters", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    }
  }, [jobData?.status, projectId, queryClient]);

  const analyzeMutation = useMutation({
    mutationFn: () => projectsApi.analyze(projectId),
    onSuccess: (data) => {
      setActiveJobId(data.id);
      addToast({ title: "Analysis started" });
    },
    onError: (err: Error) => {
      addToast({
        title: "Analysis failed",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  // Lazy burst detection (explicit user action — loads recording from disk)
  const [showBursts, setShowBursts] = React.useState(false);
  const [burstData, setBurstData] = React.useState<BurstDetection | null>(null);
  const [burstLoading, setBurstLoading] = React.useState(false);

  const detectBursts = async () => {
    setBurstLoading(true);
    try {
      const res = await projectsApi.detectBursts(projectId);
      setBurstData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Burst detection failed";
      addToast({ title: "Burst detection failed", description: msg, variant: "destructive" });
    } finally {
      setBurstLoading(false);
    }
  };

  const waveformData: Data[] = [
    {
      x: waveDown.x, y: waveDown.y, type: "scattergl", mode: "lines",
      name: "I", line: { width: 1, color: CHART_TRACE_COLORS.waveformI },
    },
    {
      x: waveImagDown.x, y: waveImagDown.y, type: "scattergl", mode: "lines",
      name: "Q", line: { width: 1, color: CHART_TRACE_COLORS.waveformQ },
    },
  ];

  const scatterData: Data[] = [
    {
      x: scatterDown.x, y: scatterDown.y, type: "scattergl", mode: "markers",
      marker: { size: 2, opacity: 0.4, color: CHART_TRACE_COLORS.scatter },
    },
  ];

  const psdData: Data[] = analysis
    ? [{
        x: analysis.psd.freqs_hz, y: analysis.psd.psd_db, type: "scattergl", mode: "lines",
        line: { width: 1.5, color: CHART_TRACE_COLORS.psd },
      }]
    : [];

  const waterfallData: Data[] = analysis
    ? ([{
        z: analysis.waterfall.db,
        x: analysis.waterfall.freqs_hz,
        y: analysis.waterfall.times_s,
        type: "heatmap",
        colorscale: CHART_WATERFALL_COLORSCALE,
      }] as Data[])
    : [];

  const constellationData: Data[] = analysis
    ? [{
        x: analysis.demodulation.constellation.map((p) => p[0]),
        y: analysis.demodulation.constellation.map((p) => p[1]),
        type: "scattergl", mode: "markers",
        marker: { size: 3, opacity: 0.6, color: CHART_TRACE_COLORS.constellation },
      }]
    : [];

  const analysisFeatures = analysis
    ? Object.entries(analysis.features as Record<string, { value: number | string | null; unit?: string | null; source: import("@/lib/types").Source; confidence: number | null }>)
        .map(([name, f]) => ({
          name,
          meta: FEATURE_RANGES[name],
          value: f.value as number | null,
          source: f.source,
          confidence: f.confidence,
        }))
    : [];

  const modHypotheses = analysis
    ? [
        { label: analysis.modulation.label, confidence: analysis.modulation.confidence, evidence: analysis.modulation.evidence },
        ...(analysis.modulation.alternatives ?? []).map((a) => ({
          label: a.label,
          confidence: a.confidence,
          evidence: [] as string[],
        })),
      ]
    : [];

  const isLoading = projectLoading || recordingLoading;
  const jobCompleted = jobData?.status === "completed";
  const jobFailed = jobData?.status === "failed";
  const jobRunning = jobData?.status === "running" || jobData?.status === "queued";

  const estimates: ParameterEstimate[] = parameters ?? [];

  const burstStats = burstData && Object.entries(burstData.stats).filter(([k]) =>
    ["burst_count", "burst_duration_s", "repetition_interval_s", "duty_cycle"].includes(k)
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 shimmer rounded" />
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-[110px] rounded-lg border bg-card shimmer" />
          ))}
        </div>
      </div>
    );
  }

  if (!project || !recording) {
    return (
      <div className="space-y-6">
        <h1 className="font-display text-2xl font-semibold">Analysis Workspace</h1>
        <div className="text-sm text-destructive">Project not found.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between reveal">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex h-2 w-2 rounded-full bg-primary animate-pulse-glow" />
            <h1 className="font-display text-2xl font-semibold tracking-tight truncate">
              {project.name}
            </h1>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
            <Radio className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{recording.original_filename}</span>
          </p>
        </div>
        <Button
          onClick={() => analyzeMutation.mutate()}
          disabled={analyzeMutation.isPending || jobRunning}
          className="shrink-0 w-full sm:w-auto"
        >
          {jobRunning ? (
            <Loader2 className="mr-2 h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4 shrink-0" />
          )}
          {jobRunning
            ? `Analyzing... ${jobData?.progress_percent ?? 0}%`
            : jobCompleted
              ? "Re-run Analysis"
              : "Run Parameter Estimation"}
        </Button>
      </div>

      {/* Job progress */}
      {jobRunning && (
        <Card className="reveal reveal-delay-1">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
              <div>
                <div className="text-sm font-medium">
                  Analysis in progress — {jobData?.current_stage ?? "starting"}
                </div>
                <div className="text-xs text-muted-foreground font-mono">
                  {Math.round(jobData?.progress_percent ?? 0)}% complete
                </div>
              </div>
            </div>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted sm:ml-2">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
                style={{ width: `${jobData?.progress_percent ?? 0}%` }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {jobFailed && (
        <Card className="border-destructive reveal">
          <CardContent className="flex items-start gap-2 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="text-sm text-destructive">
              Analysis failed: {jobData?.error_message || "Unknown error"}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recording metadata */}
      <Card className="reveal reveal-delay-1">
        <CardHeader>
          <CardTitle className="font-display text-base font-semibold">
            Recording Metadata
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="rounded-lg border bg-card/50 p-4">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Sample Rate</div>
              <div className="mt-1 font-mono text-lg font-semibold">
                {meta?.sample_rate ? formatFrequency(meta.sample_rate) : "unknown"}
              </div>
              <div className="mt-2">
                <ProvenanceBadge
                  source={(meta?.metadata_source as import("@/lib/types").Source) ?? "unknown"}
                  confidence={meta?.metadata_confidence ?? null}
                />
              </div>
            </div>
            <div className="rounded-lg border bg-card/50 p-4">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Center Frequency</div>
              <div className="mt-1 font-mono text-lg font-semibold">
                {meta?.center_frequency ? formatFrequency(meta.center_frequency) : "unknown"}
              </div>
            </div>
            <div className="rounded-lg border bg-card/50 p-4">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Duration</div>
              <div className="mt-1 font-mono text-lg font-semibold">
                {duration ? formatDuration(duration) : "unknown"}
              </div>
            </div>
            <div className="rounded-lg border bg-card/50 p-4">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Samples</div>
              <div className="mt-1 font-mono text-lg font-semibold">
                {totalSamples.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {[
              meta?.is_complex ? "Complex I/Q" : "Real",
              meta?.data_type ?? "unknown",
              `${meta?.channel_count ?? 1} ch`,
              recording.file_format.toUpperCase(),
              formatBytes(recording.file_size),
            ].map((label) => (
              <span
                key={label}
                className="rounded-full border px-3 py-1 text-xs font-medium text-muted-foreground"
              >
                {label}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ROI */}
      {preview && (
        <Card className="reveal reveal-delay-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-display text-base font-semibold">
              <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
              Region of Interest
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                <span>{roiStart}%</span>
                <span>
                  {duration > 0
                    ? `${((roiStart / 100) * duration).toFixed(3)}s – ${((roiEnd / 100) * duration).toFixed(3)}s`
                    : `samples ${Math.floor((roiStart / 100) * totalSamples).toLocaleString()} – ${Math.floor((roiEnd / 100) * totalSamples).toLocaleString()}`}
                </span>
                <span>{roiEnd}%</span>
              </div>
              <Slider
                value={[roiStart, roiEnd]}
                min={0}
                max={100}
                step={0.5}
                onValueChange={(v) => {
                  if (v[0] < v[1]) {
                    setRoiStart(v[0]);
                    setRoiEnd(v[1]);
                  }
                }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Waveform / scatter */}
      <div className="space-y-4 reveal reveal-delay-2">
        <SectionTabs
          tabs={[
            { key: "waveform", label: "Waveform" },
            { key: "scatter", label: "I/Q Scatter" },
          ]}
          value={activeTab}
          onChange={setActiveTab}
        />

        {activeTab === "waveform" && (
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-base font-semibold">
                Waveform (I/Q Time Domain)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {previewLoading ? (
                <div className="py-12 text-center text-sm text-muted-foreground">Loading preview...</div>
              ) : (
                <PlotlyChart
                  data={waveformData}
                  layout={{
                    title: "Time waveform",
                    xaxis: { title: "Time (s)" },
                    yaxis: { title: "Amplitude" },
                    height: 400,
                  }}
                />
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "scatter" && (
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-base font-semibold">
                I/Q Scatter
              </CardTitle>
            </CardHeader>
            <CardContent>
              {previewLoading ? (
                <div className="py-12 text-center text-sm text-muted-foreground">Loading preview...</div>
              ) : (
                <PlotlyChart
                  data={scatterData}
                  layout={{
                    title: "I/Q scatter",
                    xaxis: { title: "I" },
                    yaxis: { title: "Q", scaleanchor: "x" },
                    height: 450,
                    width: 480,
                  }}
                />
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Deep analysis */}
      <Card className="reveal reveal-delay-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-display text-base font-semibold">
            <Activity className="h-4 w-4 text-muted-foreground" />
            Deep Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SectionTabs
            tabs={[
              { key: "spectrum", label: "Spectrum & Features" },
              { key: "waterfall", label: "Waterfall" },
              { key: "demodulation", label: "Demodulation" },
              { key: "fec", label: "FEC & De-interleave" },
              { key: "correlation", label: "Correlation" },
              { key: "bursts", label: "Burst Timeline" },
            ]}
            value={analysisTab}
            onChange={setAnalysisTab}
            className="mb-4"
          />

          {analysisError ? (
            <div className="text-sm text-destructive py-4">Deep analysis failed.</div>
          ) : analysisTab === "bursts" ? (
            <BurstPanel
              showBursts={showBursts}
              setShowBursts={setShowBursts}
              burstLoading={burstLoading}
              burstData={burstData}
              detectBursts={detectBursts}
              duration={duration}
              burstStats={burstStats}
            />
          ) : !analysis ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              Computing spectra, modulation, and demodulation hypothesis...
            </div>
          ) : (
            <>
              {analysisTab === "spectrum" && (
                <div className="space-y-4">
                  <PlotlyChart
                    data={psdData}
                    layout={{
                      title: "Power Spectral Density (Welch, ROI window)",
                      xaxis: { title: "Frequency (Hz, relative)" },
                      yaxis: { title: "dB" },
                      height: 380,
                    }}
                  />

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {analysisFeatures.map((f) => (
                      <MetricCard
                        key={f.name}
                        label={f.meta?.label ?? f.name}
                        value={f.value}
                        unit={f.meta?.unit ?? null}
                        source={f.source}
                        confidence={f.confidence}
                        accent="primary"
                        rangeMin={f.meta?.min}
                        rangeMax={f.meta?.max}
                      />
                    ))}
                  </div>

                  <div className="grid gap-3 lg:grid-cols-2">
                    <div className="rounded-lg border bg-card p-4 space-y-3">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-primary" />
                        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                          Modulation Hypothesis
                        </span>
                      </div>
                      <RankedBars items={modHypotheses} />
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      <MetricCard
                        label="Symbol Rate"
                        value={analysis.symbol_rate_hz}
                        unit="Hz"
                        source="estimated"
                        confidence={analysis.symbol_rate_confidence}
                        accent="secondary"
                      />
                      <div className="rounded-lg border bg-card/50 p-3">
                        <div className="text-xs font-medium text-muted-foreground">
                          Symbol-rate candidates
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(analysis.symbol_rate_candidates ?? []).length > 0 ? (
                            analysis.symbol_rate_candidates.map((c, i) => (
                              <span key={i} className="rounded-full border px-2.5 py-1 font-mono text-xs">
                                {formatFrequency(c)}
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {analysisTab === "waterfall" && (
                <PlotlyChart
                  data={waterfallData}
                  layout={{
                    title: "Spectrogram (waterfall)",
                    xaxis: { title: "Frequency (Hz, relative)" },
                    yaxis: { title: "Time (s)" },
                    yaxis_autorange: "reversed",
                    height: 440,
                  }}
                />
              )}

              {analysisTab === "demodulation" && (
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <MetricCard label="Modulation" value={analysis.demodulation.modulation} accent="primary" />
                    <MetricCard label="Bits / Symbol" value={analysis.demodulation.bits_per_symbol} accent="secondary" />
                    <MetricCard label="Samples / Symbol" value={analysis.demodulation.samples_per_symbol} accent="primary" />
                    <MetricCard label="Symbols" value={analysis.demodulation.n_symbols.toLocaleString()} accent="secondary" />
                  </div>

                  <PlotlyChart
                    data={constellationData}
                    layout={{
                      title: "Demodulated constellation",
                      xaxis: { title: "I" },
                      yaxis: { title: "Q", scaleanchor: "x" },
                      height: 420,
                    }}
                  />

                  <div className="grid gap-3 md:grid-cols-2">
                    <MonoPanel title="Hard bits (first 128)">
                      {analysis.demodulation.hard_bits_preview || "No bits recovered"}
                    </MonoPanel>
                    <MonoPanel title="First bytes (hex)">
                      {analysis.demodulation.first_bytes_hex || "—"}
                    </MonoPanel>
                  </div>

                  <WarningList warnings={analysis.demodulation.warnings} />
                </div>
              )}

              {analysisTab === "fec" && (
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <MetricCard label="De-interleave" value={analysis.deinterleave.best_attempt} accent="primary" />
                    <MetricCard label="Validation Score" value={analysis.deinterleave.validation_score.toFixed(3)} accent="secondary" />
                    <MetricCard label="Decoded Bits" value={analysis.fec.decoded_bits_count.toLocaleString()} accent="primary" />
                    <MetricCard label="Path Metric" value={analysis.fec.path_metric.toFixed(1)} accent="secondary" />
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      CRC-16:
                    </span>
                    <span
                      className={cn(
                        "rounded-full px-2.5 py-1 text-xs font-medium",
                        analysis.fec.crc_valid === true
                          ? "bg-confidence-high/10 text-confidence-high"
                          : analysis.fec.crc_valid === false
                            ? "bg-destructive/10 text-destructive"
                            : "bg-muted text-muted-foreground"
                      )}
                    >
                      {analysis.fec.crc_valid === null
                        ? "no frame"
                        : analysis.fec.crc_valid
                          ? "OK"
                          : "mismatch"}
                    </span>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <MonoPanel title="Recovered bit stream (de-interleaved, first 64)">
                      {analysis.deinterleave.recovered_preview || "—"}
                    </MonoPanel>
                    <MonoPanel title="FEC-decoded bytes (first 32)">
                      {analysis.fec.first_bytes_hex || "—"}
                    </MonoPanel>
                  </div>

                  <div className="text-xs text-muted-foreground">{analysis.fec.crc_detail}</div>
                  <WarningList warnings={analysis.fec.warnings} />
                </div>
              )}

              {analysisTab === "correlation" && (
                <div className="space-y-4">
                  {analysis.correlation.sequences.length > 0 ? (
                    <div className="grid gap-3 md:grid-cols-2">
                      {analysis.correlation.sequences.map((s, i) => (
                        <div key={i} className="rounded-lg border bg-card p-3 space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-semibold">{s.pattern_hex}</span>
                            <span className="rounded-full bg-secondary/10 px-2 py-0.5 text-[10px] font-medium text-secondary">
                              {s.repeat_count}x
                            </span>
                          </div>
                          <div className="text-xs text-muted-foreground font-mono">
                            offsets: {s.offsets.join(", ") || "—"}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-8 text-center text-sm text-muted-foreground">
                      No repeated 24-bit patterns found in the decoded bit stream
                      (candidate header/preamble sync).
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Parameter estimates */}
      <Card className="reveal reveal-delay-3">
        <CardHeader>
          <CardTitle className="font-display text-base font-semibold">
            Parameter Estimates
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Every estimate carries a source, confidence, and evidence.
          </p>
        </CardHeader>
        <CardContent>
          {estimates.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {estimates.map((est) => (
                <MetricCard
                  key={est.id}
                  label={est.parameter_name.replaceAll("_", " ")}
                  value={est.value_json?.value as number | string | null ?? null}
                  unit={est.value_json?.unit as string | null ?? null}
                  source={est.source as import("@/lib/types").Source}
                  confidence={est.confidence}
                  accent={
                    est.parameter_name.includes("duty") ||
                    est.parameter_name.includes("snr") ||
                    est.parameter_name.includes("bandwidth")
                      ? "primary"
                      : "secondary"
                  }
                  rangeMin={est.parameter_name === "snr" ? -10 : undefined}
                  rangeMax={est.parameter_name === "snr" ? 60 : undefined}
                />
              ))}
            </div>
          ) : (
            <div className="py-10 text-center text-sm text-muted-foreground">
              No parameter estimates yet. Click &quot;Run Parameter Estimation&quot;
              to analyze this recording.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function BurstPanel({
  showBursts,
  setShowBursts,
  burstLoading,
  burstData,
  detectBursts,
  duration,
  burstStats,
}: {
  showBursts: boolean;
  setShowBursts: React.Dispatch<React.SetStateAction<boolean>>;
  burstLoading: boolean;
  burstData: BurstDetection | null;
  detectBursts: () => void;
  duration: number;
  burstStats?: [string, { name: string; value: number | string | null; unit: string | null; source: string; confidence: number | null }][];
}) {
  if (!showBursts) {
    return (
      <div className="py-8 text-center">
        <p className="mb-4 text-sm text-muted-foreground">
          Run burst detection over the recording ROI to visualize activity bursts.
        </p>
        <Button onClick={() => { setShowBursts(true); detectBursts(); }} disabled={burstLoading}>
          {burstLoading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Plus className="mr-2 h-4 w-4" />
          )}
          {burstLoading ? "Detecting bursts..." : "Detect Bursts"}
        </Button>
      </div>
    );
  }

  if (burstLoading && !burstData) {
    return (
      <div className="py-10 text-center">
        <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Detecting bursts from the recording...</p>
      </div>
    );
  }

  if (!burstData || burstData.bursts.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-muted-foreground">No bursts detected in this window.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {burstStats && burstStats.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {burstStats.map(([key, s]) => (
            <MetricCard
              key={key}
              label={s.name.replaceAll("_", " ")}
              value={s.value}
              unit={s.unit ?? null}
              source={s.source as import("@/lib/types").Source}
              confidence={s.confidence}
              accent="primary"
              rangeMin={key === "duty_cycle" ? 0 : undefined}
              rangeMax={key === "duty_cycle" ? 1 : undefined}
            />
          ))}
        </div>
      )}

      <BurstTimeline
        bursts={burstData.bursts.map((b) => ({
          startSample: b.start_sample,
          endSample: b.end_sample,
          startTimeS: b.start_time_s,
          endTimeS: b.end_time_s,
          peakPowerDb: b.peak_power_db,
          meanPowerDb: b.mean_power_db,
          confidence: b.confidence,
        }))}
        durationS={duration}
      />

      <div className="text-xs text-muted-foreground">
        {burstData.bursts.length} bursts across the selected region.
      </div>
    </div>
  );
}