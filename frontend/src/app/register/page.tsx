"use client";

import { ArrowRight, Check } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import AuthShell from "@/components/auth-shell";
import PasswordInput from "@/components/password-input";
import { ErrorBanner, Field, Spinner, cx, inputClass, primaryButtonClass } from "@/components/ui";
import { api, ApiError, type User } from "@/lib/api";
import { safeNextPath, useSession } from "@/lib/session";

const PASSWORD_MIN = 8;
const NAME_MAX = 60;

/** `useSearchParams` (the `?next=` target) needs a Suspense boundary. */
export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}

/**
 * POST /api/auth/register, POST /api/auth/login (registration returns no
 * session on its own), then PATCH /api/me/profile with the name. The login
 * moves a guest cart to the new account, so "register at checkout" keeps the
 * dishes; then `?next=` or the account (/account). A failed name save never blocks
 * the new account - the name can be set later in /account/profile.
 */
function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNextPath(params.get("next"));
  const { refresh } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const longEnough = password.length >= PASSWORD_MIN;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!longEnough) {
      setErrors([`Use at least ${PASSWORD_MIN} characters for your password.`]);
      return;
    }
    setBusy(true);
    setErrors([]);
    try {
      await api.post<User>("/auth/register", { email, password });
      await api.post<User>("/auth/login", { email, password });
      if (name.trim()) {
        await api.patch<User>("/me/profile", { display_name: name.trim() }).catch(() => undefined);
      }
      await refresh();
      router.push(next);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle={next === "/checkout" ? "One step before checkout - your bag is saved." : "Order from home cooks near you in minutes."}
    >
      <form onSubmit={submit} className="space-y-5">
        <ErrorBanner lines={errors} />
        <Field label="Your name" optional hint="Shown to the cooks you order from.">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="name"
            maxLength={NAME_MAX}
            autoFocus
            className={inputClass}
          />
        </Field>
        <Field label="Email">
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
            className={inputClass}
          />
        </Field>
        <Field label="Password">
          <PasswordInput
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            required
            maxLength={128}
            aria-describedby="password-rule"
          />
          <span
            id="password-rule"
            className={cx("mt-1.5 flex items-center gap-1.5 text-xs", longEnough ? "text-herb" : "text-ink-soft")}
          >
            <Check className="h-3.5 w-3.5" aria-hidden="true" /> At least {PASSWORD_MIN} characters
          </span>
        </Field>
        <button type="submit" disabled={busy} className={cx(primaryButtonClass, "h-12 w-full text-[15px]")}>
          {busy ? <Spinner /> : null} Create account {!busy && <ArrowRight className="h-4 w-4" />}
        </button>
        <p className="text-center text-sm text-ink-muted">
          Already have an account?{" "}
          <Link
            href={next === "/account" ? "/login" : `/login?next=${encodeURIComponent(next)}`}
            className="font-semibold text-brand hover:underline"
          >
            Log in
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
