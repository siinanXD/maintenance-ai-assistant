import { type ReactNode } from "react";

import { type AdminAiRagBoardProps, EMPTY_TRAINING_FORM, ragText } from "../adminAiRagBoardModel";
import { filterChange, formChange, submitTraining } from "./AdminAiRagBoardShared";

/**
 * Render manual training list and editor.
 */
export function TrainingEntriesPanel(props: AdminAiRagBoardProps): ReactNode {
  const { onDeleteTraining, onSaveTraining, onSelectTraining, onTrainingFilterChange, onTrainingFormChange, ragBoardState } = props;
  const form = ragBoardState.trainingForm;

  return (
    <section className="panel admin-training-panel" id="ai-training-data">
      <div className="panel-header">
        <div>
          <span className="section-kicker">4. Trainingsdaten</span>
          <h3>Manuelles Wissen gezielt pflegen</h3>
          <p className="panel-meta">Freigegebene Trainingseinträge ergänzen die strukturierten Quellen.</p>
        </div>
        <div className="admin-filterbar">
          <input className="input input-bordered" placeholder="Training durchsuchen" value={ragBoardState.filters.trainingQuery} onChange={filterChange(onTrainingFilterChange, "trainingQuery")} />
          <select className="input input-bordered" aria-label="Training nach Status filtern" value={ragBoardState.filters.trainingActive} onChange={filterChange(onTrainingFilterChange, "trainingActive")}>
            <option value="">Alle Trainings</option>
            <option value="true">Nur aktiv</option>
            <option value="false">Nur inaktiv</option>
          </select>
        </div>
      </div>
      <div className="admin-training-workflow">
        <aside className="admin-training-list" aria-label="Trainingseinträge">
          {ragBoardState.training.length ? ragBoardState.training.map((entry) => (
            <article className={`training-card ${form.id === String(entry.id) ? "is-selected" : ""}`} key={ragText(entry.id)}>
              <strong>{ragText(entry.title)}</strong>
              <p>{ragText(entry.question)}</p>
              <div className="training-card-meta">
                <span className={`status-pill ${entry.is_active ? "is-active" : "is-muted"}`}>{entry.is_active ? "aktiv" : "inaktiv"}</span>
                <span className="status-pill">Priorität {ragText(entry.priority)}</span>
                <span className="status-pill">{ragText(entry.category)}</span>
                <span className="status-pill">{ragText(entry.department, "alle Abteilungen")}</span>
              </div>
              <div className="training-card-actions">
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => onSelectTraining(entry)}>Bearbeiten</button>
                <button className="btn btn-ghost btn-sm" type="button" onClick={() => onDeleteTraining(Number(entry.id))}>Löschen</button>
              </div>
            </article>
          )) : <div className="guided-empty-state"><strong>Keine passenden Trainingseinträge gefunden.</strong><p>Passe Suche oder Statusfilter an.</p></div>}
        </aside>
        <form className="admin-training-editor" onSubmit={(event) => submitTraining(event, onSaveTraining, form)}>
          <input type="hidden" name="id" value={form.id} />
          <div className="training-editor-header">
            <div><span className="section-kicker">Editor</span><h4>{form.id ? "Training bearbeiten" : "Neuer Trainingseintrag"}</h4></div>
            <span className={`status-pill ${form.isActive ? "is-active" : "is-stale"}`}>
              {form.isActive ? "Aktiv im RAG-Index" : "Nach dem Speichern neu indexieren"}
            </span>
          </div>
          <div className="training-status-strip">
            <label className="inline-form training-active-toggle"><span>Aktiv</span><input name="is_active" type="checkbox" checked={form.isActive} onChange={(event) => onTrainingFormChange({ ...form, isActive: event.target.checked })} /></label>
            <label className="inline-form training-priority-field"><span>Priorität</span><input className="input input-bordered" name="priority" type="number" min="0" max="100" value={form.priority} onChange={formChange(form, onTrainingFormChange, "priority")} /></label>
          </div>
          <div className="content-grid two-columns">
            <input className="input input-bordered" name="title" maxLength={220} placeholder="Titel" value={form.title} onChange={formChange(form, onTrainingFormChange, "title")} />
            <input className="input input-bordered" name="category" maxLength={80} placeholder="Kategorie, z. B. Wartung" value={form.category} onChange={formChange(form, onTrainingFormChange, "category")} />
            <input className="input input-bordered" name="department" maxLength={120} placeholder="Abteilung optional" value={form.department} onChange={formChange(form, onTrainingFormChange, "department")} />
            <input className="input input-bordered" name="keywords" maxLength={1000} placeholder="Keywords, Synonyme, Fehlercodes" value={form.keywords} onChange={formChange(form, onTrainingFormChange, "keywords")} />
          </div>
          <textarea className="input input-bordered" name="question" maxLength={1000} rows={3} placeholder="Typische Frage oder Situation" value={form.question} onChange={formChange(form, onTrainingFormChange, "question")} />
          <textarea className="input input-bordered" name="answer" maxLength={6000} rows={6} placeholder="Freigegebene Antwort, Regel oder Wartungshinweis" value={form.answer} onChange={formChange(form, onTrainingFormChange, "answer")} />
          <p className="panel-meta">Aktuelle strukturierte Daten bleiben führend; Training ergänzt nur freigegebenes Erfahrungswissen.</p>
          <div className="toolbar training-editor-actions">
            <button className="btn btn-primary" disabled={ragBoardState.isSaving} type="submit">Training speichern</button>
            <button className="btn btn-ghost" type="button" onClick={() => onTrainingFormChange(EMPTY_TRAINING_FORM)}>Neu</button>
          </div>
        </form>
      </div>
    </section>
  );
}
