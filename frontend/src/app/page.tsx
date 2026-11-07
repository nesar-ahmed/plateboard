"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

type Health = {
  status: string;
  version?: string;
  environment?: string;
  database?: string;
  database_info?: {
    engine?: string;
    journal_mode?: string;
    foreign_keys?: boolean;
  };
};

const HEALTH_URL = "/api/health";
const REFRESH_INTERVAL_MS = 5_000;

function Dot({ tone, label }: { tone: "good" | "bad" | "waiting"; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 font-mono text-sm ${
        tone === "good"
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
          : tone === "bad"
            ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
            : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          tone === "good" ? "bg-emerald-500" : tone === "bad" ? "bg-red-500" : "bg-zinc-400"
        }`}
      />
      {label}
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-zinc-100 py-3 last:border-none dark:border-zinc-800">
      <dt className="text-sm text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="text-right font-mono text-sm text-zinc-900 dark:text-zinc-100">{children}</dd>
    </div>
  );
}

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const check = useCallback(async () => {
    try {
      const response = await fetch(HEALTH_URL, { cache: "no-store" });
      const body = (await response.json()) as Health;
      setHealth({ ...body, status: response.ok ? body.status : `${body.status} (${response.status})` });
      setError(response.ok ? null : `HTTP ${response.status}`);
    } catch (cause) {
      setHealth(null);
      setError(cause instanceof Error ? cause.message : "request failed");
    } finally {
      setCheckedAt(new Date());
    }
  }, []);

  useEffect(() => {
    // Fire the first probe from a callback (timeout 0) rather than the effect
    // body itself: the body must not set state synchronously
    // (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void check(), 0);
    const timer = window.setInterval(() => void check(), REFRESH_INTERVAL_MS);
    return () => {
      window.clearTimeout(kickOff);
      window.clearInterval(timer);
    };
  }, [check]);

  const status = health?.status ?? (error ? "down" : "checking");
  const tone = status === "ok" ? "good" : error || (health && health.status !== "ok") ? "bad" : "waiting";

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-8 font-sans">
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Plateboard
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Backend health</p>
          </div>
          <Dot tone={tone} label={status} />
        </header>

        <dl>
          <Row label="API status">
            <Dot tone={health?.status === "ok" ? "good" : health ? "bad" : "waiting"} label={health?.status ?? "…"} />
          </Row>
          <Row label="Database">
            <Dot
              tone={health?.database === "ok" ? "good" : health ? "bad" : "waiting"}
              label={health?.database ?? "…"}
            />
          </Row>
          {health?.database_info?.engine === "sqlite" && (
            <>
              <Row label="Journal mode">
                <code>{health.database_info.journal_mode}</code>
              </Row>
              <Row label="Foreign keys">
                <code>{health.database_info.foreign_keys ? "on" : "off"}</code>
              </Row>
            </>
          )}
          <Row label="Version">
            <code>{health?.version ?? "—"}</code>
          </Row>
          <Row label="Environment">
            <code>{health?.environment ?? "—"}</code>
          </Row>
        </dl>

        <footer className="mt-6 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
          <span>
            {error ? `Error: ${error}` : checkedAt ? `Last check: ${checkedAt.toLocaleTimeString()}` : "…"}
          </span>
          <button
            type="button"
            onClick={() => void check()}
            className="rounded-full border border-zinc-300 px-3 py-1 font-medium transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Check again
          </button>
        </footer>
      </div>

      <p className="text-xs text-zinc-400 dark:text-zinc-500">
        Polled from <code>{HEALTH_URL}</code> every {REFRESH_INTERVAL_MS / 1000}s
      </p>
    </main>
  );
}
