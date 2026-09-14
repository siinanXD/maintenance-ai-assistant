import { formatMoney } from "../utils/number";
import { safeErrorMessage } from "../utils/errors";
import type { InventoryMaterial } from "./inventoryTypes";

export type MessageState = {
  readonly text: string;
  readonly error: boolean;
};

/**
 * Return the safest message for a user-facing inventory error.
 */
export function inventoryErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Lagerdaten konnten nicht geladen werden.");
}

/**
 * Return normalized lowercase text for local card search.
 */
export function searchText(value: unknown): string {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

/**
 * Return the badge class for a forecast risk level.
 */
export function forecastRiskBadgeClass(riskLevel: string | undefined): string {
  if (riskLevel === "critical") return "badge badge-error text-white";
  if (riskLevel === "high") return "badge badge-warning text-slate-900";
  return "badge badge-info text-white";
}

/**
 * Return material card search text.
 */
export function materialSearchText(material: InventoryMaterial): string {
  const machineName = material.machine?.name || "Keine Maschine";
  return [material.name, material.manufacturer, machineName, String(material.quantity)]
    .filter(Boolean)
    .join(" ");
}

/**
 * Return the figures for the inventory stat strip.
 */
export function inventoryStats(materials: readonly InventoryMaterial[]) {
  const totalValue = materials.reduce((sum, material) => sum + Number(material.total_value || 0), 0);
  const lowStock = materials.filter((material) => (
    Number(material.min_quantity || 0) > 0 && Number(material.quantity || 0) <= Number(material.min_quantity)
  )).length;

  return { count: materials.length, lowStock, totalValue: formatMoney(totalValue) };
}
