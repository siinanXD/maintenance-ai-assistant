import { useEffect } from "react";

import { markIslandMounted } from "../app/islandMount";
import { subscribeToSessionChange } from "../auth/sessionChange";
import {
  SHIFTPLANS_ISLAND,
  SHIFTPLANS_ROOT_SELECTOR,
  SHIFTPLANS_SHELL_SELECTOR,
} from "./ShiftplansAppModel";

/**
 * Mark the Shiftplans island mounted only after its shell exists.
 */
export function useShiftplansMountMarker(): void {
  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      const rootElement = document.querySelector(SHIFTPLANS_ROOT_SELECTOR);
      if (rootElement?.querySelector(SHIFTPLANS_SHELL_SELECTOR)) {
        markIslandMounted(SHIFTPLANS_ISLAND);
      }
    });
    return () => window.cancelAnimationFrame(frameId);
  }, []);
}

/**
 * Reload shiftplan data after the login session actually changes.
 */
export function useShiftplansAuthReload(onReload: () => void): void {
  useEffect(() => subscribeToSessionChange(onReload), [onReload]);
}
