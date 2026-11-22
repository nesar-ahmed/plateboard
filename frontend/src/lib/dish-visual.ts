/**
 * Deterministic visuals for dishes - the data has no photos yet.
 *
 * Every dish gets the same "plate art" everywhere (card, detail page, cart
 * line, order): a food-inspired gradient chosen from keywords in its name
 * (chilli -> chili, desserts -> plum, seafood -> ocean, greens -> basil,
 * otherwise a stable hash of the name) and an icon matched from the name.
 * Pure functions, no React, so server and client render identical markup.
 */

import type { LucideIcon } from "lucide-react";
import {
  Beef,
  CakeSlice,
  ChefHat,
  CookingPot,
  Drumstick,
  EggFried,
  Fish,
  Leaf,
  Pizza,
  Salad,
  Sandwich,
  Shrimp,
  Soup,
  Wheat,
} from "lucide-react";

export type Palette = {
  name: string;
  /** Gradient stops (light -> deep). */
  from: string;
  to: string;
  /** Ink for the icon on the plate. */
  ink: string;
};

const PALETTES: Record<string, Palette> = {
  saffron: { name: "saffron", from: "#f7cf7e", to: "#dc8a2c", ink: "#8a4a08" },
  paprika: { name: "paprika", from: "#f0a07e", to: "#b9482a", ink: "#8e2e14" },
  chili: { name: "chili", from: "#f59a7e", to: "#c2352a", ink: "#8c1e16" },
  basil: { name: "basil", from: "#bfd9a1", to: "#5f8f4d", ink: "#2f5a26" },
  matcha: { name: "matcha", from: "#d7e6b0", to: "#86a85e", ink: "#44632a" },
  plum: { name: "plum", from: "#e6c3d6", to: "#9a5c85", ink: "#5e2c50" },
  ocean: { name: "ocean", from: "#bcd9e4", to: "#4e8aa1", ink: "#1f5366" },
  sesame: { name: "sesame", from: "#efe1c8", to: "#b99a6d", ink: "#6b4f24" },
  turmeric: { name: "turmeric", from: "#f6de8a", to: "#d1a12a", ink: "#7a5a05" },
  cocoa: { name: "cocoa", from: "#e2c6ad", to: "#8f5f3f", ink: "#4f2f19" },
};

/** Warm/green palettes only: ocean means seafood and plum means sweet, never chance. */
const HASHED = ["saffron", "paprika", "sesame", "turmeric", "cocoa", "matcha"];

/** First match wins: the kind of dish (soup, curry, dumplings...) before its
 * protein, so "Chicken Biryani" is a pot, not a drumstick. */
const ICON_RULES: [RegExp, LucideIcon][] = [
  [/\b(soup|ramen|pho|borscht|broth|sopa|bisque|chowder)\b/, Soup],
  [/\b(salad|slaw|tabbouleh)\b/, Salad],
  [/\b(pizza|flatbread)\b/, Pizza],
  [/\b(cake|tart|pie|pudding|brownie|cookie|dessert|baklava|knedl|custard|flan|churro)/, CakeSlice],
  [/\b(sandwich|burger|bao|bun|wrap|taco|burrito|shawarma)\b/, Sandwich],
  [/\b(curry|korma|masala|biryani|polao|pilaf|tehari|stew|mole|dal|dhal|arroz|tikka|gobi)\b/, CookingPot],
  [/\b(pasta|tagliatelle|noodle|spaghetti|dumpling|pierogi|gow|gyoza|momo|golubtsi|bread)\b/, Wheat],
  [/\b(prawn|shrimp|crab|lobster|crustacean)/, Shrimp],
  [/\b(fish|salmon|tuna|cod|mackerel|seafood)\b/, Fish],
  [/\b(egg|omelette|shakshuka|frittata)\b/, EggFried],
  [/\b(chicken|wings|drumstick|poultry|duck)\b/, Drumstick],
  [/\b(beef|lamb|mutton|pork|ragu|ragù|goulash|meatball)/, Beef],
  [/\b(tofu|vegan|lentil|bean|chickpea|greens|veg|rice)\b/, Leaf],
];

function hash(text: string): number {
  let value = 2166136261;
  for (const ch of text) {
    value ^= ch.charCodeAt(0);
    value = Math.imul(value, 16777619) >>> 0;
  }
  return value;
}

/** Only the name is used: cart lines and order lines carry nothing else, and a
 * dish must look the same on its card, in the bag and on the order. */
export type DishLike = { name: string };

const PALETTE_RULES: [RegExp, string][] = [
  [/\b(chil+i|spicy|sichuan|szechuan|mapo|vindaloo|diavola|harissa|jalape)/, "chili"],
  [/\b(cake|tart|pie|pudding|brownie|cookie|dessert|baklava|knedl|custard|flan|churro|sweet)/, "plum"],
  [/\b(fish|salmon|tuna|cod|prawn|shrimp|crab|seafood|gow|sushi)/, "ocean"],
  [/\b(salad|green|herb|pesto|spinach|palak|falafel|veg|aloo|gobi|tabbouleh)/, "basil"],
];

export function dishPalette(dish: DishLike): Palette {
  const text = dish.name.toLowerCase();
  for (const [pattern, name] of PALETTE_RULES) {
    if (pattern.test(text)) return PALETTES[name];
  }
  return PALETTES[HASHED[hash(text) % HASHED.length]];
}

export function dishIcon(dish: DishLike): LucideIcon {
  const text = dish.name.toLowerCase();
  for (const [pattern, icon] of ICON_RULES) {
    if (pattern.test(text)) return icon;
  }
  return ChefHat;
}
