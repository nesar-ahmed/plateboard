"use client";

import { KeyRound, LogOut, MonitorSmartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import PasswordInput from "@/components/password-input";
import {
  Badge,
  ErrorBanner,
  Field,
  PageHeader,
  Spinner,
  cx,
  darkButtonClass,
  ghostButtonClass,
  smallButton,
} from "@/components/ui";
import { api, ApiError, type SessionInfo } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/format";
import { useNotifications } from "@/lib/notifications";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const PASSWORD_MIN = 8;
const SESSIONS_SHOWN = 6;

/** /account/security - password (POST /api/me/password) + signed-in sessions. */
export default function SecurityPage() {
  return (
    <div className="space-y-6">
      <PageHeader size="compact" title="Login & security" lead="Keep your account yours." />
      <PasswordCard />
      <SessionsCard />
    </div>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const notifications = useNotifications();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    setFieldError(null);
    setDone(null);
    try {
      const result = await api.post<{ signed_out_sessions: number }>("/me/password", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      const n = result.signed_out_sessions;
      void notifications.refresh(); // the security notice is in the inbox now
      setDone(`Password changed.${n ? ` We signed you out on ${n} other ${n === 1 ? "session" : "sessions"}.` : ""}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.fieldErrors.some((e) => e.type === "wrong_password")) {
        setFieldError("That's not your current password.");
      } else {
        setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
        <KeyRound className="h-5 w-5 text-ink-soft" aria-hidden="true" /> Password
      </h2>
      <p className="mt-1 text-sm text-ink-muted">Changing it signs you out everywhere except here.</p>
      <form onSubmit={submit} className="mt-5 max-w-md space-y-4">
        <ErrorBanner lines={errors} />
        {done && (
          <p role="status" className="rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
            {done}
          </p>
        )}
        <Field label="Current password" error={fieldError}>
          <PasswordInput value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </Field>
        <Field label="New password" hint={`At least ${PASSWORD_MIN} characters, different from the current one.`}>
          <PasswordInput
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            minLength={PASSWORD_MIN}
            maxLength={128}
            required
          />
        </Field>
        <button
          type="submit"
          disabled={busy || !current || next.length < PASSWORD_MIN}
          className={darkButtonClass}
        >
          {busy && <Spinner />} Change password
        </button>
      </form>
    </section>
  );
}

function SessionsCard() {
  const router = useRouter();
  const { refresh } = useSession();
  const { data: sessions, error, reload } = useApi<SessionInfo[]>("/me/sessions");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const others = (sessions ?? []).filter((session) => !session.current).length;

  const signOutOthers = async () => {
    setBusy(true);
    try {
      const { signed_out_sessions: n } = await api.post<{ signed_out_sessions: number }>("/me/sessions/revoke-others", {});
      setMessage(`Signed out ${n} other ${n === 1 ? "session" : "sessions"}.`);
      await reload();
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  const logOut = async () => {
    try {
      await api.post("/auth/logout", {});
    } finally {
      router.push("/");
      await refresh();
    }
  };

  return (
    <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
            <MonitorSmartphone className="h-5 w-5 text-ink-soft" aria-hidden="true" /> Where you&apos;re signed in
          </h2>
          <p className="mt-1 text-sm text-ink-muted">Sessions last 7 days unless you log out.</p>
        </div>
        {others > 0 && (
          <button type="button" onClick={() => setConfirming(true)} className={cx(ghostButtonClass, smallButton)}>
            Sign out other sessions
          </button>
        )}
      </div>

      <ErrorBanner lines={error ? [error] : []} />
      {message && (
        <p role="status" className="mt-4 rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          {message}
        </p>
      )}

      {!sessions ? (
        <div className="mt-5 h-24 animate-pulse rounded-2xl bg-muted" aria-busy="true" />
      ) : (
        <ul className="mt-5 divide-y divide-line">
          {sessions.slice(0, SESSIONS_SHOWN).map((session) => (
            <li key={session.id} className="flex items-center gap-4 py-3.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-ink-muted">
                <MonitorSmartphone className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="flex-1">
                <p className="flex items-center gap-2 text-sm font-medium text-ink">
                  Browser session {session.current && <Badge tone="herb">This device</Badge>}
                </p>
                <p className="text-xs text-ink-soft">
                  Signed in {formatRelative(session.created_at)} · expires {formatDate(session.expires_at)}
                </p>
              </div>
            </li>
          ))}
          {sessions.length > SESSIONS_SHOWN && (
            <li className="py-3 text-sm text-ink-soft">
              +{sessions.length - SESSIONS_SHOWN} more {sessions.length - SESSIONS_SHOWN === 1 ? "session" : "sessions"}
            </li>
          )}
        </ul>
      )}

      <div className="mt-4 border-t border-line pt-4">
        <button type="button" onClick={() => void logOut()} className={cx(ghostButtonClass, smallButton)}>
          <LogOut className="h-4 w-4" aria-hidden="true" /> Log out on this device
        </button>
      </div>

      {confirming && (
        <ConfirmDialog
          title="Sign out everywhere else?"
          confirmLabel="Sign them out"
          busy={busy}
          onConfirm={() => void signOutOthers()}
          onCancel={() => setConfirming(false)}
        >
          {others} other {others === 1 ? "session" : "sessions"} will need to log in again. You stay signed in here.
        </ConfirmDialog>
      )}
    </section>
  );
}
