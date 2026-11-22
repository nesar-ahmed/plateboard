"use client";

import { ArrowLeft, Check, Lock, MapPin, Pencil, Phone, Plus, ShoppingBag, StickyNote } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import AddressForm from "@/components/address-form";
import { AvailabilityPill } from "@/components/availability";
import DishArt from "@/components/dish-art";
import {
  Avatar,
  Badge,
  ButtonLink,
  Container,
  EmptyState,
  ErrorBanner,
  Spinner,
  cx,
  primaryButtonClass,
  quietButtonClass,
  smallButton,
  textareaClass,
} from "@/components/ui";
import VerifiedBadge from "@/components/verified-badge";
import { api, ApiError, type Address, type CookPublic, type Order } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { formatMinorUnits } from "@/lib/format";
import { useNotifications } from "@/lib/notifications";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const NOTE_MAX = 300;

/**
 * Checkout - signed-in users only. Guests are sent to log in first
 * (`/login?next=/checkout`); the backend moves their guest cart to the
 * account at that login, so the same dishes are waiting here.
 *
 * One page, three steps: where it goes (pick a saved address or add one),
 * a note for the cook, and the order review. "Place order" posts the cart
 * with the chosen address (POST /api/me/orders) and opens the order page.
 */
export default function CheckoutPage() {
  const router = useRouter();
  const { user, checked } = useSession();
  const { cart, openDrawer, reload } = useCart();
  const notifications = useNotifications();
  // Only a visitor who *arrives* signed out is sent to log in. Someone who
  // logs out while on this page is on their way home (the nav navigates);
  // redirecting them to the login form would race with that.
  const sawUser = useRef(false);

  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState("");
  const [placing, setPlacing] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  // The bag's kitchen: verified? taking orders right now? (orders are only
  // placed while it is - the API answers 409 kitchen_closed otherwise)
  const kitchen = useApi<CookPublic>(cart?.cook ? `/cooks/${cart.cook.id}` : null);

  useEffect(() => {
    if (user) sawUser.current = true;
    else if (checked && !sawUser.current) router.replace("/login?next=/checkout");
  }, [checked, user, router]);

  const loadAddresses = useCallback(async () => {
    try {
      const book = await api.get<Address[]>("/me/addresses");
      setAddresses(book);
      setSelected((current) =>
        current && book.some((a) => a.id === current) ? current : (book.find((a) => a.is_default) ?? book[0])?.id ?? null,
      );
      setAdding(book.length === 0);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not load your addresses"]);
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    const kickOff = window.setTimeout(() => void loadAddresses(), 0);
    return () => window.clearTimeout(kickOff);
  }, [user, loadAddresses]);

  if (!checked || !user) {
    return (
      <Container className="py-24 text-center text-ink-muted">
        {checked ? "Taking you to log in…" : <Spinner className="h-6 w-6" />}
      </Container>
    );
  }

  const items = cart?.items ?? [];
  const available = items.filter((item) => item.available);
  const closed = kitchen.data !== null && !kitchen.data.availability.accepting_orders;
  const canPlace =
    !!selected && available.length > 0 && (cart?.unavailable_count ?? 0) === 0 && !placing && !closed;

  const placeOrder = async () => {
    if (!selected) return;
    setPlacing(true);
    setErrors([]);
    try {
      const order = await api.post<Order>("/me/orders", { address_id: selected, note: note.trim() || null });
      await reload();
      void notifications.refresh(); // the order confirmation is in the inbox now
      router.push(`/account/orders/${order.id}?placed=1`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "cart_changed") {
        await reload();
        setErrors(["Your bag changed while placing the order - please check it and try again."]);
      } else if (cause instanceof ApiError && cause.code === "kitchen_closed") {
        await kitchen.reload(); // show when it opens again
        setErrors(["This kitchen stopped taking orders a moment ago - your bag is saved for when it opens."]);
      } else if (cause instanceof ApiError && cause.fieldErrors.some((e) => e.type === "unknown_address")) {
        await loadAddresses();
        setErrors(["That address is no longer in your address book - please pick another."]);
      } else {
        setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
      setPlacing(false);
    }
  };

  if (cart !== null && items.length === 0) {
    return (
      <Container size="narrow" className="py-16">
        <EmptyState
          icon={<ShoppingBag className="h-6 w-6" />}
          title="Your bag is empty"
          action={<ButtonLink href="/dishes">Browse dishes</ButtonLink>}
        >
          Add a few dishes from one kitchen, then come back here to check out.
        </EmptyState>
      </Container>
    );
  }

  return (
    <Container className="pb-32 pt-8 sm:pt-10 lg:pb-16">
      <Link href="/dishes" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Keep shopping
      </Link>
      <h1 className="mt-4 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Checkout</h1>
      <p className="mt-1 text-ink-muted">Ordering as {user.display_name ?? user.email}</p>

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start">
        <div className="min-w-0 space-y-6">
          <ErrorBanner lines={errors} />

          <Step number={1} title="Delivery address" icon={MapPin}>
            {addresses === null ? (
              <div className="h-24 animate-pulse rounded-2xl bg-muted" />
            ) : (
              <div className="space-y-3">
                {addresses.length > 0 && (
                  <div role="radiogroup" aria-label="Saved addresses" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {addresses.map((address) => (
                      <AddressOption
                        key={address.id}
                        address={address}
                        checked={selected === address.id}
                        onSelect={() => setSelected(address.id)}
                      />
                    ))}
                  </div>
                )}
                {adding ? (
                  <div className="rounded-2xl border border-line bg-canvas p-4 sm:p-5">
                    <p className="mb-4 font-medium text-ink">{addresses.length ? "Add a new address" : "Where should we bring it?"}</p>
                    <AddressForm
                      defaultRecipient={user.display_name}
                      hasAddresses={addresses.length > 0}
                      onCancel={addresses.length ? () => setAdding(false) : undefined}
                      onSaved={(address) => {
                        setSelected(address.id);
                        setAdding(false);
                        void loadAddresses();
                      }}
                    />
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setAdding(true)}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-line-strong py-4 text-sm font-medium text-ink-muted hover:border-ink-soft hover:text-ink"
                  >
                    <Plus className="h-4 w-4" /> Add a new address
                  </button>
                )}
              </div>
            )}
          </Step>

          <Step number={2} title="Note for the cook" icon={StickyNote} optional>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value.slice(0, NOTE_MAX))}
              rows={3}
              placeholder="Less spicy please, no coriander, ring the bell…"
              aria-label="Note for the cook"
              className={textareaClass}
            />
            <p className="mt-1.5 text-right text-xs text-ink-soft">
              {note.length}/{NOTE_MAX}
            </p>
          </Step>

          <Step
            number={3}
            title="Your order"
            icon={ShoppingBag}
            action={
              <button type="button" onClick={openDrawer} className={cx(quietButtonClass, smallButton)}>
                <Pencil className="h-3.5 w-3.5" /> Edit bag
              </button>
            }
          >
            {cart === null ? (
              <div className="h-24 animate-pulse rounded-2xl bg-muted" />
            ) : (
              <ul className="divide-y divide-line">
                {items.map((item) => (
                  <li key={item.dish_id} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
                    <DishArt dish={item} size="xs" className="h-14 w-14 shrink-0" rounded="rounded-xl" />
                    <div className="min-w-0 flex-1">
                      <p className={cx("truncate font-medium", item.available ? "text-ink" : "text-ink-soft line-through")}>
                        {item.name}
                      </p>
                      <p className="text-sm text-ink-muted">
                        {item.quantity} × {formatMinorUnits(item.price)}
                        {!item.available && <span className="ml-2 text-saffron no-underline">unavailable</span>}
                      </p>
                    </div>
                    <p className="font-semibold tabular-nums text-ink">
                      {item.available ? formatMinorUnits(item.line_total) : "—"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Step>
        </div>

        <aside className="min-w-0 lg:sticky lg:top-24">
          <div className="rounded-3xl border border-line bg-surface p-6 shadow-card">
            {cart?.cook && (
              <div className="flex items-center gap-3 border-b border-line pb-5">
                <Avatar name={cart.cook.name} />
                <div className="min-w-0">
                  <p className="text-xs text-ink-soft">Cooked by</p>
                  <p className="flex items-center gap-1 font-medium text-ink">
                    {cart.cook.name ?? "A home cook"}
                    {kitchen.data?.verified && <VerifiedBadge compact />}
                  </p>
                  {kitchen.data && <AvailabilityPill availability={kitchen.data.availability} className="mt-1" />}
                </div>
              </div>
            )}
            <dl className="space-y-2.5 py-5 text-sm">
              <div className="flex justify-between text-ink-muted">
                <dt>
                  Subtotal · {cart?.item_count ?? 0} {cart?.item_count === 1 ? "portion" : "portions"}
                </dt>
                <dd className="tabular-nums">{formatMinorUnits(cart?.total ?? 0)}</dd>
              </div>
              <div className="flex justify-between text-ink-muted">
                <dt>Delivery</dt>
                <dd>Arranged with your cook</dd>
              </div>
              <div className="flex items-baseline justify-between border-t border-line pt-4">
                <dt className="font-medium text-ink">Total</dt>
                <dd className="font-display text-3xl font-semibold tabular-nums text-ink">
                  {formatMinorUnits(cart?.total ?? 0)}
                </dd>
              </div>
            </dl>
            {closed && (
              <p role="status" className="mb-4 rounded-xl bg-saffron-soft px-3 py-2 text-sm text-saffron">
                {kitchen.data?.availability.status === "paused"
                  ? "The cook has paused new orders for now."
                  : "This kitchen isn't taking orders right now."}{" "}
                Your bag is saved - place the order once it opens.
              </p>
            )}
            {(cart?.unavailable_count ?? 0) > 0 && (
              <p className="mb-4 rounded-xl bg-saffron-soft px-3 py-2 text-sm text-saffron">
                Remove the unavailable {cart?.unavailable_count === 1 ? "dish" : "dishes"} from your bag first.
              </p>
            )}
            <button
              type="button"
              disabled={!canPlace}
              onClick={() => void placeOrder()}
              className={cx(primaryButtonClass, "hidden h-12 w-full text-[15px] lg:flex")}
            >
              {placing ? <Spinner /> : <Lock className="h-4 w-4" />} Place order
            </button>
            {!selected && addresses !== null && (
              <p className="mt-3 text-center text-xs text-ink-soft">Add a delivery address to continue.</p>
            )}
            <p className="mt-4 text-xs leading-relaxed text-ink-soft">
              Your cook confirms the order before they start cooking. You can cancel it until then.
            </p>
          </div>
        </aside>
      </div>

      {/* mobile: sticky action bar */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-xl items-center gap-4">
          <div className="min-w-0">
            <p className="text-xs text-ink-soft">Total</p>
            <p className="font-display text-xl font-semibold tabular-nums text-ink">{formatMinorUnits(cart?.total ?? 0)}</p>
          </div>
          <button
            type="button"
            disabled={!canPlace}
            onClick={() => void placeOrder()}
            className={cx(primaryButtonClass, "h-12 flex-1 text-[15px]")}
          >
            {placing ? <Spinner /> : <Lock className="h-4 w-4" />} Place order
          </button>
        </div>
      </div>
    </Container>
  );
}

function Step({
  number,
  title,
  icon: Icon,
  optional,
  action,
  children,
}: {
  number: number;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  optional?: boolean;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6" aria-labelledby={`step-${number}`}>
      <header className="mb-5 flex items-center justify-between gap-3">
        <h2 id={`step-${number}`} className="flex items-center gap-3 font-display text-xl font-semibold tracking-tight text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink font-sans text-sm text-canvas">
            {number}
          </span>
          {title}
          {optional && <span className="font-sans text-xs font-normal text-ink-soft">Optional</span>}
        </h2>
        {action ?? <Icon className="h-5 w-5 text-ink-soft" aria-hidden="true" />}
      </header>
      {children}
    </section>
  );
}

function AddressOption({
  address,
  checked,
  onSelect,
}: {
  address: Address;
  checked: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onSelect}
      className={cx(
        "relative flex h-full flex-col rounded-2xl border p-4 text-left transition-all",
        checked ? "border-ink bg-canvas ring-1 ring-ink" : "border-line-strong hover:border-ink-soft",
      )}
    >
      <span className="flex items-center gap-2">
        <span className="font-semibold text-ink">{address.label ?? "Address"}</span>
        {address.is_default && <Badge>Default</Badge>}
      </span>
      <span className="mt-2 text-sm leading-relaxed text-ink-muted">
        {address.recipient}
        <br />
        {address.line1}
        {address.line2 && `, ${address.line2}`}
        <br />
        {[address.postal_code, address.city].filter(Boolean).join(" ")}
      </span>
      <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
        <span className="flex items-center gap-1">
          <Phone className="h-3 w-3" /> {address.phone}
        </span>
        {address.zone && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3 w-3" /> {address.zone.name}
          </span>
        )}
      </span>
      <span
        aria-hidden="true"
        className={cx(
          "absolute right-4 top-4 flex h-5 w-5 items-center justify-center rounded-full border",
          checked ? "border-ink bg-ink text-canvas" : "border-line-strong",
        )}
      >
        {checked && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
    </button>
  );
}
