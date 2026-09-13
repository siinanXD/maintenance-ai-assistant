import { apiRequest } from "../api/client";
import { listData, unwrapData } from "../api/payload";
import type { InventoryForecast, InventoryMaterial, Machine, ReorderSuggestions } from "./inventoryTypes";

export type CreateMaterialPayload = {
  readonly name: string;
  readonly unit_cost: number;
  readonly quantity: number;
  readonly manufacturer: string;
  readonly machine_id?: number | null;
};

type ForecastPayload = {
  readonly low_stock_threshold: number;
  readonly status: "open";
  readonly limit: number;
};

/**
 * Load inventory materials from the existing API.
 */
export async function loadInventoryMaterials(): Promise<InventoryMaterial[]> {
  const response = await apiRequest<unknown>("/api/v1/inventory?limit=200");
  return listData<InventoryMaterial>(response);
}

/**
 * Load machines for the optional inventory machine relation.
 */
export async function loadMachines(): Promise<Machine[]> {
  const response = await apiRequest<unknown>("/api/v1/machines?limit=200");
  return listData<Machine>(response);
}

/**
 * Create one inventory material through the existing API.
 */
export async function createInventoryMaterial(payload: CreateMaterialPayload): Promise<InventoryMaterial> {
  return apiRequest<InventoryMaterial>("/api/v1/inventory", {
    method: "POST",
    body: payload
  });
}

/**
 * Delete one inventory material through the existing API.
 */
export async function deleteInventoryMaterial(materialId: number): Promise<void> {
  await apiRequest<null>(`/api/v1/inventory/${materialId}`, {
    method: "DELETE"
  });
}

/**
 * Calculate the inventory forecast through the existing API.
 */
export async function calculateInventoryForecast(payload: ForecastPayload): Promise<InventoryForecast> {
  const response = await apiRequest<unknown>("/api/v1/inventory/forecast", {
    method: "POST",
    body: payload
  });

  return unwrapData<InventoryForecast>(response);
}

/**
 * Load materials at or below minimum stock with order proposals.
 */
export async function loadReorderSuggestions(): Promise<ReorderSuggestions> {
  return unwrapData<ReorderSuggestions>(await apiRequest<unknown>("/api/v1/inventory/reorder"));
}

/**
 * Book delivered parts into stock.
 */
export async function bookGoodsReceipt(materialId: number, quantity: number, note: string): Promise<void> {
  await apiRequest<unknown>(`/api/v1/inventory/${materialId}/receipts`, {
    method: "POST",
    body: { quantity, note }
  });
}
