"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { projectsApi, recordingsApi, jobsApi } from "@/lib/api";
import type { Recording, ParameterEstimate, Job } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  Radio,
  Settings,
  BarChart3,
} from "lucide-react";
import type { Data } from "plotly.js-dist-min";

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

  const { data: parameters } = useQuery({
    queryKey: ["parameters", projectId],
    queryFn: () => projectsApi.parameters(projectId),
    enabled: !!projectId,
  });

  const [roiStart, setRoiStart] = React.useState(0);
  const [roiEnd, setRoiEnd] = React.useState(100);
  const [activeTab, setActiveTab] = React.useState("waveform");

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

  const waveDown = downsamplePair(
    timeArr.slice(roiStartIdx, roiEndIdx),
    samplesReal.slice(roiStartIdx, roiEndIdx),
    20000
  );
  const waveImagDown = downsamplePair(
    timeArr.slice(roiStartIdx, roiEndIdx),
    samplesImag.slice(roiStartIdx, roiEndIdx),
    20000
  );
  const scatterDown = downsamplePair(
    samplesReal.slice(roiStartIdx, roiEndIdx),
    samplesImag.slice(roiStartIdx, roiEndIdx),
    5000
  );

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

  const scatterData: PlotData[] = [
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
  const jobRunning = jobData?.status === "running" || jobData?.status === "queued";

  const estimates: ParameterEstimate[] = parameters ?? [];

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
            {recording.original_filename}
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
            ? `Analyzing... ${jobData?.progress_percent ?? 0}%`
            : jobCompleted
            ? "Re-run Analysis"
            : "Run Parameter Estimation"}
        </Button>
      </div>

      {jobRunning && (
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <div>
              <div className="text-sm font-medium">
                Analysis in progress — {jobData?.current_stage ?? "starting"}
              </div>
              <div className="text-xs text-muted-foreground">
                {Math.round(jobData?.progress_percent ?? 0)}% complete
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {jobFailed && (
        <Card className="border-destructive">
          <CardContent className="p-4">
            <div className="text-sm text-destructive">
              Analysis failed: {jobData?.error_message || "Unknown error"}
            </div>
          </CardContent>
        </Card>
      )}

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
                {meta?.sample_rate
                  ? formatFrequency(meta.sample_rate)
                  : "unknown"}
              </div>
              {meta?.metadata_source && (
                <ProvenanceBadge
                  source={meta.metadata_source as any}
                  confidence={meta.metadata_confidence}
                />
              )}
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Center Frequency</div>
              <div className="text-sm font-medium">
                {meta?.center_frequency
                  ? formatFrequency(meta.center_frequency)
                  : "unknown"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Duration</div>
              <div className="text-sm font-medium">
                {duration ? formatDuration(duration) : "unknown"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Samples</div>
              <div className="text-sm font-medium">
                {totalSamples.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <Badge variant="outline">
              {meta?.is_complex ? "Complex I/Q" : "Real"}
            </Badge>
            <Badge variant="outline">{meta?.data_type ?? "unknown"}</Badge>
            <Badge variant="outline">
              {meta?.channel_count ?? 1} ch
            </Badge>
            <Badge variant="outline">{recording.file_format.toUpperCase()}</Badge>
            <Badge variant="outline">{formatBytes(recording.file_size)}</Badge>
          </div>
        </CardContent>
      </Card>

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

      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {[
            { key: "waveform", label: "Waveform" },
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
              {estimates.map((est) => (
                <EstimateCard
                  key={est.id}
                  label={est.parameter_name}
                  value={est.value_json?.value as number | string | null ?? null}
                  source={est.source as any}
                  confidence={est.confidence}
                  evidence={est.evidence_json?.evidence as string[] ?? []}
                  alternatives={[]}
                  warnings={est.evidence_json?.warnings as string[] ?? []}
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
