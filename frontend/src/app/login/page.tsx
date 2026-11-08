"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Card, ErrorBanner, Field, inputClass, primaryButtonClass } from "@/components/ui";
import { api, ApiError, type User } from "@/lib/api";
import { safeNextPath, useSession } from "@/lib/session";

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
 * the cart, then we go to `?next=` (e.g. /checkout) or the dashboard.
 */
function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNextPath(params.get("next"));
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await api.post<User>("/auth/login", { email, password });
      await refresh();
      router.push(next);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-md">
      <Card title="Log in">
        <form onSubmit={submit} className="space-y-4">
          {next === "/checkout" && (
            <p className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
              Log in to check out - your cart is kept and moves to your account.
            </p>
          )}
          <ErrorBanner lines={errors} />
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
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              className={inputClass}
            />
          </Field>
          <button type="submit" disabled={busy} className={primaryButtonClass}>
            {busy ? "Logging in..." : "Log in"}
          </button>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No account yet?{" "}
            <Link
              href={next === "/dashboard" ? "/register" : `/register?next=${encodeURIComponent(next)}`}
              className="text-emerald-700 hover:underline dark:text-emerald-400"
            >
              Register
            </Link>
          </p>
        </form>
      </Card>
    </div>
  );
}
