/**
 * Product-level switches that only control whether a visualization is loaded
 * and rendered in the browser.  The backend artifact switch remains
 * independent so a deployment can stop calculation without requiring a
 * frontend rebuild, while a frontend rollout can hide the card without
 * changing persisted analysis artifacts.
 */
function envFlag(value: unknown, fallback = true): boolean {
  if (typeof value !== "string") return fallback;
  return value.trim().toLowerCase() !== "false";
}

export const kitchenArrivalCardEnabled = envFlag(import.meta.env.VITE_KITCHEN_ARRIVAL_CARD_ENABLED);
