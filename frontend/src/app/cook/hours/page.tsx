"use client";

import { CalendarClock, Copy, Infinity as InfinityIcon, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { AvailabilityPill, NextHours } from "@/components/availability";
import { ErrorBanner, PageHeader, Select, Spinner, cx, darkButtonClass, inputClass, quietButtonClass } from "@/components/ui";
import { api, ApiError, type AvailabilitySettings, type OpeningWindow } from "@/lib/api";
import { useApi } from "@/lib/use-api";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const WINDOWS_PER_DAY = 3;
/** The shared input look at a fixed width (inputClass is full-width). */
const timeInputClass = inputClass.replace("w-full", "w-[7.25rem] px-2.5 sm:w-[8.5rem] sm:px-3.5");

type Span = { opens: string; closes: string };
type Draft = { anytime: boolean; timezone: string; days: Span[][] };

/** API hours -> one list of spans per weekday ("24:00" shows as 00:00 = midnight). */
function toDraft(settings: AvailabilitySettings): Draft {
  const days: Span[][] = DAYS.map(() => []);
  for (const window of settings.hours) {
    days[window.day].push({ opens: window.opens, closes: window.closes === "24:00" ? "00:00" : window.closes });
  }
  return { anytime: settings.hours.length === 0, timezone: settings.timezone, days };
}

/** Draft -> API hours; a 00:00 close means midnight ("24:00"). */
function toHours(draft: Draft): OpeningWindow[] {
  if (draft.anytime) return [];
  return draft.days.flatMap((spans, day) =>
    spans.map((span) => ({ day, opens: span.opens, closes: span.closes === "00:00" ? "24:00" : span.closes })),
  );
}

function spanError(span: Span): string | null {
  if (!span.opens || !span.closes) return "Set both times";
  if (span.closes !== "00:00" && span.closes <= span.opens) return "Closes before it opens";
  return null;
}

function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

function allZones(current: string): string[] {
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return [...new Set([current, "UTC", ...zones])].sort();
}

/** /cook/hours - when the kitchen takes orders (GET/PUT /api/cooks/me/availability). */
export default function KitchenHoursPage() {
  const { data, error, setData } = useApi<AvailabilitySettings>("/cooks/me/availability");
  if (error) return <ErrorBanner lines={[error]} />;
  if (!data) {
    return (
      <div className="flex justify-center py-16 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  // Remount on every save so the form restarts from the server's answer.
  return <HoursForm key={JSON.stringify([data.timezone, data.hours, data.orders_paused])} saved={data} onSaved={setData} />;
}

function HoursForm({ saved, onSaved }: { saved: AvailabilitySettings; onSaved: (next: AvailabilitySettings) => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(saved));
  const [busy, setBusy] = useState<"save" | "pause" | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const detected = browserZone();

  const hours = toHours(draft);
  const dirty =
    draft.timezone !== saved.timezone || JSON.stringify(hours) !== JSON.stringify(saved.hours);
  const invalid = !draft.anytime && draft.days.some((spans) => spans.some((span) => spanError(span)));
  const noDays = !draft.anytime && hours.length === 0;

  const put = async (body: { timezone: string; hours: OpeningWindow[]; orders_paused: boolean }, kind: "save" | "pause") => {
    setBusy(kind);
    setErrors([]);
    try {
      onSaved(await api.put<AvailabilitySettings>("/cooks/me/availability", body));
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      setBusy(null);
    }
  };

  // The pause switch saves at once - from the *saved* hours, never a half-edited draft.
  const togglePause = () =>
    void put({ timezone: saved.timezone, hours: saved.hours, orders_paused: !saved.orders_paused }, "pause");
  const save = () => void put({ timezone: draft.timezone, hours, orders_paused: saved.orders_paused }, "save");

  const setDay = (day: number, spans: Span[]) =>
    setDraft((current) => ({ ...current, days: current.days.map((held, index) => (index === day ? spans : held)) }));

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Hours & availability"
        lead="When neighbours can order from you. Outside these hours your menu stays visible - orders wait until you open."
      />

      <ErrorBanner lines={errors} />

      <section aria-label="Right now" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Right now</p>
            <AvailabilityPill availability={saved.availability} className="mt-2 px-3 py-1 text-sm" />
          </div>
          <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-line px-4 py-3">
            <span className="text-sm">
              <span className="block font-semibold text-ink">Pause new orders</span>
              <span className="block text-xs text-ink-muted">Busy or away? Customers can&apos;t order until you switch back.</span>
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={saved.orders_paused}
              aria-label="Pause new orders"
              disabled={busy !== null}
              onClick={togglePause}
              className={cx(
                "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50",
                saved.orders_paused ? "bg-saffron" : "bg-line-strong",
              )}
            >
              <span
                className={cx(
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
                  saved.orders_paused ? "left-[22px]" : "left-0.5",
                )}
              />
            </button>
          </label>
        </div>
        <div className="mt-6 border-t border-line pt-5">
          <p className="mb-3 text-sm font-semibold text-ink">What customers see for the next 24 hours</p>
          <NextHours availability={saved.availability} />
        </div>
      </section>

      <section aria-label="Weekly hours" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
          <CalendarClock className="h-5 w-5 text-brand" aria-hidden="true" /> Weekly hours
        </h2>
        <div role="radiogroup" aria-label="Schedule" className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {[
            { anytime: true, icon: InfinityIcon, title: "No fixed hours", text: "Take orders any time - you still accept each one." },
            { anytime: false, icon: CalendarClock, title: "Weekly hours", text: "Take orders only inside the times you set." },
          ].map((option) => {
            const on = draft.anytime === option.anytime;
            return (
              <button
                key={option.title}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setDraft((current) => ({ ...current, anytime: option.anytime }))}
                className={cx(
                  "flex items-start gap-3 rounded-2xl border p-4 text-left transition-colors",
                  on ? "border-ink bg-muted" : "border-line-strong hover:border-ink-soft",
                )}
              >
                <span
                  className={cx(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
                    on ? "bg-ink text-canvas" : "bg-muted text-ink-muted",
                  )}
                >
                  <option.icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span>
                  <span className="block text-sm font-semibold text-ink">{option.title}</span>
                  <span className="block text-xs leading-relaxed text-ink-muted">{option.text}</span>
                </span>
              </button>
            );
          })}
        </div>

        {!draft.anytime && (
          <>
            <ul className="mt-6 divide-y divide-line">
              {DAYS.map((name, day) => {
                const spans = draft.days[day];
                const open = spans.length > 0;
                return (
                  <li key={name} className="grid grid-cols-1 gap-3 py-4 sm:grid-cols-[150px_minmax(0,1fr)] sm:items-start">
                    <label className="flex items-center gap-3 text-sm font-medium text-ink sm:pt-2.5">
                      <input
                        type="checkbox"
                        checked={open}
                        onChange={() => setDay(day, open ? [] : [{ opens: "11:00", closes: "21:00" }])}
                        className="h-4 w-4 rounded accent-[var(--brand)]"
                      />
                      {name}
                    </label>
                    {open ? (
                      <div className="space-y-2">
                        {spans.map((span, index) => {
                          const problem = spanError(span);
                          const update = (patch: Partial<Span>) =>
                            setDay(day, spans.map((held, i) => (i === index ? { ...held, ...patch } : held)));
                          return (
                            <div key={index} className="flex flex-wrap items-center gap-2">
                              <input
                                type="time"
                                value={span.opens}
                                onChange={(event) => update({ opens: event.target.value })}
                                aria-label={`${name} opens`}
                                className={cx(timeInputClass, "h-10", problem && "border-danger")}
                              />
                              <span className="text-sm text-ink-soft">to</span>
                              <input
                                type="time"
                                value={span.closes}
                                onChange={(event) => update({ closes: event.target.value })}
                                aria-label={`${name} closes`}
                                className={cx(timeInputClass, "h-10", problem && "border-danger")}
                              />
                              {span.closes === "00:00" && <span className="text-xs text-ink-soft">midnight</span>}
                              <button
                                type="button"
                                onClick={() => setDay(day, spans.filter((_, i) => i !== index))}
                                aria-label={`Remove ${name} ${span.opens}-${span.closes}`}
                                className={cx(quietButtonClass, "h-9 w-9 px-0 hover:text-danger")}
                              >
                                <Trash2 className="h-4 w-4" aria-hidden="true" />
                              </button>
                              {problem && <span className="w-full text-xs font-medium text-danger">{problem}</span>}
                            </div>
                          );
                        })}
                        {spans.length < WINDOWS_PER_DAY && (
                          <button
                            type="button"
                            onClick={() => setDay(day, [...spans, { opens: "17:00", closes: "21:00" }])}
                            className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline"
                          >
                            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add hours
                          </button>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-ink-soft sm:pt-2.5">Closed</p>
                    )}
                  </li>
                );
              })}
            </ul>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line pt-4 text-sm">
              <button
                type="button"
                onClick={() => setDraft((current) => ({ ...current, days: current.days.map(() => [...current.days[0]]) }))}
                className="inline-flex items-center gap-1.5 font-medium text-brand hover:underline"
              >
                <Copy className="h-3.5 w-3.5" aria-hidden="true" /> Copy Monday to every day
              </button>
              <span className="text-xs text-ink-soft">A closing time of 00:00 means midnight.</span>
            </div>
          </>
        )}

        <div className="mt-6 border-t border-line pt-5">
          <label className="block max-w-md">
            <span className="mb-1.5 block text-sm font-medium text-ink">Your time zone</span>
            <Select value={draft.timezone} onChange={(event) => setDraft((current) => ({ ...current, timezone: event.target.value }))}>
              {allZones(draft.timezone).map((zone) => (
                <option key={zone} value={zone}>
                  {zone.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
            <span className="mt-1.5 block text-xs text-ink-soft">
              Your hours are in this zone; customers see them in their own time.
              {detected !== draft.timezone && (
                <>
                  {" "}
                  <button
                    type="button"
                    onClick={() => setDraft((current) => ({ ...current, timezone: detected }))}
                    className="font-medium text-brand hover:underline"
                  >
                    Use {detected.replaceAll("_", " ")} (this device)
                  </button>
                </>
              )}
            </span>
          </label>
        </div>
      </section>

      <div className="sticky bottom-4 z-10 flex flex-col gap-3 rounded-3xl border border-line bg-surface/95 p-4 shadow-lift backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className={cx("text-sm", noDays || invalid ? "text-danger" : "text-ink-muted")} aria-live="polite">
          {noDays
            ? "Open at least one day - or choose \u201cNo fixed hours\u201d, or pause orders."
            : invalid
              ? "Fix the highlighted hours first."
              : dirty
                ? "You have unsaved changes."
                : "Everything is saved."}
        </p>
        <button type="button" disabled={!dirty || invalid || noDays || busy !== null} onClick={save} className={darkButtonClass}>
          {busy === "save" && <Spinner />} Save hours
        </button>
      </div>
    </div>
  );
}
