"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/ConfidenceIndicator";
import { formatBytes, formatDuration } from "@/lib/utils";
import Link from "next/link";
import { ArrowRight, FolderOpen, Radio } from "lucide-react";

export default function DashboardPage() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.stats,
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1 reveal">
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Dashboard
        </h1>
        <p className="text-sm text-muted-foreground">
          Overview of your RF analysis workspace.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-[110px] rounded-lg border bg-card shimmer" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/40 p-6 text-sm text-destructive">
          Failed to load dashboard data.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 reveal reveal-delay-1">
          <MetricCard
            label="Recordings"
            value={stats?.recording_count ?? 0}
            accent="primary"
            className="card-hover"
          />
          <MetricCard
            label="Projects"
            value={stats?.project_count ?? 0}
            accent="secondary"
            className="card-hover"
          />
          <MetricCard
            label="Active Jobs"
            value={stats?.running_jobs?.length ?? 0}
            accent={stats?.running_jobs?.length ? "warning" : "primary"}
            className="card-hover"
          />
        </div>
      )}

      {/* Running jobs */}
      {stats?.running_jobs && stats.running_jobs.length > 0 && (
        <Card className="reveal reveal-delay-2">
          <CardHeader>
            <CardTitle className="text-base font-display font-semibold">
              Running Jobs
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {stats.running_jobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between rounded-lg border p-3 transition-colors duration-150 hover:bg-muted/40"
              >
                <div className="space-y-1">
                  <div className="text-sm font-medium font-mono">
                    Job {job.id.slice(0, 8)}
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all duration-300"
                        style={{ width: `${job.progress_percent ?? 0}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {job.current_stage ?? job.status}
                    </span>
                  </div>
                </div>
                <span className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                  running
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Recent projects */}
      <Card className="reveal reveal-delay-2">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base font-display font-semibold">
            Recent Projects
          </CardTitle>
          <Link
            href="/recordings"
            className="text-xs text-primary hover:underline inline-flex items-center gap-1"
          >
            New analysis <ArrowRight className="h-3 w-3" />
          </Link>
        </CardHeader>
        <CardContent>
          {stats?.recent_projects && stats.recent_projects.length > 0 ? (
            <div className="divide-y divide-border rounded-lg border">
              {stats.recent_projects.map((project) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="group flex items-center justify-between px-4 py-3 transition-colors duration-150 hover:bg-muted/40"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10">
                      <FolderOpen className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{project.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(project.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          project.status === "completed"
                            ? "bg-confidence-high"
                            : project.status === "active"
                              ? "bg-primary"
                              : "bg-muted-foreground"
                        }`}
                      />
                      <span className="ml-1.5 text-muted-foreground">{project.status}</span>
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5" />
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No projects yet. Upload a recording to get started.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent recordings */}
      <Card className="reveal reveal-delay-3">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base font-display font-semibold">
            Recent Recordings
          </CardTitle>
          <Link href="/recordings" className="text-xs text-primary hover:underline">
            View library
          </Link>
        </CardHeader>
        <CardContent>
          {stats?.recent_recordings && stats.recent_recordings.length > 0 ? (
            <div className="divide-y divide-border rounded-lg border">
              {stats.recent_recordings.map((rec) => (
                <div
                  key={rec.id}
                  className="flex items-center justify-between px-4 py-3 transition-colors duration-150 hover:bg-muted/40"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary/10">
                      <Radio className="h-3.5 w-3.5 text-secondary" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {rec.original_filename}
                      </div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {rec.file_format.toUpperCase()} · {formatBytes(rec.file_size)}
                        {rec.duration_seconds
                          ? ` · ${formatDuration(rec.duration_seconds)}`
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
            <div className="py-8 text-center text-sm text-muted-foreground">
              No recordings yet.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}