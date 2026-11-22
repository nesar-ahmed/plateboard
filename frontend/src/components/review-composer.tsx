"use client";

import { MessageSquareText, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import StarInput from "@/components/star-input";
import Stars from "@/components/stars";
import {
  ButtonLink,
  ErrorBanner,
  Spinner,
  cx,
  ghostButtonClass,
  primaryButtonClass,
  quietButtonClass,
  smallButton,
  textareaClass,
} from "@/components/ui";
import { api, ApiError, type MyReview, type MyReviewPage, type PendingReview, type PendingReviewPage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { REVIEW_MAX_LENGTH } from "@/lib/reviews";
import { useSession } from "@/lib/session";

type Standing = { userId: string; mine: MyReview | null; pending: PendingReview | null };

const CARD = "rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6";

function errorLines(cause: unknown): string[] {
  return cause instanceof ApiError ? cause.lines : ["Could not reach the API"];
}

/**
 * "Rate this dish" on the dish page. What it shows depends on the viewer:
 * guests are asked to log in; the dish's own cook sees a note; a customer who
 * received the dish (GET /api/me/reviews/pending) gets the form; one who
 * already reviewed it sees their review with edit / delete; anyone else learns
 * when they can review. Admin-only accounts see nothing.
 */
export default function ReviewComposer({
  dishId,
  cookId,
  cookName,
  onChanged,
}: {
  dishId: string;
  cookId: string;
  cookName: string | null | undefined;
  onChanged: () => void;
}) {
  const { user, checked } = useSession();
  const userId = user?.id ?? null;
  const canReview = !!user && user.roles.includes("customer") && user.id !== cookId;
  const [standing, setStanding] = useState<Standing | null>(null);
  const [loadError, setLoadError] = useState<string[]>([]);

  const load = useCallback(async () => {
    if (!canReview || !userId) return;
    try {
      const [mine, pending] = await Promise.all([
        api.get<MyReviewPage>(`/me/reviews?dish_id=${dishId}&limit=1`),
        api.get<PendingReviewPage>(`/me/reviews/pending?dish_id=${dishId}&limit=1`),
      ]);
      setStanding({ userId, mine: mine.items[0] ?? null, pending: pending.items[0] ?? null });
      setLoadError([]);
    } catch (cause) {
      setLoadError(errorLines(cause));
    }
  }, [canReview, dishId, userId]);

  useEffect(() => {
    const kickOff = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(kickOff);
  }, [load]);

  const changed = async () => {
    await load();
    onChanged();
  };

  if (!checked) return null;

  if (!user) {
    return (
      <div className={CARD}>
        <h3 className="font-display text-lg font-semibold text-ink">Had this dish?</h3>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">
          Reviews come only from customers who received it. Log in to rate yours.
        </p>
        <ButtonLink
          href={`/login?next=${encodeURIComponent(`/dishes/${dishId}#reviews`)}`}
          variant="ghost"
          className={cx(smallButton, "mt-4")}
        >
          Log in to review
        </ButtonLink>
      </div>
    );
  }

  if (user.id === cookId) {
    return (
      <div className={CARD}>
        <h3 className="font-display text-lg font-semibold text-ink">This is your dish</h3>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">
          Customers who received it rate it here - their reviews shape your kitchen&apos;s rating.
        </p>
      </div>
    );
  }

  if (!canReview) return null;

  const current = standing && standing.userId === userId ? standing : null;
  if (!current) {
    return loadError.length > 0 ? (
      <ErrorBanner lines={loadError} />
    ) : (
      <div className={cx(CARD, "h-40 animate-pulse bg-muted")} aria-busy="true" />
    );
  }

  if (current.mine) {
    return <YourReview review={current.mine} cookName={cookName} onChanged={changed} />;
  }

  if (current.pending) {
    return (
      <div className={CARD}>
        <h3 className="font-display text-lg font-semibold text-ink">Rate this dish</h3>
        <p className="mt-1 text-sm text-ink-muted">
          You received it on <time suppressHydrationWarning>{formatDate(current.pending.completed_at)}</time>.
          How was it?
        </p>
        <ReviewForm
          submitLabel="Post review"
          onSubmit={async (rating, comment) => {
            await api.post<MyReview>("/me/reviews", {
              order_id: current.pending?.order_id,
              dish_id: dishId,
              rating,
              comment,
            });
            await changed();
          }}
          onAlreadyReviewed={changed}
        />
      </div>
    );
  }

  return (
    <div className={CARD}>
      <h3 className="font-display text-lg font-semibold text-ink">Rate this dish</h3>
      <p className="mt-1 text-sm leading-relaxed text-ink-muted">
        You can review it once you&apos;ve received it: order it, and after the cook marks it ready and you confirm
        you have it, your rating goes here.
      </p>
    </div>
  );
}

function YourReview({
  review,
  cookName,
  onChanged,
}: {
  review: MyReview;
  cookName: string | null | undefined;
  onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  if (editing) {
    return (
      <div className={CARD}>
        <h3 className="font-display text-lg font-semibold text-ink">Edit your review</h3>
        <ReviewForm
          initialRating={review.rating}
          initialComment={review.comment ?? ""}
          submitLabel="Save changes"
          onSubmit={async (rating, comment) => {
            await api.patch<MyReview>(`/me/reviews/${review.id}`, { rating, comment });
            setEditing(false);
            await onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      </div>
    );
  }

  const remove = async () => {
    setBusy(true);
    setErrors([]);
    try {
      await api.delete<void>(`/me/reviews/${review.id}`);
      setConfirmDelete(false);
      await onChanged();
    } catch (cause) {
      setConfirmDelete(false);
      setErrors(errorLines(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={CARD}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-lg font-semibold text-ink">Your review</h3>
        <Stars value={review.rating} size="sm" className="mt-1" />
      </div>
      <p className="mt-1 text-xs text-ink-soft">
        <time suppressHydrationWarning>{formatDate(review.created_at)}</time>
        {review.edited_at && " · edited"}
      </p>
      {review.comment ? (
        <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink">{review.comment}</p>
      ) : (
        <p className="mt-3 text-sm italic text-ink-soft">A rating without words.</p>
      )}
      {review.reply && (
        <div className="mt-4 rounded-2xl bg-muted p-4">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
            <MessageSquareText className="h-3.5 w-3.5" aria-hidden="true" /> {cookName ?? "The cook"} replied
          </p>
          <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink-muted">{review.reply.body}</p>
        </div>
      )}
      <ErrorBanner lines={errors} />
      <div className="mt-4 flex flex-wrap gap-1 border-t border-line pt-3">
        <button type="button" onClick={() => setEditing(true)} className={cx(quietButtonClass, smallButton, "-ml-2")}>
          <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
        </button>
        <button type="button" onClick={() => setConfirmDelete(true)} className={cx(quietButtonClass, smallButton)}>
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Delete
        </button>
      </div>
      {confirmDelete && (
        <ConfirmDialog
          title="Delete your review?"
          confirmLabel="Delete review"
          tone="danger"
          busy={busy}
          onConfirm={() => void remove()}
          onCancel={() => setConfirmDelete(false)}
        >
          Your rating and words disappear from this dish{review.reply ? ", and so does the cook's reply" : ""}. You can
          review it again later.
        </ConfirmDialog>
      )}
    </div>
  );
}

function ReviewForm({
  initialRating = null,
  initialComment = "",
  submitLabel,
  onSubmit,
  onCancel,
  onAlreadyReviewed,
}: {
  initialRating?: number | null;
  initialComment?: string;
  submitLabel: string;
  onSubmit: (rating: number, comment: string | null) => Promise<void>;
  onCancel?: () => void;
  onAlreadyReviewed?: () => Promise<void>;
}) {
  const [rating, setRating] = useState<number | null>(initialRating);
  const [comment, setComment] = useState(initialComment);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (rating === null) return;
    setBusy(true);
    setErrors([]);
    try {
      await onSubmit(rating, comment.trim() || null);
    } catch (cause) {
      // Reviewed meanwhile (another tab): show that review instead of an error.
      if (cause instanceof ApiError && cause.code === "already_reviewed" && onAlreadyReviewed) {
        await onAlreadyReviewed();
        return;
      }
      setErrors(errorLines(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="mt-4 space-y-4">
      <StarInput value={rating} onChange={setRating} disabled={busy} />
      <div>
        <label htmlFor="review-comment" className="text-sm font-medium text-ink">
          Your review <span className="font-normal text-ink-soft">(optional)</span>
        </label>
        <textarea
          id="review-comment"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          maxLength={REVIEW_MAX_LENGTH}
          rows={4}
          disabled={busy}
          placeholder="Taste, portion, packaging - what should the next person know?"
          className={cx(textareaClass, "mt-1.5")}
        />
        <p className="mt-1 text-right text-xs tabular-nums text-ink-soft">
          {comment.length}/{REVIEW_MAX_LENGTH}
        </p>
      </div>
      <ErrorBanner lines={errors} />
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || rating === null} className={cx(primaryButtonClass, smallButton)}>
          {busy && <Spinner />} {submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={busy} className={cx(ghostButtonClass, smallButton)}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
