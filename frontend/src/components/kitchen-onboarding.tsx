"use client";

import {
  Banknote,
  CircleCheck,
  ClipboardCheck,
  Eye,
  Hourglass,
  MapPin,
  MessageSquareQuote,
  RotateCcw,
  UtensilsCrossed,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import DishArt from "@/components/dish-art";
import {
  Badge,
  ErrorBanner,
  Field,
  Select,
  Spinner,
  Tag,
  cx,
  inputClass,
  primaryButtonClass,
  quietButtonClass,
  smallButton,
} from "@/components/ui";
import { api, ApiError, type CookProfile } from "@/lib/api";
import { formatDate, formatDateTime, formatRelative, splitList } from "@/lib/format";
import { useNotifications } from "@/lib/notifications";
import { useSession } from "@/lib/session";
import { useZones } from "@/lib/use-zones";

const PERKS = [
  { icon: UtensilsCrossed, text: "Publish dishes - or keep them private until they're ready" },
  { icon: ClipboardCheck, text: "Accept only the orders you can cook" },
  { icon: Eye, text: "See what sells, who comes back and what you earn" },
  { icon: Banknote, text: "Get paid directly by your customer at pickup" },
];

/** Invented names - only their plate art is shown. */
const PLATES = ["Lamb Biryani", "Lemon Tart", "Miso Ramen"];

type Loaded = { loaded: false } | { loaded: true; application: CookProfile | null; error: string | null };

/**
 * The cook panel for signed-in users without a kitchen - rendered by the
 * cook shell on every /cook/* route. Becoming a cook is an application an
 * admin decides (GET /api/cooks/me/application):
 *
 * * none yet -> the application form (POST /api/cooks);
 * * `pending` -> "with our team": what was sent and what happens next;
 * * `rejected` -> the admin's reason, and *Apply again* (the form, filled in
 *   with the previous answers);
 * * `accepted` -> the session is refreshed: the `cook` role appears and the
 *   shell swaps this for the panel (covers a decision made while the user
 *   was signed in).
 *
 * The decision arrives as an /account notification, so the application is
 * re-read whenever that inbox's unread count changes - someone waiting on
 * this screen sees the answer without reloading.
 */
export default function KitchenOnboarding() {
  const { user, refresh: refreshSession } = useSession();
  const { counts } = useNotifications();
  const [state, setState] = useState<Loaded>({ loaded: false });
  const [reapplying, setReapplying] = useState(false);

  const load = useCallback(async () => {
    try {
      const application = await api.get<CookProfile>("/cooks/me/application");
      setState({ loaded: true, application, error: null });
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "no_application") {
        setState({ loaded: true, application: null, error: null });
      } else {
        setState({
          loaded: true,
          application: null,
          error: cause instanceof ApiError ? cause.message : "Could not reach the API",
        });
      }
    }
  }, []);

  const accountUnread = counts?.account;
  useEffect(() => {
    // Timeout kick-off (react-hooks/set-state-in-effect); re-read when a
    // decision may have arrived.
    const kickOff = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(kickOff);
  }, [load, accountUnread]);

  const accepted = state.loaded && state.application?.status === "accepted";
  useEffect(() => {
    if (!accepted) return;
    const kickOff = window.setTimeout(() => void refreshSession(), 0);
    return () => window.clearTimeout(kickOff);
  }, [accepted, refreshSession]);

  const applied = (application: CookProfile) => {
    setReapplying(false);
    setState({ loaded: true, application, error: null });
  };

  const firstName = user?.display_name?.split(" ")[0];
  const application = state.loaded ? state.application : null;
  return (
    <div className="grid grid-cols-1 overflow-hidden rounded-3xl border border-line bg-surface shadow-card lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <aside className="grain relative overflow-hidden bg-night p-6 text-on-night sm:p-10">
        <div
          aria-hidden="true"
          className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[radial-gradient(circle,var(--brand)_0%,transparent_70%)] opacity-30"
        />
        <p className="relative text-xs font-semibold uppercase tracking-[0.16em] text-brand">For home cooks</p>
        <h1 className="relative mt-3 font-display text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          {firstName ? `${firstName}, open` : "Open"} your kitchen{" "}
          <span className="italic text-brand">to the neighbourhood.</span>
        </h1>
        <div aria-hidden="true" className="relative my-8 hidden max-w-xs grid-cols-3 gap-3 sm:grid">
          {PLATES.map((name, index) => (
            <DishArt
              key={name}
              dish={{ name }}
              size="sm"
              className={index === 1 ? "aspect-square translate-y-4" : "aspect-square"}
            />
          ))}
        </div>
        <ul className="relative mt-6 space-y-3 text-sm text-on-night/80 sm:mt-0">
          {PERKS.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-start gap-3">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>
      </aside>

      <section className="p-6 sm:p-10" aria-live="polite">
        {!state.loaded ? (
          <div className="flex h-full min-h-64 items-center justify-center text-ink-muted" aria-busy="true">
            <Spinner className="h-6 w-6" />
          </div>
        ) : state.error ? (
          <div className="space-y-4">
            <ErrorBanner lines={[state.error]} />
            <button type="button" onClick={() => void load()} className={cx(quietButtonClass, smallButton)}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" /> Try again
            </button>
          </div>
        ) : application?.status === "accepted" ? (
          <Approved onOpen={() => void refreshSession()} />
        ) : application?.status === "pending" ? (
          <Pending application={application} />
        ) : application?.status === "rejected" && !reapplying ? (
          <Rejected application={application} onApplyAgain={() => setReapplying(true)} />
        ) : (
          <ApplicationForm
            key={reapplying ? "again" : "first"}
            previous={reapplying ? application : null}
            onApplied={applied}
            onConflict={() => void load()}
            onCancel={reapplying ? () => setReapplying(false) : undefined}
          />
        )}
      </section>
    </div>
  );
}

/** What the applicant sent: headline, specialties, neighbourhood. */
function Summary({ application }: { application: CookProfile }) {
  return (
    <div className="mt-6 rounded-2xl border border-line bg-canvas p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Your application</p>
      <p className="mt-2 font-display text-lg font-semibold leading-snug text-ink">“{application.headline}”</p>
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
    </div>
  );
}

function Pending({ application }: { application: CookProfile }) {
  const steps = [
    { label: "Application sent", detail: formatDateTime(application.submitted_at), done: true },
    { label: "Review by the Plateboard team", detail: "In progress", done: false, current: true },
    { label: "Your kitchen opens", detail: "Add dishes and take orders", done: false },
  ];
  return (
    <div>
      <Badge tone="saffron">
        <Hourglass className="h-3 w-3" aria-hidden="true" /> Waiting for review
      </Badge>
      <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-ink">
        Your application is with our team
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-ink-muted">
        Sent {formatRelative(application.submitted_at)}. An admin checks every new kitchen before it opens - you&apos;ll
        be notified on the bell and in your account as soon as they decide.
      </p>
      <ol className="mt-6 space-y-3">
        {steps.map((step, index) => (
          <li key={step.label} className="flex items-start gap-3">
            <span
              className={cx(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-bold",
                step.done
                  ? "border-herb bg-herb text-white"
                  : step.current
                    ? "border-saffron text-saffron"
                    : "border-line-strong text-ink-soft",
              )}
            >
              {step.done ? <CircleCheck className="h-4 w-4" aria-hidden="true" /> : index + 1}
            </span>
            <div>
              <p className={cx("text-sm font-semibold", step.done || step.current ? "text-ink" : "text-ink-soft")}>
                {step.label}
              </p>
              <p className="text-xs text-ink-soft">{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
      <Summary application={application} />
      <Link href="/account/notifications" className="mt-6 inline-flex text-sm font-medium text-brand hover:underline">
        Your notifications
      </Link>
    </div>
  );
}

function Rejected({ application, onApplyAgain }: { application: CookProfile; onApplyAgain: () => void }) {
  return (
    <div>
      <Badge>Not approved</Badge>
      <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-ink">
        Your application wasn&apos;t approved
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        The Plateboard team reviewed it{application.reviewed_at ? ` on ${formatDate(application.reviewed_at)}` : ""}.
      </p>
      <figure className="mt-5 rounded-2xl border border-line bg-canvas p-4">
        <figcaption className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">
          <MessageSquareQuote className="h-4 w-4" aria-hidden="true" /> Their reason
        </figcaption>
        <blockquote className="mt-2 text-sm leading-relaxed text-ink">
          {application.rejection_reason ? `“${application.rejection_reason}”` : "No reason was given."}
        </blockquote>
      </figure>
      <p className="mt-5 text-sm text-ink-muted">
        Update your details and apply again - your previous answers are filled in.
      </p>
      <button type="button" onClick={onApplyAgain} className={cx(primaryButtonClass, "mt-4 w-full sm:w-auto")}>
        <RotateCcw className="h-4 w-4" aria-hidden="true" /> Apply again
      </button>
      <Summary application={application} />
    </div>
  );
}

function Approved({ onOpen }: { onOpen: () => void }) {
  return (
    <div>
      <Badge tone="herb">
        <CircleCheck className="h-3 w-3" aria-hidden="true" /> Approved
      </Badge>
      <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-ink">Your kitchen is approved</h2>
      <p className="mt-1 text-sm text-ink-muted">Opening your kitchen panel…</p>
      <button type="button" onClick={onOpen} className={cx(primaryButtonClass, "mt-5")}>
        Open my kitchen
      </button>
    </div>
  );
}

/**
 * The application itself - first time, or again after a rejection (then
 * `previous` fills it in and `onCancel` goes back to the answer).
 */
function ApplicationForm({
  previous,
  onApplied,
  onConflict,
  onCancel,
}: {
  previous: CookProfile | null;
  onApplied: (application: CookProfile) => void;
  onConflict: () => void;
  onCancel?: () => void;
}) {
  const { zones } = useZones();
  const [headline, setHeadline] = useState(previous?.headline ?? "");
  const [specialties, setSpecialties] = useState(previous?.specialties.join(", ") ?? "");
  const [zone, setZone] = useState(previous?.zone?.slug ?? "");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    setFieldErrors({});
    try {
      onApplied(
        await api.post<CookProfile>("/cooks", {
          headline: headline.trim(),
          specialties: splitList(specialties).map((tag) => tag.toLowerCase()),
          ...(zone ? { zone } : {}),
        }),
      );
    } catch (cause) {
      if (cause instanceof ApiError && (cause.code === "application_pending" || cause.code === "already_cook")) {
        onConflict(); // decided or sent elsewhere meanwhile: show where it stands
      } else if (cause instanceof ApiError && cause.fieldErrors.length > 0) {
        setFieldErrors(Object.fromEntries(cause.fieldErrors.map((error) => [error.field, error.message])));
      } else {
        setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
      setBusy(false);
    }
  };

  return (
    <>
      <h2 className="font-display text-2xl font-semibold tracking-tight text-ink">
        {previous ? "Apply again" : "Apply in one step"}
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        {previous
          ? "Change what the team asked about - everything else is as you sent it."
          : "A headline and a few specialties are enough - you can polish everything once your kitchen opens."}
      </p>
      <form onSubmit={submit} className="mt-6 space-y-5">
        <ErrorBanner lines={errors} />
        <Field label="Headline" hint="One line customers see under your name." error={fieldErrors.headline}>
          <input
            value={headline}
            onChange={(event) => setHeadline(event.target.value)}
            placeholder="Biryani, reinvented one pot at a time"
            required
            minLength={3}
            maxLength={80}
            className={inputClass}
          />
        </Field>
        <Field label="Specialties" optional hint="Comma separated, e.g. biryani, korma." error={fieldErrors.specialties}>
          <input
            value={specialties}
            onChange={(event) => setSpecialties(event.target.value)}
            placeholder="biryani, korma"
            className={inputClass}
          />
        </Field>
        <Field
          label="Neighbourhood"
          optional
          hint="Where your kitchen is - customers filter dishes by distance."
          error={fieldErrors.zone}
        >
          <Select value={zone} onChange={(event) => setZone(event.target.value)} disabled={!zones}>
            <option value="">Choose later</option>
            {(zones ?? []).map((candidate) => (
              <option key={candidate.slug} value={candidate.slug}>
                {candidate.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" disabled={busy} className={`${primaryButtonClass} w-full sm:w-auto`}>
            {busy && <Spinner />} {previous ? "Send again" : "Send application"}
          </button>
          {onCancel && (
            <button type="button" onClick={onCancel} className={quietButtonClass}>
              Back
            </button>
          )}
        </div>
        <ul className="space-y-2 text-xs text-ink-soft">
          <li className="flex items-center gap-2">
            <Hourglass className="h-4 w-4 shrink-0 text-saffron" aria-hidden="true" />
            An admin reviews every new kitchen before it opens - you&apos;ll be notified.
          </li>
          <li className="flex items-center gap-2">
            <CircleCheck className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" />
            You keep your customer account - cooks order food too.
          </li>
        </ul>
      </form>
    </>
  );
}
