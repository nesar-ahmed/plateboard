"use client";

import { BellOff, CheckCheck, Mail, MailOpen, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { NotificationIcon, NotificationTime, UnreadDot } from "@/components/notification-bits";
import { CountPill, EmptyState, ErrorBanner, PageHeader, Pager, cx, quietButtonClass, smallButton } from "@/components/ui";
import { ApiError, type AppNotification, type NotificationAudience, type NotificationPage } from "@/lib/api";
import { notificationHref } from "@/lib/notification-kinds";
import { useNotifications } from "@/lib/notifications";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 20;

const TABS = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
] as const;

/**
 * One panel's notification inbox (GET /api/me/notifications?audience=...):
 * newest first, by tab (URL: ?tab=&offset=) - the page of /account, /admin
 * (and /cook once connected) renders it with its own title and empty text.
 * Needs a <Suspense> boundary above it (it reads the search params).
 *
 * Read state lives on the server, so it follows the user across devices:
 * opening a notification marks it read, each row can be marked read / unread
 * or dismissed, and "Mark all as read" stops at the newest one on screen.
 * New arrivals (the shared unread count rises) reload the list.
 */
export default function NotificationInbox({
  audience,
  lead,
  empty,
}: {
  audience: NotificationAudience;
  lead: string;
  /** What shows up here, for the "Nothing yet" state. */
  empty: ReactNode;
}) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = TABS.find((candidate) => candidate.key === params.get("tab")) ?? TABS[0];
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const query = new URLSearchParams({ audience, limit: String(PAGE_SIZE), offset: String(offset) });
  if (tab.key === "unread") query.set("unread", "true");
  const { data: page, error, reload, setData } = useApi<NotificationPage>(`/me/notifications?${query.toString()}`);
  const { counts, setRead, markAllRead, dismiss } = useNotifications();
  const [busy, setBusy] = useState<string | null>(null); // a notification id, or "all"
  const [actionErrors, setActionErrors] = useState<string[]>([]);

  // New arrivals: when the shared unread count rises, re-read this page.
  const unread = counts?.[audience];
  const lastUnread = useRef<number | undefined>(undefined);
  useEffect(() => {
    const previous = lastUnread.current;
    lastUnread.current = unread;
    if (previous === undefined || unread === undefined || unread <= previous) return;
    const kickOff = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(kickOff);
  }, [unread, reload]);

  // The newest notification this view has shown: "mark all" stops there.
  const newestSeen = useRef<string | null>(null);
  useEffect(() => {
    const first = page?.items[0]?.created_at;
    if (first && (!newestSeen.current || Date.parse(first) > Date.parse(newestSeen.current))) {
      newestSeen.current = first;
    }
  }, [page]);

  const go = (nextTab: string, nextOffset = 0) => {
    const next = new URLSearchParams();
    if (nextTab !== "all") next.set("tab", nextTab);
    if (nextOffset) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  /** Run one action; failures show above the list. */
  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setActionErrors([]);
    try {
      await action();
    } catch (cause) {
      setActionErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(null);
    }
  };

  /** Apply an updated notification to the page (its unread count too). */
  const applyRead = (updated: AppNotification) =>
    setData((current) => {
      if (!current) return current;
      const before = current.items.find((item) => item.id === updated.id);
      const delta = before && before.read !== updated.read ? (updated.read ? -1 : 1) : 0;
      return {
        ...current,
        unread: Math.max(0, current.unread + delta),
        items: current.items.map((item) => (item.id === updated.id ? updated : item)),
      };
    });

  const toggleRead = (notification: AppNotification) =>
    run(notification.id, async () => applyRead(await setRead(notification.id, !notification.read)));

  /** Opening a notification marks it read - without holding up the navigation. */
  const markOpened = (notification: AppNotification) => {
    if (notification.read) return;
    applyRead({ ...notification, read: true, read_at: new Date().toISOString() });
    void setRead(notification.id, true).catch(() => undefined);
  };

  const remove = (notification: AppNotification) =>
    run(notification.id, async () => {
      await dismiss(notification.id);
      // Re-read: the page refills from the next one (or steps back if emptied).
      if (page && page.items.length === 1 && offset > 0) go(tab.key, Math.max(0, offset - PAGE_SIZE));
      else await reload();
    });

  const markAll = () =>
    run("all", async () => {
      await markAllRead(audience, newestSeen.current ?? undefined);
      await reload();
    });

  const unreadNow = page?.unread ?? unread ?? 0;
  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Notifications"
        lead={lead}
        actions={
          unreadNow > 0 && (
            <button
              type="button"
              onClick={() => void markAll()}
              disabled={busy !== null}
              className={cx(quietButtonClass, smallButton)}
            >
              <CheckCheck className="h-4 w-4" aria-hidden="true" /> Mark all as read
            </button>
          )
        }
      />

      <div role="tablist" aria-label="Filter notifications" className="flex gap-1 rounded-full border border-line bg-surface p-1 sm:w-fit">
          {TABS.map((candidate) => (
            <button
              key={candidate.key}
              role="tab"
              type="button"
              aria-selected={candidate.key === tab.key}
              onClick={() => go(candidate.key)}
              className={cx(
                "flex h-9 flex-1 items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors sm:flex-none",
                candidate.key === tab.key ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
              )}
            >
              {candidate.label}
              {candidate.key === "unread" && <CountPill count={unreadNow} active={candidate.key === tab.key} />}
            </button>
          ))}
      </div>

      <ErrorBanner lines={error ? [error] : actionErrors} />

      <section aria-label="Your notifications" className="rounded-3xl border border-line bg-surface shadow-card">
        {!page ? (
          <div className="space-y-3 p-5" aria-busy="true">
            {[0, 1, 2, 3].map((key) => (
              <div key={key} className="h-16 animate-pulse rounded-2xl bg-muted" />
            ))}
          </div>
        ) : page.items.length === 0 ? (
          <div className="p-5">
            {tab.key === "unread" ? (
              <EmptyState icon={<CheckCheck className="h-6 w-6" />} title="You're all caught up">
                No unread notifications.{" "}
                <button type="button" onClick={() => go("all")} className="font-medium text-brand hover:underline">
                  See all
                </button>
              </EmptyState>
            ) : (
              <EmptyState icon={<BellOff className="h-6 w-6" />} title="Nothing yet">
                {empty}
              </EmptyState>
            )}
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {page.items.map((notification) => (
              <NotificationRow
                key={notification.id}
                notification={notification}
                busy={busy === notification.id || busy === "all"}
                onOpen={() => markOpened(notification)}
                onToggleRead={() => void toggleRead(notification)}
                onDismiss={() => void remove(notification)}
              />
            ))}
          </ul>
        )}
      </section>

      {page && page.total > PAGE_SIZE && (
        <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={(next) => go(tab.key, next)} />
      )}
    </div>
  );
}

