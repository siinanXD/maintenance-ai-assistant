/**
 * Format a numeric value as German Euro currency.
 */
export function formatMoney(value: unknown): string {
  const amount = Number(value || 0);

  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR"
  }).format(Number.isFinite(amount) ? amount : 0);
}
