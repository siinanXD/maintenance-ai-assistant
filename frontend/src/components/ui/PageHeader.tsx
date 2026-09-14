import type { ReactNode } from "react";

import { PageActionBar, type PageAction } from "./PageActionBar";

type PageHeaderProps = {
  readonly title: string;
  readonly description?: string;
  readonly actions?: readonly PageAction[];
};

/**
 * Title, one-line description and the page commands, identical on every page.
 */
export function PageHeader({ actions = [], description, title }: PageHeaderProps): ReactNode {
  return (
    <header className="page-header">
      <div className="page-header-text">
        <h1 className="page-header-title">{title}</h1>
        {description ? <p className="page-header-description">{description}</p> : null}
      </div>
      <PageActionBar actions={actions} label={`${title}: Aktionen`} />
    </header>
  );
}
