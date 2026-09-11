"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { recordingsApi, projectsApi } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { UploadWizard } from "@/components/UploadWizard";
import { formatBytes, formatDuration, formatFrequency } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import {
  Upload,
  Trash2,
  Clock,
  Radio,
  Plus,
  FileAudio,
} from "lucide-react";

export default function RecordingsPage() {
  const [showUpload, setShowUpload] = React.useState(false);
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const { data: recordings, isLoading } = useQuery({
    queryKey: ["recordings"],
    queryFn: recordingsApi.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => recordingsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recordings"] });
      addToast({ title: "Recording deleted" });
    },
    onError: (err: Error) => {
      addToast({
        title: "Delete failed",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  const createProjectMutation = useMutation({
    mutationFn: (recordingId: string) =>
      projectsApi.create({ recording_id: recordingId }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      window.location.href = `/projects/${project.id}`;
    },
    onError: (err: Error) => {
      addToast({
        title: "Failed to create project",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  if (showUpload) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            Upload Recording
          </h1>
          <Button variant="ghost" onClick={() => setShowUpload(false)}>
            Cancel
          </Button>
        </div>
        <UploadWizard onComplete={() => setShowUpload(false)} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between reveal">
        <div className="space-y-1">
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            Recording Library
          </h1>
          <p className="text-sm text-muted-foreground">
            WAV, raw I/Q, and SigMF recordings for analysis.
          </p>
        </div>
        <Button onClick={() => setShowUpload(true)} className="shrink-0 w-full sm:w-auto">
          <Upload className="mr-2 h-4 w-4" />
          Upload
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-lg border bg-card shimmer" />
          ))}
        </div>
      ) : !recordings || recordings.length === 0 ? (
        <Card className="reveal reveal-delay-1">
          <CardContent className="flex flex-col items-center justify-center py-14">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-secondary/10">
              <FileAudio className="h-7 w-7 text-secondary" />
            </div>
            <p className="text-lg font-display font-semibold">No recordings</p>
            <p className="mt-1 mb-5 text-sm text-muted-foreground">
              Upload a WAV, Raw IQ, or SigMF recording to get started.
            </p>
            <Button onClick={() => setShowUpload(true)}>
              <Upload className="mr-2 h-4 w-4" />
              Upload your first recording
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {recordings.map((rec) => {
            const meta = rec.metadata_entry;
            return (
              <Card key={rec.id} className="card-hover reveal">
                <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-4 min-w-0 flex-1">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                      <Radio className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">
                        {rec.original_filename}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-mono text-muted-foreground">
                        <span className="rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider">
                          {rec.file_format.toUpperCase()}
                        </span>
                        <span>{formatBytes(rec.file_size)}</span>
                        {rec.duration_seconds && (
                          <span className="inline-flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatDuration(rec.duration_seconds)}
                          </span>
                        )}
                        {meta?.sample_rate && <span>{formatFrequency(meta.sample_rate)}</span>}
                        {meta?.center_frequency && (
                          <span>@ {formatFrequency(meta.center_frequency)}</span>
                        )}
                        <span>{(rec.total_samples || 0).toLocaleString()} samples</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      size="sm"
                      onClick={() => createProjectMutation.mutate(rec.id)}
                      disabled={createProjectMutation.isPending}
                    >
                      <Plus className="mr-1 h-3 w-3" />
                      Analyze
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => {
                        if (confirm(`Delete "${rec.original_filename}"? This cannot be undone.`)) {
                          deleteMutation.mutate(rec.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      aria-label={`Delete ${rec.original_filename}`}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
