"use client";

import { BadgeCheck, MessageSquareText, Star, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import ReviewComposer from "@/components/review-composer";
import Stars from "@/components/stars";
import { Avatar, EmptyState, ErrorBanner, Spinner, cx, ghostButtonClass } from "@/components/ui";
import { api, ApiError, type RatingSummary, type Review, type ReviewPage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { REVIEWS_PAGE_SIZE, formatAverage, reviewCount } from "@/lib/reviews";

type Loaded = { items: Review[]; total: number; summary: RatingSummary };

/** Comments longer than this start clamped, with "Read more". */
const CLAMP_AFTER = 320;

/**
 * The dish page's reviews: a summary (average, count, per-star bars that
 * filter the list), the viewer's "rate this dish" card, and the reviews with
 * the cook's replies - newest first, more on "Show more reviews". The first
 * page comes server-rendered (`initial`); later pages and filters are fetched
 * here (GET /api/dishes/{id}/reviews).
 */
export default function DishReviews({
  dishId,
  cookId,
  cookName,
  initial,
}: {
  dishId: string;
  cookId: string;
  cookName: string | null | undefined;
  initial: ReviewPage | null;
}) {
  const router = useRouter();
  const [loaded, setLoaded] = useState<Loaded | null>(
    initial && { items: initial.items, total: initial.total, summary: initial.summary },
  );
  const [filter, setFilter] = useState<number | null>(null);
  const [busy, setBusy] = useState<"more" | "list" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(
    (rating: number | null, offset: number) => {
      const query = new URLSearchParams({ limit: String(REVIEWS_PAGE_SIZE), offset: String(offset) });
      if (rating !== null) query.set("rating", String(rating));
      return api.get<ReviewPage>(`/dishes/${dishId}/reviews?${query.toString()}`);
    },
    [dishId],
  );

  const reloadFirstPage = useCallback(
    async (rating: number | null) => {
      setBusy("list");
      try {
        const page = await fetchPage(rating, 0);
        setLoaded({ items: page.items, total: page.total, summary: page.summary });
        setError(null);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "Could not reach the API");
      } finally {
        setBusy(null);
      }
    },
    [fetchPage],
  );

  const missingInitial = initial === null;
  useEffect(() => {
    if (!missingInitial) return;
    // Timeout kick-off (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void reloadFirstPage(null), 0);
    return () => window.clearTimeout(kickOff);
  }, [missingInitial, reloadFirstPage]);

  const loadMore = async () => {
    if (!loaded) return;
    setBusy("more");
    try {
      const page = await fetchPage(filter, loaded.items.length);
      setLoaded((previous) => {
        if (!previous) return previous;
        // A review posted meanwhile shifts the offsets: skip ones already shown.
        const seen = new Set(previous.items.map((item) => item.id));
        return {
          items: [...previous.items, ...page.items.filter((item) => !seen.has(item.id))],
          total: page.total,
          summary: page.summary,
        };
      });
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    } finally {
      setBusy(null);
    }
  };

  const chooseFilter = (rating: number | null) => {
    const next = rating === filter ? null : rating;
    setFilter(next);
    void reloadFirstPage(next);
  };

  const summary = loaded?.summary ?? null;

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[340px_minmax(0,1fr)] lg:gap-12">
      <div className="space-y-4 lg:sticky lg:top-24 lg:self-start">
        {summary ? (
          <RatingSummaryCard summary={summary} filter={filter} onFilter={chooseFilter} />
        ) : (
          !error && <div className="h-72 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
        )}
        <ReviewComposer
          dishId={dishId}
          cookId={cookId}
          cookName={cookName}
          onChanged={() => {
            void reloadFirstPage(filter);
            router.refresh(); // the rating under the dish's name is server-rendered
          }}
        />
      </div>

      <div className="min-w-0">
        <ErrorBanner lines={error ? [error] : []} />
        {loaded === null ? (
          !error && (
            <div className="space-y-4" aria-busy="true">
              {[0, 1, 2].map((key) => (
                <div key={key} className="h-36 animate-pulse rounded-3xl bg-muted" />
              ))}
            </div>
          )
        ) : loaded.summary.count === 0 ? (
          <EmptyState icon={<Star className="h-6 w-6" />} title="No reviews yet">
            Reviews come from customers who received this dish - the first one will show up here.
          </EmptyState>
        ) : (
          <>
            <div className="mb-4 flex min-h-8 flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-ink-muted" aria-live="polite">
                Showing {loaded.items.length} of {loaded.total}
                {filter !== null ? ` ${filter}-star` : ""} {loaded.total === 1 ? "review" : "reviews"}
              </p>
              {filter !== null && (
                <button
                  type="button"
                  onClick={() => chooseFilter(null)}
                  aria-label={`Remove filter ${filter} stars`}
                  className="inline-flex h-8 items-center gap-1.5 rounded-full bg-ink pl-3 pr-2 text-xs font-medium text-canvas hover:bg-ink/85"
                >
                  {filter} {filter === 1 ? "star" : "stars"}
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              )}
            </div>

            <ul className={cx("space-y-4 transition-opacity", busy === "list" && "opacity-50")}>
              {loaded.items.map((review) => (
                <li key={review.id}>
                  <ReviewCard review={review} cookName={cookName} />
                </li>
              ))}
            </ul>

            {loaded.items.length < loaded.total ? (
              <button
                type="button"
                onClick={() => void loadMore()}
                disabled={busy !== null}
                className={cx(ghostButtonClass, "mt-6 w-full")}
              >
                {busy === "more" && <Spinner />}
                Show more reviews
                <span className="font-normal text-ink-muted">({loaded.total - loaded.items.length} more)</span>
              </button>
            ) : (
              loaded.total > REVIEWS_PAGE_SIZE && (
                <p className="mt-6 text-center text-sm text-ink-soft">That&apos;s every review.</p>
              )
            )}
          </>
        )}
      </div>
    </div>
  );
}

