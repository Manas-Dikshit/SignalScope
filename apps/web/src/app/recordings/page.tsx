"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { recordingsApi, projectsApi } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { UploadWizard } from "@/components/UploadWizard";
import { formatBytes, formatDuration, formatFrequency } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import {
  Upload,
  Trash2,
  Clock,
  FileAudio,
  Plus,
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
          <h1 className="text-3xl font-bold">Upload Recording</h1>
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
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Recording Library</h1>
        <Button onClick={() => setShowUpload(true)}>
          <Upload className="mr-2 h-4 w-4" />
          Upload
        </Button>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-sm">Loading recordings...</div>
      ) : !recordings || recordings.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FileAudio className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No recordings</p>
            <p className="text-sm text-muted-foreground mt-1 mb-4">
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
              <Card key={rec.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-4 min-w-0 flex-1">
                    <FileAudio className="h-8 w-8 text-primary shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">
                        {rec.original_filename}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground mt-1">
                        <Badge variant="outline" className="text-[10px]">
                          {rec.file_format.toUpperCase()}
                        </Badge>
                        <span>{formatBytes(rec.file_size)}</span>
                        {rec.duration_seconds && (
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatDuration(rec.duration_seconds)}
                          </span>
                        )}
                        {meta?.sample_rate && (
                          <span>{formatFrequency(meta.sample_rate)}</span>
                        )}
                        {meta?.center_frequency && (
                          <span>@ {formatFrequency(meta.center_frequency)}</span>
                        )}
                        <span>{(rec.total_samples || 0).toLocaleString()} samples</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    <Button
                      size="sm"
                      onClick={() =>
                        createProjectMutation.mutate(rec.id)
                      }
                      disabled={createProjectMutation.isPending}
                    >
                      <Plus className="mr-1 h-3 w-3" />
                      Analyze
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => {
                        if (
                          confirm(
                            `Delete "${rec.original_filename}"? This cannot be undone.`
                          )
                        ) {
                          deleteMutation.mutate(rec.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
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
