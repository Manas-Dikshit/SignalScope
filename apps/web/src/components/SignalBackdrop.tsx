"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { WAVEFORM_ART } from "@/lib/tokens";

type Variant = "full" | "hero";

// Deterministic PRNG (mulberry32) — the artwork is identical across
// renders and hydration, so SSR/client DOM match.
function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const W = 1440;
const H = 520;
const N = 220;

interface TraceParams {
  seed: number;
  freq: number;
  phase: number;
  amp: number;
  bias: number;
  burst?: { x: number; width: number };
}

function buildTrace({ seed, freq, phase, amp, bias, burst }: TraceParams): string {
  const rnd = mulberry32(seed);
  const pts: string[] = [];
  for (let i = 0; i <= N; i++) {
    const x = (i / N) * W;
    let y =
      0.45 * Math.sin(x * freq + phase) +
      0.22 * Math.sin(x * freq * 1.9 + phase * 1.7) +
      (rnd() - 0.5) * 0.32;
    if (burst) {
      y +=
        Math.pow(Math.E, -Math.pow((x - burst.x) / burst.width, 2)) *
        Math.sin(x * 0.28 + phase) *
        0.5;
    }
    const env = 0.3 + 0.7 * Math.pow(Math.sin((Math.PI * i) / N), 0.5);
    const py = H / 2 + bias * H * 0.16 + (y * env * amp * H) / 2.7;
    pts.push(`${x.toFixed(1)},${py.toFixed(1)}`);
  }
  return pts.join(" ");
}

function buildTraces() {
  return {
    glowBand: buildTrace({
      seed: 7,
      freq: 0.017,
      phase: 0.4,
      amp: 0.62,
      bias: 0,
      burst: { x: W * 0.42, width: 26 },
    }),
    traceI: buildTrace({
      seed: 11,
      freq: 0.023,
      phase: 1.1,
      amp: 0.5,
      bias: 0.06,
      burst: { x: W * 0.42, width: 22 },
    }),
    traceQ: buildTrace({
      seed: 23,
      freq: 0.031,
      phase: 2.6,
      amp: 0.4,
      bias: -0.1,
      burst: { x: W * 0.68, width: 18 },
    }),
  };
}

function useReducedMotion() {
  return React.useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
      mq?.addEventListener("change", cb);
      return () => mq?.removeEventListener("change", cb);
    },
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
    () => false
  );
}

export default function SignalBackdrop({
  variant = "full",
  className,
}: {
  variant?: Variant;
  className?: string;
}) {
  const { glowBand, traceI, traceQ } = React.useMemo(buildTraces, []);
  const parallaxRef = React.useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();

  React.useEffect(() => {
    if (variant !== "hero" || reducedMotion) return;
    const el = parallaxRef.current;
    if (!el) return;
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const y = Math.min(window.scrollY, 500) * 0.18;
        el.style.transform = `translate3d(0, ${y}px, 0)`;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
      el.style.transform = "";
    };
  }, [variant, reducedMotion]);

  return (
    <div
      className={cn(
        "aurora-bg",
        variant === "hero" && "absolute z-0",
        className
      )}
      aria-hidden
    >
      <div
        ref={parallaxRef}
        className={cn(variant === "hero" && "signal-parallax")}
      >
        <div className="signal-traces">
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            focusable="false"
          >
            <defs>
              <filter id="sb-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="12" />
              </filter>
              <linearGradient id="sb-fade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={WAVEFORM_ART.trace} stopOpacity="0" />
                <stop offset="0.2" stopColor={WAVEFORM_ART.trace} stopOpacity="0.1" />
                <stop offset="0.8" stopColor={WAVEFORM_ART.traceViolet} stopOpacity="0.08" />
                <stop offset="1" stopColor={WAVEFORM_ART.traceViolet} stopOpacity="0" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width={W} height={H} fill="url(#sb-fade)" />
            <polyline
              points={glowBand}
              fill="none"
              stroke={WAVEFORM_ART.trace}
              strokeWidth="10"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              opacity="0.09"
              filter="url(#sb-glow)"
            />
            <polyline
              points={traceI}
              fill="none"
              stroke={WAVEFORM_ART.trace}
              strokeWidth="1.5"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              opacity="0.32"
            />
            <polyline
              points={traceQ}
              fill="none"
              stroke={WAVEFORM_ART.traceViolet}
              strokeWidth="1.2"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              opacity="0.24"
            />
          </svg>
        </div>
      </div>
    </div>
  );
}