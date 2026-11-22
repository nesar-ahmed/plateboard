"use client";

import { ArrowLeft, MessageSquareText, Star } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import Stars from "@/components/stars";
import { Avatar, ButtonLink, EmptyState, ErrorBanner, PageHeader } from "@/components/ui";
import type { MyReview } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { RATING_LABELS } from "@/lib/reviews";
import { useApi } from "@/lib/use-api";

/**
 * /account/reviews/{id} (GET /api/me/reviews/{id}) - one of my reviews with
 * the cook's reply: where a "the cook replied" notification lands. Editing
 * happens on the dish page; this page also works once the dish is hidden or
 * deleted (the dish page is then a 404).
 */
export default function MyReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { data: review, error } = useApi<MyReview>(`/me/reviews/${id}`);
  const missing = error !== null && error.toLowerCase().includes("not found");

  return (
    <div className="space-y-6">
      <Link href="/account" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Your account
      </Link>

      {missing ? (
        <EmptyState
          icon={<Star className="h-6 w-6" />}
          title="Review not found"
          action={<ButtonLink href="/dishes">Browse dishes</ButtonLink>}
        >
          It may have been deleted.
        </EmptyState>
      ) : error ? (
        <ErrorBanner lines={[error]} />
      ) : !review ? (
        <div className="h-64 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
      ) : (
        <>
          <PageHeader
            size="compact"
            title="Your review"
            lead={
              <>
                of <span className="font-medium text-ink">{review.dish_name}</span>
                {review.cook_name && <> by {review.cook_name}</>}
              </>
            }
            actions={
              review.dish_id && (
                <ButtonLink href={`/dishes/${review.dish_id}#reviews`} variant="ghost">
                  See it on the dish page
                </ButtonLink>
              )
            }
          />

          <article className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Stars value={review.rating} size="md" />
              <span className="text-sm font-semibold text-ink">{RATING_LABELS[review.rating]}</span>
              <span className="text-sm text-ink-soft">
                <time dateTime={review.created_at} suppressHydrationWarning>
                  {formatDate(review.created_at)}
                </time>
                {review.edited_at && " · edited"}
              </span>
            </div>
            {review.comment ? (
              <p className="mt-4 whitespace-pre-line text-lg leading-relaxed text-ink">{review.comment}</p>
            ) : (
              <p className="mt-4 italic text-ink-soft">A rating without words.</p>
            )}

            {review.reply ? (
              <div className="mt-6 rounded-2xl border border-brand/20 bg-brand-soft p-5">
                <div className="flex items-center gap-3">
                  <Avatar name={review.cook_name ?? "Cook"} size="sm" />
                  <div>
                    <p className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                      <MessageSquareText className="h-4 w-4 text-brand" aria-hidden="true" />
                      {review.cook_name ?? "The cook"} replied
                    </p>
                    <p className="text-xs text-ink-soft">
                      <time dateTime={review.reply.replied_at} suppressHydrationWarning>
                        {formatDate(review.reply.replied_at)}
                      </time>
                    </p>
                  </div>
                </div>
                <p className="mt-3 whitespace-pre-line leading-relaxed text-ink">{review.reply.body}</p>
              </div>
            ) : (
              <p className="mt-6 rounded-2xl bg-muted px-4 py-3 text-sm text-ink-muted">
                No reply from the cook yet - you&apos;ll get a notification when there is one.
              </p>
            )}

            {!review.dish_id && (
              <p className="mt-4 text-sm text-ink-soft">This dish is no longer on the menu.</p>
            )}
          </article>
        </>
      )}
    </div>
  );
}
