import { redirect } from "next/navigation";

/** Orders moved into the user panel; keep old links (and ?placed=1) working. */
export default async function LegacyOrderPage({ params, searchParams }: PageProps<"/orders/[id]">) {
  const { id } = await params;
  const placed = (await searchParams).placed === "1" ? "?placed=1" : "";
  redirect(`/account/orders/${encodeURIComponent(id)}${placed}`);
}
