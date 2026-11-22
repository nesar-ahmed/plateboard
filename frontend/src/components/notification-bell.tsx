"use client";

import { Bell, BellOff, CheckCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { NotificationIcon, NotificationTime, UnreadDot } from "@/components/notification-bits";
import { CountPill, cx } from "@/components/ui";
import { api, ApiError, type AppNotification, type NotificationAudience, type NotificationPage, type User } from "@/lib/api";
import { formatCount } from "@/lib/format";
import { defaultInbox, inboxesFor, notificationHref, unreadIn } from "@/lib/notification-kinds";
import { useNotifications } from "@/lib/notifications";

const PREVIEW_SIZE = 6;

/**
 * Header bell (signed-in users, every page - so every panel): the unread
 * count of every connected inbox the user can read as a badge (like the
 * cart's), and a dropdown with the newest notifications - open one to go
 * where it points (it is marked read on the way), mark them all read, or jump
 * to the full inbox.
 *
 * Someone with more than one inbox (an admin: *Admin* + *Account*) gets a tab
 * per inbox, each with its count; the dropdown opens on the panel they are in
 * (else the first inbox with unread ones). Which inboxes exist and who sees
 * them: `INBOXES` in lib/notification-kinds.ts. The counts come from the
 * shared NotificationsProvider; the preview is read when the dropdown opens,
 * on a tab switch, and whenever that inbox's count moves while it is open.
 *
 * Render it with `key={user.id}`: a different account never sees the
 * previous one's cached preview.
 */
export default function NotificationBell({ user }: { user: User }) {
  const pathname = usePathname();
  const { counts, setRead, markAllRead } = useNotifications();
  const inboxes = inboxesFor(user);
  const [open, setOpen] = useState(false);
  const [audience, setAudience] = useState<NotificationAudience>(() => defaultInbox(inboxes, pathname, counts).audience);
  const [preview, setPreview] = useState<{ audience: NotificationAudience; page: NotificationPage } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const inbox = inboxes.find((candidate) => candidate.audience === audience) ?? inboxes[0];
  const total = unreadIn(inboxes, counts);
  const unread = counts?.[inbox.audience] ?? 0;
  // Only the selected inbox's preview is shown (never the previous tab's).
  const shown = preview?.audience === inbox.audience ? preview.page : null;

  const load = useCallback(async (target: NotificationAudience) => {
    try {
      const page = await api.get<NotificationPage>(`/me/notifications?audience=${target}&limit=${PREVIEW_SIZE}`);
      setPreview({ audience: target, page });
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    }
  }, []);

  const toggle = () => {
    if (!open) setAudience(defaultInbox(inboxes, pathname, counts).audience);
    setOpen((value) => !value);
  };

  // Open: close on a press outside or Escape (focus back on the bell).
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Open: (re)read the selected inbox - on opening, on a tab switch, and
  // when new ones arrive.
  const target = inbox.audience;
  useEffect(() => {
    if (!open) return;
    // Timeout kick-off (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void load(target), 0);
    return () => window.clearTimeout(kickOff);
  }, [open, target, unread, load]);

  /** Mark read in the preview right away; the server call follows. */
  const markLocally = (notification: AppNotification) => {
    if (notification.read) return;
    setPreview(
      (current) =>
        current && {
          ...current,
          page: {
            ...current.page,
            unread: Math.max(0, current.page.unread - 1),
            items: current.page.items.map((item) => (item.id === notification.id ? { ...item, read: true } : item)),
          },
        },
    );
    void setRead(notification.id, true).catch(() => undefined);
  };

  const markAll = async () => {
    setMarking(true);
    try {
      // Up to the newest one on screen: anything arriving meanwhile stays unread.
      await markAllRead(target, shown?.items[0]?.created_at);
      await load(target);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    } finally {
      setMarking(false);
    }
  };

  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        onClick={toggle}
        aria-label={total > 0 ? `Notifications, ${total} unread` : "Notifications"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? "notification-panel" : undefined}
        className={cx(
          "relative flex h-10 w-10 items-center justify-center rounded-full text-ink transition-colors hover:bg-muted",
          open && "bg-muted",
        )}
      >
        <Bell className="h-[21px] w-[21px]" strokeWidth={1.9} aria-hidden="true" />
        {total > 0 && (
          <span
            key={total}
            aria-hidden="true"
            className={cx(
              // Same badge as the cart's: grows to the right for "99+".
              "animate-pop absolute left-[55%] top-0 flex h-5 min-w-5 items-center justify-center rounded-full",
              "bg-brand px-1 text-[11px] font-bold leading-none tabular-nums text-on-brand ring-2 ring-canvas",
            )}
          >
            {formatCount(total)}
          </span>
        )}
      </button>

      {open && (
        <div
          id="notification-panel"
          role="dialog"
          aria-label="Notifications"
          className={cx(
            "animate-rise z-50 overflow-hidden rounded-3xl border border-line bg-surface shadow-pop",
            // Phones: a full-width sheet under the header; from `sm`: a dropdown.
            "fixed inset-x-3 top-[4.25rem] sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-96",
          )}
        >
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <p className="font-semibold text-ink">Notifications</p>
              <p className="text-xs text-ink-soft" aria-live="polite">
                {total > 0 ? `${total} unread` : "You're all caught up"}
              </p>
            </div>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => void markAll()}
                disabled={marking}
                className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-medium text-ink-muted transition-colors hover:bg-muted hover:text-ink disabled:opacity-50"
              >
                <CheckCheck className="h-4 w-4" aria-hidden="true" /> Mark all read
              </button>
            )}
          </div>

          {inboxes.length > 1 && (
            <div role="tablist" aria-label="Inboxes" className="flex gap-1 border-b border-line px-3 py-2">
              {inboxes.map((candidate) => {
                const selected = candidate.audience === inbox.audience;
                const count = counts?.[candidate.audience] ?? 0;
                return (
                  <button
                    key={candidate.audience}
                    role="tab"
                    type="button"
                    aria-selected={selected}
                    onClick={() => setAudience(candidate.audience)}
                    className={cx(
                      "flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors",
                      selected ? "bg-ink text-canvas" : "text-ink-muted hover:bg-muted hover:text-ink",
                    )}
                  >
                    {candidate.label}
                    <CountPill count={count} active={selected} size="sm" />
                  </button>
                );
              })}
            </div>
          )}

          <div className="max-h-[min(28rem,calc(100dvh-10rem))] overflow-y-auto overscroll-contain">
            {error ? (
              <p role="alert" className="px-4 py-6 text-sm text-danger">
                {error}
              </p>
            ) : !shown ? (
              <div className="space-y-3 p-4" aria-busy="true">
                {[0, 1, 2].map((key) => (
                  <div key={key} className="h-14 animate-pulse rounded-2xl bg-muted" />
                ))}
              </div>
            ) : shown.items.length === 0 ? (
              <div className="flex flex-col items-center px-6 py-10 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-ink-muted">
                  <BellOff className="h-5 w-5" aria-hidden="true" />
                </span>
                <p className="mt-3 text-sm font-medium text-ink">No notifications yet</p>
                <p className="mt-1 text-xs text-ink-muted">
                  {inbox.audience === "admin"
                    ? "Cook applications and kitchens' late cancellations will show up here."
                    : inbox.audience === "cook"
                      ? "New order requests, cancellations and pickups will show up here."
                      : "Order updates and account news will show up here."}
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {shown.items.map((notification) => (
                  <PreviewItem
                    key={notification.id}
                    notification={notification}
                    onOpen={() => {
                      markLocally(notification);
                      setOpen(false);
                    }}
                    onMarkRead={() => markLocally(notification)}
                  />
                ))}
              </ul>
            )}
          </div>

          <Link
            href={inbox.href}
            onClick={() => setOpen(false)}
            className="block border-t border-line px-4 py-3 text-center text-sm font-medium text-brand transition-colors hover:bg-muted"
          >
            See all {inboxes.length > 1 ? `${inbox.label.toLowerCase()} ` : ""}notifications
          </Link>
        </div>
      )}
    </div>
  );
}

