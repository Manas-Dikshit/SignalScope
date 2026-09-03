"use client";

import dynamic from "next/dynamic";
import type { Data, Layout, Config } from "plotly.js-dist-min";

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
  layout?: Partial<Layout>;
  config?: Partial<Config>;
  className?: string;
  useWebGL?: boolean;
}

export function PlotlyChart({
  data,
  layout = {},
  config = {},
  className,
  useWebGL = false,
}: PlotlyChartProps) {
  const defaultLayout: Partial<Layout> = {
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

  const defaultConfig: Partial<Config> = {
    responsive: true,
    displayModeBar: false,
    ...config,
  };

  return (
    <div className={className}>
      <Plot
        data={data}
        layout={defaultLayout}
        config={defaultConfig}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}

export type { Data, Layout };
