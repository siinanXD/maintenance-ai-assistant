import { useEffect, useState } from "react";

import { apiRequest } from "../api/client";
import {
  applyHighContrastPreference,
  readHighContrastPreference,
  writeHighContrastPreference
} from "./shellPreferences";

type ShellShiftState = {
  readonly dateTitle: string;
  readonly dateValue: string;
  readonly key: "early" | "late" | "night";
  readonly label: string;
  readonly time: string;
};

type NotificationListResponse = {
  readonly data?: {
    readonly unread_count?: unknown;
  };
  readonly unread_count?: unknown;
};

type NotificationReadResponse = {
  readonly data?: {
    readonly updated?: unknown;
  };
  readonly updated?: unknown;
};

/**
 * Return the active shift for a date.
 */
function currentShiftFor(date: Date): Pick<ShellShiftState, "key" | "label" | "time"> {
  const minutes = date.getHours() * 60 + date.getMinutes();
  if (minutes >= 6 * 60 && minutes < 14 * 60) {
    return { key: "early", label: "Frühschicht", time: "06:00 - 14:00" };
  }
  if (minutes >= 14 * 60 && minutes < 22 * 60) {
    return { key: "late", label: "Spätschicht", time: "14:00 - 22:00" };
  }
  return { key: "night", label: "Nachtschicht", time: "22:00 - 06:00" };
}

/**
 * Build the visible topbar clock state.
 */
function shellShiftState(date: Date): ShellShiftState {
  const shift = currentShiftFor(date);
  return {
    ...shift,
    dateTitle: date.toLocaleDateString("de-DE", { weekday: "long" }),
    dateValue: new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric"
    }).format(date)
  };
}

/**
 * Keep the React shell topbar date and shift state fresh.
 */
export function useShellShiftState(): ShellShiftState {
  const [shiftState, setShiftState] = useState<ShellShiftState>(() => shellShiftState(new Date()));

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setShiftState(shellShiftState(new Date()));
    }, 60 * 1000);

    return () => window.clearInterval(intervalId);
  }, []);

  return shiftState;
}

/**
 * Keep the React topbar in sync with the high contrast preference shared with auth.js.
 */
export function useHighContrastPreference(): readonly [boolean, () => void] {
  const [isEnabled, setIsEnabled] = useState<boolean>(() => readHighContrastPreference());

  useEffect(() => {
    applyHighContrastPreference(isEnabled);
  }, [isEnabled]);

  useEffect(() => {
    /**
     * Refresh the contrast state after a login change or a change in another tab.
     */
    function refreshContrastPreference(): void {
      setIsEnabled(readHighContrastPreference());
    }

    window.addEventListener("maintenance-auth-ready", refreshContrastPreference);
    window.addEventListener("maintenance-auth-changed", refreshContrastPreference);
    window.addEventListener("storage", refreshContrastPreference);

    return () => {
      window.removeEventListener("maintenance-auth-ready", refreshContrastPreference);
      window.removeEventListener("maintenance-auth-changed", refreshContrastPreference);
      window.removeEventListener("storage", refreshContrastPreference);
    };
  }, []);

  /**
   * Toggle and persist high contrast for React-owned shell controls.
   */
  function toggleHighContrast(): void {
    setIsEnabled((currentValue) => {
      const nextValue = !currentValue;
      writeHighContrastPreference(nextValue);
      return nextValue;
    });
  }

  return [isEnabled, toggleHighContrast] as const;
}

/**
 * Return a finite non-negative notification count from an API response.
 */
function notificationCount(value: unknown): number {
  const count = typeof value === "number" ? value : Number(value);
  return Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
}

/**
 * Read the unread count from a notification list payload.
 */
function unreadCountFromResponse(response: NotificationListResponse): number {
  return notificationCount(response.data?.unread_count ?? response.unread_count);
}

/**
 * Keep the React topbar notification badge synced with the current session.
 */
export function useNotificationBadge(isLoggedIn: boolean): readonly [number, () => Promise<void>] {
  const [unreadCount, setUnreadCount] = useState<number>(0);

  useEffect(() => {
    const controller = new AbortController();

    /**
     * Load the current unread count from the existing notification API.
     */
    async function loadUnreadCount(): Promise<void> {
      if (!isLoggedIn) {
        setUnreadCount(0);
        return;
      }

      try {
        const response = await apiRequest<NotificationListResponse>("/api/v1/notifications?limit=5", {
          signal: controller.signal
        });
        setUnreadCount(unreadCountFromResponse(response));
      } catch (error) {
        if (!controller.signal.aborted) {
          console.warn("Benachrichtigungen konnten nicht geladen werden.", error);
          setUnreadCount(0);
        }
      }
    }

    void loadUnreadCount();

    return () => controller.abort();
  }, [isLoggedIn]);

  /**
   * Mark all notifications read and update the React badge state.
   */
  async function markAllRead(): Promise<void> {
    if (!isLoggedIn || unreadCount <= 0) return;

    try {
      const response = await apiRequest<NotificationReadResponse>("/api/v1/notifications/read-all", {
        method: "PATCH"
      });
      const updatedCount = notificationCount(response.data?.updated ?? response.updated);
      setUnreadCount((currentCount) => Math.max(0, currentCount - updatedCount));
    } catch (error) {
      console.warn("Benachrichtigungen konnten nicht als gelesen markiert werden.", error);
      setUnreadCount(unreadCount);
    }
  }

  return [unreadCount, markAllRead] as const;
}
