# LangGraph RAG Workflow

## Ziel

Die RAG-Orchestrierung ist als modularer LangGraph-Workflow eingeführt, ohne
bestehende Chat-Endpunkte, UI-Flows oder Berechtigungen zu ändern. Die
bestehende Retrieval-Pipeline bleibt der einzige Ort für SQL-basierte
Rollenprüfung, Sichtbarkeit, Dokumentstatus, Quality Gates und Hybrid Ranking.

## Workflow

```text
Question
-> Intent Classification
-> Structured Data Retrieval
-> Vector Retrieval
-> Context Assembly
-> Answer Generation
-> Validation
-> Trace Logging
```

Die Knoten liegen in `app/services/langgraph_rag_workflow.py`:

- `question_node`: validiert und normalisiert die Frage.
- `intent_classification_node`: nutzt die bestehende Query-Klassifikation.
- `structured_data_retrieval_node`: ruft die konsolidierte Retrieval-Pipeline auf.
- `vector_retrieval_node`: protokolliert Knowledge-/Vector-Diagnostik aus dem Retrieval-Ergebnis.
- `context_assembly_node`: baut das bestehende `rag`-Diagnosepayload.
- `answer_generation_node`: erzeugt die Antwort. Der Chat-Handler übergibt einen
  `answer_generator`, der Evidence-Gate, Provider-Fallback und Diagnostik
  kapselt; ohne Generator wird der aktive Provider direkt aufgerufen.
- `validation_node`: wendet Confidence- und Safety-Prüfungen an.
- `trace_logging_node`: ergänzt prompt-sichere Workflow-Diagnostik.

Der Chat-Endpunkt `POST /api/v1/ai/chat` führt die komplette Sequenz aus.
`rag.langgraph.completed_nodes` in der Antwort zeigt, welche Knoten gelaufen
sind.

## Evidence-Gate

Ohne sichtbare Quelle wird der Provider nicht aufgerufen, solange
`AI_GENERATE_WITHOUT_EVIDENCE=false` ist (Default). Die Antwort ist dann eine
lokale, geerdete No-Answer mit `diagnostics.generation_skipped = "no_evidence"`.
Provider-Fehlkonfigurationen wie `api_key_missing` bleiben in `diagnostics.status`
sichtbar.

## Kompatibilität

`app/services/rag_service.py` bleibt die stabile öffentliche Fassade:

- `build_rag_context(...)`
- `answer_with_rag(...)`

Die konkrete Node-Sequenz liegt in `LANGGRAPH_RAG_PIPELINE_STEPS` innerhalb von
`app/services/langgraph_rag_workflow.py`. Die Fassade exportiert nur noch die
produktiven Aufruffunktionen, damit kein zweiter Pipeline-Vertrag entsteht.

Bestehende Aufrufer müssen nicht umgestellt werden. Wenn `langgraph` verfügbar
ist, wird der Graph kompiliert und ausgeführt. Wenn `langgraph` noch fehlt oder
die Graph-Kompilierung fehlschlägt, läuft derselbe Node-Code deterministisch in
Reihenfolge als Fallback.

## Berechtigungen und Retrieval

Die Orchestrierung dupliziert keine Retrieval-Implementierung. Sie ruft weiter
`retrieve_context(...)` auf. Dadurch bleiben erhalten:

- Rollenfilter
- Sichtbarkeitsprüfungen
- Dokumentstatus-Gates
- Quality Gates
- Hybrid Retrieval und Ranking
- bestehende No-Source-/Fallback-Logik

## Erweiterung

Neue Knoten sollten als kleine Funktionen mit stabilem State-Vertrag ergänzt
werden. Für zukünftige Reindexing-, Governance- oder LangGraph-Erweiterungen
kann die Node-Sequenz erweitert werden, ohne die Chat-Route oder die
Retrieval-Services zu verändern.
