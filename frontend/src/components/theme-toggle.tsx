"use client";

import { Moon, Sun } from "lucide-react";

import { cx } from "@/components/ui";
import { useTheme } from "@/lib/use-theme";

/**
 * Navbar light/dark switch: one icon button showing what a click switches
 * *to* (moon in light mode, sun in dark mode). Before hydration the theme is
 * unknown, so it renders an empty placeholder of the same size - no layout
 * shift, no mismatched icon.
 */
export default function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      disabled={theme === null}
      aria-label={theme === null ? "Switch theme" : `Switch to ${next} mode`}
      title={theme === null ? undefined : `Switch to ${next} mode`}
      className={cx(
        "flex h-10 w-10 items-center justify-center rounded-full text-ink transition-colors hover:bg-muted",
        className,
      )}
    >
      {theme === "dark" ? (
        <Sun className="h-5 w-5" aria-hidden="true" />
      ) : theme === "light" ? (
        <Moon className="h-5 w-5" aria-hidden="true" />
      ) : null}
    </button>
  );
}
