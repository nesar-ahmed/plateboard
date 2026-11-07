/** The fixed allergen vocabulary - must mirror the backend enum. */

// Keep in sync with Allergen in backend/app/api/dishes/models.py.
export const ALLERGENS = [
  "gluten",
  "crustaceans",
  "eggs",
  "fish",
  "peanuts",
  "milk",
  "nuts",
  "celery",
  "mustard",
  "sesame",
  "soy",
  "lupin",
  "molluscs",
  "sulphites",
] as const;

export type Allergen = (typeof ALLERGENS)[number];
