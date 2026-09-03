"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface SliderProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange"> {
  value?: number[];
  defaultValue?: number[];
  max?: number;
  min?: number;
  step?: number;
  onValueChange?: (value: number[]) => void;
}

const Slider = React.forwardRef<HTMLDivElement, SliderProps>(
  (
    {
      className,
      min = 0,
      max = 100,
      step = 1,
      value: controlledValue,
      defaultValue,
      onValueChange,
      ...props
    },
    ref
  ) => {
    const [internalValue, setInternalValue] = React.useState<number[]>(
      defaultValue ?? [min]
    );
    const values = controlledValue ?? internalValue;

    const handleMinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newMin = Number(e.target.value);
      if (values.length === 2) {
        const clamped = Math.min(newMin, values[1] - step);
        const newValues = [clamped, values[1]];
        setInternalValue(newValues);
        onValueChange?.(newValues);
      } else {
        const newValues = [newMin];
        setInternalValue(newValues);
        onValueChange?.(newValues);
      }
    };

    const handleMaxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newMax = Number(e.target.value);
      const newValues = [values[0], newMax];
      setInternalValue(newValues);
      onValueChange?.(newValues);
    };

    const minPercent = ((values[0] - min) / (max - min)) * 100;
    const maxPercent =
      values.length === 2 ? ((values[1] - min) / (max - min)) * 100 : minPercent;

    return (
      <div ref={ref} className={cn("relative flex w-full touch-none select-none items-center", className)}>
        <div className="relative h-2 w-full grow overflow-hidden rounded-full bg-secondary">
          <div
            className="absolute h-full bg-primary"
            style={{
              left: `${values.length === 2 ? minPercent : 0}%`,
              right: `${100 - maxPercent}%`,
            }}
          />
        </div>
        {values.length === 2 ? (
          <>
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              value={values[0]}
              onChange={handleMinChange}
              className="absolute w-full appearance-none bg-transparent [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-primary [&::-webkit-slider-thumb]:bg-background [&::-webkit-slider-thumb]:shadow-md"
              {...props}
            />
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              value={values[1]}
              onChange={handleMaxChange}
              className="absolute w-full appearance-none bg-transparent [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-primary [&::-webkit-slider-thumb]:bg-background [&::-webkit-slider-thumb]:shadow-md"
            />
          </>
        ) : (
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={values[0]}
            onChange={handleMinChange}
            className="absolute w-full appearance-none bg-transparent [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-primary [&::-webkit-slider-thumb]:bg-background [&::-webkit-slider-thumb]:shadow-md"
            {...props}
          />
        )}
      </div>
    );
  }
);
Slider.displayName = "Slider";

export { Slider };
