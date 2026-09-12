import * as React from "react";
import { cn, waveformPoints } from "@/lib/utils";
import { WAVEFORM_ART } from "@/lib/tokens";

/**
 * Small waveform glyph drawn from a recording's real preview samples
 * (I = cyan, Q = violet). Content-visual for library cards — decorative,
 * so the SVG is hidden from the accessibility tree.
 */
export default function WaveformThumb({
  samplesReal,
  samplesImag,
  className,
}: {
  samplesReal: number[];
  samplesImag?: number[];
  className?: string;
}) {
  const real = React.useMemo(() => waveformPoints(samplesReal, 96, 40), [samplesReal]);
  const imag = React.useMemo(
    () => (samplesImag ? waveformPoints(samplesImag, 96, 40) : ""),
    [samplesImag]
  );

  return (
    <svg
      viewBox="0 0 96 40"
      preserveAspectRatio="none"
      className={cn("h-10 w-24", className)}
      aria-hidden
      focusable="false"
    >
      <polyline
        points={real}
        fill="none"
        stroke={WAVEFORM_ART.trace}
        strokeWidth="1.2"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        opacity="0.9"
      />
      {imag && (
        <polyline
          points={imag}
          fill="none"
          stroke={WAVEFORM_ART.traceViolet}
          strokeWidth="0.9"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          opacity="0.7"
        />
      )}
    </svg>
  );
}