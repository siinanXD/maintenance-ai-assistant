import type { ReactNode } from "react";

/** Colour of the top edge. Only states get colour; counts stay neutral. */
type StatTone = "neutral" | "primary" | "warning" | "danger" | "success";

type Stat = {
  readonly label: string;
  readonly value: ReactNode;
  readonly meta?: string;
  readonly tone?: StatTone;
};

/**
 * Row of key figures above a page's main content.
 */
export function StatStrip({ label, stats }: { readonly label: string; readonly stats: readonly Stat[] }): ReactNode {
  return (
    <section className="stat-strip" aria-label={label}>
      {stats.map((stat) => (
        <article className={`stat-tile is-${stat.tone ?? "neutral"}`} key={stat.label}>
          <span className="stat-tile-label">{stat.label}</span>
          <strong className="stat-tile-value">{stat.value}</strong>
          {stat.meta ? <small className="stat-tile-meta">{stat.meta}</small> : null}
        </article>
      ))}
    </section>
  );
}
