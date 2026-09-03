import * as React from "react";
import dynamic from "next/dynamic";
import type { Data, Layout as PlotlyLayout, Config as PlotlyConfig } from "plotly.js-dist-min";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[350px] items-center justify-center text-muted-foreground text-sm">
      Loading chart...
    </div>
  ),
});

interface PlotlyChartProps {
  data: Data[];
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  className?: string;
  useWebGL?: boolean;
}

export function PlotlyChart({
  data,
  layout = {},
  config = {},
  className,
}: PlotlyChartProps) {
  const defaultLayout: Record<string, unknown> = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#94a3b8", size: 12 },
    margin: { l: 50, r: 20, t: 40, b: 50 },
    xaxis: {
      gridcolor: "hsl(217, 33%, 17%)",
      zerolinecolor: "hsl(217, 33%, 17%)",
    },
    yaxis: {
      gridcolor: "hsl(217, 33%, 17%)",
      zerolinecolor: "hsl(217, 33%, 17%)",
    },
    height: 350,
    ...layout,
  };

  const defaultConfig: Record<string, unknown> = {
    responsive: true,
    displayModeBar: false,
    ...config,
  };

  return (
    <div className={className}>
      <Plot
        data={data as Data[]}
        layout={defaultLayout as PlotlyLayout}
        config={defaultConfig as PlotlyConfig}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}
