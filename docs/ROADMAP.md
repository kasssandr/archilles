# ARCHILLES — Product Roadmap

> **Your Intelligent Research Archive**
> *Mein Korpus, meine Wahl.*

**Last updated:** February 2026

---

## Vision

ARCHILLES verwandelt persönliche Calibre-Bibliotheken in semantisch durchsuchbare Wissensbasen. Das übergeordnete Ziel: Tausende Titel — mitsamt den Verlagstexten, Kritiken, KI-Analysen (z.B. aus NotebookLM) sowie eigenen Exzerpten und Gedanken — per KI erschließen, durchsuchen und in Beziehung setzen.

Dabei gibt es zwei komplementäre Zugangswege. Der eine führt über Calibres eigene KI-Schnittstellen (seit v8.16: GitHubAI, GoogleAI, OllamaAI, OpenRouter), die ein Gesprächsinterface für einzelne Bücher bieten. Der andere — und das ist ARCHILLES' Domäne — ermöglicht die semantische Suche über die gesamte Bibliothek mit verifizierbaren Quellenangaben, verbunden mit der analytischen Kraft eines Frontier-Modells wie Claude über das Model Context Protocol (MCP).

Die beiden Ansätze sind komplementär, nicht konkurrierend: Calibres AI-Features nutzen externes Wissen, um über einzelne Bücher zu sprechen. ARCHILLES durchsucht die tatsächlichen Inhalte der gesamten Bibliothek und liefert zitierfähige Quellenangaben.

---

## Positionierung: ARCHILLES und Calibre AI

Calibre 8.16 führte im Dezember 2025 eigene AI-Features ein. Systematische Tests zeigten die unterschiedlichen Stärken und Grenzen: Lokale Modelle (z.B. Gemma3 über Ollama) halluzinierten bei unvollständigen Dokumenten, während Cloud-Modelle (z.B. Gemini) sich auf Web-Grounding stützten und bei unveröffentlichten Manuskripten versagten. ARCHILLES löst ein fundamental anderes Problem — nicht einzelne Bücher besprechen, sondern die gesamte Bibliothek semantisch erschließen.

Für Nutzer empfiehlt sich die Kombination: Calibres Ollama-Integration für schnelle Einzelbuch-Gespräche, ARCHILLES über MCP für bibliotheksweite Recherche mit Frontier-Modellen.

---

## Aktueller Stand: v0.9 (Gamma)

**Status:** Kernfunktionalität produktionsreif, MCP-Server operativ.

Die Basis steht. Der Core-Bestand (Leit-Literatur) mit 267 Titeln ist nahezu vollständig indexiert, und das System skaliert über die LanceDB-Architektur auf Millionen von Chunks. Die Zwei-Datenbanken-Architektur trennt sauber zwischen Buchinhalten (`archilles_books`) und Nutzerdaten (`archilles_meta` — Kommentare, Annotationen, NotebookLM-Analysen, eigene Exzerpte).

**Abgeschlossen:**

Volltextindexierung über 30+ Formate via Calibre-Converter. Semantische Suche mit BGE-M3-Embeddings (multilingual, 75+ Sprachen). Keyword-Suche über BM25. Hybride Suche mit Reciprocal Rank Fusion. Calibre-Metadaten-Integration einschließlich Tags, Comments (mit HTML-Cleaning) und automatischer Custom-Field-Erkennung. Annotationsextraktion aus dem Calibre E-book Viewer (Highlights, Notes, Bookmarks). LanceDB als Vektordatenbank mit nativer Hybrid-Search und IVF-PQ-Indexing. Zwei-Datenbanken-Architektur vollständig realisiert: Mit der Migration von ChromaDB zu LanceDB (Februar 2026) nutzen sowohl Buchinhalte als auch Annotationen einheitlich BGE-M3-Embeddings in zwei getrennten LanceDB-Tabellen — eine einzige Vektor-DB-Engine, keine externe Dependency mehr. Service-Layer-Architektur (`ArchillesService`) als zentrale Geschäftslogik-Fassade für MCP-Server, Web UI und CLI. Cross-Encoder Reranking (optional, BAAI/bge-reranker-v2-m3). MCP-Server mit 12 Tools für Claude Desktop und andere MCP-kompatible Clients. Bibliographie-Export in BibTeX, RIS, EndNote, JSON und CSV. Duplikaterkennung nach Titel+Autor, ISBN oder exaktem Titel. Streamlit-basiertes Web UI als Companion-Interface. Batch-Indexierung mit Tag-/Autoren-Filtern, Checkpoint-Resume und Hardware-Profilen.

---

## v1.0 — Stabilisierung und Dokumentation (Ziel: Q1 2026)

**Fokus:** Das Fundament für den Community-Release legen.

