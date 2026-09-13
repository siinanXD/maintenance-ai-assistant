import type { ReactNode } from "react";

const SHELL_ICON_PATHS = {
  "icon-admin": "M12 2 4 5.5v6.2c0 4.9 3.3 8.7 8 10.3 4.7-1.6 8-5.4 8-10.3V5.5L12 2Zm0 2.2 6 2.6v4.9c0 3.8-2.3 6.7-6 8.1-3.7-1.4-6-4.3-6-8.1V6.8l6-2.6Zm-1 4.3h2v4h-2v-4Zm0 6h2v2h-2v-2Z",
  "icon-ai": "M11 2h2v3h3a3 3 0 0 1 3 3v3h3v2h-3v3a3 3 0 0 1-3 3h-3v3h-2v-3H8a3 3 0 0 1-3-3v-3H2v-2h3V8a3 3 0 0 1 3-3h3V2Zm-3 5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1H8Zm1.2 7 2-5h1.6l2 5h-1.5l-.35-.95h-1.9L10.7 14H9.2Zm2.25-2.1h1.1L12 10.35l-.55 1.55Z",
  "icon-alert": "M12 3 2 20h20L12 3Zm1 14h-2v-2h2v2Zm0-4h-2V8h2v5Z",
  "icon-calendar": "M7 2h2v2h6V2h2v2h3v18H4V4h3V2Zm11 8H6v10h12V10ZM6 8h12V6H6v2Z",
  "icon-dashboard": "M4 13h7V4H4v9Zm9 7h7V4h-7v16ZM4 20h7v-5H4v5Z",
  "icon-document": "M6 2h8l5 5v15H6V2Zm7 1.8V8h4.2L13 3.8ZM8 12h8v2H8v-2Zm0 4h8v2H8v-2Z",
  "icon-inspection": "M9 2h6v2h4v18H5V4h4V2Zm2 2v2h2V4h-2ZM7 6v14h10V6h-2v2H9V6H7Zm8.3 4.3 1.4 1.4-5.2 5.2-3.2-3.2 1.4-1.4 1.8 1.8 3.8-3.8Z",
  "icon-handover": "M7 7h9.2l-2.6-2.6L15 3l5 5-5 5-1.4-1.4L16.2 9H7V7Zm10 10H7.8l2.6 2.6L9 21l-5-5 5-5 1.4 1.4L7.8 15H17v2Z",
  "icon-inventory": "M4 5.5 12 2l8 3.5V18l-8 4-8-4V5.5Zm8 2.2 4.9-2.1L12 3.8 7.1 5.6 12 7.7Zm-6 9.1 5 2.5V9.4l-5-2.2v9.6Zm7 2.5 5-2.5V7.2l-5 2.2v9.9Z",
  "icon-machine": "M4 5h16v8H4V5Zm2 2v4h12V7H6Zm-1 8h14l2 4v1H3v-1l2-4Zm3 .8L7.4 18h9.2l-.6-2.2H8Z",
  "icon-tasks": "M9 3h6l1 2h4v16H4V5h4l1-2Zm1.2 2-.5 1h4.6l-.5-1h-3.6ZM8 11l2.1 2.1L15.6 8 17 9.4l-6.9 6.5L6.6 12.4 8 11Z",
  "icon-users": "M8.5 12a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0 2c3.1 0 5.5 1.6 5.5 3.6V20H3v-2.4C3 15.6 5.4 14 8.5 14Zm7-2.2a3.4 3.4 0 0 1-1.7-.45A5.9 5.9 0 0 0 14.5 8c0-1.15-.33-2.22-.9-3.12A3.5 3.5 0 1 1 15.5 11.8ZM16.5 14c2.5.1 4.5 1.5 4.5 3.2V20h-5v-2.4c0-1.3-.58-2.46-1.55-3.4.6-.14 1.28-.2 2.05-.2Z",
  "icon-vacation": "M7 2h2v2h6V2h2v2h3v18H4V4h3V2Zm11 8H6v10h12V10ZM8 12h3v3H8v-3Zm5 0h3v3h-3v-3Z"
} as const;

/**
 * Render the icon symbol sprite used by the React application shell.
 */
export function ShellIconSprite(): ReactNode {
  return (
    <svg className="icon-sprite" aria-hidden="true" focusable="false">
      {Object.entries(SHELL_ICON_PATHS).map(([iconId, pathDefinition]) => (
        <symbol id={iconId} viewBox="0 0 24 24" key={iconId}>
          <path d={pathDefinition} />
        </symbol>
      ))}
    </svg>
  );
}
