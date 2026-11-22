"use client";

import { ArrowUpRight, Check, MapPin, Store, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import {
  Avatar,
  Badge,
  CountPill,
  EmptyState,
  ErrorBanner,
  Field,
  PageHeader,
  Pager,
  Tag,
  cx,
  ghostButtonClass,
  primaryButtonClass,
  smallButton,
  textareaClass,
} from "@/components/ui";
import { useAdminPanel } from "@/lib/admin-context";
import { api, ApiError, type CookApplication, type CookApplicationPage, type CookApplicationStatus } from "@/lib/api";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useNotifications } from "@/lib/notifications";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 10;
/** Same cap as the backend (REJECTION_REASON_MAX_LENGTH). */
const REASON_MAX = 300;

const TABS: { key: CookApplicationStatus | "all"; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "accepted", label: "Accepted" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All" },
];

const STATUS: Record<CookApplicationStatus, { label: string; tone: "saffron" | "herb" | "neutral" }> = {
  pending: { label: "Waiting for review", tone: "saffron" },
  accepted: { label: "Accepted", tone: "herb" },
  rejected: { label: "Rejected", tone: "neutral" },
};

export default function ApplicationsPage() {
  return (
    <Suspense fallback={null}>
      <Applications />
    </Suspense>
  );
}

type Decision = { application: CookApplication; action: "accept" | "reject" };

/**
 * /admin/applications - the cook-application review queue
 * (GET /api/admin/cook-applications; URL: ?tab=&offset=). Pending ones come
 * oldest first - first come, first served. Accepting opens the kitchen (the
 * applicant gains the cook role); rejecting needs a reason (the API refuses a
 * blank one) - the applicant sees it, and may apply again. Either way the applicant is notified, and
 * every admin's "new application" notification is marked read - so the bell,
 * the pending badge and this list all refresh after a decision.
 */
