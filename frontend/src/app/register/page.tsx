"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card, ErrorBanner, Field, inputClass, primaryButtonClass } from "@/components/ui";
import { api, ApiError, type User } from "@/lib/api";

/**
 * POST /api/auth/register then POST /api/auth/login (registration returns no
 * session on its own), landing on the dashboard as a fresh customer.
 */
export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== repeat) {
      setErrors(["passwords do not match"]);
      return;
    }
    setBusy(true);
    setErrors([]);
    try {
      await api.post<User>("/auth/register", { email, password });
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
      <Card title="Create an account">
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
          <Field label="Password" hint="At least 8 characters.">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
              className={inputClass}
            />
          </Field>
          <Field label="Repeat password">
            <input
              type="password"
              value={repeat}
              onChange={(event) => setRepeat(event.target.value)}
              autoComplete="new-password"
              required
              className={inputClass}
            />
          </Field>
          <button type="submit" disabled={busy} className={primaryButtonClass}>
            {busy ? "Creating..." : "Register"}
          </button>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Already registered?{" "}
            <Link href="/login" className="text-emerald-700 hover:underline dark:text-emerald-400">
              Log in
            </Link>
          </p>
        </form>
      </Card>
    </div>
  );
}
