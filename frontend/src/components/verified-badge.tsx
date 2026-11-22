import { BadgeCheck } from "lucide-react";

import { cx } from "@/components/ui";

/**
 * "Verified" - the kitchen was checked by the Plateboard team (an admin sets
 * it in the back office). Server-safe. `compact` shows only the icon (cards).
 */
export default function VerifiedBadge({ compact = false, className }: { compact?: boolean; className?: string }) {
  const label = "Verified by Plateboard - this kitchen was checked by our team";
  if (compact) {
    return (
      <span title={label} className={cx("inline-flex shrink-0 text-herb", className)}>
        <BadgeCheck className="h-5 w-5" aria-hidden="true" />
        <span className="sr-only">Verified kitchen</span>
      </span>
    );
  }
  return (
    <span
      title={label}
      className={cx(
        "inline-flex shrink-0 items-center gap-1 rounded-full bg-herb-soft px-2.5 py-0.5 text-xs font-semibold text-herb",
        className,
      )}
    >
      <BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" /> Verified
    </span>
  );
}
