"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card, ErrorBanner, Field, inputClass, primaryButtonClass } from "@/components/ui";
import { api, ApiError, type User } from "@/lib/api";

/** POST /api/auth/login - sets the HTTP-only session cookie, then lands on
 * the dashboard (bad credentials show the backend's generic 401 message). */
export default function LoginPage() {
  const router = useRouter();
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
      router.push("/dashboard");
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
            <Link href="/register" className="text-emerald-700 hover:underline dark:text-emerald-400">
              Register
            </Link>
          </p>
        </form>
      </Card>
    </div>
  );
}
