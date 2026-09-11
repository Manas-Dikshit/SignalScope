"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import type { Data, Layout as PlotlyLayout, Config as PlotlyConfig } from "plotly.js-dist-min";
import { PALETTE, CHART_WATERFALL_COLORSCALE } from "@/lib/tokens";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[380px] items-center justify-center text-sm text-muted-foreground">
      Loading chart...
    </div>
  ),
});

interface PlotlyChartProps {
  data: Data[];
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  className?: string;
}

const commonAxis = {
  gridcolor: "hsl(217 18% 16%)",
  zerolinecolor: "hsl(217 18% 22%)",
  linecolor: "hsl(217 18% 22%)",
  tickfont: { color: PALETTE.mutedForeground, size: 11 },
  titlefont: { color: PALETTE.mutedForeground, size: 12 },
};

export function PlotlyChart({ data, layout = {}, config = {}, className }: PlotlyChartProps) {
  const fullLayout = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: {
      color: PALETTE.mutedForeground,
      size: 12,
      family: "var(--font-inter), system-ui, sans-serif",
    },
    margin: { l: 56, r: 24, t: 56, b: 56 },
    height: 400,
    colorway: [PALETTE.primary, PALETTE.secondary, PALETTE.warning],
    autosize: true as const,
    hoverlabel: {
      bgcolor: PALETTE.card,
      bordercolor: PALETTE.border,
      font: { color: PALETTE.foreground },
    },
    legend: {
      bgcolor: "rgba(0,0,0,0)",
      font: { color: PALETTE.mutedForeground },
      orientation: "h" as const,
      yanchor: "bottom" as const,
    },
    xaxis: commonAxis,
    yaxis: commonAxis,
    ...layout,
  };

  const fullConfig = {
    responsive: true,
    displayModeBar: false,
    toImageButtonOptions: { format: "svg", filename: "signalscope-chart", scale: 1 },
    ...config,
  };

  return (
    <div className={className}>
      <Plot
        data={data as Data[]}
        layout={fullLayout as PlotlyLayout}
        config={fullConfig as PlotlyConfig}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}

export { CHART_WATERFALL_COLORSCALE };
