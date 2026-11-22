import { redirect } from "next/navigation";

/** The cook tools moved into the cook panel; keep old links and bookmarks working. */
export default function LegacyDashboardPage() {
  redirect("/cook");
}
