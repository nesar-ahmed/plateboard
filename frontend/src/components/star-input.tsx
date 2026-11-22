"use client";

import { Star } from "lucide-react";
import { useState } from "react";

import { cx } from "@/components/ui";
import { RATING_LABELS } from "@/lib/reviews";

/**
 * Pick 1..5 stars. Real radio inputs underneath, so arrow keys, focus and
 * screen readers work natively; hovering previews a rating and its label.
 */
export default function StarInput({
  value,
  onChange,
  disabled = false,
  name = "rating",
}: {
  value: number | null;
  onChange: (rating: number) => void;
  disabled?: boolean;
  name?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const shown = hover ?? value ?? 0;
  return (
    <fieldset disabled={disabled} className="min-w-0">
      <legend className="sr-only">Your rating</legend>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="-ml-1 flex" onMouseLeave={() => setHover(null)}>
          {[1, 2, 3, 4, 5].map((stars) => (
            <label key={stars} className="cursor-pointer p-1" onMouseEnter={() => setHover(stars)}>
              <input
                type="radio"
                name={name}
                value={stars}
                checked={value === stars}
                onChange={() => onChange(stars)}
                className="peer sr-only"
              />
              <Star
                className={cx(
                  "h-8 w-8 rounded-md transition-transform duration-100 hover:scale-110",
                  "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand",
                  stars <= shown ? "text-brand" : "text-line-strong",
                )}
                fill="currentColor"
                strokeWidth={0}
                aria-hidden="true"
              />
              <span className="sr-only">
                {stars} {stars === 1 ? "star" : "stars"} - {RATING_LABELS[stars]}
              </span>
            </label>
          ))}
        </div>
        <span className="text-sm font-semibold text-ink-muted" aria-hidden="true">
          {shown ? RATING_LABELS[shown] : "Tap a star to rate"}
        </span>
      </div>
    </fieldset>
  );
}
