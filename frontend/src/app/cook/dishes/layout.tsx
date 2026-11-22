import type { Metadata } from "next";

/**
 * Server layout only for the tab title (the page is a Client Component).
 * It re-states the cook template: a nested layout with a plain title would
 * stop /cook/dishes/new from inheriting "%s · Your kitchen · Plateboard".
 */
export const metadata: Metadata = { title: { default: "Menu", template: "%s · Your kitchen · Plateboard" } };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
