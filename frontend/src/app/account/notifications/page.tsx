"use client";

import { Bell, Mail, MessageSquare } from "lucide-react";
import { Suspense } from "react";

import NotificationInbox from "@/components/notification-inbox";
import { Badge, cx } from "@/components/ui";

/**
 * /account/notifications - the user panel's inbox (`audience=account`):
 * order updates, cook-application answers, account and security notices
 * (components/notification-inbox.tsx), plus the delivery-channel settings.
 */
export default function NotificationsPage() {
  return (
    <div className="space-y-6">
      <Suspense fallback={null}>
        <NotificationInbox
          audience="account"
          lead="Order updates, answers about your kitchen and account news - in one place, on every device."
          empty="When you order, every step - accepted, ready for pickup, cancelled - shows up here, along with news about your account."
        />
      </Suspense>
      <ChannelSettings />
    </div>
  );
}

/** Delivery channels. In-app is live; email and SMS are honest "coming soon"s. */
function ChannelSettings() {
  return (
    <section aria-label="Notification settings" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <h2 className="font-display text-xl font-semibold text-ink">How we reach you</h2>
      <p className="mt-1 text-sm text-ink-muted">In-app notifications are on. Email and SMS are coming soon.</p>
      <ul className="mt-5 divide-y divide-line">
        {[
          { icon: Bell, name: "In-app", detail: "Here and on the bell at the top of every page", on: true, live: true },
          { icon: Mail, name: "Email", detail: "Order confirmations and status changes", on: false, live: false },
          { icon: MessageSquare, name: "SMS", detail: "A text when your order is ready for pickup", on: false, live: false },
        ].map((channel) => (
          <li key={channel.name} className="flex items-center gap-4 py-3.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-ink-muted">
              <channel.icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="flex-1">
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                {channel.name} {!channel.live && <Badge>Coming soon</Badge>}
              </p>
              <p className="text-xs text-ink-soft">{channel.detail}</p>
            </div>
            <span
              role="switch"
              aria-checked={channel.on}
              aria-disabled="true"
              aria-label={`${channel.name} notifications`}
              className={cx(
                "relative h-6 w-11 shrink-0 rounded-full transition-colors",
                channel.on ? "bg-herb" : "bg-line-strong",
                !channel.live && "opacity-50",
              )}
            >
              <span
                className={cx(
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
                  channel.on ? "left-[22px]" : "left-0.5",
                )}
              />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
