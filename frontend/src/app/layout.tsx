import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import Nav from "@/components/nav";
import Providers from "@/components/providers";
import SiteFooter from "@/components/site-footer";
import { THEME_SCRIPT } from "@/lib/theme";
import "./globals.css";

/*
 * Every font is self-hosted from node_modules (next/font/local): the build
 * and the running server never call fonts.googleapis.com, so `npm run build`
 * works offline and nothing is fetched at runtime.
 *
 * - Geist Sans / Mono (the `geist` package) - UI text
 * - Fraunces (variable, @fontsource-variable/fraunces) - display headings
 */
const fraunces = localFont({
  src: [
    {
      path: "../../node_modules/@fontsource-variable/fraunces/files/fraunces-latin-wght-normal.woff2",
      style: "normal",
    },
    {
      path: "../../node_modules/@fontsource-variable/fraunces/files/fraunces-latin-wght-italic.woff2",
      style: "italic",
    },
  ],
  variable: "--font-fraunces",
  weight: "100 900",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Plateboard - home-cooked food from your neighbourhood",
    template: "%s · Plateboard",
  },
  description:
    "Order dishes made by home cooks near you. Honest ingredients, every allergen declared, one kitchen per order.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbf8f3" },
    { media: "(prefers-color-scheme: dark)", color: "#14110f" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning: THEME_SCRIPT sets data-theme on <html> before
    // React hydrates (on purpose - no flash of the wrong palette).
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <head>
        {/* Render-blocking on purpose: picks light/dark before the first paint (lib/theme.ts). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col bg-canvas text-ink">
        <a
          href="#main"
          className="sr-only z-[60] rounded-full bg-ink px-4 py-2 text-sm font-medium text-canvas focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
        >
          Skip to content
        </a>
        <Providers>
          <Nav />
          <main id="main" className="flex-1">
            {children}
          </main>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
