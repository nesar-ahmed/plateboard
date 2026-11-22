import Link from "next/link";

import { cx } from "@/components/ui";

/** Wordmark: a plate-and-steam mark + "Plateboard" in the display face. */
export default function Logo({
  className,
  tone = "ink",
  onClick,
}: {
  className?: string;
  tone?: "ink" | "night";
  onClick?: () => void;
}) {
  return (
    <Link
      href="/"
      onClick={onClick}
      aria-label="Plateboard home"
      className={cx("flex shrink-0 items-center gap-2.5", className)}
    >
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden="true">
        <rect width="32" height="32" rx="10" className="fill-brand" />
        <circle cx="16" cy="19" r="8.5" fill="none" stroke="white" strokeWidth="2" />
        <circle cx="16" cy="19" r="4.5" fill="white" fillOpacity="0.9" />
        <path
          d="M12.5 9.5c0-1.5 1.5-1.5 1.5-3M17.5 9.5c0-1.5 1.5-1.5 1.5-3"
          fill="none"
          stroke="white"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
      <span
        className={cx(
          "font-display text-xl font-semibold tracking-tight",
          tone === "night" ? "text-on-night" : "text-ink",
        )}
      >
        Plateboard
      </span>
    </Link>
  );
}
