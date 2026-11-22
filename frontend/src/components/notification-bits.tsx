/**
 * Pieces shared by the header bell and the inbox pages (server-safe: no
 * hooks). The copy itself is the backend's `title` / `body`; the icon, tone
 * and link come from lib/notification-kinds.ts.
 */

import { cx } from "@/components/ui";
import type { AppNotification } from "@/lib/api";
import { formatDateTime, formatRelative } from "@/lib/format";
import { notificationVisual } from "@/lib/notification-kinds";

/** The type's icon on its tinted tile. */
export function NotificationIcon({
  notification,
  size = "md",
}: {
  notification: AppNotification;
  size?: "sm" | "md";
}) {
  const { icon: Icon, tone } = notificationVisual(notification);
  return (
    <span
      className={cx(
        "flex shrink-0 items-center justify-center",
        size === "sm" ? "h-9 w-9 rounded-xl" : "h-10 w-10 rounded-xl",
        tone,
      )}
    >
      <Icon className={size === "sm" ? "h-[18px] w-[18px]" : "h-5 w-5"} aria-hidden="true" />
    </span>
  );
}

/** "12 min ago", with the exact time on hover and for assistive tech. */
export function NotificationTime({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={formatDateTime(iso)} suppressHydrationWarning>
      {formatRelative(iso)}
    </time>
  );
}

/** The brand dot marking an unread notification. */
export function UnreadDot({ className }: { className?: string }) {
  return <span className={cx("h-2 w-2 shrink-0 rounded-full bg-brand", className)} aria-label="Unread" />;
}