function RatingSummaryCard({
  summary,
  filter,
  onFilter,
}: {
  summary: RatingSummary;
  filter: number | null;
  onFilter: (rating: number) => void;
}) {
  const rated = summary.count > 0;
  return (
    <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      {rated ? (
        <div className="flex items-end gap-4">
          <p className="font-display text-6xl font-semibold leading-none tracking-tight tabular-nums text-ink">
            {formatAverage(summary.average)}
          </p>
          <div className="pb-1">
            <Stars value={summary.average ?? 0} size="md" />
            <p className="mt-1 text-sm text-ink-muted">{reviewCount(summary.count)}</p>
          </div>
        </div>
      ) : (
        <div>
          <Stars value={0} size="md" />
          <p className="mt-2 font-display text-lg font-semibold text-ink">Not rated yet</p>
        </div>
      )}

      {rated && (
        <ul className="mt-5 space-y-0.5" aria-label="Filter by rating">
          {summary.distribution.map(({ rating, count }) => {
            const share = count / summary.count;
            const active = filter === rating;
            return (
              <li key={rating}>
                <button
                  type="button"
                  disabled={count === 0}
                  aria-pressed={active}
                  aria-label={`${rating} stars: ${reviewCount(count)}${active ? " - showing only these" : ""}`}
                  onClick={() => onFilter(rating)}
                  className={cx(
                    "flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-sm transition-colors disabled:opacity-45",
                    active ? "bg-ink text-canvas" : "text-ink-muted enabled:hover:bg-muted enabled:hover:text-ink",
                  )}
                >
                  <span className="flex w-9 shrink-0 items-center gap-1 font-medium tabular-nums">
                    {rating}
                    <Star className="h-3.5 w-3.5" fill="currentColor" strokeWidth={0} aria-hidden="true" />
                  </span>
                  <span className={cx("h-2 flex-1 overflow-hidden rounded-full", active ? "bg-canvas/25" : "bg-muted")}>
                    <span
                      className={cx("block h-full rounded-full", active ? "bg-canvas" : "bg-brand")}
                      style={{ width: `${share * 100}%` }}
                    />
                  </span>
                  <span className="w-8 shrink-0 text-right text-xs tabular-nums">{count}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-5 flex gap-2 border-t border-line pt-4 text-xs leading-relaxed text-ink-muted">
        <BadgeCheck className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" />
        Every review is from a customer who received this dish.
      </p>
    </div>
  );
}

function ReviewCard({ review, cookName }: { review: Review; cookName: string | null | undefined }) {
  const [expanded, setExpanded] = useState(false);
  const long = (review.comment?.length ?? 0) > CLAMP_AFTER;
  const author = review.author_name ?? "A customer";
  return (
    <article className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
      <header className="flex items-start gap-3">
        <Avatar name={review.author_name ?? "Customer"} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
            <p className="font-semibold text-ink">{author}</p>
            <span className="inline-flex items-center gap-1 text-xs font-medium text-herb">
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" /> Verified order
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-soft">
            <Stars value={review.rating} size="xs" />
            <time dateTime={review.created_at} suppressHydrationWarning>
              {formatDate(review.created_at)}
            </time>
            {review.edited_at && <span>· edited</span>}
          </div>
        </div>
      </header>

      {review.comment && (
        <div className="mt-3">
          <p className={cx("whitespace-pre-line leading-relaxed text-ink", long && !expanded && "line-clamp-4")}>
            {review.comment}
          </p>
          {long && (
            <button
              type="button"
              onClick={() => setExpanded((open) => !open)}
              aria-expanded={expanded}
              className="mt-1 text-sm font-semibold text-brand hover:underline"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </div>
      )}

      {review.reply && (
        <div className="mt-4 rounded-2xl bg-muted p-4">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
            <span className="flex items-center gap-1.5 font-semibold text-ink">
              <MessageSquareText className="h-3.5 w-3.5" aria-hidden="true" />
              Reply from {cookName ?? "the cook"}
            </span>
            <time dateTime={review.reply.replied_at} className="text-ink-soft" suppressHydrationWarning>
              {formatDate(review.reply.replied_at)}
            </time>
          </div>
          <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink-muted">{review.reply.body}</p>
        </div>
      )}
    </article>
  );
}
