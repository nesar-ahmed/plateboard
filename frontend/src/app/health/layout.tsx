import type { Metadata } from "next";

import { Page } from "@/components/ui";

export const metadata: Metadata = { title: "Service status" };

/** Page column for this (pre-redesign) route; its own markup stays unchanged. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <Page>{children}</Page>;
}
