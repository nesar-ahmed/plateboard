"use client";

import { Suspense } from "react";

import NotificationInbox from "@/components/notification-inbox";

/**
 * /cook/notifications - the kitchen inbox (`audience=cook`): new order
 * requests, customers cancelling before you accepted, customers confirming
 * they have their food, and the verified badge coming or going
 * (components/notification-inbox.tsx). A request's notification is marked
 * read once you answer it.
 */
export default function CookNotificationsPage() {
  return (
    <Suspense fallback={null}>
      <NotificationInbox
        audience="cook"
        lead="New requests, cancellations and pickups for your kitchen - plus news about your verified badge."
        empty="New order requests show up here the moment they arrive, along with cancellations and customers confirming they have their food."
      />
    </Suspense>
  );
}
