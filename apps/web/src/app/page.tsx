"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { formatBytes, formatDuration, formatFrequency } from "@/lib/utils";
import Link from "next/link";
import {
  Library,
  FolderOpen,
  Activity,
  Radio,
  ArrowRight,
} from "lucide-react";

export default function DashboardPage() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.stats,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <div className="text-muted-foreground text-sm">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <div className="text-destructive text-sm">
          Failed to load dashboard data.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Dashboard</h1>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Recordings</CardTitle>
            <Library className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.recording_count ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Projects</CardTitle>
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.project_count ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Running Jobs</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.running_jobs.length ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Running jobs */}
      {stats?.running_jobs && stats.running_jobs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Running Jobs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {stats.running_jobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between rounded-md border p-3"
              >
                <div className="space-y-1">
                  <div className="text-sm font-medium">
                    Job {job.id.slice(0, 8)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {job.status}
                  </div>
                </div>
                <Badge variant={job.status === "running" ? "default" : "secondary"}>
                  {job.status}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Recent projects */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Recent Projects</CardTitle>
        </CardHeader>
        <CardContent>
          {stats?.recent_projects && stats.recent_projects.length > 0 ? (
            <div className="space-y-2">
              {stats.recent_projects.map((project) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="flex items-center justify-between rounded-md border p-3 hover:bg-muted transition-colors"
                >
                  <div className="space-y-1">
                    <div className="text-sm font-medium">{project.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {project.recording?.filename ?? "Unknown recording"} ·{" "}
                      {new Date(project.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        project.status === "completed"
                          ? "default"
                          : project.status === "analyzing"
                          ? "secondary"
                          : "outline"
                      }
                    >
                      {project.status}
                    </Badge>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground py-4 text-center">
              No projects yet. Upload a recording to get started.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent recordings */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Recent Recordings</CardTitle>
          <Link
            href="/recordings"
            className="text-sm text-primary hover:underline"
          >
            View all
          </Link>
        </CardHeader>
        <CardContent>
          {stats?.recent_recordings && stats.recent_recordings.length > 0 ? (
            <div className="space-y-2">
              {stats.recent_recordings.map((rec) => (
                <div
                  key={rec.id}
                  className="flex items-center justify-between rounded-md border p-3"
                >
                  <div className="flex items-center gap-3">
                    <Radio className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="space-y-0.5">
                      <div className="text-sm font-medium">
                        {rec.name || rec.filename}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {rec.format.toUpperCase()} · {formatBytes(rec.file_size)}
                        {rec.metadata.duration_seconds
                          ? ` · ${formatDuration(rec.metadata.duration_seconds)}`
                          : ""}
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(rec.created_at).toLocaleDateString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground py-4 text-center">
              No recordings yet.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
