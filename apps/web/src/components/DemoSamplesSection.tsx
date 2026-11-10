"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { recordingsApi, projectsApi } from "@/lib/api";
import type { DemoSampleItem, Recording } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Radio, Sparkles, Loader2, Play, Plus, Zap } from "lucide-react";

const FALLBACK_DEMOS: DemoSampleItem[] = [
  {
    id: "qpsk_48k",
    name: "QPSK Carrier (48 kHz)",
    description: "Clean 4-phase PSK constellation at 2400 baud with 25 dB SNR. Great for constellation & symbol rate checks.",
    modulation: "qpsk",
    sample_rate_hz: 48000,
    symbol_rate_hz: 2400,
    snr_db: 25,
    filename: "demo_qpsk_48k.wav",
  },
  {
    id: "2fsk_48k",
    name: "2-FSK Binary FSK (48 kHz)",
    description: "Binary Frequency Shift Keying at 1200 baud with 1.2 kHz deviation tone spacing.",
    modulation: "2fsk",
    sample_rate_hz: 48000,
    symbol_rate_hz: 1200,
    snr_db: 20,
    filename: "demo_2fsk_48k.wav",
  },
  {
    id: "16qam_48k",
    name: "16-QAM Grid (48 kHz)",
    description: "16-state Quadrature Amplitude Modulation grid at 2400 baud with 30 dB SNR.",
    modulation: "16qam",
    sample_rate_hz: 48000,
    symbol_rate_hz: 2400,
    snr_db: 30,
    filename: "demo_16qam_48k.wav",
  },
  {
    id: "bpsk_burst_48k",
    name: "BPSK Pulsed Bursts (48 kHz)",
    description: "Intermittent pulsed BPSK signal with duty cycle, ideal for testing burst detection & power profiles.",
    modulation: "bpsk",
    sample_rate_hz: 48000,
    symbol_rate_hz: 2400,
    snr_db: 22,
    filename: "demo_bpsk_burst_48k.wav",
  },
  {
    id: "8psk_48k",
    name: "8-PSK Circular (48 kHz)",
    description: "8-phase circular phase shift keying at 2400 baud with 25 dB SNR.",
    modulation: "8psk",
    sample_rate_hz: 48000,
    symbol_rate_hz: 2400,
    snr_db: 25,
    filename: "demo_8psk_48k.wav",
  },
];

interface DemoSamplesSectionProps {
  variant?: "compact" | "full";
  onSampleLoaded?: (recording: Recording) => void;
  autoAnalyze?: boolean;
}

export function DemoSamplesSection({
  variant = "full",
  onSampleLoaded,
  autoAnalyze = false,
}: DemoSamplesSectionProps) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const { addToast } = useToast();
  const [loadingId, setLoadingId] = React.useState<string | null>(null);

  const { data: serverDemos } = useQuery({
    queryKey: ["demo-samples"],
    queryFn: recordingsApi.listDemos,
    staleTime: 1000 * 60 * 10,
  });

  const demos = serverDemos && serverDemos.length > 0 ? serverDemos : FALLBACK_DEMOS;

  const loadMutation = useMutation({
    mutationFn: async ({ sampleId, analyze }: { sampleId: string; analyze: boolean }) => {
      setLoadingId(sampleId);
      const recording = await recordingsApi.loadDemo(sampleId);
      if (analyze || autoAnalyze) {
        const project = await projectsApi.create({
          name: `${recording.original_filename.replace(/\.wav$/i, "")} Analysis`,
          recording_id: recording.id,
        });
        return { recording, project };
      }
      return { recording, project: null };
    },
    onSuccess: ({ recording, project }) => {
      queryClient.invalidateQueries({ queryKey: ["recordings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });

      addToast({
        title: "Demo signal loaded",
        description: `"${recording.original_filename}" is now in your recordings.`,
      });

      if (onSampleLoaded) {
        onSampleLoaded(recording);
      }

      if (project) {
        router.push(`/projects/${project.id}`);
      }
    },
    onError: (err: Error) => {
      addToast({
        title: "Failed to load demo",
        description: err.message,
        variant: "destructive",
      });
    },
    onSettled: () => {
      setLoadingId(null);
    },
  });

  if (variant === "compact") {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span>Quick Start with Demo Samples:</span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {demos.slice(0, 3).map((demo) => {
            const isLoading = loadingId === demo.id;
            return (
              <button
                key={demo.id}
                type="button"
                disabled={Boolean(loadingId)}
                onClick={() => loadMutation.mutate({ sampleId: demo.id, analyze: false })}
                className="flex items-center justify-between rounded-lg border border-border/70 bg-card/60 p-2.5 text-left transition-all hover:border-primary/50 hover:bg-muted/40 disabled:opacity-50"
              >
                <div className="min-w-0 pr-2">
                  <div className="flex items-center gap-1.5">
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary uppercase">
                      {demo.modulation}
                    </span>
                    <span className="truncate text-xs font-medium text-foreground">
                      {demo.name}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    {demo.sample_rate_hz / 1000} kHz · {demo.symbol_rate_hz} baud · {demo.snr_db} dB SNR
                  </div>
                </div>
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
                ) : (
                  <Plus className="h-4 w-4 text-muted-foreground shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <Card className="border border-primary/20 bg-gradient-to-br from-card to-primary/5 shadow-elevation-1">
      <CardContent className="p-5 sm:p-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-display text-base font-semibold text-foreground">
                Demo Signals Library
              </h3>
              <p className="text-xs text-muted-foreground">
                No local RF files handy? Pick a pre-synthesized signal to explore the pipeline immediately.
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {demos.map((demo) => {
            const isLoading = loadingId === demo.id;
            return (
              <div
                key={demo.id}
                className="group relative flex flex-col justify-between rounded-xl border border-border/80 bg-card p-4 transition-all duration-200 hover:border-primary/50 hover:shadow-elevation-1"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary uppercase tracking-wide">
                      {demo.modulation}
                    </span>
                    <span className="text-[11px] font-mono text-muted-foreground">
                      {demo.snr_db} dB SNR
                    </span>
                  </div>

                  <h4 className="font-medium text-sm text-foreground line-clamp-1">
                    {demo.name}
                  </h4>
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                    {demo.description}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-border/50">
                  <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground mb-3">
                    <span>Fs: {demo.sample_rate_hz / 1000} kHz</span>
                    <span>Rs: {demo.symbol_rate_hz} Bd</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 text-xs h-8"
                      disabled={Boolean(loadingId)}
                      onClick={() => loadMutation.mutate({ sampleId: demo.id, analyze: false })}
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                          Loading...
                        </>
                      ) : (
                        <>
                          <Plus className="mr-1.5 h-3.5 w-3.5" />
                          Add to Library
                        </>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      className="text-xs h-8 px-3"
                      disabled={Boolean(loadingId)}
                      onClick={() => loadMutation.mutate({ sampleId: demo.id, analyze: true })}
                      title="Add and start project analysis immediately"
                    >
                      {isLoading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <>
                          <Zap className="mr-1 h-3.5 w-3.5" />
                          Analyze
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