/** One preview row: the whole row opens the notification (a link when it
 * points somewhere, else a button that just marks it read). */
function PreviewItem({
  notification,
  onOpen,
  onMarkRead,
}: {
  notification: AppNotification;
  onOpen: () => void;
  onMarkRead: () => void;
}) {
  const href = notificationHref(notification);
  const titleClass = cx(
    "text-left text-sm text-ink after:absolute after:inset-0 after:content-['']",
    notification.read ? "font-normal" : "font-semibold",
  );
  return (
    <li
      className={cx(
        "relative flex gap-3 px-4 py-3 transition-colors hover:bg-muted/60",
        !notification.read && "bg-brand-soft/40",
      )}
    >
      <NotificationIcon notification={notification} size="sm" />
      <div className="min-w-0 flex-1">
        {href ? (
          <Link href={href} onClick={onOpen} className={titleClass}>
            {notification.title}
          </Link>
        ) : (
          <button type="button" onClick={onMarkRead} className={titleClass}>
            {notification.title}
          </button>
        )}
        {notification.body && <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{notification.body}</p>}
        <p className="mt-1 text-[11px] text-ink-soft">
          <NotificationTime iso={notification.created_at} />
        </p>
      </div>
      {!notification.read && <UnreadDot className="mt-1.5" />}
    </li>
  );
}