function Applications() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = TABS.find((candidate) => candidate.key === params.get("tab")) ?? TABS[0];
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const query = new URLSearchParams({ status: tab.key, limit: String(PAGE_SIZE), offset: String(offset) });
  const { data: page, error, reload } = useApi<CookApplicationPage>(`/admin/cook-applications?${query.toString()}`);
  const { pendingApplications, refresh: refreshPending } = useAdminPanel();
  const { refresh: refreshNotifications } = useNotifications();
  const [deciding, setDeciding] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  const go = (nextTab: string, nextOffset = 0) => {
    const next = new URLSearchParams();
    if (nextTab !== "pending") next.set("tab", nextTab);
    if (nextOffset) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  const open = (application: CookApplication, action: Decision["action"]) => {
    setReason("");
    setNotice(null);
    setErrors([]);
    setDeciding({ application, action });
  };

  const decide = async () => {
    if (!deciding) return;
    const { application, action } = deciding;
    const name = application.display_name ?? application.email;
    const why = reason.trim();
    if (action === "reject" && !why) return; // required - the button is off meanwhile
    setBusy(true);
    try {
      await api.post<CookApplication>(
        `/admin/cook-applications/${application.user_id}/${action}`,
        action === "reject" ? { reason: why } : {},
      );
      setNotice(
        action === "accept"
          ? `${name}'s kitchen is open - they've been notified and can start cooking.`
          : `${name}'s application was rejected - they've been notified, with your reason.`,
      );
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "application_not_pending") {
        setErrors([`${cause.message} - perhaps by another admin. The list is up to date now.`]);
      } else {
        setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
    } finally {
      setBusy(false);
      setDeciding(null);
      await reload();
      void refreshPending();
      void refreshNotifications(); // the admins' "new application" notices are resolved
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Cook applications"
        lead="Who may cook on Plateboard. Accepting opens the kitchen; a rejection always tells the applicant why - they can apply again."
      />

      <div role="tablist" aria-label="Status" className="flex gap-1 overflow-x-auto rounded-full border border-line bg-surface p-1 sm:w-fit">
        {TABS.map((candidate) => (
          <button
            key={candidate.key}
            role="tab"
            type="button"
            aria-selected={candidate.key === tab.key}
            onClick={() => go(candidate.key)}
            className={cx(
              "flex h-9 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-full px-3 text-sm font-medium transition-colors sm:flex-none sm:px-4",
              candidate.key === tab.key ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
            )}
          >
            {candidate.label}
            {candidate.key === "pending" && (
              <CountPill count={pendingApplications} active={candidate.key === tab.key} />
            )}
          </button>
        ))}
      </div>

      {notice && (
        <p role="status" className="animate-rise rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          {notice}
        </p>
      )}
      <ErrorBanner lines={error ? [error] : errors} />

      {!page ? (
        <div className="space-y-3" aria-busy="true">
          {[0, 1].map((key) => (
            <div key={key} className="h-48 animate-pulse rounded-3xl bg-muted" />
          ))}
        </div>
      ) : page.items.length === 0 ? (
        <EmptyState icon={<Store className="h-6 w-6" />} title={tab.key === "pending" ? "Nothing to review" : "No applications here"}>
          {tab.key === "pending"
            ? "New cook applications show up here - and in your notifications."
            : "Applications appear here once they are decided."}
        </EmptyState>
      ) : (
        <>
          <ul className="space-y-3">
            {page.items.map((application) => (
              <li key={application.user_id}>
                <ApplicationCard
                  application={application}
                  onAccept={() => open(application, "accept")}
                  onReject={() => open(application, "reject")}
                />
              </li>
            ))}
          </ul>
          {page.total > PAGE_SIZE && (
            <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={(next) => go(tab.key, next)} />
          )}
        </>
      )}

      {deciding?.action === "accept" && (
        <ConfirmDialog
          title="Open this kitchen?"
          confirmLabel="Accept application"
          busy={busy}
          onConfirm={() => void decide()}
          onCancel={() => setDeciding(null)}
        >
          {deciding.application.display_name ?? deciding.application.email} becomes a cook right away: they can publish
          dishes and take orders. They&apos;ll be notified.
        </ConfirmDialog>
      )}
      {deciding?.action === "reject" && (
        <ConfirmDialog
          title="Reject this application?"
          confirmLabel="Reject application"
          tone="danger"
          busy={busy}
          confirmDisabled={!reason.trim()}
          onConfirm={() => void decide()}
          onCancel={() => setDeciding(null)}
        >
          <p>
            {deciding.application.display_name ?? deciding.application.email} stays a customer and can apply again.
            Tell them why, so they know what to change - they&apos;ll be notified with your reason.
          </p>
          <div className="mt-4">
            <Field label="Reason" hint={`Required · ${reason.length}/${REASON_MAX} · shown to the applicant`}>
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={REASON_MAX}
                rows={3}
                required
                aria-required="true"
                placeholder="e.g. Please add a photo of your kitchen set-up and apply again."
                className={textareaClass}
              />
            </Field>
          </div>
        </ConfirmDialog>
      )}
    </div>
  );
}

function ApplicationCard({
  application,
  onAccept,
  onReject,
}: {
  application: CookApplication;
  onAccept: () => void;
  onReject: () => void;
}) {
  const name = application.display_name ?? application.email;
  const status = STATUS[application.status];
  const pending = application.status === "pending";
  return (
    <article className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <Avatar name={name} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-ink">{name}</h3>
              <Badge tone={status.tone}>{status.label}</Badge>
            </div>
            <p className="mt-0.5 truncate text-xs text-ink-soft">
              {application.email}
              {application.area && ` · ${application.area}`} ·{" "}
              <time dateTime={application.submitted_at} title={formatDateTime(application.submitted_at)}>
                applied {formatRelative(application.submitted_at)}
              </time>
            </p>
          </div>
        </div>
        {pending ? (
          <div className="flex shrink-0 gap-2">
            <button type="button" onClick={onReject} className={cx(ghostButtonClass, smallButton)}>
              <X className="h-4 w-4" aria-hidden="true" /> Reject
            </button>
            <button type="button" onClick={onAccept} className={cx(primaryButtonClass, smallButton)}>
              <Check className="h-4 w-4" aria-hidden="true" /> Accept
            </button>
          </div>
        ) : (
          application.status === "accepted" && (
            <Link
              href={`/cooks/${application.user_id}`}
              className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-brand hover:underline"
            >
              Public kitchen page <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          )
        )}
      </div>

      <p className="mt-4 font-display text-lg font-semibold leading-snug text-ink">“{application.headline}”</p>
      {(application.specialties.length > 0 || application.zone) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {application.zone && (
            <Tag className="gap-1">
              <MapPin className="h-3 w-3" aria-hidden="true" /> {application.zone.name}
            </Tag>
          )}
          {application.specialties.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </div>
      )}
      {application.bio && <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-ink-muted">{application.bio}</p>}

      {!pending && application.reviewed_at && (
        <p className="mt-4 border-t border-line pt-3 text-xs text-ink-soft">
          {application.status === "accepted" ? "Accepted" : "Rejected"} {formatDateTime(application.reviewed_at)}
          {application.rejection_reason && (
            <span className="mt-1 block text-sm text-ink-muted">“{application.rejection_reason}”</span>
          )}
        </p>
      )}
    </article>
  );
}
