"use client";

import * as React from "react";
import { BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlotlyChart } from "@/components/PlotlyChart";
import { cn } from "@/lib/utils";
import type { Data } from "plotly.js-dist-min";

/**
 * Button that toggles a Plotly chart into view. Uses the project's existing
 * Plotly palette/fonts so graphs match the rest of the workspace.
 */
export function GraphToggle({
  data,
  title,
  layout = {},
}: {
  data: Data[];
  title: string;
  layout?: Record<string, unknown>;
}) {
  const [shown, setShown] = React.useState(false);

  return (
    <div className="space-y-2">
      <Button variant="outline" size="sm" onClick={() => setShown((s) => !s)}>
        <BarChart3 className={cn("h-3.5 w-3.5", shown && "text-primary")} />
        {shown ? "Hide graph" : "View graphically"}
      </Button>
      {shown && (
        <div className="rounded-lg border bg-card/40 p-2">
          <PlotlyChart data={data} layout={{ title, height: 360, ...layout }} />
        </div>
      )}
    </div>
  );
}