"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

import { SYSTEM_DARK_QUERY, THEME_STORAGE_KEY, type Theme } from "@/lib/theme";

function current(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

function apply(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

/**
 * The active theme (null while rendering on the server and hydrating - the
 * server cannot know it) and a setter that also remembers the choice.
 * Without a saved choice the page follows the system setting live.
 */
export function useTheme(): { theme: Theme | null; setTheme: (theme: Theme) => void } {
  const theme = useSyncExternalStore(subscribe, current, () => null);

  useEffect(() => {
    const media = window.matchMedia(SYSTEM_DARK_QUERY);
    const onSystem = () => {
      if (!window.localStorage.getItem(THEME_STORAGE_KEY)) apply(media.matches ? "dark" : "light");
    };
    media.addEventListener("change", onSystem);
    return () => media.removeEventListener("change", onSystem);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage disabled (private mode): still switch for this page view.
    }
    apply(next);
  }, []);

  return { theme, setTheme };
}
