import Link from "next/link";

import Logo from "@/components/logo";
import { Container } from "@/components/ui";

const COLUMNS = [
  {
    title: "Explore",
    links: [
      { href: "/dishes", label: "All dishes" },
      { href: "/cooks", label: "Home cooks" },
      { href: "/dishes?dietary_tag=vegan", label: "Vegan dishes" },
      { href: "/#how-it-works", label: "How it works" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/login", label: "Log in" },
      { href: "/register", label: "Create an account" },
      { href: "/account", label: "My account" },
      { href: "/checkout", label: "Checkout" },
    ],
  },
  {
    title: "Cook with us",
    links: [
      { href: "/register?next=/cook", label: "Open your kitchen" },
      { href: "/health", label: "Service status" },
    ],
  },
];

export default function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-line bg-surface print:hidden">
      <Container className="py-12">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
          <div className="max-w-xs">
            <Logo />
            <p className="mt-4 text-sm leading-relaxed text-ink-muted">
              Home-cooked food from the kitchens in your neighbourhood. Every ingredient listed,
              every allergen declared.
            </p>
          </div>
          {COLUMNS.map((column) => (
            <div key={column.title}>
              <p className="text-sm font-semibold text-ink">{column.title}</p>
              <ul className="mt-3 space-y-2.5">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="text-sm text-ink-muted transition-colors hover:text-ink">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col gap-2 border-t border-line pt-6 text-xs text-ink-soft sm:flex-row sm:justify-between">
          <p>© {new Date().getFullYear()} Plateboard. Cooked at home, listed in the open.</p>
          <p>One kitchen per order · Every allergen declared</p>
        </div>
      </Container>
    </footer>
  );
}
