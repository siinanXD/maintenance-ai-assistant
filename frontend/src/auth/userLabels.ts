import type { MaintenanceUser } from "./session";

const ROLE_LABELS: Readonly<Record<string, string>> = {
  instandhaltung: "Instandhaltung",
  it: "IT",
  master_admin: "Administration",
  personalabteilung: "Personalabteilung",
  produktion: "Produktion",
  verwaltung: "Verwaltung"
};

/**
 * Return the readable German role label for a user.
 */
export function userRoleLabel(user: MaintenanceUser | null): string {
  const role = typeof user?.role === "string" ? user.role : "";
  return ROLE_LABELS[role] ?? "Angemeldet";
}

/**
 * Return up to two uppercase initials from a display name such as "thomas.hoffmann".
 */
export function userInitials(displayName: string): string {
  const parts = displayName
    .split(/[\s._-]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return (parts[0] ?? "?").slice(0, 2).toUpperCase();
}
