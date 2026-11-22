"use client";

import {
  ArrowUpRight,
  Bell,
  Eye,
  LayoutDashboard,
  Receipt,
  ShieldCheck,
  Store,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Avatar, CountPill, cx } from "@/components/ui";
import { useAdminPanel } from "@/lib/admin-context";
import type { User } from "@/lib/api";
import { useNotifications } from "@/lib/notifications";

type Item = { href: string; label: string; icon: LucideIcon; badge?: "applications" | "unread" };

/** The admin panel's sections (same grouping idea as the account and cook panels). */
export const ADMIN_SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "Platform",
    items: [
      { href: "/admin", label: "Overview", icon: LayoutDashboard },
      { href: "/admin/users", label: "Users", icon: Users },
      { href: "/admin/orders", label: "Orders", icon: Receipt },
    ],
  },
  {
    title: "Review",
    items: [
      { href: "/admin/applications", label: "Cook applications", icon: Store, badge: "applications" },
      { href: "/admin/notifications", label: "Notifications", icon: Bell, badge: "unread" },
    ],
  },
];

const ALL_ITEMS = ADMIN_SECTIONS.flatMap((section) => section.items);

function useActive() {
  const pathname = usePathname();
  return (href: string) => (href === "/admin" ? pathname === "/admin" : pathname.startsWith(href));
}

/** The item's live count: pending applications, or unread admin notifications. */
function ItemBadge({ badge, active }: { badge: NonNullable<Item["badge"]>; active: boolean }) {
  const { pendingApplications } = useAdminPanel();
  const { counts } = useNotifications();
  const count = badge === "applications" ? (pendingApplications ?? 0) : (counts?.admin ?? 0);
  return (
    <CountPill
      count={count}
      active={active}
      label={badge === "applications" ? `${count} waiting for review` : `${count} unread`}
      className="ml-auto"
    />
  );
}

/** Desktop sidebar (from `lg`): identity, sections, shortcuts to the public site. */
export function AdminSidebar({ user }: { user: User }) {
  const isActive = useActive();
  return (
    <aside aria-label="Admin" className="hidden print:hidden lg:block">
      <div className="sticky top-24 space-y-6">
        <div className="flex items-center gap-3 px-2">
          <Avatar name={user.display_name ?? user.email} size="lg" />
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold text-ink">{user.display_name ?? "Admin"}</p>
            <p className="flex items-center gap-1 text-xs text-ink-soft">
              <ShieldCheck className="h-3 w-3" aria-hidden="true" /> Platform admin
            </p>
          </div>
        </div>

        <nav className="space-y-5">
          {ADMIN_SECTIONS.map((section) => (
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
          {[
            { href: "/dishes", label: "Public menu" },
            { href: "/cooks", label: "Cook directory" },
          ].map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="group flex items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 text-sm font-medium text-ink transition-shadow hover:shadow-card"
            >
              {link.label}
              <ArrowUpRight className="h-4 w-4 text-ink-soft transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </Link>
          ))}
          <div className="rounded-2xl border border-line bg-surface p-4">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-ink-muted">
              <Eye className="h-5 w-5" aria-hidden="true" />
            </span>
            <p className="mt-3 text-sm font-semibold text-ink">You see, they change</p>
            <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
              Orders and menus belong to their cooks and customers. Your switches: who may cook (Cook applications)
              and the verified badge (Users).
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}

/** Below `lg`: the same sections as a pill bar. */
export function AdminMobileNav() {
  const isActive = useActive();
  return (
    <nav
      aria-label="Admin sections"
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
