import { ArrowUpRight, MapPin } from "lucide-react";
import Link from "next/link";

import { AvailabilityPill } from "@/components/availability";
import { Avatar, cx } from "@/components/ui";
import VerifiedBadge from "@/components/verified-badge";
import type { CookPublic } from "@/lib/api";

/**
 * A cook in a directory/grid: face (initials), name (+ verified check),
 * headline, specialties, whether the kitchen takes orders now, zone.
 */
export default function CookCard({ cook, className }: { cook: CookPublic; className?: string }) {
  return (
    <article
      className={cx(
        "group relative flex h-full flex-col rounded-3xl border border-line bg-surface p-6 shadow-card",
        "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift",
        className,
      )}
    >
      <div className="flex items-start justify-between">
        <Avatar name={cook.display_name} size="lg" />
        <ArrowUpRight
          aria-hidden="true"
          className="h-5 w-5 text-ink-soft transition-all group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-brand"
        />
      </div>
      <h3 className="mt-4 flex items-center gap-1.5 font-display text-xl font-semibold tracking-tight text-ink">
        <Link
          href={`/cooks/${cook.user_id}`}
          className="min-w-0 truncate after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
        >
          {cook.display_name ?? "A home cook"}
        </Link>
        {cook.verified && <VerifiedBadge compact />}
      </h3>
      <p className="mt-1 text-sm leading-relaxed text-ink-muted">{cook.headline}</p>
      <div className="mt-auto pt-5">
        {cook.specialties.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {cook.specialties.map((specialty) => (
              <span
                key={specialty}
                className="rounded-full border border-line px-2.5 py-0.5 text-xs font-medium capitalize text-ink-muted"
              >
                {specialty}
              </span>
            ))}
          </div>
        )}
        <AvailabilityPill availability={cook.availability} className="mt-4" />
        {(cook.zone || cook.area) && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-soft">
            <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
            {[cook.zone?.name, cook.area].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>
    </article>
  );
}
