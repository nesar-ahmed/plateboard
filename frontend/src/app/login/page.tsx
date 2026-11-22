"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import AuthShell from "@/components/auth-shell";
import PasswordInput from "@/components/password-input";
import { ErrorBanner, Field, Spinner, cx, inputClass, primaryButtonClass } from "@/components/ui";
import { api, ApiError, type User } from "@/lib/api";
import { homeFor, safeNextPath, useSession } from "@/lib/session";

/** `useSearchParams` (the `?next=` target) needs a Suspense boundary. */
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

/**
 * POST /api/auth/login - sets the HTTP-only session cookie (bad credentials
 * show the backend's generic 401 message). The backend moves this browser's
 * guest cart to the account at this moment; refreshing the session reloads
 * the cart, then we go to `?next=` (e.g. /checkout) or, without one, to the
 * panel of the user's role (`homeFor`: /admin, /cook or /account).
 */
function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const asked = params.get("next");
  const next = safeNextPath(asked);
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const atCheckout = next === "/checkout";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await api.post<User>("/auth/login", { email, password });
      const user = await refresh();
      router.push(asked ? next : homeFor(user));
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title={atCheckout ? "Log in to check out" : "Welcome back"}
      subtitle={atCheckout ? "Your bag is saved and moves to your account." : "Log in to order from cooks near you."}
    >
      <form onSubmit={submit} className="space-y-5">
        <ErrorBanner lines={errors} />
        <Field label="Email">
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
            autoFocus
            className={inputClass}
          />
        </Field>
        <Field label="Password">
          <PasswordInput
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <button type="submit" disabled={busy} className={cx(primaryButtonClass, "h-12 w-full text-[15px]")}>
          {busy ? <Spinner /> : null} Log in {!busy && <ArrowRight className="h-4 w-4" />}
        </button>
        <p className="text-center text-sm text-ink-muted">
          New to Plateboard?{" "}
          <Link
            href={next === "/account" ? "/register" : `/register?next=${encodeURIComponent(next)}`}
            className="font-semibold text-brand hover:underline"
          >
            Create an account
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}
