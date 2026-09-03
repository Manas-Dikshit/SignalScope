"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { projectsApi, recordingsApi, jobsApi } from "@/lib/api";
import type { Recording, PreviewData, Estimate, Job } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { PlotlyChart } from "@/components/PlotlyChart";
import {
  ProvenanceBadge,
  EstimateCard,
} from "@/components/ProvenanceBadge";
import { formatBytes, formatDuration, formatFrequency, downsamplePair } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import {
  Play,
  Loader2,
  Clock,
  Radio,
  Settings,
  BarChart3,
} from "lucide-react";
import type { Data, Layout } from "plotly.js-dist-min";

export default function AnalysisWorkspacePage() {
  const params = useParams();
  const projectId = params.id as string;
  const { addToast } = useToast();

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

  const [roiStart, setRoiStart] = React.useState(0);
  const [roiEnd, setRoiEnd] = React.useState(100);
  const [activeTab, setActiveTab] = React.useState("waveform");
  const [fftSize, setFftSize] = React.useState(2048);

  const totalSamples = recording?.metadata?.total_samples ?? 0;
  const duration = recording?.metadata?.duration_seconds ?? 0;
  const sampleRate = (recording?.metadata?.sample_rate?.value as number) ?? 1;

  React.useEffect(() => {
    if (preview) {
      setRoiStart(0);
      setRoiEnd(100);
    }
  }, [preview]);

  const filterByRoi = React.useCallback(
    <T extends number[]>(arr: T, ref?: number[]): T => {
      if (!ref || arr.length === 0) return arr;
      const startIdx = Math.floor((roiStart / 100) * ref.length);
      const endIdx = Math.ceil((roiEnd / 100) * ref.length);
      return ref.slice(startIdx, endIdx) as T;
    },
    [roiStart, roiEnd]
  );

  const waveformTime = preview
    ? filterByRoi(preview.waveform.time, preview.waveform.time)
    : [];
  const waveformReal = preview
    ? filterByRoi(preview.waveform.real, preview.waveform.time)
    : [];
  const waveformImag = preview
    ? filterByRoi(preview.waveform.imag, preview.waveform.time)
    : [];

  const scatterReal = preview ? preview.scatter.real : [];
  const scatterImag = preview ? preview.scatter.imag : [];

  const waveDown = downsamplePair(
    waveformTime as number[],
    waveformReal as number[],
    20000
  );
  const waveImagDown = downsamplePair(
    waveformTime as number[],
    waveformImag as number[],
    20000
  );
  const scatterDown = downsamplePair(
    scatterReal as number[],
    scatterImag as number[],
    5000
  );

  // Job polling
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

  const analyzeMutation = useMutation({
    mutationFn: () => projectsApi.analyze(projectId),
    onSuccess: (data) => {
      setActiveJobId(data.job_id);
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

  const waveformData: Data[] = [
    {
      x: waveDown.x,
      y: waveDown.y,
      type: "scattergl",
      mode: "lines",
      name: "I",
      line: { width: 1, color: "#3b82f6" },
    },
    {
      x: waveImagDown.x,
      y: waveImagDown.y,
      type: "scattergl",
      mode: "lines",
      name: "Q",
      line: { width: 1, color: "#f97316" },
    },
  ];

  const psdData: Data[] = preview
    ? [
        {
          x: preview.psd.frequency,
          y: preview.psd.power,
          type: "scatter",
          mode: "lines",
          line: { width: 1, color: "#3b82f6" },
        },
      ]
    : [];

  const waterfallData: Data[] =
    preview && preview.waterfall.spectrogram.length > 0
      ? [
          {
            z: preview.waterfall.spectrogram,
            x: preview.waterfall.frequency,
            y: preview.waterfall.time,
            type: "heatmap",
            colorscale: "Viridis",
          },
        ]
      : [];

  const scatterData: Data[] = [
    {
      x: scatterDown.x,
      y: scatterDown.y,
      type: "scattergl",
      mode: "markers",
      marker: { size: 2, opacity: 0.4, color: "#3b82f6" },
    },
  ];

  const isLoading = projectLoading || recordingLoading;
  const jobCompleted = jobData?.status === "completed";
  const jobFailed = jobData?.status === "failed";
  const jobRunning =
    jobData?.status === "running" || jobData?.status === "pending";

  const estimates: Estimate[] = jobCompleted
    ? ((jobData?.result?.parameter_estimates as Estimate[]) ??
      project?.parameter_estimates ??
      [])
    : project?.parameter_estimates ?? [];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Analysis Workspace</h1>
        <div className="text-muted-foreground text-sm">Loading project...</div>
      </div>
    );
  }

  if (!project || !recording) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Analysis Workspace</h1>
        <div className="text-destructive text-sm">Project not found.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{project.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {recording.name || recording.filename}
          </p>
        </div>
        <Button
          onClick={() => analyzeMutation.mutate()}
          disabled={analyzeMutation.isPending || jobRunning}
        >
          {jobRunning ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          {jobRunning
            ? "Analyzing..."
            : jobCompleted
            ? "Re-run Analysis"
            : "Run Parameter Estimation"}
        </Button>
      </div>

      {/* Job progress */}
      {jobRunning && (
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <div>
              <div className="text-sm font-medium">Analysis in progress</div>
              <div className="text-xs text-muted-foreground">
                Job {activeJobId?.slice(0, 8)}... — polling for results
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {jobFailed && (
        <Card className="border-destructive">
          <CardContent className="p-4">
            <div className="text-sm text-destructive">
              Analysis failed: {(jobData?.error as string) || "Unknown error"}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Metadata overview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Radio className="h-4 w-4" />
            Recording Metadata
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">Sample Rate</div>
              <div className="text-sm font-medium">
                {recording.metadata.sample_rate.value
                  ? formatFrequency(recording.metadata.sample_rate.value as number)
                  : "unknown"}
              </div>
              <ProvenanceBadge
                source={recording.metadata.sample_rate.source}
                confidence={recording.metadata.sample_rate.confidence}
              />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Center Frequency</div>
              <div className="text-sm font-medium">
                {recording.metadata.center_frequency?.value
                  ? formatFrequency(
                      recording.metadata.center_frequency.value as number
                    )
                  : "unknown"}
              </div>
              {recording.metadata.center_frequency && (
                <ProvenanceBadge
                  source={recording.metadata.center_frequency.source}
                  confidence={recording.metadata.center_frequency.confidence}
                />
              )}
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Duration</div>
              <div className="text-sm font-medium">
                {recording.metadata.duration_seconds
                  ? formatDuration(recording.metadata.duration_seconds)
                  : "unknown"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Samples</div>
              <div className="text-sm font-medium">
                {(recording.metadata.total_samples || 0).toLocaleString()}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <Badge variant="outline">
              {recording.metadata.is_complex ? "Complex I/Q" : "Real"}
            </Badge>
            <Badge variant="outline">{recording.metadata.sample_dtype}</Badge>
            <Badge variant="outline">
              {recording.metadata.channel_count} ch
            </Badge>
            <Badge variant="outline">{recording.format.toUpperCase()}</Badge>
            <Badge variant="outline">{formatBytes(recording.file_size)}</Badge>
          </div>
        </CardContent>
      </Card>

      {/* Region of interest */}
      {preview && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Region of Interest</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{roiStart}%</span>
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
              <div className="text-xs text-muted-foreground text-center">
                {duration > 0
                  ? `${((roiStart / 100) * duration).toFixed(3)}s – ${(
                      (roiEnd / 100) * duration
                    ).toFixed(3)}s`
                  : `Samples ${Math.floor(
                      (roiStart / 100) * totalSamples
                    ).toLocaleString()} – ${Math.floor(
                      (roiEnd / 100) * totalSamples
                    ).toLocaleString()}`}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Plots */}
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {[
            { key: "waveform", label: "Waveform" },
            { key: "psd", label: "PSD" },
            { key: "waterfall", label: "Waterfall" },
            { key: "scatter", label: "I/Q Scatter" },
          ].map((tab) => (
            <Button
              key={tab.key}
              variant={activeTab === tab.key ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </Button>
          ))}
        </div>

        {activeTab === "waveform" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Waveform (I/Q Time Domain)</CardTitle>
            </CardHeader>
            <CardContent>
              {previewLoading ? (
                <div className="text-muted-foreground text-sm py-8 text-center">
                  Loading preview...
                </div>
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

        {activeTab === "psd" && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Power Spectral Density</CardTitle>
              <Select
                value={String(fftSize)}
                onValueChange={(v) => setFftSize(Number(v))}
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[256, 512, 1024, 2048, 4096, 8192].map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      FFT: {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              {previewLoading ? (
                <div className="text-muted-foreground text-sm py-8 text-center">
                  Loading preview...
                </div>
              ) : (
                <PlotlyChart
                  data={psdData}
                  layout={{
                    title: "Power spectral density",
                    xaxis: { title: "Frequency (Hz, relative to center)" },
                    yaxis: { title: "Power (dB)" },
                    height: 400,
                  }}
                />
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "waterfall" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Waterfall / Spectrogram</CardTitle>
            </CardHeader>
            <CardContent>
              {previewLoading ? (
                <div className="text-muted-foreground text-sm py-8 text-center">
                  Loading preview...
                </div>
              ) : waterfallData.length > 0 ? (
                <PlotlyChart
                  data={waterfallData}
                  layout={{
                    title: "Waterfall / spectrogram",
                    xaxis: { title: "Frequency (Hz)" },
                    yaxis: { title: "Time (s)" },
                    height: 450,
                  }}
                />
              ) : (
                <div className="text-muted-foreground text-sm py-8 text-center">
                  No waterfall data available.
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "scatter" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">I/Q Scatter</CardTitle>
            </CardHeader>
            <CardContent>
              {previewLoading ? (
                <div className="text-muted-foreground text-sm py-8 text-center">
                  Loading preview...
                </div>
              ) : (
                <PlotlyChart
                  data={scatterData}
                  layout={{
                    title: "I/Q scatter",
                    xaxis: { title: "I" },
                    yaxis: { title: "Q", scaleanchor: "x" },
                    height: 450,
                    width: 450,
                  }}
                />
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Parameter estimation results */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Parameter Estimates
          </CardTitle>
        </CardHeader>
        <CardContent>
          {estimates.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {estimates.map((est, i) => (
                <EstimateCard
                  key={`${est.name}-${i}`}
                  label={est.name}
                  value={est.value}
                  unit={est.unit}
                  source={est.source}
                  confidence={est.confidence}
                  evidence={est.evidence}
                  alternatives={est.alternatives}
                  warnings={est.warnings}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Settings className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">
                No parameter estimates yet. Click &quot;Run Parameter Estimation&quot;
                to analyze this recording.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
