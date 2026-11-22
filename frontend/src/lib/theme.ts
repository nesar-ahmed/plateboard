/**
 * Light / dark theme - server-safe constants (the hook is lib/use-theme.ts).
 *
 * The theme is the `data-theme` attribute on <html> ("light" | "dark"); the
 * CSS tokens in globals.css switch on it. `THEME_SCRIPT` runs before the
 * first paint (inline in layout.tsx), so there is no flash of the wrong
 * palette: it applies the visitor's saved choice, or the system setting when
 * they never chose. The navbar switch saves a choice in localStorage; until
 * then the page keeps following the system (also when it changes).
 */

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "plateboard.theme";

export const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

/** Inline and render-blocking: keep it tiny and dependency-free. */
export const THEME_SCRIPT = `(function(){try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");var t=s==="light"||s==="dark"?s:(matchMedia("${SYSTEM_DARK_QUERY}").matches?"dark":"light");document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;
