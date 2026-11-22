"use client";

import { Suspense } from "react";

import NotificationInbox from "@/components/notification-inbox";

/**
 * /admin/notifications - the admin inbox (`audience=admin`): new cook
 * applications to review and kitchens cancelling orders they had accepted.
 * Every admin reads (and dismisses) their own copy; a decided application's
 * notice is marked read for all of them (components/notification-inbox.tsx).
 */
export default function AdminNotificationsPage() {
  return (
    <Suspense fallback={null}>
      <NotificationInbox
        audience="admin"
        lead="What needs an admin: cook applications to review and kitchens cancelling orders they had accepted."
        empty="New cook applications and late cancellations by kitchens show up here."
      />
    </Suspense>
  );
}
