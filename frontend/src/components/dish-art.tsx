import { createElement } from "react";

import { cx } from "@/components/ui";
import { dishIcon, dishPalette, type DishLike } from "@/lib/dish-visual";

/**
 * "Plate art" for a dish: warm gradient, soft light, a plate with the dish's
 * icon. Server-safe and deterministic (see lib/dish-visual.ts), so a dish
 * looks the same on its card, its page and in the cart.
 */
export default function DishArt({
  dish,
  className,
  size = "md",
  rounded = "rounded-2xl",
}: {
  dish: DishLike;
  className?: string;
  size?: "xs" | "sm" | "md" | "lg";
  rounded?: string;
}) {
  const palette = dishPalette(dish);
  // dishIcon() returns one of a fixed set of module-level Lucide icons;
  // createElement states that plainly (no component is created per render).
  const icon = dishIcon(dish);
  const plate = { xs: "w-[62%]", sm: "w-[58%]", md: "w-[46%]", lg: "w-[44%]" }[size];
  const iconSize = { xs: "h-4 w-4", sm: "h-6 w-6", md: "h-10 w-10", lg: "h-16 w-16" }[size];
  return (
    <div
      aria-hidden="true"
      className={cx("relative isolate overflow-hidden", rounded, className)}
      style={{ background: `linear-gradient(135deg, ${palette.from} 0%, ${palette.to} 100%)` }}
    >
      {/* soft top-left light + bottom vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_15%_10%,rgb(255_255_255/0.45),transparent_55%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(90%_70%_at_85%_110%,rgb(0_0_0/0.18),transparent_60%)]" />
      {/* subtle linen texture */}
      <div className="absolute inset-0 opacity-[0.18] [background-image:repeating-linear-gradient(45deg,rgb(255_255_255/0.35)_0_1px,transparent_1px_7px)]" />
      {/* the plate */}
      <div
        className={cx(
          "absolute left-1/2 top-1/2 aspect-square -translate-x-1/2 -translate-y-1/2 rounded-full",
          "bg-[radial-gradient(circle_at_50%_45%,#fffdf9_0%,#fbf5ec_58%,#efe4d4_60%,#fffaf3_66%,#f1e6d6_100%)]",
          "shadow-[0_18px_30px_-12px_rgb(0_0_0/0.35),inset_0_-6px_12px_rgb(0_0_0/0.06)]",
          plate,
        )}
      >
        {createElement(icon, {
          className: cx("absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2", iconSize),
          style: { color: palette.ink },
          strokeWidth: 1.5,
        })}
      </div>
    </div>
  );
}
