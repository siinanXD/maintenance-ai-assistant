export type ShellNavigationLink = {
  readonly dashboardKey: string;
  readonly featureKey?: string;
  readonly href: string;
  readonly iconId?: string;
  readonly label: string;
  readonly permissionKey?: string;
  readonly routePrefix?: string;
  readonly variant?: "admin" | "default";
};

export type ShellNavigationSection = {
  readonly defaultOpen?: boolean;
  readonly links: readonly ShellNavigationLink[];
  readonly title: string;
};

export type ShellNavigationProps = {
  readonly collapsed?: boolean;
  readonly currentPath: string;
  readonly onToggleCollapsed?: () => void;
};

export type ShellNavigationCounts = {
  readonly errors: number;
  readonly tasks: number;
};
