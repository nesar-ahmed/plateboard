"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { Spinner, cx, darkButtonClass, dangerButtonClass, ghostButtonClass } from "@/components/ui";

/**
 * Small modal confirmation (role=alertdialog): focus lands on the safe
 * choice, Escape or the backdrop cancels. Render it only while open.
 * `children` may hold a field (a rejection reason): focus moves to the safe
 * choice only once, on open - never again while the user types.
 *
 * Portalled to <body>: inside a sticky or transformed ancestor (a stacking
 * context) its z-index would otherwise lose to content later on the page.
 */
export default function ConfirmDialog({
  title,
  children,
  confirmLabel,
  tone = "dark",
  busy = false,
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  tone?: "dark" | "danger";
  busy?: boolean;
  /** Keep the confirm button off until the dialog's field is filled in. */
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  // The latest onCancel, for the Escape key: callers pass inline functions,
  // and re-running the effect below on each render would steal the focus
  // back from a field inside the dialog.
  const onCancelRef = useRef(onCancel);
  useEffect(() => {
    onCancelRef.current = onCancel;
  });
  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancelRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-4 sm:items-center">
      <div className="animate-fade-in absolute inset-0 bg-night/50" onClick={onCancel} aria-hidden="true" />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-body"
        className="animate-rise relative w-full max-w-md rounded-3xl border border-line bg-surface p-6 shadow-pop"
      >
        <h2 id="confirm-title" className="font-display text-xl font-semibold text-ink">
          {title}
        </h2>
        <div id="confirm-body" className="mt-2 text-sm leading-relaxed text-ink-muted">
          {children}
        </div>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button ref={cancelRef} type="button" onClick={onCancel} className={ghostButtonClass}>
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
            className={cx(tone === "danger" ? dangerButtonClass : darkButtonClass)}
          >
            {busy && <Spinner />} {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