Die verbleibende Arbeit für v1.0 betrifft weniger neue Features als Konsolidierung: Die Dokumentation muss vollständig und verständlich sein, der Installationsprozess reibungslos, und die bestehenden Funktionen müssen robust genug für Nutzer sein, die keine Entwickler sind.

Konkret geplant: Inkrementelle Indexierung (nur geänderte Bücher aktualisieren, mit Index-Queue-Management und Hintergrundverarbeitung). Umfassende Dokumentation einschließlich Installationsanleitung, Konfigurationsreferenz und Troubleshooting. Unit-Test-Suite und Performance-Benchmarks. Windows-Installer und macOS-Bundle als mittelfristiges Ziel.

**In Arbeit:** Die Re-Indexierung des Core-Bestands (Leit-Literatur) mit vollständigen Section-Metadaten und Page-Labels steht bei 259 von 267 Titeln kurz vor dem Abschluss. Danach folgt eine umfassende Testrunde — sowohl für die Suchqualität über den erweiterten Index als auch für die MCP-Integration mit Claude Desktop.

---

## v1.1 — Chunking-Intelligenz und Retrieval-Qualität (Q2 2026)

**Fokus:** Die Qualität der Suchergebnisse substantiell verbessern.

Die Chunking-Intelligence-Analyse (durchgeführt über Gemini, Grok und ChatGPT, November 2025) identifizierte hierarchisches Chunking als den größten einzelnen Qualitätshebel. Die aktuelle Konfiguration (RecursiveCharacterTextSplitter mit 1000 Token / 200 Overlap) liefert solide Ergebnisse, verschenkt aber Potenzial bei langen argumentativen Passagen — genau dem Texttyp, der für geisteswissenschaftliche Arbeit zentral ist.

**Small-to-Big Retrieval und Parent-Child-Hierarchien:** Indexiere kleine Chunks (Absatzebene) für hohe Retrieval-Präzision, liefere dem LLM aber den größeren Kontext (Kapitel oder erweiterte Passage). Das löst das Kernproblem, das Geisteswissenschaftler an RAG-Systemen frustriert: Sätze, die mitten im Argument abreißen. Bereits einfaches Recursive Hierarchical Chunking bringt ca. 80% des Qualitätsgewinns gegenüber flachem Chunking.

**Semantic-Hybrid-Chunking (Upgrade-Pfad):** Kombiniert semantisches Splitting via Embedding-Ähnlichkeit mit Agglomerative Clustering und dynamischen Thresholds, die sich automatisch pro Buch anpassen. Weitere 20–30% Qualitätsgewinn, aber signifikant mehr Implementierungsaufwand — daher als optionaler Upgrade-Pfad nach der Parent-Child-Grundlage.

**Embedding-Evaluation:** Vergleich von BGE-M3 mit multilingual-e5 und jina-embeddings-v3. Domain-spezifische Optimierungsmöglichkeiten evaluieren.

---

## v1.2 — OCR und erweiterte Formate (Q3 2026)

**Fokus:** Gescannte PDFs und historische Dokumente erschließen.

Viele geisteswissenschaftliche Bibliotheken enthalten gescannte PDFs — ältere Fachbücher, Dissertationen, historische Quelleneditionen. Ohne OCR bleiben diese unsichtbar.

**Vision-Language-OCR (primär):** Moderne Modelle wie LightOnOCR-2 oder olmOCR-2 verstehen Layout, Lesereihenfolge und Dokumentstruktur — nicht nur einzelne Zeichen. Ideal für akademische Dokumente mit Fußnoten, Tabellen und mehrspaltigem Layout. Vollständig lokal betreibbar.

**Tesseract (Fallback):** Für einfache Dokumente als schneller und ressourcenschonender Fallback. Die OCR-Schnittstelle ist als austauschbares Modul im Extractors Layer angelegt; der `ArchillesService` exponiert bereits die `ocr_backend`-Konfiguration (auto/tesseract/lighton/olmocr).

Die strategische Entscheidung: Die OCR-Landschaft entwickelt sich rasant. Die Schnittstelle wird sauber definiert, das beste verfügbare Modell zum Implementierungszeitpunkt eingesetzt.

---

## v1.5 — Community-Release und Open Source (Q3–Q4 2026)

**Fokus:** ARCHILLES in die Hände der Zielgruppe bringen.

Open-Source-Veröffentlichung unter MIT-Lizenz. Domains sind gesichert (archilles.org, archilles.net, archilles.de). Die Zielgruppe sind technisch versierte Einzelforscher aus den Geisteswissenschaften — Geschichte, Literatur, Philosophie —, die große, kuratierte Calibre-Bibliotheken pflegen und Wert auf Privacy und lokale Datenkontrolle legen.

Community-Aufbau über akademische Kanäle: r/DigitalHumanities, r/AskHistorians, GitHub Discussions, DH-Discord-Server und spezialisierte Foren. Der ARCHILLATOR (Browser-basierter akademischer Textübersetzer) dient als Lead Magnet.

