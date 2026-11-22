import type { Metadata } from "next";

/** Server layout only for the tab title (the page is a Client Component). */
export const metadata: Metadata = { title: "Kitchen profile" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
