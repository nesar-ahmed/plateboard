"use client";

import { ChefHat, ChevronDown, LayoutDashboard, LogOut, Menu, ShieldCheck, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import CartButton from "@/components/cart-button";
import Logo from "@/components/logo";
import NotificationBell from "@/components/notification-bell";
import ThemeToggle from "@/components/theme-toggle";
import { Avatar, cx, darkButtonClass, quietButtonClass, smallButton } from "@/components/ui";
import { api, type User } from "@/lib/api";
import { useSession } from "@/lib/session";

/** The role panels a signed-in user can open (besides /account). */
function panelLinks(user: User): { href: string; label: string; icon: LucideIcon }[] {
  return [
    ...(user.roles.includes("admin") ? [{ href: "/admin", label: "Admin panel", icon: ShieldCheck }] : []),
    ...(user.roles.includes("cook") ? [{ href: "/cook", label: "My kitchen", icon: ChefHat }] : []),
  ];
}

const LINKS = [
  { href: "/dishes", label: "Dishes" },
  { href: "/cooks", label: "Cooks" },
  { href: "/#how-it-works", label: "How it works" },
];

/**
 * Site header: sticky, translucent. Desktop shows links, the notification
 * bell (signed in), the cart and the account menu; below `md` it collapses
 * to logo + bell + cart + a menu sheet.
 * Searching lives on the pages that list dishes (landing hero, /dishes).
 * Auth state comes from the shared session (lib/session.tsx).
 */
export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, checked, refresh } = useSession();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const logout = async () => {
    setSheetOpen(false);
    try {
      await api.post("/auth/logout", {});
    } finally {
      router.push("/"); // leave signed-in pages first...
      await refresh(); // ...then become a guest; the cart follows (guest cart)
    }
  };

  const isActive = (href: string) => !href.includes("#") && pathname.startsWith(href);

  return (
    <header
      className={cx(
        "sticky top-0 z-40 border-b bg-canvas/85 backdrop-blur-lg transition-colors print:hidden",
        scrolled || sheetOpen ? "border-line" : "border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Logo onClick={() => setSheetOpen(false)} />

        <nav aria-label="Main" className="ml-6 hidden items-center gap-1 md:flex">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={isActive(link.href) ? "page" : undefined}
              className={cx(
                "rounded-full px-3.5 py-2 text-sm font-medium transition-colors",
                isActive(link.href) ? "bg-muted text-ink" : "text-ink-muted hover:text-ink",
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
          <ThemeToggle />
          {/* Keyed on the account: another user never sees a cached preview. */}
          {user && <NotificationBell key={user.id} user={user} />}
          <CartButton />
          <div className="hidden items-center gap-1 md:flex">
            {/* One entry point: the login page links to registration. */}
            {checked && !user && (
              <Link href="/login" className={cx(darkButtonClass, smallButton)}>
                Log in
              </Link>
            )}
            {user && <AccountMenu user={user} onLogout={() => void logout()} />}
          </div>
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center rounded-full text-ink hover:bg-muted md:hidden"
            aria-expanded={sheetOpen}
            aria-controls="mobile-menu"
            aria-label={sheetOpen ? "Close menu" : "Open menu"}
            onClick={() => setSheetOpen((open) => !open)}
          >
            {sheetOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {sheetOpen && (
        <div id="mobile-menu" className="animate-fade-in border-t border-line bg-canvas md:hidden">
          <div className="space-y-5 px-4 pb-6 pt-4">
            <nav aria-label="Mobile" className="grid gap-1">
              {LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setSheetOpen(false)}
                  className={cx(
                    "rounded-2xl px-4 py-3 text-base font-medium",
                    isActive(link.href) ? "bg-muted text-ink" : "text-ink-muted",
                  )}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
            <div className="border-t border-line pt-5">
              {user ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 px-1">
                    <Avatar name={user.display_name ?? user.email} />
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">{user.display_name ?? "Your account"}</p>
                      <p className="truncate text-sm text-ink-muted">{user.email}</p>
                    </div>
                  </div>
                  {panelLinks(user).map((panel) => (
                    <Link
                      key={panel.href}
                      href={panel.href}
                      onClick={() => setSheetOpen(false)}
                      className={cx(quietButtonClass, "w-full border border-line-strong")}
                    >
                      <panel.icon className="h-4 w-4" /> {panel.label}
                    </Link>
                  ))}
                  <div className="grid grid-cols-2 gap-2">
                    <Link
                      href="/account"
                      onClick={() => setSheetOpen(false)}
                      className={cx(darkButtonClass, "w-full")}
                    >
                      My account
                    </Link>
                    <button type="button" onClick={() => void logout()} className={cx(quietButtonClass, "w-full border border-line-strong")}>
                      Log out
                    </button>
                  </div>
                </div>
              ) : (
                <Link href="/login" onClick={() => setSheetOpen(false)} className={cx(darkButtonClass, "w-full")}>
                  Log in
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

function AccountMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = user.display_name ?? user.email;
  const role = user.roles.includes("admin") ? "Admin" : user.roles.includes("cook") ? "Cook" : "Customer";
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 items-center gap-2 rounded-full border border-line bg-surface pl-1 pr-3 text-sm font-medium text-ink hover:border-line-strong"
      >
        <Avatar name={name} size="sm" />
        <span className="max-w-28 truncate">{user.display_name?.split(" ")[0] ?? "Account"}</span>
        <ChevronDown className={cx("h-4 w-4 text-ink-soft transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div
          role="menu"
          className="animate-rise absolute right-0 top-12 w-64 overflow-hidden rounded-2xl border border-line bg-surface p-1.5 shadow-pop"
        >
          <div className="px-3 pb-3 pt-2">
            <p className="truncate font-medium text-ink">{name}</p>
            <p className="truncate text-xs text-ink-muted">
              {user.email} · {role}
            </p>
          </div>
          <div className="border-t border-line pt-1.5">
            {[...panelLinks(user), { href: "/account", label: "My account", icon: LayoutDashboard }].map((item) => (
              <Link
                key={item.href}
                role="menuitem"
                href={item.href}
                onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-ink hover:bg-muted"
              >
                <item.icon className="h-4 w-4 text-ink-muted" /> {item.label}
              </Link>
            ))}
            <button
              role="menuitem"
              type="button"
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm text-ink hover:bg-muted"
            >
              <LogOut className="h-4 w-4 text-ink-muted" /> Log out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
