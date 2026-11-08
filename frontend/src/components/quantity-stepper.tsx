"use client";

/**
 * − [n] + control. Purely presentational: the parent decides what a step
 * does (local state on the dish page, a PATCH ... {delta} in the cart).
 */
export default function QuantityStepper({
  value,
  min = 1,
  max = 100,
  disabled = false,
  label,
  onStep,
}: {
  value: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  /** Accessible name, e.g. "Quantity of Veg curry". */
  label: string;
  onStep: (delta: 1 | -1) => void;
}) {
  const button =
    "flex h-8 w-8 items-center justify-center rounded-full border border-zinc-300 text-base font-medium " +
    "text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40 " +
    "dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800";
  return (
    <div className="inline-flex items-center gap-2" role="group" aria-label={label}>
      <button
        type="button"
        className={button}
        disabled={disabled || value <= min}
        onClick={() => onStep(-1)}
        aria-label="Decrease quantity"
      >
        −
      </button>
      <span className="w-8 text-center font-mono text-sm tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className={button}
        disabled={disabled || value >= max}
        onClick={() => onStep(1)}
        aria-label="Increase quantity"
      >
        +
      </button>
    </div>
  );
}
