export const FIELD_LABEL: Record<string, string> = {
  dish: "dish",
  cuisine: "cuisine",
  ingredients: "ingredients",
  diet: "diet",
  budget: "budget",
  delivery_time: "delivery time",
  min_rating: "rating",
  rating_preference: "rating preference",
  price_preference: "price preference",
  speed_preference: "speed preference",
  location: "location",
  other_preferences: "other preferences",
};

export function fieldLabel(field: string): string {
  return FIELD_LABEL[field] ?? field;
}
