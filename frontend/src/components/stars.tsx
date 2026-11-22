import { Star } from "lucide-react";

import { cx } from "@/components/ui";

const SIZES = { xs: "h-3.5 w-3.5", sm: "h-4 w-4", md: "h-5 w-5", lg: "h-6 w-6" } as const;

function Row({ size, className }: { size: keyof typeof SIZES; className: string }) {
  return (
    <span className={cx("flex gap-0.5", className)} aria-hidden="true">
      {[0, 1, 2, 3, 4].map((index) => (
        <Star key={index} className={cx(SIZES[size], "shrink-0")} fill="currentColor" strokeWidth={0} />
      ))}
    </span>
  );
}

/**
 * Read-only stars (server-safe). Fractions show as a partly filled star: a
 * filled row clipped to `value / 5` of the width lies over an empty row.
 */
export default function Stars({
  value,
  size = "sm",
  className,
}: {
  value: number;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(5, value));
  return (
    <span
      role="img"
      aria-label={`${Number.isInteger(clamped) ? clamped : clamped.toFixed(1)} out of 5 stars`}
      className={cx("relative inline-flex shrink-0", className)}
    >
      <Row size={size} className="text-line-strong" />
      <span className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${(clamped / 5) * 100}%` }}>
        <Row size={size} className="text-brand" />
      </span>
    </span>
  );
}
