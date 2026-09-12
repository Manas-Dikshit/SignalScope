import { WAVEFORM_ART } from "@/lib/tokens";

/**
 * Schematic blueprint backdrop for the analysis workspace: fine drafting grid
 * with major intersection lines and corner registration marks. Decorative —
 * hidden from the accessibility tree.
 */
export default function BlueprintBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0">
      <div className="blueprint-grid absolute inset-0" />
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" focusable="false">
        <g
          stroke={WAVEFORM_ART.corner}
          strokeWidth="2"
          fill="none"
          vectorEffect="non-scaling-stroke"
        >
          <path d="M 3 13 V 3 H 13" />
          <path d="M 87 3 H 97 V 13" />
          <path d="M 3 97 V 87 H 13" />
          <path d="M 87 97 H 97 V 87" />
        </g>
      </svg>
    </div>
  );
}