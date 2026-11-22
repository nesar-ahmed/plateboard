"use client";

import { MessageSquareText, Pencil, Reply, Trash2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import Stars from "@/components/stars";
import {
  Avatar,
  Badge,
  Spinner,
  cx,
  ghostButtonClass,
  primaryButtonClass,
  quietButtonClass,
  smallButton,
  textareaClass,
} from "@/components/ui";
import { api, ApiError, type CookReview } from "@/lib/api";
import { formatDate, orderRef } from "@/lib/format";
import { REPLY_MAX_LENGTH, replyStarters } from "@/lib/reviews";

/**
 * One review of the cook's dish, with the cook's reply: write it
 * (`PUT /api/cooks/me/reviews/{id}/reply`), rewrite it, or take it down
 * (`DELETE`, confirmed). Replies are public - they show under the review on
 * the dish page - and the first one tells the customer. `startReplying`
 * opens the editor straight away (arriving from a notification).
 */
export default function CookReviewCard({
  review,
  highlight = false,
  startReplying = false,
  onChanged,
  onError,
}: {
  review: CookReview;
  highlight?: boolean;
  startReplying?: boolean;
  onChanged: (updated: CookReview, action: "posted" | "updated" | "removed") => void;
  onError: (lines: string[]) => void;
}) {
  const [editing, setEditing] = useState(startReplying && review.reply === null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [busy, setBusy] = useState(false);
  const customer = review.customer_name ?? "A customer";
  const editedAfterReply =
    review.reply !== null && review.edited_at !== null && review.edited_at > review.reply.replied_at;

  const run = async (request: () => Promise<CookReview>, action: "posted" | "updated" | "removed") => {
    setBusy(true);
    onError([]);
    try {
      const updated = await request();
      setEditing(false);
      setConfirmRemove(false);
      onChanged(updated, action);
    } catch (cause) {
      setConfirmRemove(false);
      onError(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  const save = (text: string) =>
    run(
      () => api.put<CookReview>(`/cooks/me/reviews/${review.id}/reply`, { reply: text }),
      review.reply ? "updated" : "posted",
    );

  return (
    <article
      className={cx(
        "rounded-3xl border bg-surface p-5 shadow-card sm:p-6",
        highlight ? "border-brand ring-4 ring-brand/10" : "border-line",
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <Avatar name={review.customer_name ?? "Customer"} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink">{customer}</p>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-soft">
              <Stars value={review.rating} size="xs" />
              <time dateTime={review.created_at} suppressHydrationWarning>
                {formatDate(review.created_at)}
              </time>
              {review.edited_at && <span>· edited</span>}
            </div>
          </div>
        </div>
        {review.reply ? <Badge tone="herb">Answered</Badge> : <Badge tone="saffron">Needs a reply</Badge>}
      </header>

      <p className="mt-3 flex flex-wrap gap-x-2 text-sm text-ink-muted">
        <span>
          on{" "}
          {review.dish_id ? (
            <Link href={`/cook/dishes/${review.dish_id}`} className="font-medium text-ink hover:text-brand">
              {review.dish_name}
            </Link>
          ) : (
            <span className="font-medium text-ink">{review.dish_name}</span>
          )}
        </span>
        {review.order_id && (
          <>
            <span className="text-line-strong" aria-hidden="true">
              ·
            </span>
            <Link href={`/cook/orders/${review.order_id}`} className="hover:text-brand">
              Order {orderRef(review.order_id)}
            </Link>
          </>
        )}
      </p>

      {review.comment ? (
        <p className="mt-3 whitespace-pre-line leading-relaxed text-ink">{review.comment}</p>
      ) : (
        <p className="mt-3 text-sm italic text-ink-soft">Rated without words.</p>
      )}

      {editedAfterReply && (
        <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-saffron">
          <TriangleAlert className="h-3.5 w-3.5" aria-hidden="true" /> {customer} edited the review after your reply -
          check it still fits.
        </p>
      )}

      <div className="mt-4 border-t border-line pt-4">
        {editing ? (
          <ReplyEditor
            rating={review.rating}
            initial={review.reply?.body ?? ""}
            submitLabel={review.reply ? "Save reply" : "Post reply"}
            busy={busy}
            autoFocus
            onSubmit={(text) => void save(text)}
            onCancel={() => setEditing(false)}
          />
        ) : review.reply ? (
          <div className="rounded-2xl bg-muted p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                <MessageSquareText className="h-3.5 w-3.5" aria-hidden="true" /> Your reply
                <time dateTime={review.reply.replied_at} className="font-normal text-ink-soft" suppressHydrationWarning>
                  · {formatDate(review.reply.replied_at)}
                </time>
              </p>
              <div className="flex gap-1">
                <button type="button" onClick={() => setEditing(true)} className={cx(quietButtonClass, "h-8 px-3 text-xs")}>
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRemove(true)}
                  className={cx(quietButtonClass, "h-8 px-3 text-xs")}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Remove
                </button>
              </div>
            </div>
            <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink-muted">{review.reply.body}</p>
          </div>
        ) : (
          <button type="button" onClick={() => setEditing(true)} className={cx(primaryButtonClass, smallButton)}>
            <Reply className="h-4 w-4" aria-hidden="true" /> Reply
          </button>
        )}
      </div>

      {confirmRemove && (
        <ConfirmDialog
          title="Remove your reply?"
          confirmLabel="Remove reply"
          tone="danger"
          busy={busy}
          onConfirm={() =>
            void run(() => api.delete<CookReview>(`/cooks/me/reviews/${review.id}/reply`), "removed")
          }
          onCancel={() => setConfirmRemove(false)}
        >
          It disappears from under {customer}&apos;s review on the dish page. You can write a new one any time.
        </ConfirmDialog>
      )}
    </article>
  );
}

function ReplyEditor({
  rating,
  initial,
  submitLabel,
  busy,
  autoFocus,
  onSubmit,
  onCancel,
}: {
  rating: number;
  initial: string;
  submitLabel: string;
  busy: boolean;
  autoFocus: boolean;
  onSubmit: (text: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initial);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (autoFocus) field.current?.focus();
  }, [autoFocus]);
  const id = useId();

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim()) onSubmit(text.trim());
      }}
      className="space-y-3"
    >
      <label htmlFor={id} className="text-sm font-medium text-ink">
        Your reply <span className="font-normal text-ink-soft">- public, shown under the review</span>
      </label>
      <div className="flex flex-wrap gap-1.5" aria-label="Reply starters">
        {replyStarters(rating).map((starter) => (
          <button
            key={starter}
            type="button"
            disabled={busy}
            onClick={() => setText(starter)}
            className="rounded-full border border-line bg-canvas px-3 py-1 text-xs text-ink-muted hover:border-line-strong hover:text-ink"
          >
            {starter}
          </button>
        ))}
      </div>
      <textarea
        id={id}
        ref={field}
        value={text}
        onChange={(event) => setText(event.target.value)}
        maxLength={REPLY_MAX_LENGTH}
        rows={3}
        disabled={busy}
        placeholder="Thank them, answer a question, or say what you'll do differently."
        className={textareaClass}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-2">
          <button type="submit" disabled={busy || !text.trim()} className={cx(primaryButtonClass, smallButton)}>
            {busy && <Spinner />} {submitLabel}
          </button>
          <button type="button" onClick={onCancel} disabled={busy} className={cx(ghostButtonClass, smallButton)}>
            Cancel
          </button>
        </div>
        <span className="text-xs tabular-nums text-ink-soft">
          {text.length}/{REPLY_MAX_LENGTH}
        </span>
      </div>
    </form>
  );
}
