"use client";

import { Bell, CircleCheck, MessageSquareText, Star, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import CookReviewCard from "@/components/cook-review-card";
import Stars from "@/components/stars";
import { CountPill, EmptyState, ErrorBanner, PageHeader, Pager, cx } from "@/components/ui";
import type { CookReview, CookReviewPage, RatingSummary } from "@/lib/api";
import { useKitchen } from "@/lib/kitchen-context";
import { useNotifications } from "@/lib/notifications";
import { formatAverage, reviewCount } from "@/lib/reviews";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 10;

type Tab = { key: string; label: string; replied: boolean | null };

const TABS: Tab[] = [
  { key: "open", label: "To answer", replied: false },
  { key: "answered", label: "Answered", replied: true },
  { key: "all", label: "All", replied: null },
];

function reviewsPath(tab: Tab, offset: number): string {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (tab.replied !== null) query.set("replied", String(tab.replied));
  return `/cooks/me/reviews?${query.toString()}`;
}

export default function CookReviewsPage() {
  return (
    <Suspense fallback={null}>
      <CookReviews />
    </Suspense>
  );
}

/**
 * /cook/reviews (GET /api/cooks/me/reviews) - what customers say about the
 * kitchen's dishes, by tab (URL: ?tab=&offset=), with the reply right on each
 * card. ?open=<review id> (a "new review" notification) puts that review on
 * top with the reply box open.
 */
function CookReviews() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const kitchen = useKitchen();
  const notifications = useNotifications();
  const tab = TABS.find((candidate) => candidate.key === params.get("tab")) ?? TABS[0];
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const openId = params.get("open");

  const { data: page, error, setData } = useApi<CookReviewPage>(reviewsPath(tab, offset));
  const opened = useApi<CookReview>(openId ? `/cooks/me/reviews/${openId}` : null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionErrors, setActionErrors] = useState<string[]>([]);

  const go = (next: { tab?: string; offset?: number; open?: string | null }) => {
    const query = new URLSearchParams();
    const nextTab = next.tab ?? tab.key;
    if (nextTab !== TABS[0].key) query.set("tab", nextTab);
    if (next.offset) query.set("offset", String(next.offset));
    const nextOpen = next.open === undefined ? openId : next.open;
    if (nextOpen) query.set("open", nextOpen);
    setNotice(null);
    setActionErrors([]);
    router.push(query.size ? `${pathname}?${query.toString()}` : pathname, { scroll: false });
  };

  const changed = (updated: CookReview, action: "posted" | "updated" | "removed") => {
    const who = updated.customer_name ?? "The customer";
    setNotice(
      action === "posted"
        ? `Reply posted - ${who} was told, and it shows under the review.`
        : action === "updated"
          ? "Reply updated."
          : "Reply removed.",
    );
    // Update in place; the card stays where it is until the tab is reloaded.
    setData((current) =>
      current && {
        ...current,
        unreplied: Math.max(0, current.unreplied + (action === "posted" ? -1 : action === "removed" ? 1 : 0)),
        items: current.items.map((item) => (item.id === updated.id ? updated : item)),
      },
    );
    if (opened.data?.id === updated.id) opened.setData(updated);
    void kitchen.refresh();
    void notifications.refresh();
  };

  const listed = (page?.items ?? []).filter((review) => review.id !== openId);

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Reviews"
        lead="What customers say about your dishes. Your reply shows under their review on the dish page."
      />

      {page && <KitchenRating summary={page.summary} unreplied={page.unreplied} />}

      {notice && (
        <p role="status" className="animate-rise flex items-center gap-2 rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          <CircleCheck className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" /> {notice}
        </p>
      )}
      <ErrorBanner lines={[...(error ? [error] : []), ...actionErrors]} />

      {openId && (
        <section aria-label="Review from your notification" className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Bell className="h-4 w-4 text-brand" aria-hidden="true" /> From your notifications
            </p>
            <button
              type="button"
              onClick={() => go({ open: null })}
              aria-label="Close"
              className="flex h-8 w-8 items-center justify-center rounded-full text-ink-soft hover:bg-muted hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {opened.data ? (
            <CookReviewCard
              key={opened.data.id}
              review={opened.data}
              highlight
              startReplying
              onChanged={changed}
              onError={setActionErrors}
            />
          ) : opened.error ? (
            <p className="rounded-2xl border border-dashed border-line-strong px-4 py-3 text-sm text-ink-muted">
              This review is no longer there - its author deleted it.
            </p>
          ) : (
            <div className="h-48 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
          )}
        </section>
      )}

      <div
        role="tablist"
        aria-label="Filter reviews"
        className="-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0"
      >
        <div className="flex gap-1 rounded-full border border-line bg-surface p-1">
          {TABS.map((candidate) => {
            const selected = candidate.key === tab.key;
            return (
              <button
                key={candidate.key}
                role="tab"
                type="button"
                aria-selected={selected}
                onClick={() => go({ tab: candidate.key, offset: 0 })}
                className={cx(
                  "inline-flex h-9 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors",
                  selected ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
                )}
              >
                {candidate.label}
                {candidate.key === "open" && <CountPill count={kitchen.unrepliedReviews} active={selected} />}
              </button>
            );
          })}
        </div>
      </div>

      {!page ? (
        !error && (
          <div className="space-y-3" aria-busy="true">
            {[0, 1, 2].map((key) => (
              <div key={key} className="h-48 animate-pulse rounded-3xl bg-muted" />
            ))}
          </div>
        )
      ) : listed.length === 0 ? (
        <EmptyState
          icon={tab.key === "open" ? <CircleCheck className="h-6 w-6" /> : <MessageSquareText className="h-6 w-6" />}
          title={tab.key === "open" ? "All caught up" : tab.key === "answered" ? "No replies yet" : "No reviews yet"}
        >
          {tab.key === "open"
            ? "Every review has an answer. New ones land here, and your kitchen inbox tells you."
            : tab.key === "answered"
              ? "Reviews you've answered show up here."
              : "Customers can review a dish once they've received it."}
        </EmptyState>
      ) : (
        <>
          <ul className="space-y-4">
            {listed.map((review) => (
              <li key={review.id}>
                <CookReviewCard review={review} onChanged={changed} onError={setActionErrors} />
              </li>
            ))}
          </ul>
          {page.total > PAGE_SIZE && (
            <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={(next) => go({ offset: next })} />
          )}
        </>
      )}
    </div>
  );
}

