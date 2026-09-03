"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { recordingsApi } from "@/lib/api";
import type { Recording, PreviewData } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { PlotlyChart } from "@/components/PlotlyChart";
import { downsamplePair, downsample } from "@/lib/utils";
import { Upload, FileAudio, Check, X, ArrowLeft } from "lucide-react";
import { useToast } from "@/components/ui/toast";
import type { Data } from "plotly.js-dist-min";

type Step = "select" | "format" | "preview" | "done";
type FileFormat = "wav" | "raw_iq" | "sigmf";

export function UploadWizard({ onComplete }: { onComplete?: () => void }) {
  const [step, setStep] = React.useState<Step>("select");
  const [files, setFiles] = React.useState<File[]>([]);
  const [format, setFormat] = React.useState<FileFormat>("wav");
  const [name, setName] = React.useState("");
  const [uploadProgress, setUploadProgress] = React.useState(0);

  const [wavStereoMode, setWavStereoMode] = React.useState("left_is_i_right_is_q");
  const [rawDtype, setRawDtype] = React.useState("float32");
  const [rawLayout, setRawLayout] = React.useState("interleaved");
  const [rawEndian, setRawEndian] = React.useState("little");
  const [rawSampleRate, setRawSampleRate] = React.useState("");
  const [rawCenterFreq, setRawCenterFreq] = React.useState("");

  const [createdRecording, setCreatedRecording] = React.useState<Recording | null>(null);
  const [previewData, setPreviewData] = React.useState<PreviewData | null>(null);

  const [dragOver, setDragOver] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const metaInputRef = React.useRef<HTMLInputElement>(null);

  const queryClient = useQueryClient();
  const router = useRouter();
  const { addToast } = useToast();

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData();
      if (format === "sigmf") {
        formData.append("file", files[0]);
        if (files[1]) formData.append("data_file", files[1]);
      } else {
        formData.append("file", files[0]);
      }
      formData.append("loader", format);
      if (format === "raw_iq") {
        formData.append(
          "raw_iq_params",
          JSON.stringify({
            dtype: rawDtype,
            layout: rawLayout,
            endian: rawEndian,
            sample_rate_hz: rawSampleRate ? Number(rawSampleRate) : null,
            center_frequency_hz: rawCenterFreq ? Number(rawCenterFreq) : null,
          })
        );
      }
      if (format === "wav") {
        formData.append(
          "wav_params",
          JSON.stringify({ stereo_mode: wavStereoMode })
        );
      }
      setUploadProgress(30);
      const recording = await recordingsApi.upload(formData);
      setUploadProgress(70);
      return recording;
    },
    onSuccess: async (recording) => {
      setCreatedRecording(recording);
      setUploadProgress(85);
      try {
        const preview = await recordingsApi.preview(recording.id);
        setPreviewData(preview);
      } catch {
        // Preview not critical
      }
      setUploadProgress(100);
      queryClient.invalidateQueries({ queryKey: ["recordings"] });
      setStep("preview");
    },
    onError: (err: Error) => {
      addToast({ title: "Upload failed", description: err.message, variant: "destructive" });
      setUploadProgress(0);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => recordingsApi.delete(createdRecording!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recordings"] });
      resetWizard();
      addToast({ title: "Upload cancelled" });
    },
  });

  const resetWizard = () => {
    setStep("select");
    setFiles([]);
    setCreatedRecording(null);
    setPreviewData(null);
    setUploadProgress(0);
    setName("");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files);
    if (dropped.length > 0) {
      setFiles(dropped);
      if (dropped[0].name.endsWith(".sigmf-meta") || dropped[0].name.endsWith(".json")) {
        setFormat("sigmf");
      } else if (
        dropped[0].name.endsWith(".wav")
      ) {
        setFormat("wav");
      } else {
        setFormat("raw_iq");
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || []);
    if (selected.length > 0) {
      setFiles(selected);
      if (selected[0].name.endsWith(".sigmf-meta") || selected[0].name.endsWith(".json")) {
        setFormat("sigmf");
      } else if (selected[0].name.endsWith(".wav")) {
        setFormat("wav");
      } else {
        setFormat("raw_iq");
      }
    }
  };

  const canProceedToFormat = files.length > 0;
  const canUpload =
    files.length > 0 &&
    (format !== "sigmf" || files.length >= 2);

  const waveformPlotData: Data[] = previewData
    ? [
        {
          x: previewData.samples_imag.map((_, i) =>
            previewData.sample_rate
              ? i / previewData.sample_rate
              : i
          ),
          y: previewData.samples_real,
          type: "scattergl",
          mode: "lines",
          name: "I",
          line: { width: 1 },
        },
        {
          x: previewData.samples_imag.map((_, i) =>
            previewData.sample_rate
              ? i / previewData.sample_rate
              : i
          ),
          y: previewData.samples_imag,
          type: "scattergl",
          mode: "lines",
          name: "Q",
          line: { width: 1 },
        },
      ]
    : [];

  const scatterPlotData: Data[] = previewData
    ? [
        {
          x: previewData.samples_real,
          y: previewData.samples_imag,
          type: "scattergl",
          mode: "markers",
          marker: { size: 2, opacity: 0.4 },
        },
      ]
    : [];

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">
            {step === "select" && "Select Files"}
            {step === "format" && "Configure Format"}
            {step === "preview" && "Preview Recording"}
            {step === "done" && "Upload Complete"}
          </CardTitle>
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {["select", "format", "preview"].map((s, i) => (
                <div
                  key={s}
                  className={`h-1.5 w-8 rounded-full ${
                    ["select", "format", "preview"].indexOf(step) >= i
                      ? "bg-primary"
                      : "bg-muted"
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Step 1: File selection */}
        {step === "select" && (
          <>
            <div
              className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer ${
                dragOver
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-muted-foreground/50"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-10 w-10 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground">
                Drag & drop files here, or click to browse
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                WAV, Raw IQ (.iq/.bin/.dat), or SigMF (.sigmf-meta + .sigmf-data)
              </p>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                multiple
                accept=".wav,.iq,.bin,.dat,.raw,.sigmf-meta,.sigmf-data,.json"
                onChange={handleFileSelect}
              />
            </div>

            {files.length > 0 && (
              <div className="space-y-2">
                <Label>Selected files</Label>
                <div className="space-y-1">
                  {files.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm"
                    >
                      <FileAudio className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="truncate flex-1">{f.name}</span>
                      <span className="text-muted-foreground text-xs">
                        {(f.size / 1024 / 1024).toFixed(1)} MB
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setFiles(files.filter((_, j) => j !== i));
                        }}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>

                <div className="space-y-2 pt-2">
                  <Label>Recording name (optional)</Label>
                  <Input
                    placeholder="e.g. captured_signal_001"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className="flex justify-end">
              <Button
                disabled={!canProceedToFormat}
                onClick={() => setStep("format")}
              >
                Next
              </Button>
            </div>
          </>
        )}

        {/* Step 2: Format configuration */}
        {step === "format" && (
          <>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>File format</Label>
                <Select value={format} onValueChange={(v) => setFormat(v as FileFormat)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="wav">WAV</SelectItem>
                    <SelectItem value="raw_iq">Raw IQ</SelectItem>
                    <SelectItem value="sigmf">SigMF</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {format === "wav" && (
                <div className="space-y-2">
                  <Label>Stereo interpretation</Label>
                  <Select value={wavStereoMode} onValueChange={setWavStereoMode}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="left_is_i_right_is_q">
                        Left = I, Right = Q
                      </SelectItem>
                      <SelectItem value="left_only">Left channel only</SelectItem>
                      <SelectItem value="right_only">
                        Right channel only
                      </SelectItem>
                      <SelectItem value="mono_mix">Mono mix</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {format === "raw_iq" && (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-3">
                    <div className="space-y-2">
                      <Label>Sample dtype</Label>
                      <Select value={rawDtype} onValueChange={setRawDtype}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {["int8", "uint8", "int16", "uint16", "int32", "float32", "float64"].map(
                            (d) => (
                              <SelectItem key={d} value={d}>
                                {d}
                              </SelectItem>
                            )
                          )}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Layout</Label>
                      <Select value={rawLayout} onValueChange={setRawLayout}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="interleaved">Interleaved</SelectItem>
                          <SelectItem value="separate_iq">
                            Separate I/Q
                          </SelectItem>
                          <SelectItem value="real_only">Real only</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Endianness</Label>
                      <Select value={rawEndian} onValueChange={setRawEndian}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="little">Little-endian</SelectItem>
                          <SelectItem value="big">Big-endian</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label>Sample rate (Hz, optional)</Label>
                      <Input
                        type="number"
                        placeholder="e.g. 1000000"
                        value={rawSampleRate}
                        onChange={(e) => setRawSampleRate(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Center frequency (Hz, optional)</Label>
                      <Input
                        type="number"
                        placeholder="e.g. 915000000"
                        value={rawCenterFreq}
                        onChange={(e) => setRawCenterFreq(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              )}

              {format === "sigmf" && (
                <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
                  Select both the <code>.sigmf-meta</code> and{" "}
                  <code>.sigmf-data</code> files. The metadata file should be
                  first.
                </div>
              )}
            </div>

            {uploadProgress > 0 && (
              <Progress value={uploadProgress} />
            )}

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep("select")}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button
                disabled={!canUpload || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
              >
                {uploadMutation.isPending ? "Uploading..." : "Upload & Preview"}
              </Button>
            </div>
          </>
        )}

        {/* Step 3: Preview */}
        {step === "preview" && previewData && (
          <>
            <div className="space-y-2 text-sm text-muted-foreground">
              <span>Samples: {previewData.preview_count.toLocaleString()} of {previewData.total_samples.toLocaleString()}</span>
              {previewData.sample_rate && (
                <span> · Sample rate: {(previewData.sample_rate / 1e6).toFixed(2)} MHz</span>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <Label className="text-sm font-medium mb-2 block">
                  Waveform (I/Q time domain)
                </Label>
                <PlotlyChart
                  data={waveformPlotData}
                  layout={{ title: "Time waveform", xaxis: { title: "Time (s)" }, yaxis: { title: "Amplitude" } }}
                />
              </div>
              <div>
                <Label className="text-sm font-medium mb-2 block">
                  I/Q Scatter
                </Label>
                <PlotlyChart
                  data={scatterPlotData}
                  layout={{
                    title: "I/Q scatter",
                    xaxis: { title: "I" },
                    yaxis: { title: "Q", scaleanchor: "x" },
                    height: 350,
                    width: 350,
                  }}
                />
              </div>
            </div>

            <div className="flex justify-between">
              <Button
                variant="destructive"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
              >
                Cancel & Delete
              </Button>
              <Button
                onClick={() => {
                  setStep("done");
                  router.push("/recordings");
                  onComplete?.();
                }}
              >
                <Check className="mr-2 h-4 w-4" />
                Confirm
              </Button>
            </div>
          </>
        )}

        {step === "preview" && !previewData && (
          <div className="text-center py-8 text-muted-foreground">
            Recording uploaded. Preview unavailable.
            <div className="mt-4 flex justify-between">
              <Button
                variant="destructive"
                onClick={() => deleteMutation.mutate()}
              >
                Cancel & Delete
              </Button>
              <Button onClick={() => { setStep("done"); router.push("/recordings"); onComplete?.(); }}>
                <Check className="mr-2 h-4 w-4" />
                Confirm
              </Button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="text-center py-8">
            <Check className="h-12 w-12 text-green-500 mx-auto mb-4" />
            <p className="text-lg font-medium">Upload complete</p>
            <p className="text-sm text-muted-foreground mt-1">
              {createdRecording?.original_filename} is now in your library.
            </p>
            <Button className="mt-4" onClick={resetWizard}>
              Upload another
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
