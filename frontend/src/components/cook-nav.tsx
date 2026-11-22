"use client";

import {
  ArrowUpRight,
  Bell,
  Clock,
  LayoutDashboard,
  MapPin,
  Plus,
  Receipt,
  ShoppingBag,
  Star,
  Store,
  UtensilsCrossed,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Avatar, CountPill, cx } from "@/components/ui";
import type { User } from "@/lib/api";
import { useKitchen } from "@/lib/kitchen-context";
import { useNotifications } from "@/lib/notifications";

type Item = { href: string; label: string; icon: LucideIcon; badge?: "requests" | "reviews" | "unread" };

/** The cook panel's sections - same grouping idea as the account panel. */
export const COOK_SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "Kitchen",
    items: [
      { href: "/cook", label: "Overview", icon: LayoutDashboard },
      { href: "/cook/orders", label: "Orders", icon: Receipt, badge: "requests" },
      { href: "/cook/reviews", label: "Reviews", icon: Star, badge: "reviews" },
      { href: "/cook/notifications", label: "Notifications", icon: Bell, badge: "unread" },
      { href: "/cook/earnings", label: "Earnings", icon: Wallet },
    ],
  },
  {
    title: "Menu",
    items: [
      { href: "/cook/dishes", label: "Dishes", icon: UtensilsCrossed },
      { href: "/cook/dishes/new", label: "Add a dish", icon: Plus },
    ],
  },
  {
    title: "Settings",
    items: [
      { href: "/cook/profile", label: "Kitchen profile", icon: Store },
      { href: "/cook/hours", label: "Hours", icon: Clock },
    ],
  },
];

const ALL_ITEMS = COOK_SECTIONS.flatMap((section) => section.items);

/** The active item is the one with the longest matching href ("/cook/dishes/new" beats "/cook/dishes"). */
function useActive() {
  const pathname = usePathname();
  const matches = ALL_ITEMS.filter((item) =>
    item.href === "/cook" ? pathname === "/cook" : pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  const best = matches.sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (href: string) => href === best;
}

/** An item's live count: requests or reviews waiting for an answer, or unread kitchen notifications. */
function ItemBadge({ badge, active }: { badge: NonNullable<Item["badge"]>; active: boolean }) {
  const { requests, unrepliedReviews } = useKitchen();
  const { counts } = useNotifications();
  const count =
    badge === "requests" ? (requests ?? 0) : badge === "reviews" ? (unrepliedReviews ?? 0) : (counts?.cook ?? 0);
  const label = badge === "requests" ? `${count} waiting` : badge === "reviews" ? `${count} to answer` : `${count} unread`;
  return <CountPill count={count} active={active} label={label} className="ml-auto" />;
}

/** Desktop sidebar (from `lg`): identity, grouped sections, the account card. */
export function CookSidebar({ user }: { user: User }) {
  const isActive = useActive();
  const { profile } = useKitchen();
  return (
    <aside aria-label="Kitchen" className="hidden print:hidden lg:block">
      <div className="sticky top-24 space-y-6">
        <div className="flex items-center gap-3 px-2">
          <Avatar name={user.display_name ?? user.email} size="lg" />
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold text-ink">{user.display_name ?? "Your kitchen"}</p>
            <p className="flex items-center gap-1 truncate text-xs text-ink-soft">
              {profile?.zone ? (
                <>
                  <MapPin className="h-3 w-3 shrink-0" aria-hidden="true" /> {profile.zone.name}
                </>
              ) : (
                "Home kitchen"
              )}
            </p>
          </div>
        </div>

        <nav className="space-y-5">
          {COOK_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft">
                {section.title}
              </p>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const active = isActive(item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={cx(
                          "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                          active ? "bg-ink text-canvas" : "text-ink-muted hover:bg-muted hover:text-ink",
                        )}
                      >
                        <item.icon className="h-[18px] w-[18px]" aria-hidden="true" />
                        {item.label}
                        {item.badge && <ItemBadge badge={item.badge} active={active} />}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="space-y-2">
          <Link
            href={`/cooks/${user.id}`}
            className="group flex items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 text-sm font-medium text-ink transition-shadow hover:shadow-card"
          >
            View your public page
            <ArrowUpRight className="h-4 w-4 text-ink-soft transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
          </Link>
          <Link
            href="/account"
            className="group block rounded-2xl border border-line bg-surface p-4 transition-shadow hover:shadow-card"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-herb-soft text-herb">
              <ShoppingBag className="h-5 w-5" aria-hidden="true" />
            </span>
            <p className="mt-3 text-sm font-semibold text-ink">Your account</p>
            <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">Your own orders, addresses and settings.</p>
          </Link>
        </div>
      </div>
    </aside>
  );
}

/** Below `lg`: the same sections as a swipeable pill bar. */
export function CookMobileNav() {
  const isActive = useActive();
  return (
    <nav
      aria-label="Kitchen sections"
      className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] print:hidden sm:-mx-6 sm:px-6 lg:hidden"
    >
      {ALL_ITEMS.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "flex h-10 shrink-0 items-center gap-2 rounded-full border px-4 text-sm font-medium",
              active ? "border-ink bg-ink text-canvas" : "border-line bg-surface text-ink-muted",
            )}
          >
            <item.icon className="h-4 w-4" aria-hidden="true" />
            {item.label}
            {item.badge && <ItemBadge badge={item.badge} active={active} />}
          </Link>
        );
      })}
    </nav>
  );
}
