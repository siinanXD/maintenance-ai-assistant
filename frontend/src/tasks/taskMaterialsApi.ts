import { apiRequest } from "../api/client";
import { listData, unwrapData } from "../api/payload";

export type InventoryOption = {
  readonly id: number;
  readonly name: string;
  readonly quantity: number;
};

type StockMovement = {
  readonly id: number;
  readonly material_name: string;
  readonly quantity_change: number;
  readonly note: string;
  readonly value: number;
};

export type TaskMaterials = {
  readonly items: readonly StockMovement[];
  readonly total_value: number;
};

/**
 * Load the spare parts booked on a work order.
 */
export async function loadTaskMaterials(taskId: number): Promise<TaskMaterials> {
  return unwrapData<TaskMaterials>(await apiRequest<unknown>(`/api/v1/tasks/${taskId}/materials`));
}

/**
 * Load stock items that can be withdrawn, alphabetically.
 */
export async function loadInventoryOptions(): Promise<InventoryOption[]> {
  const materials = listData<InventoryOption>(await apiRequest<unknown>("/api/v1/inventory?limit=200"));
  return [...materials].sort((first, second) => first.name.localeCompare(second.name, "de-DE"));
}

/**
 * Withdraw parts from stock for a work order.
 */
export async function withdrawTaskMaterial(taskId: number, materialId: number, quantity: number): Promise<StockMovement> {
  return unwrapData<StockMovement>(
    await apiRequest<unknown>(`/api/v1/tasks/${taskId}/materials`, {
      method: "POST",
      body: { material_id: materialId, quantity }
    })
  );
}
