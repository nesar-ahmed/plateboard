import {
  BadgeCheck,
  Bell,
  ChefHat,
  CircleCheck,
  CircleX,
  KeyRound,
  MessageSquareText,
  Package,
  ShoppingBag,
  Sparkles,
  Star,
  Store,
  type LucideIcon,
} from "lucide-react";

import type { AppNotification, NotificationAudience, UnreadCounts, User } from "@/lib/api";

/**
 * How each notification type looks and where it leads. The *text* comes from
 * the backend (title/body); this file only picks the icon, the colour tone
 * (semantic tokens, so dark mode follows) and the link. Types mirror the
 * backend catalog (backend/app/modules/notifications/catalog.py); an unknown
 * type - one added to the backend first - still shows, with a plain bell.
 */
export type NotificationVisual = { icon: LucideIcon; tone: string };

const ACCENT = "bg-brand-soft text-brand";
const GOOD = "bg-herb-soft text-herb";
const HEADS_UP = "bg-saffron-soft text-saffron";
const BAD = "bg-danger-soft text-danger";
const QUIET = "bg-muted text-ink-muted";

const VISUALS: Record<string, NotificationVisual> = {
  "account.welcome": { icon: Sparkles, tone: ACCENT },
  "account.password_changed": { icon: KeyRound, tone: HEADS_UP },
  "cook_application.submitted": { icon: Store, tone: HEADS_UP },
  "cook_application.accepted": { icon: Store, tone: GOOD },
  "cook_application.rejected": { icon: Store, tone: QUIET },
  "kitchen.verified": { icon: BadgeCheck, tone: GOOD },
  "kitchen.verification_revoked": { icon: BadgeCheck, tone: QUIET },
  "order.placed": { icon: ShoppingBag, tone: HEADS_UP },
  "order.accepted": { icon: ChefHat, tone: ACCENT },
  "order.ready": { icon: Package, tone: ACCENT },
  "order.received": { icon: CircleCheck, tone: GOOD },
  "order.rejected": { icon: CircleX, tone: BAD },
  "order.cancelled_by_cook": { icon: CircleX, tone: BAD },
  "order.cancelled_by_customer": { icon: CircleX, tone: QUIET },
  "review.posted": { icon: Star, tone: HEADS_UP },
  "review.replied": { icon: MessageSquareText, tone: GOOD },
};

const FALLBACK: NotificationVisual = { icon: Bell, tone: QUIET };

export function notificationVisual(notification: AppNotification): NotificationVisual {
  return VISUALS[notification.type] ?? FALLBACK;
}

// --- inboxes ---------------------------------------------------------------------

/** One panel's inbox as the frontend shows it. */
export type Inbox = {
  audience: NotificationAudience;
  /** Tab label in the bell. */
  label: string;
  /** The panel it belongs to, and its full inbox page there. */
  panel: string;
  href: string;
  /** The role needed to see it (null: every signed-in user). */
  role: string | null;
  /** Shown by the frontend (a new inbox can be listed before its UI exists). */
  connected: boolean;
};

/** Role panels first (the inbox that needs acting on), the account last. */
export const INBOXES: Inbox[] = [
  { audience: "admin", label: "Admin", panel: "/admin", href: "/admin/notifications", role: "admin", connected: true },
  { audience: "cook", label: "Kitchen", panel: "/cook", href: "/cook/notifications", role: "cook", connected: true },
  { audience: "account", label: "Account", panel: "/account", href: "/account/notifications", role: null, connected: true },
];

/** The connected inboxes this user can read, in tab order. */
export function inboxesFor(user: User): Inbox[] {
  return INBOXES.filter((inbox) => inbox.connected && (inbox.role === null || user.roles.includes(inbox.role)));
}

/** Unread notifications across these inboxes (the bell's badge). */
export function unreadIn(inboxes: Inbox[], counts: UnreadCounts | null): number {
  return inboxes.reduce((sum, inbox) => sum + (counts?.[inbox.audience] ?? 0), 0);
}

/**
 * The inbox the bell opens on: the panel the user is in, else the first one
 * with unread notifications, else the first one.
 */
export function defaultInbox(inboxes: Inbox[], pathname: string, counts: UnreadCounts | null): Inbox {
  return (
    inboxes.find((inbox) => pathname === inbox.panel || pathname.startsWith(`${inbox.panel}/`)) ??
    inboxes.find((inbox) => (counts?.[inbox.audience] ?? 0) > 0) ??
    inboxes[0]
  );
}

// --- links ------------------------------------------------------------------------

/**
 * Where a notification leads, or null when there is nothing to open.
 *
 * * `/account`: orders open the order page; a cook's reply to a review opens
 *   the review (`/account/reviews/{id}`); a cook application's answer
 *   opens the kitchen panel (a kitchen once accepted; the application form
 *   to try again once rejected); security notices open login & security.
 * * `/cook`: an order (a new request, a customer's cancellation or
 *   confirmation of receipt) opens the kitchen's order page; a new review
 *   opens the reviews page with that review on top, ready for a reply; the
 *   verified badge (granted or removed) opens the kitchen profile.
 * * `/admin`: a new cook application opens the review queue; an order (a
 *   cook cancelling one they had accepted) opens that kitchen's cancelled
 *   orders with the order expanded.
 */
export function notificationHref(notification: AppNotification): string | null {
  if (notification.audience === "admin") return adminHref(notification);
  if (notification.audience === "cook") {
    if (notification.subject?.kind === "order") return `/cook/orders/${notification.subject.id}`;
    if (notification.subject?.kind === "review") return `/cook/reviews?open=${notification.subject.id}`;
    if (notification.type.startsWith("kitchen.")) return "/cook/profile";
    return null;
  }
  if (notification.audience !== "account") return null;
  if (notification.subject?.kind === "order") return `/account/orders/${notification.subject.id}`;
  if (notification.subject?.kind === "review") return `/account/reviews/${notification.subject.id}`;
  switch (notification.type) {
    case "account.welcome":
      return "/dishes";
    case "account.password_changed":
      return "/account/security";
    case "cook_application.accepted":
    case "cook_application.rejected":
      return "/cook";
    default:
      return null;
  }
}

function adminHref(notification: AppNotification): string | null {
  if (notification.type === "cook_application.submitted") return "/admin/applications";
  if (notification.subject?.kind !== "order") return null;
  const query = new URLSearchParams({ open: notification.subject.id });
  if (notification.type === "order.cancelled_by_cook") {
    query.set("tab", "cancelled");
    // The actor is the kitchen that cancelled; its name rides along for the chip.
    if (notification.actor_id) {
      query.set("cook_id", notification.actor_id);
      const cook = notification.data.cook_name;
      if (typeof cook === "string") query.set("cook", cook);
    }
  }
  return `/admin/orders?${query.toString()}`;
}
