import { type ReactNode } from "react";
import { type AdminAiRagBoardProps, objectPayload, ragText } from "../adminAiRagBoardModel";
import { filterChange, isPayload, QUALITY_OPTIONS, SelectFilter, SOURCE_OPTIONS } from "./AdminAiRagBoardShared";
import { numberText } from "../adminAiFormat";
import { StatRow } from "./AdminAiShared";
import { networkTypeLabel, sourceTypeLabel, truncateLabel } from "../adminAiRagLabels";

/**
 * Render the knowledge network inspector.
 */
export function KnowledgeNetworkPanel({ onNetworkFilterChange, ragBoardState }: AdminAiRagBoardProps): ReactNode {
  const network = ragBoardState.network || {};
  const stats = objectPayload(network.stats);
  const groups = Array.isArray(network.groups) ? network.groups.filter(isPayload) : [];
  const nodes = Array.isArray(network.nodes) ? network.nodes.filter(isPayload) : [];
  const edges = Array.isArray(network.edges) ? network.edges.filter(isPayload) : [];
  const filters = ragBoardState.filters;

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h3>Wissensnetz</h3>
          <p className="panel-meta">Nur-Lese Sicht auf Maschinen, Fehler, Dokumente, Inventar, Trends und Wissenslücken.</p>
        </div>
        <div className="toolbar admin-ai-toolbar">
          <input className="input input-bordered" placeholder="Netzwerk durchsuchen" value={filters.networkQuery} onChange={filterChange(onNetworkFilterChange, "networkQuery")} />
          <SelectFilter ariaLabel="Netzwerk nach Quelle filtern" value={filters.networkSource} onChange={filterChange(onNetworkFilterChange, "networkSource")} options={SOURCE_OPTIONS} />
          <SelectFilter ariaLabel="Netzwerk nach Qualität filtern" value={filters.networkQuality} onChange={filterChange(onNetworkFilterChange, "networkQuality")} options={QUALITY_OPTIONS} />
          <select className="input input-bordered" aria-label="Wissensnetz Ansicht" value={filters.networkFocusType} onChange={filterChange(onNetworkFilterChange, "networkFocusType")}>
            <option value="">Gesamtnetz</option>
            <option value="machine">Maschinenzentriert</option>
            <option value="error">Fehlerzentriert</option>
            <option value="task">Aufgabezentriert</option>
            <option value="knowledge_gap">Gapzentriert</option>
          </select>
          <input className="input input-bordered" placeholder="Fokus optional" value={filters.networkFocus} onChange={filterChange(onNetworkFilterChange, "networkFocus")} />
          <button className="btn btn-secondary" type="button" onClick={() => onNetworkFilterChange("networkQuery", filters.networkQuery)}>
            Aktualisieren
          </button>
        </div>
      </div>
      <div className="dashboard-grid dashboard-grid-4">
        {([
          ["Nodes", stats.node_count || 0],
          ["Edges", stats.edge_count || 0],
          ["Roh-Nodes", stats.raw_node_count || 0],
          ["Zeitraum", `${ragText(stats.window_days, "30")} Tage`]
        ] as const).map(([label, value]) => (
          <article className="metric-card" key={label}><span>{label}</span><strong>{ragText(value)}</strong></article>
        ))}
      </div>
      <div className="knowledge-network-groups mt-4" aria-label="Gruppierte Wissensknoten">
        {groups.length ? groups.map((group) => (
          <article className="knowledge-network-group-card" key={ragText(group.type)}>
            <div className="knowledge-network-group-header">
              <strong>{ragText(group.label) || networkTypeLabel(group.type)}</strong>
              <span>{numberText(group.count || 0)} Nodes / {numberText(group.edge_count || 0)} Links</span>
            </div>
            <div className="knowledge-network-group-nodes">
              {(Array.isArray(group.top_nodes) ? group.top_nodes.filter(isPayload) : []).map((node) => (
                <button className="knowledge-network-node-chip" type="button" key={ragText(node.id)}>
                  {truncateLabel(node.label, 34)}
                </button>
              ))}
            </div>
          </article>
        )) : <StatRow label="Gruppen" value="Keine gruppierten Nodes vorhanden" />}
      </div>
      <div className="knowledge-network-layout mt-4">
        <div className="stats-list" aria-label="Wissensnetz Visualisierung">
          {nodes.slice(0, 20).map((node) => (
            <StatRow key={ragText(node.id)} label={networkTypeLabel(node.type)} value={truncateLabel(node.label || node.title, 80)} />
          ))}
          {!nodes.length ? <StatRow label="Wissensnetz" value="Keine Daten für diesen Filter." /> : null}
        </div>
        <aside className="stats-list" aria-label="Wissensnetz Details">
          {nodes[0] ? (
            <>
              <StatRow label="Titel" value={ragText(nodes[0].title || nodes[0].label)} />
              <StatRow label="Typ" value={networkTypeLabel(nodes[0].type)} />
              <StatRow label="Gewicht" value={Number(nodes[0].weight || 0).toFixed(1)} />
              <StatRow label="Quelle" value={sourceTypeLabel(nodes[0].source_type)} />
            </>
          ) : <StatRow label="Auswahl" value="Node anklicken" />}
        </aside>
      </div>
      <div className="knowledge-network-relations mt-4" aria-label="Klickbare Wissensverbindungen">
        <div className="knowledge-network-relations-header">
          <strong>Klickbare Verbindungen</strong>
          <span>{edges.length ? `${Math.min(edges.length, 16)} wichtigste Beziehungen` : "Keine sichtbaren Beziehungen"}</span>
        </div>
        {edges.slice(0, 16).map((edge) => (
          <button className="knowledge-network-relation-card" type="button" key={ragText(edge.id)}>
            <span>{ragText(edge.label || edge.type)}</span>
            <strong>{truncateLabel(edge.source, 34)} -&gt; {truncateLabel(edge.target, 34)}</strong>
            <small>Gewicht {Number(edge.weight || 0).toFixed(1)} / Evidenz {numberText(edge.evidence_count || 0)}</small>
          </button>
        ))}
      </div>
      <div className="stats-list mt-4" aria-label="Wissensnetz Legende">
        {Object.entries(objectPayload(stats.nodes_by_type)).map(([type, count]) => (
          <StatRow key={type} label={networkTypeLabel(type)} value={`${numberText(count)} Nodes`} />
        ))}
        <StatRow label="Privacy" value={ragText(objectPayload(network.privacy).mode, "metadata_only")} />
      </div>
    </section>
  );
}