Freemium-Modell: Kostenlose Basisversion ohne Bibliotheksbeschränkung. Premium-Features und disziplinspezifische Erweiterungen (Special Editions) finanzieren die Weiterentwicklung.

---

## v2.0 — Graph RAG und Wissensvernetzung (2027)

**Fokus:** Vom Suchen zum Verstehen — Beziehungen zwischen Entitäten, Ideen und Texten sichtbar machen.

Hier wird ARCHILLES mehr als ein Suchwerkzeug. Graph RAG ermöglicht die Extraktion von Entitäten (Personen, Orte, Konzepte, Ereignisse), das Mapping ihrer Beziehungen und die Visualisierung als Netzwerkgraphen und Zeitleisten. Für Historiker bedeutet das: Prosopographie über die gesamte Bibliothek — wer kannte wen, wer zitierte wen, welche Ideen wanderten wohin.

**Evaluierung:** LightRAG als potenzielles Backend, Wikidata und Wikipedia als Seed-Quellen für Entity-Disambiguierung. Evaluation geplant für Q2 2026, Implementation frühestens 2027.

---

## Special Editions (ab v2.0)

Disziplinspezifische Erweiterungen als kostenpflichtige Add-ons, die die Weiterentwicklung finanzieren:

**Historical Edition:** Zeitleisten-Visualisierung, Prosopographie (Personennetzwerke), chronologiebewusste Suche, Primärquellenverarbeitung, mittelalterliche Datierungssysteme.

**Literary Edition:** Motivverfolgung, intertextuelle Verbindungen, Erzählstrukturanalyse, Figurennetzwerke, stilometrische Werkzeuge.

**Legal Edition:** Zitationsnetzwerke, Präzedenzfall-Tracking, jurisdiktionsbewusste Suche, Fallrecht-Verarbeitung.

**Musical Edition:** Partituranalyse-Integration, musiktheoretische Terminologie, Komponistennetzwerke, epochenbewusste Suche.

Detaillierte Pläne: siehe [EDITIONS.md](EDITIONS.md).

---

## Langfristiger Horizont

**Multi-Library-Support:** Verwaltung mehrerer Calibre-Bibliotheken, bibliotheksübergreifende Suche, bibliotheksspezifische Konfigurationen.

**Zotero-Backend:** Parallele Unterstützung neben Calibre für Nutzer, die ihre Referenzverwaltung dort pflegen.

**Wikidata-Integration:** Entity-Disambiguierung für präzisere Wissensgraphen.

**Erweiterte Plattformunterstützung:** Desktop-Anwendungen, Linux-Paketmanager (apt, yum, AUR), Mobile Companion App (Suche).

**Institutionelle Features (optional):** Scoped Knowledge Bases, institutionelle Lizenzen — nur wenn die Nachfrage es rechtfertigt. Der Fokus bleibt auf dem individuellen Forscher.

---

## Leitprinzipien

**Privacy ist die Architektur, nicht ein Feature.** Keine Netzwerk-Calls im normalen Betrieb, keine Telemetrie, alle Daten lokal. Wenn der Nutzer sich mit einem Cloud-LLM verbindet, ist das seine bewusste Entscheidung — „Mein Korpus, meine Wahl."

**Weniger Code, mehr Architektur.** Wo eine architektonische Lösung bessere Ergebnisse liefert als eine code-intensive Heuristik, wird die Architektur gewählt.

**Modulare Erweiterbarkeit vor Featurefülle.** Registry-Pattern, Plugin-fähige Schnittstellen und definierte Erweiterungszonen sind wichtiger als jedes einzelne Feature.

**Akademischer Anspruch als Differenzierung.** Exakte Zitationen mit Seitenangaben, transparentes Retrieval, disziplinspezifische Optimierungen — das unterscheidet ARCHILLES von generischen RAG-Lösungen.

**Aufschub als bewusste Strategie.** Graph RAG, OCR, institutionelle Features werden zum richtigen Zeitpunkt implementiert. Ein funktionierendes Produkt hat Vorrang vor einer vorzeitig aufgeblähten Architektur.

**Core bleibt frei und Open Source** (MIT-Lizenz). Special Editions finanzieren die Weiterentwicklung. Keine Breaking Changes ohne Migrationspfad.

---

## Community

Die Roadmap wird durch Nutzerbedürfnisse geformt.

Feature Requests und Bug Reports: [GitHub Issues](https://github.com/archilles/archilles/issues)
Diskussionen: [GitHub Discussions](https://github.com/archilles/archilles/discussions)
Beta-Testing: Programm in Vorbereitung für v1.0.

---

*Für die technischen Architekturentscheidungen hinter dieser Roadmap siehe [DECISIONS.md](DECISIONS.md).*
*Für die Systemarchitektur siehe [ARCHITECTURE.md](ARCHITECTURE.md).*