/** The kitchen's rating across every dish: average, stars, count, per-star bars. */
function KitchenRating({ summary, unreplied }: { summary: RatingSummary; unreplied: number }) {
  return (
    <section
      aria-label="Your kitchen's rating"
      className="grid grid-cols-1 gap-5 rounded-3xl border border-line bg-surface p-5 shadow-card sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center sm:gap-8 sm:p-6"
    >
      <div className="flex items-end gap-4">
        <p className="font-display text-5xl font-semibold leading-none tracking-tight tabular-nums text-ink">
          {formatAverage(summary.average)}
        </p>
        <div className="pb-0.5">
          <Stars value={summary.average ?? 0} size="sm" />
          <p className="mt-1 text-sm text-ink-muted">
            {summary.count > 0 ? reviewCount(summary.count) : "No reviews yet"}
          </p>
          {unreplied > 0 && <p className="text-xs font-medium text-saffron">{unreplied} waiting for a reply</p>}
        </div>
      </div>
      <ul className="space-y-1" aria-label="Reviews per rating">
        {summary.distribution.map(({ rating, count }) => (
          <li key={rating} className="flex items-center gap-3 text-xs text-ink-muted">
            <span className="flex w-8 shrink-0 items-center gap-0.5 font-medium tabular-nums">
              {rating}
              <Star className="h-3 w-3" fill="currentColor" strokeWidth={0} aria-hidden="true" />
            </span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-brand"
                style={{ width: `${summary.count ? (count / summary.count) * 100 : 0}%` }}
              />
            </span>
            <span className="w-6 shrink-0 text-right tabular-nums">{count}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
