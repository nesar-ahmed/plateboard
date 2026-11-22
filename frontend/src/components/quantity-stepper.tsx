"use client";

import { Minus, Plus } from "lucide-react";

import { cx } from "@/components/ui";

/**
 * − [n] + control. Purely presentational: the parent decides what a step
 * does (local state on the dish page, a PATCH ... {delta} in the cart).
 */
export default function QuantityStepper({
  value,
  min = 1,
  max = 100,
  disabled = false,
  size = "md",
  label,
  onStep,
}: {
  value: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  /** Accessible name, e.g. "Quantity of Veg curry". */
  label: string;
  onStep: (delta: 1 | -1) => void;
}) {
  const box = { sm: "h-8", md: "h-10", lg: "h-12" }[size];
  const button = cx(
    "flex aspect-square h-full items-center justify-center rounded-full text-ink transition-colors",
    "hover:bg-muted disabled:cursor-not-allowed disabled:opacity-35",
  );
  const icon = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  return (
    <div
      className={cx("inline-flex items-center rounded-full border border-line-strong bg-surface p-0.5", box)}
      role="group"
      aria-label={label}
    >
      <button
        type="button"
        className={button}
        disabled={disabled || value <= min}
        onClick={() => onStep(-1)}
        aria-label="Decrease quantity"
      >
        <Minus className={icon} strokeWidth={2.25} />
      </button>
      <span
        className={cx("min-w-8 text-center font-semibold tabular-nums", size === "sm" ? "text-sm" : "text-base")}
        aria-live="polite"
      >
        {value}
      </span>
      <button
        type="button"
        className={button}
        disabled={disabled || value >= max}
        onClick={() => onStep(1)}
        aria-label="Increase quantity"
      >
        <Plus className={icon} strokeWidth={2.25} />
      </button>
    </div>
  );
}