function NotificationRow({
  notification,
  busy,
  onOpen,
  onToggleRead,
  onDismiss,
}: {
  notification: AppNotification;
  busy: boolean;
  onOpen: () => void;
  onToggleRead: () => void;
  onDismiss: () => void;
}) {
  const href = notificationHref(notification);
  const fresh = !notification.read;
  return (
    <li className={cx("group relative flex gap-4 px-5 py-4 sm:px-6", fresh && "bg-brand-soft/40")}>
      <NotificationIcon notification={notification} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          {href ? (
            <Link
              href={href}
              onClick={onOpen}
              className={cx(
                "text-sm text-ink after:absolute after:inset-0 after:content-[''] hover:text-brand",
                fresh ? "font-semibold" : "font-medium",
              )}
            >
              {notification.title}
            </Link>
          ) : (
            <p className={cx("text-sm text-ink", fresh ? "font-semibold" : "font-medium")}>{notification.title}</p>
          )}
          {fresh && <UnreadDot className="mt-1.5" />}
        </div>
        {notification.body && <p className="mt-0.5 text-sm text-ink-muted">{notification.body}</p>}
        <p className="mt-1 text-xs text-ink-soft">
          <NotificationTime iso={notification.created_at} />
        </p>
      </div>
      {/* Above the row's link overlay (relative + z-10). */}
      <div className="relative z-10 flex shrink-0 items-start gap-1">
        <button
          type="button"
          onClick={onToggleRead}
          disabled={busy}
          title={fresh ? "Mark as read" : "Mark as unread"}
          aria-label={`${fresh ? "Mark as read" : "Mark as unread"}: ${notification.title}`}
          className="flex h-9 w-9 items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-muted hover:text-ink disabled:opacity-50"
        >
          {fresh ? <MailOpen className="h-4 w-4" aria-hidden="true" /> : <Mail className="h-4 w-4" aria-hidden="true" />}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={busy}
          title="Dismiss"
          aria-label={`Dismiss: ${notification.title}`}
          className="flex h-9 w-9 items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-danger-soft hover:text-danger disabled:opacity-50"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </li>
  );
}
