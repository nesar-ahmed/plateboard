"use client";

import {
  Bell,
  ChefHat,
  CreditCard,
  FileText,
  Heart,
  LayoutDashboard,
  Leaf,
  MapPin,
  Receipt,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Avatar, CountPill, cx } from "@/components/ui";
import type { User } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useNotifications } from "@/lib/notifications";
import { useSession } from "@/lib/session";

/** `role`: only shown to accounts holding it (favourites are for customers). */
type Item = { href: string; label: string; icon: LucideIcon; badge?: "unread"; role?: string };

/** The user panel's sections, grouped like the market leaders do. */
export const ACCOUNT_SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "Activity",
    items: [
      { href: "/account", label: "Overview", icon: LayoutDashboard },
      { href: "/account/orders", label: "Orders", icon: Receipt },
      { href: "/account/favourites", label: "Favourites", icon: Heart, role: "customer" },
      { href: "/account/invoices", label: "Invoices", icon: FileText },
      { href: "/account/notifications", label: "Notifications", icon: Bell, badge: "unread" },
    ],
  },
  {
    title: "Account",
    items: [
      { href: "/account/profile", label: "Profile", icon: UserRound },
      { href: "/account/addresses", label: "Addresses", icon: MapPin },
      { href: "/account/payments", label: "Payments", icon: CreditCard },
    ],
  },
  {
    title: "Settings",
    items: [
      { href: "/account/preferences", label: "Food preferences", icon: Leaf },
      { href: "/account/security", label: "Login & security", icon: ShieldCheck },
    ],
  },
];

/** The items this account may open. */
function visible(items: Item[], user: User | null): Item[] {
  return items.filter((item) => !item.role || !!user?.roles.includes(item.role));
}

function useActive() {
  const pathname = usePathname();
  return (href: string) => (href === "/account" ? pathname === "/account" : pathname.startsWith(href));
}

/** Unread notifications of the /account inbox, on the "Notifications" item. */
function UnreadBadge({ active }: { active: boolean }) {
  const unread = useNotifications().counts?.account ?? 0;
  return <CountPill count={unread} active={active} label={`${unread} unread`} className="ml-auto" />;
}

/** Desktop sidebar (from `lg`): identity, grouped sections, kitchen card. */
export function AccountSidebar({ user }: { user: User }) {
  const isActive = useActive();
  const isCook = user.roles.includes("cook");
  return (
    <aside aria-label="Account" className="hidden print:hidden lg:block">
      <div className="sticky top-24 space-y-6">
        <div className="flex items-center gap-3 px-2">
          <Avatar name={user.display_name ?? user.email} size="lg" />
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold text-ink">{user.display_name ?? "Your account"}</p>
            <p className="truncate text-xs text-ink-soft">Member since {formatDate(user.created_at)}</p>
          </div>
        </div>

        <nav className="space-y-5">
          {ACCOUNT_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft">
                {section.title}
              </p>
              <ul className="space-y-0.5">
                {visible(section.items, user).map((item) => {
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
                        {item.badge === "unread" && <UnreadBadge active={active} />}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <Link
          href="/cook"
          className="group block rounded-2xl border border-line bg-surface p-4 transition-shadow hover:shadow-card"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <ChefHat className="h-5 w-5" aria-hidden="true" />
          </span>
          <p className="mt-3 text-sm font-semibold text-ink">{isCook ? "My kitchen" : "Cook with Plateboard"}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
            {isCook ? "Manage your menu and cook profile." : "Share your cooking with the neighbourhood."}
          </p>
        </Link>
      </div>
    </aside>
  );
}

/** Below `lg`: the same sections as a swipeable pill bar. */
export function AccountMobileNav() {
  const isActive = useActive();
  const { user } = useSession();
  return (
    <nav
      aria-label="Account sections"
      className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] print:hidden sm:-mx-6 sm:px-6 lg:hidden"
    >
      {visible(
        ACCOUNT_SECTIONS.flatMap((section) => section.items),
        user,
      ).map((item) => {
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
            {item.badge === "unread" && <UnreadBadge active={active} />}
          </Link>
        );
      })}
    </nav>
  );
}
