import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

/**
 * Render a page into the root element its Jinja template provides.
 * Pages without that element (another route) are left untouched.
 */
export function mountPage(rootId: string, page: ReactNode): void {
  const rootElement = document.getElementById(rootId);
  if (!rootElement) return;
  createRoot(rootElement).render(<StrictMode>{page}</StrictMode>);
}
