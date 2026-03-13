# ARCHILLES – Entscheidungsarchiv

**Dokumenttyp:** Lebende Referenz für strategische und technische Entscheidungen  
**Erstfassung:** 13. Februar 2026
**Letzte Überarbeitung:** 11. März 2026 (ADR-019–024: Research Interest Boosting, list_books_by_author, Erweiterte Batch-Optionen, MPS-Support, Stop-Word-Removal, Progress-DB)
**Zweck:** Jede neue Claude-Session, jeder künftige Contributor und Tom selbst in drei Monaten sollen verstehen, *warum* ARCHILLES so gebaut ist, wie es gebaut ist.

---

## Was dieses Dokument ist und was nicht

Dieses Dokument hält die wesentlichen Entscheidungen fest, die das Projekt geformt haben – nicht als lückenlose Chronik, sondern als destillierte Begründungssammlung. Es erklärt Architekturentscheidungen, Marktpositionierung, bewusst aufgeschobene Optionen und verworfene Alternativen. Die technische Implementierung wird separat in ARCHITECTURE.md beschrieben; hier geht es um das *Warum*.

Die Entscheidungen sind nach inhaltlicher Logik gruppiert, nicht chronologisch. Wo es zum Verständnis beiträgt, sind Zeitpunkte angegeben.

---

## I. Marktpositionierung und Validierung

### Die Grundthese: Humanities-Forscher sind unterversorgt

Im November 2025 wurde der RAG-Markt parallel über fünf verschiedene KI-Modelle (ChatGPT, Claude Opus, Google Gemini, Grok 4.1 und LMArena) analysiert. Die Modelle konvergierten auf mehreren Befunden, die zur strategischen Grundlage des Projekts wurden.

Der Gesamtmarkt für RAG-Systeme wächst von ca. 300 Mio. USD (2024) auf projizierte 2,5 Mrd. USD (2030). Innerhalb dieses Marktes existiert eine strukturelle Lücke: Geisteswissenschaftler, Historiker und Forscher mit großen persönlichen Textsammlungen werden von existierenden Lösungen nicht bedient. Cloud-basierte Systeme wie Elicit, Consensus oder Scite setzen auf ihre eigenen Korpora oder institutionelle Zugänge; lokale Open-Source-Frameworks wie LlamaIndex, LangChain oder AnythingLLM sind generisch und liefern keine zitierfähigen Quellenangaben in akademischem Format.

Der europäische Markt zeigt dabei eine 2-3x höhere Zahlungsbereitschaft für datenschutzkonforme Lösungen als der US-Markt, weil die DSGVO-Anforderungen das Bedürfnis nach lokaler Datenverarbeitung verstärken.

### Warum RAG und nicht Fine-Tuning

Eine Analyse im Januar 2026 bestätigte, dass echtes LLM-Fine-Tuning mit Kosten von 50-90 Mio. USD für Training von Grund auf und erheblichem ML-Engineering-Aufwand selbst für domänenspezifische Anpassungen fest im Enterprise-Bereich verankert bleibt. RAG ist kein Kompromiss, sondern die technisch angemessene Lösung für individuelle Forscher, die ihre vorhandenen Bibliotheken mit LLM-Fähigkeiten verbinden wollen, ohne Machine-Learning-Infrastruktur betreiben zu müssen. Diese Erkenntnis gibt ARCHILLES ein Zeitfenster von mindestens 12-18 Monaten, bevor günstigere Fine-Tuning-Methoden die Nische bedrohen könnten.

### Calibre 8.16: Validierung durch Wettbewerbsanalyse

Im Dezember 2025 führte Calibre Version 8.16 eigene AI-Features ein: KI-gestützte Buchdiskussionen, Ähnlichkeitsempfehlungen und lokale Modellunterstützung über LM Studio/Ollama. Systematische Tests mit verschiedenen Dokumenttypen ergaben:

Lokale Modelle wie Gemma3 produzierten bei einem PDF, das nur ein Inhaltsverzeichnis enthielt (Hans Blumenberg, *Die Genesis der kopernikanischen Welt*), umfangreiche Halluzinationen – erfundene Kapitel und Inhalte. Googles Gemini-Modelle lieferten bessere Ergebnisse, stützten sich dabei aber auf Web-Grounding: Sie durchsuchten externe Quellen wie dandelon.com, einen europäischen Bibliothekskatalog-Anreicherungsdienst. Bei einem unveröffentlichten Manuskript (Skriptum zur Deutschen Rechtsgeschichte) konnte Gemini nur generische Beschreibungen liefern, weil kein Web-Grounding verfügbar war.

Die Schlussfolgerung: Calibres AI-Features lösen ein fundamental anderes Problem als ARCHILLES. Calibre bietet ein Gesprächsinterface für einzelne Bücher, das auf externem Wissen basiert. ARCHILLES ermöglicht semantische Suche über die gesamte persönliche Bibliothek mit verifizierbaren Quellenangaben aus den tatsächlichen Dokumenten. Die beiden Ansätze sind komplementär, nicht konkurrierend.

### Direkte Konkurrenz: überschaubar und schwach

Die Wettbewerbsanalyse zum Jahreswechsel 2025/26 identifizierte als direktesten Konkurrenten das Projekt calibre-rag-mcp-nodejs von ispyridis (veröffentlicht Dezember 2025, FAISS + Xenova Transformers, Windows-optimiert). Es fehlen exakte Zitationen, Annotationssuche und hybrides Retrieval; die Adoption lag bei 2 GitHub-Stars. Im Zotero-Ökosystem existieren reifere Lösungen (zotero-mcp, PapersGPT, mcp-research), die aber auf Referenzverwaltung statt Volltextsuche spezialisiert sind.

ARCHILLES' Alleinstellungsmerkmale bleiben bestätigt: exakte Zitationsfähigkeit mit Seitenangaben, Annotations-Indexierung, hybrides Retrieval (semantisch + keyword) und vollständig lokaler Betrieb.

---

## II. Technische Architekturentscheidungen

### ADR-001: LanceDB statt ChromaDB (Februar 2026)

**Kontext:** ARCHILLES lief produktiv mit ChromaDB und 46.354 Chunks aus ca. 87 Büchern. Die Analyse ergab, dass ChromaDB ab ca. 100.000 Chunks Performance-Degradation zeigt. Bei durchschnittlich 533 Chunks pro Buch bedeutet das ein Maximum von ca. 188 Büchern – weit unter dem Ziel von 500-1.000 Leit-Titeln aus einer Gesamtbibliothek von 8.000+.

**Entscheidung:** Migration zu LanceDB.

**Begründung:** LanceDB bringt native Hybrid-Search (dense + sparse Vectors) mit. Die IVF-PQ-Indexstruktur ist für Millionen von Chunks optimiert und optional GPU-beschleunigbar. Die Migration wurde bewusst früh durchgeführt, als die Datenbank noch klein und ein Re-Indexing unkompliziert war.

**Konsequenzen:** Der gesamte Storage-Layer, Indexer und Retriever mussten umgeschrieben werden. Alle ca. 87 Bücher wurden aus den Quelldateien neu indexiert – nicht aus ChromaDB exportiert –, was zwei Vorteile brachte: Erstens erhielten auch die älteren Bücher die seit Januar 2026 verfügbare Section-Metadata (Front Matter / Hauptinhalt / Back Matter Klassifikation), zweitens entfiel die Abhängigkeit vom alten ChromaDB-Format. Der Indexstand stieg durch Re-Indexierung und neue Bücher auf über 78.000 Chunks.

Im selben Zug wurde der bibliography/index-Rauschfilter architektonisch gelöst: Eine 118-Zeilen-Text-Heuristik (`_is_bibliography_or_index()`), die bei Tests 0 von 4 echten Rausch-Chunks erkannte und dafür Fußnoten als False Positives produzierte, wurde komplett entfernt. Stattdessen filtert das System nun auf DB-Ebene über `section_type`: Default `section_filter='main'` schließt Anhang, Register und Inhaltsverzeichnis automatisch aus. Das Ergebnis: minus 159 Zeilen netto bei besserem Ergebnis – ein Musterbeispiel für das Leitprinzip "weniger Code, mehr Architektur".

Das Architekturprinzip dabei: "Wir bauen ein Chassis, in das wir später bessere Motoren einbauen können – und verlegen jetzt schon Kabel zu Steckplätzen, an denen wir künftig erwartbare neue Geräte einstecken können." Die Parameter-Ebene im Code wurde von Beginn an auf Diversifizierung und Erweiterbarkeit ausgerichtet.

**Technisches Detail zur Hybrid-Search:** LanceDB implementiert intern eine eigene Variante der Fusion von Vektor- und Keyword-Ergebnissen. Die zuvor selbst implementierte BM25- und RRF-Logik konnte daher stark vereinfacht werden, ist aber nicht vollständig entfallen – der Retriever nutzt LanceDBs native Hybrid-Search-API statt eigener Fusionsalgorithmen.

### ADR-002: BGE-M3 als Embedding-Modell

**Kontext:** Für ein System, das Texte in Deutsch, Englisch, Latein, Altgriechisch und weiteren Sprachen verarbeiten muss, ist ein multilinguales Embedding-Modell entscheidend. Die Zielgruppe arbeitet mit historischen und modernen Quellen in wechselnden Sprachen.

**Entscheidung:** BGE-M3 von BAAI als primäres Embedding-Modell (1024 Dimensionen, multilingual).

**Begründung:** BGE-M3 wurde in der Marktanalyse über mehrere KI-Modelle hinweg als einer der Spitzenreiter für multilinguales Retrieval identifiziert. Es bietet native Unterstützung für Dense-, Sparse- und ColBERT-Retrieval in einem einzigen Modell. Die Chunking-Intelligence-Analyse (parallel über Gemini, Grok und ChatGPT durchgeführt) bestätigte die Eignung für wissenschaftliche Texte.

**Offene Frage:** Evaluation von multilingual-e5 und jina-embeddings-v3 als Alternativen für den Mid-term (Q2 2026).

### ADR-003: PyMuPDF als primärer PDF-Extraktor

**Kontext:** Die Qualität der Textextraktion bestimmt die Qualität der Suchergebnisse. Verschiedene PDF-Extraktionsbibliotheken wurden evaluiert.

**Entscheidung:** PyMuPDF (fitz) als primärer Extraktor, mit Multi-Tier-Fallback-System.

**Begründung:** PyMuPDF bietet die beste Kombination aus Geschwindigkeit und Extraktionsqualität für die Mehrzahl der Dokumente. Es liefert zuverlässiges Seitenzahlen-Mapping, das für zitierfähige Quellenangaben unerlässlich ist. Die ursprünglich als primärer Extraktor vorgesehene Bibliothek pdfplumber wurde auf eine Fallback-Rolle zurückgestuft. Für problematische PDFs (historische Scans, komplexe Layouts) steht ein Fallback-System bereit, das bei Qualitätsproblemen alternative Extraktoren einschaltet.

**Verworfene Alternativen:** Marker (LLM-gestützter Korrekturmodus) wurde als bedarfsgesteuertes Feature für die Zukunft notiert, nicht als aktive Planung. Die Entscheidung fällt nach Beta-Feedback über die tatsächliche Extraktionsqualität.

**Ergänzung (21. Februar 2026): Markdown als Extraktionsziel.** Die aktuelle Extraktion liefert Plaintext-Chunks, deren Zeichenkodierung für menschliche Inspektion schwer lesbar ist (Encoding-Artefakte, fehlende Struktur). Parallel dazu hat sich im Feld eine Best Practice etabliert: PDF → strukturiertes Markdown → Chunking entlang von Heading-Hierarchien, statt blindem Token-Splitting auf flachem Text. Markdown erhält Teil/Abschnitt/Unterabschnitt-Hierarchien und ermöglicht strukturorientiertes Chunking – für historische Fachtexte mit komplexer Gliederung ein qualitativer Gewinn.

Als konkrete Implementierungsoption wird **Docling** (IBM, Open Source, lokal lauffähig) notiert: Es produziert strukturierten Markdown-Output mit erhaltenen Heading-Pfaden und ist CPU-fähig. Evaluierbar als Ergänzung oder Ersatz des PyMuPDF-Extraktors, sobald Beta-Feedback zur Extraktionsqualität vorliegt. Für die Historical Special Edition ist strukturorientiertes Chunking auf Markdown-Basis ohnehin Voraussetzung für eine sinnvolle LightRAG-Integration.

**Offene Frage:** Ob Markdown-Output bereits für das MVP sinnvoll ist (Verbesserung der menschlich inspizierbaren Chunk-Qualität) oder erst für die Special Editions, hängt vom tatsächlichen Aufwand ab und wird nach erster Docling-Evaluation entschieden.

### ADR-004: Modulare Pipeline-Architektur

**Kontext:** ARCHILLES soll verschiedene Parser, Chunker und Embedder unterstützen können – sowohl für verschiedene Dateiformate als auch für künftige Special Editions mit disziplinspezifischen Optimierungen.

**Entscheidung:** Modulare Pipeline-Architektur, auf ein Registry-Pattern hin angelegt. Parser, Chunker und Embedder sind als austauschbare Komponenten mit klar definierten Schnittstellen implementiert.

**Begründung:** Das Pattern ermöglicht die spätere Erweiterung um neue Extraktoren (etwa für DJVU, OCR-intensive Dokumente oder proprietäre Formate), neue Chunking-Strategien (semantisch vs. fixed-size vs. hybrid) und neue Embedding-Modelle, ohne den Kern des Systems zu modifizieren. Es ist zudem die technische Voraussetzung für das Freemium-Modell: Die Basisversion nutzt Standard-Komponenten, Special Editions können optimierte Varianten einsetzen.

**Implementierungsstand:** Das Registry-Pattern ist vollständig implementiert. In `src/archilles/` existieren drei formale Registries mit dynamischer Registrierung und Laufzeit-Discovery: `ParserRegistry` (für `PyMuPDFParser`, `EPUBParser`), `ChunkerRegistry` (für `FixedSizeChunker`, `SemanticChunker`) und `EmbedderRegistry` (für `BGEEmbedder` mit bge-small/base/m3-Varianten). Jedes Registry bietet `register()`, `get()`, `list_*()` und `get_default()`. Factory-Funktionen wie `create_chunker_for_profile()` verbinden Registries mit den Hardware-Profilen. Die `ModularPipeline` (`pipeline.py`) orchestriert den Dreischritt Parser → Chunker → Embedder. Parallel dazu existieren die Extractors (`src/extractors/`) als eigenständige Schicht für die Rohtextextraktion, koordiniert durch `UniversalExtractor` mit `FormatDetector`.

### ADR-005: Keine direkte Modifikation von Calibres metadata.db

**Kontext:** Metadaten-Anreicherung durch LLM-Extraktion aus Volltexten wurde als Feature diskutiert – etwa fehlende Autoren, Erscheinungsjahre oder Schlagworte automatisch ergänzen.

**Entscheidung:** Calibres metadata.db wird nie direkt modifiziert.

**Begründung:** Calibre-Nutzer verlassen sich auf die Integrität ihrer Datenbank. Direkte Modifikation birgt das Risiko von Datenbeschädigung und verletzt das Vertrauen der Nutzer. Stattdessen wird der `.archilles`-Ordner als definierte Erweiterungszone genutzt. Externe Metadaten können in einer separaten JSON- oder SQLite-Datei gespeichert und zur Laufzeit mit Calibre-Metadaten zusammengeführt werden.

### ADR-006: Hybride Suche mit Reciprocal Rank Fusion

**Kontext:** Rein semantische Suche findet konzeptionell verwandte Passagen, versagt aber bei exakten Begriffen – Eigennamen, Jahreszahlen, Fachterminologie. Reine Keyword-Suche findet exakte Treffer, versteht aber keine Bedeutung.

**Entscheidung:** Hybride Suche, die BGE-M3-Vektorembeddings mit BM25-Keyword-Matching über Reciprocal Rank Fusion kombiniert.

**Begründung:** Geisteswissenschaftler suchen sowohl nach Konzepten ("Legitimation von Herrschaft im Mittelalter") als auch nach konkreten Referenzen ("Eusebius von Caesarea" oder "325 n. Chr."). Die hybride Suche bedient beide Suchmodi. RRF als Fusionsmethode wurde in der Wettbewerbsanalyse (Dezember 2025) als algorithmisch einfach, ohne neue Dependencies und mit messbarer Qualitätsverbesserung bewertet.

**Evolutionspfad:** Die Implementierung hat sich mit der Datenbank-Migration weiterentwickelt. In der ChromaDB-Phase war RRF als eigener Algorithmus implementiert; seit der LanceDB-Migration nutzt `LanceDBStore.hybrid_search()` LanceDBs `RRFReranker` (aus `lancedb.rerankers`) für die native Fusion von Vektor- und Keyword-Ergebnissen. Die Suchlogik ist über zwei Ebenen verteilt: `LanceDBStore` (DB-Level: Hybrid-Suche, Filterung) und `archillesRAG` in `scripts/rag_demo.py` (App-Level: Modus-Auswahl, Tag-Filterung, Diversifizierung, Kontext-Expansion). Es existiert keine separate `hybrid.py`-Datei; die Vereinheitlichung läuft über den Service-Layer.

### ADR-007: OCR-Strategie – Tesseract als Basis, modularer Ausbau

**Kontext:** Ein erheblicher Teil akademischer Bibliotheken besteht aus gescannten PDFs, für die Textextraktion nur über OCR möglich ist. Die Qualitätsanforderungen sind hoch, weil fehlerhafte OCR-Ergebnisse das gesamte Retrieval kompromittieren.

**Entscheidung:** Tesseract als Basismodul, mit vorbereitetem Ausbau auf bessere Modelle.

**Begründung:** Tesseract ist frei verfügbar, gut etabliert und ausreichend für moderne Druckschriften. Für die anspruchsvolleren Fälle – historische Frakturschrift, handschriftliche Marginalien, schlecht gescannte Vorlagen – wird der modulare Ausbau vorbereitet, ohne dass die Basisversion davon abhängt. Die strategische Analyse (Februar 2026) ergab, dass sich die OCR-Landschaft rasant entwickelt und eine zu frühe Festlegung auf ein spezifisches Premium-System riskant wäre. Besser: die Schnittstelle sauber definieren und das beste verfügbare Modell einsetzen, wenn es soweit ist.

**Implementierungsstand:** `ocr_extractor.py` existiert in `src/extractors/` mit `OCRExtractor`- und `TesseractExtractor`-Klassen. Die Dataclass in `models.py` ist mit einem `output_format`-Feld vorbereitet, das verschiedene OCR-Backend-Ausgabeformate unterstützen kann. Der `ArchillesService` exponiert `ocr_backend`-Konfiguration (auto/tesseract/lighton/olmocr) zur Backend-Auswahl.

### ADR-008: Zwei-Datenbanken-Architektur → Konsolidierung in LanceDB (November 2025, aktualisiert Februar 2026)

**Kontext:** ARCHILLES verarbeitet zwei fundamental verschiedene Texttypen: den Buchinhalt selbst und alles, was *über* ein Buch geschrieben wurde – Verlagstexte, Kritiken, NotebookLM-Analysen und persönliche Exzerpte im Calibre-Kommentarfeld. Hinzu kommen Annotationen: Highlights und Notizen, die der Nutzer direkt in seinen Büchern hinterlässt (Calibre-Viewer für EPUBs, Adobe Reader für PDFs).

**Ursprüngliche Entscheidung (November 2025):** Getrennte Datenbanken: `archilles_books` für Volltext-Chunks aus den Buchdateien, `archilles_meta` für Calibre-Kommentare und Annotationen.

**Begründung:** Für Geisteswissenschaftler ist die Unterscheidung zwischen "was steht im Buch" und "was habe ich oder andere darüber geschrieben" fundamental. Eine monolithische Datenbank hätte diese Grenze verwischt. Die Trennung ermöglicht gezielte Suchmodi: nur in Quellentexten suchen, nur in eigenen Notizen suchen, oder beides mit Gewichtung.

**Konsequenzen:** Der MCP-Server exponiert beide Suchräume als separate Tools (`search_books_with_citations` für Buchinhalte, `search_annotations` für Nutzerdaten).

**Aktualisierung (Februar 2026): Annotationen in LanceDB integriert.**

Die ursprünglich als Zwischenlösung in ChromaDB (`annotations_indexer.py`, `all-mpnet-base-v2`, 384 Dim.) gespeicherten Annotationen wurden in die LanceDB-`chunks`-Tabelle migriert. Annotationen werden jetzt als `chunk_type='annotation'` gemeinsam mit Buchtext-Chunks gespeichert und mit denselben BGE-M3-Embeddings (1024 Dim.) indiziert.

Die semantische Unterscheidung zwischen Buchinhalt und Nutzernotizen bleibt über das `chunk_type`-Feld erhalten: `'content'` für Buchtext, `'calibre_comment'` für Calibre-Metadaten, `'annotation'` für Highlights und Notizen. Die Suchfilterung auf DB-Ebene ist damit weiterhin möglich, und die gezielte Suche in nur einem Datentyp funktioniert über einfache WHERE-Clauses.

Vorteile der Konsolidierung:
- **Ein Embedding-Modell statt zwei:** BGE-M3 für alles eliminiert die semantische Inkompatibilität zwischen `all-mpnet-base-v2` (384 Dim.) und BGE-M3 (1024 Dim.), die Cross-Suchen zwischen Buchtext und Annotationen erschwerte.
- **Annotationen profitieren von Hybrid-Search:** LanceDBs native Fusion aus Vektor- und Keyword-Matching (ADR-006) steht jetzt auch für Annotationen zur Verfügung.
- **Eine Dependency weniger:** ChromaDB ist für die Annotation-Suche nicht mehr erforderlich. Der ChromaDB-Index (`annotations_indexer.py`) wurde am 28. Februar 2026 vollständig entfernt (siehe ADR-016).
- **Einheitliche Änderungserkennung:** Annotationen werden über denselben Hash-Mechanismus wie Metadaten auf Änderungen geprüft (siehe ADR-011).

Die konzeptionelle Zwei-Datenbanken-Architektur ist damit technisch als Filterung innerhalb einer einzigen LanceDB-Tabelle realisiert – einfacher, performanter und wartungsärmer als zwei physisch getrennte Datenbanken.

### ADR-009: Service-Layer-Architektur (Februar 2026)

**Kontext:** Das Web-UI (`web_ui.py`), der MCP-Server (`server.py`) und das CLI (`rag_demo.py`) importierten alle die RAG-Klasse direkt. Jede Änderung an der Suchlogik musste an drei Stellen nachgezogen werden – ein wachsendes Konsistenzproblem.

**Entscheidung:** Einführung eines Service-Layers (`archilles_service.py`) als zentrale Geschäftslogik-Schicht.

**Begründung:** Das ist kein glamouröses Feature, sondern Architekturhygiene. Der Service-Layer kapselt alle Operationen – `search()`, `index_book()`, `get_index_status()`, `get_book_list()` – und wird von allen drei Clients einheitlich genutzt. Änderungen an der Suchlogik, etwa die Integration von Cross-Encoder-Reranking, müssen nur noch an einer Stelle erfolgen. Der Service-Layer ist zudem die Voraussetzung dafür, dass das in ADR-004 formulierte Prinzip der modularen Erweiterbarkeit tatsächlich funktioniert: Neue Backends, neue Suchstrategien oder neue Filter werden im Service implementiert und stehen sofort überall zur Verfügung.

**Verzeichnisstruktur nach Refactoring:**

```
src/
├── archilles/                     # Modulare Pipeline-Infrastruktur
│   ├── pipeline.py                # ModularPipeline (Parser → Chunker → Embedder)
│   ├── profiles.py                # Hardware-Profile (minimal/balanced/maximal)
│   ├── hardware.py                # Hardware-Erkennung (GPU, VRAM)
│   ├── parsers/                   # ParserRegistry + PyMuPDFParser, EPUBParser
│   ├── chunkers/                  # ChunkerRegistry + FixedSize, Semantic
│   ├── embedders/                 # EmbedderRegistry + BGEEmbedder
│   └── indexer/checkpoint.py      # Checkpoint-Resume für Batch-Indexierung
├── service/
│   └── archilles_service.py       # Zentrale Geschäftslogik-Fassade
├── extractors/
│   ├── universal_extractor.py     # Delegiert an formatspezifische Extractors
│   ├── pdf_extractor.py           # PyMuPDF + pdfplumber-Fallback
│   ├── epub_extractor.py          # ebooklib mit TOC-Parser
│   ├── ocr_extractor.py           # Tesseract-Integration
│   ├── txt_extractor.py           # Plaintext-Extraktion
│   ├── html_extractor.py          # HTML-Dokumente
│   ├── calibre_converter.py       # Calibre ebook-convert Bridge
│   ├── format_detector.py         # Formaterkennung
│   ├── language_detector.py       # Lingua-basierte Spracherkennung
│   ├── models.py                  # Gemeinsame Dataclasses
│   └── exceptions.py              # Fehlertypen-Hierarchie
├── storage/
│   └── lancedb_store.py           # LanceDBStore (alle Chunks: Buchtext + Annotationen)
├── retriever/
│   └── reranker.py                # Cross-Encoder Reranking (optional)
├── calibre_mcp/
│   ├── server.py                  # CalibreMCPServer (10 MCP-Tools)
│   ├── annotations.py             # Annotation-Extraktion, Hash-Mapping, Text-Suche
│   └── calibre_analyzer.py        # Bibliotheks-Statistiken
└── calibre_db.py                  # Read-only Calibre-Metadaten-Zugriff
```

Entry-Point: `mcp_server.py` im Projekt-Root (von Claude Desktop aufgerufen).
CLI-Skripte: `scripts/rag_demo.py`, `scripts/batch_index.py`, `scripts/web_ui.py`.

### ADR-010: Eine Datei pro Buchordner (Januar 2026)

**Kontext:** Calibre-Buchordner können neben der Hauptdatei weitere Dateien enthalten: Konvertierungen in verschiedenen Formaten, Cover-Bilder, manchmal auch vom Nutzer abgelegte Exzerpte, Notizen oder ergänzende Materialien in Unterordnern.

**Entscheidung:** Bei der Indexierung wird pro Buchordner genau eine Datei verarbeitet, mit strikter Priorität: PDF > EPUB > sonstige Formate. Unterordner werden in Version 1 bewusst ignoriert.

**Begründung:** Die Beschränkung auf eine Datei verhindert doppelte Indexierung desselben Inhalts in verschiedenen Formaten. PDF hat Vorrang wegen des zuverlässigen Seitenzahlen-Mappings, das für zitierfähige Quellenangaben entscheidend ist. EPUBs liefern dafür bessere Strukturinformationen (TOC-Parsing, Section-Metadata) und werden schneller verarbeitet.

Das Ignorieren von Unterordnern ist eine bewusste Produktentscheidung, keine technische Limitierung. Gut organisierte Nutzer lagern dort oft eigene Exzerpte und Texte, die sie durchaus indexiert haben möchten – und die sie aus guten Gründen nicht ins Calibre-Kommentarfeld schreiben. Statt sie zur Umorganisation zu nötigen, wird die Fein-Indexierung mit Wahl- und Einstelloptionen für eine spätere Version oder die Paid-Version reserviert. Das schafft einen natürlichen Upgrade-Pfad, ohne die Basis-Version zu verkomplizieren.

### ADR-011: Smart Metadata & Annotation Update mit Hash-basierter Änderungserkennung (Februar 2026)

**Kontext:** Bei 670+ indexierten Büchern mit je durchschnittlich 360 Chunks dauert eine vollständige Neu-Indexierung ca. 90 Sekunden pro Buch (Textextraktion, Chunking, BGE-M3-Embedding, LanceDB-Insert). Das ist akzeptabel für die Erstindexierung, aber inakzeptabel für Routinesituationen: Der Nutzer ergänzt ein Schlagwort in Calibre, korrigiert einen Autorennamen oder fügt ein Highlight in einem PDF hinzu – und soll dafür nicht 90 Sekunden warten.

**Entscheidung:** Hash-basierte Änderungserkennung mit differenziellem Update. Zwei unabhängige Hashes pro Buch:
- `metadata_hash` (MD5 über Calibre-Felder: `comments`, `tags`, `title`, `author`, `publisher`)
- `annotation_hash` (MD5 über alle Annotationstexte eines Buchs, sortiert für Determinismus)

**Begründung:** Die vier Datentypen eines indexierten Buchs – Volltext-Chunks, Calibre-Kommentar-Chunk, Metadaten-Felder in allen Chunks, Annotation-Chunks – haben fundamental verschiedene Änderungszyklen:

| Datentyp | Ändert sich... | Häufigkeit |
|----------|---------------|------------|
| Volltext | Nie (Datei ist immutabel) | — |
| Calibre-Kommentar | Selten (Verlagstext, Klappentext) | ~1-2× pro Buch |
| Metadaten (Tags, Titel, Autor) | Gelegentlich (Kuratierung) | ~10-50× über Bibliotheksleben |
| Annotationen | Laufend (Lesefortschritt) | Kontinuierlich |

Statt für jede Änderung alles neu zu indexieren, erkennt das System jetzt via Hash-Vergleich, *was* sich geändert hat, und aktualisiert nur den betroffenen Teil:

```
Entscheidungsbaum in index_book() (force=False, Content-Chunks vorhanden):
1. metadata_hash UND annotation_hash geändert → beides updaten (~2-3s)
2. metadata_hash geändert, annotation_hash gleich → nur Metadaten updaten (~1s)
3. metadata_hash gleich, annotation_hash geändert → nur Annotationen updaten (~2s)
4. beide gleich → komplett überspringen (~0.1s)
```

**Implementierung:** `metadata_hash` wird in jedem Chunk gespeichert (ermöglicht Batch-Updates via `LanceDBStore.update_metadata_fields()`). `annotation_hash` wird nur in Annotation-Chunks gespeichert. Bei Änderung werden alte Annotation-Chunks via `delete_by_book_id_and_type()` gelöscht und neue mit frischen BGE-M3-Embeddings eingefügt.

**Konsequenz für Batch-Indexierung:** `batch_index.py --skip-existing` überspringt Bücher nicht mehr blind, sondern leitet alle Bücher an `index_book()` weiter, das die Hash-Prüfung durchführt. Ein Batch-Lauf über 670 Bücher, bei dem sich nichts geändert hat, dauert damit ~67 Sekunden statt ~16 Stunden.

### ADR-012: Annotation-Indexierung in LanceDB (Februar 2026)

**Kontext:** Annotationen – Highlights und Notizen, die der Nutzer in seinen Büchern hinterlässt – sind für Geisteswissenschaftler oft wertvoller als der Rohtext. Sie repräsentieren kuratiertes Wissen: die Passagen, die der Forscher als relevant markiert hat, und seine Gedanken dazu. ARCHILLES extrahierte Annotationen bereits über MCP-Tools (`get_book_annotations`, `search_annotations`), speicherte sie aber in einem separaten ChromaDB-Index mit einem anderen Embedding-Modell (siehe ADR-008).

**Entscheidung:** Annotationen werden als `chunk_type='annotation'` in der LanceDB-`chunks`-Tabelle gespeichert, mit BGE-M3-Embeddings, als Teil des regulären Indexierungslaufs (Phase 2).

**Annotation-Quellen:** Zwei Quellen werden automatisch zusammengeführt:
- **Calibre-Viewer-Annotations:** JSON-Dateien in `%APPDATA%\calibre\viewer\annots\`, erzeugt beim Lesen von EPUBs im Calibre-Viewer.
- **PDF-native Annotations:** Highlights und Kommentare aus Adobe Reader (oder anderen PDF-Readern), extrahiert via PyMuPDF (`fitz`).

Die bestehende Funktion `get_combined_annotations()` aus `src/calibre_mcp/annotations.py` übernimmt die Zusammenführung mit intelligenter Filterung (TOC-Marker-Erkennung, Mindestlänge 20 Zeichen, erste 5% des Buchs ausgeschlossen).

**Text-Format der Annotation-Chunks:**
- Highlight: `[ANNOTATION] {hervorgehobener Text}`
- Highlight mit Notiz: `[ANNOTATION] {hervorgehobener Text} | Note: {Notiz}`
- Reine Notiz: `[ANNOTATION_NOTE] {Notiz}`

Das `[ANNOTATION]`-Präfix sorgt dafür, dass BGE-M3 den semantischen Kontext "Nutzermarkierung" mit einbettet, was bei der Suche nach nutzerkuratierten Inhalten die Relevanz erhöht.

**Neue LanceDB-Felder:**
- `annotation_type` (str): `'highlight'`, `'note'`, `'bookmark'`
- `annotation_source` (str): `'calibre_viewer'` oder `'pdf'`
- `annotation_hash` (str): Hash für Änderungserkennung (siehe ADR-011)

**Schema-Migration:** Die neuen Felder werden bei der ersten Nutzung automatisch via `table.add_columns()` zur bestehenden Tabelle hinzugefügt. Dieser Mechanismus wurde allgemein für alle zukünftigen Schema-Erweiterungen implementiert, sodass bestehende Indizes nie inkompatibel werden.

**Nicht-fatale Fehlerbehandlung:** Annotation-Extraktion ist in einen try/except-Block eingebettet. Wenn die Extraktion für ein Buch fehlschlägt (z.B. kein Annotations-Verzeichnis, korrupte JSON-Datei), wird eine Warnung geloggt, aber die Buchindexierung läuft normal weiter.

### ADR-013: Crash-sichere Backup-Strategie für LanceDB (Februar 2026)

### ADR-014: Citation Style Module – Prompt-basiert, CSL-ready (Februar 2026)

**Kontext:** ARCHILLES liefert Suchergebnisse mit Zitationsangaben (Autor, Titel, Jahr, Seite/Kapitel). Die Formatierung dieser Angaben – Chicago, APA, Harvard, MLA, IEEE – lag bisher implizit in der Formulierung der MCP-Tool-Ergebnisse. Es fehlte eine zentrale Stelle, die den gewünschten Zitierstil konfigurierbar macht und die Formatierungsanweisung für das LLM generiert.

**Entscheidung:** Neues Modul `src/citation/` mit drei Komponenten:
- `CITATION_STYLES`: Registry mit 6 Stilen (Chicago Author-Date, Chicago Notes, APA 7, Harvard, MLA 9, IEEE). Jeder Eintrag enthält Label, kanonische CSL-Style-ID, Locale-Hint, deutsch/englische Prompt-Fragmente und ein Formatbeispiel.
- `CitationConfig`: Dataclass für Nutzerpräferenzen (`style`, `locale`, optionaler `csl_path`). Serialisierbar für `config.json`.
- `format_bibliography_instruction()`: Generiert den Instruktionsblock, der in den RAG-System-Prompt injiziert wird, damit Claude die Bibliografie im gewünschten Stil formatiert.

**Begründung – Warum Prompt-basiert statt CSL-Prozessor:**

Die parallele CSL-Forschung (citeproc-py Evaluation, Februar 2026) ergab:

| Aspekt | citeproc-py | Prompt-basiert (aktueller Ansatz) |
|---|---|---|
| CSL-Spec-Compliance | ~60% der Test-Suite | Claude kennt APA/Chicago/Harvard nativ |
| Maintenance | Inaktiv (letzte Release v0.9.0, volunteer-maintained) | Keine externe Dependency |
| Dependencies | lxml (~4 MB), optional citeproc-py-styles (~40 MB) | Keine |
| Flexibilität | Exakt nach CSL-Spec | Claude kann Randfall-Formatierung intelligent lösen |
| Geeignet für | Offline-Rendering, Zotero-Roundtrip, Verlagseinreichung | Interaktive Recherche mit LLM |

Für den aktuellen Use Case – Claude formatiert die Bibliografie im Rahmen einer MCP-Session – ist der Prompt-basierte Ansatz überlegen: null Dependencies, sofort funktionsfähig, und Claude beherrscht die gängigen Stile aus seinem Training.

**CSL-Readiness als Architekturprinzip:** Die kanonischen CSL-Style-IDs (identisch mit Zoteros Style Repository) sind bereits im Code hinterlegt. Wenn citeproc-py als optionale Dependency hinzugefügt wird, braucht es nur noch ein ~40-Zeilen-`formatter.py`, das `CitationConfig.csl_style_id` nimmt und eine formatierte Bibliografie zurückgibt. Kein Schema-Umbau nötig. Für ARCHILLES wären nur 6 .csl-Dateien (~50 KB) statt des vollen Styles-Pakets (~40 MB) nötig.

**citeproc-py lohnt sich erst für:**
- Offline-Rendering ohne Claude
- Exakte Konformitätsprüfung (Dissertation, Verlagseinreichung)
- Zotero-Roundtrip mit garantierter Stil-Treue

**Implementierungsstand:** Modul vollständig implementiert (`src/citation/__init__.py`, `src/citation/config.py`). Noch nicht in den MCP-Server oder Service-Layer integriert – das erfolgt mit dem nächsten config.json-System.

### ADR-015: EPUB-Ergebnisse mit Originalsprachen-Zitat (Februar 2026)

**Kontext:** EPUB-Dateien haben keine physischen Seitenzahlen. ARCHILLES zitiert EPUB-Quellen mit Kapitelnamen statt Seitenzahlen: `(Autor, Titel [Jahr], Kap. Kapitelname)`. Der Nutzer muss die zitierte Passage im Originaldokument wiederfinden können – etwa um den Kontext zu prüfen, weiterzulesen oder korrekt zu zitieren.

**Entscheidung:** Bei EPUB-Quellen (und allen anderen Quellen ohne physische Seitenzahl) wird stets ein kurzes wörtliches Zitat in der Originalsprache des Textes mitgeliefert. Das Zitat muss hinreichend distinktiv sein, um mit der Suchfunktion des E-Book-Readers die Passage eindeutig zu lokalisieren.

**Begründung:** Die Kapitelangabe allein ist für die Auffindbarkeit unzureichend – Kapitel können Dutzende Seiten umfassen. Ein Originalsprachen-Zitat von 5–15 Wörtern löst das Problem elegant:
- **Findability:** Der Nutzer kann das Zitat per Strg+F im Calibre-Viewer oder jedem anderen Reader suchen und landet exakt an der Stelle.
- **Originalsprache:** Wenn der Text auf Latein, Englisch oder einer anderen Fremdsprache verfasst ist, muss das Zitat in dieser Sprache stehen – nicht in der Übersetzung. Nur so funktioniert die Textsuche im Originaldokument.
- **Verifizierbarkeit:** Das wörtliche Zitat ermöglicht eine sofortige Plausibilitätsprüfung, ob die Passage tatsächlich das behauptete Argument enthält.

**Geltungsbereich:** Diese Regel gilt für alle ARCHILLES-Ausgabeformate (Synthese, Materialliste, Zitatsammlung) und wird in ARCHILLES_SKILL.md als Handlungsanweisung für KI-Assistenten verankert.

**Beispiel:**
```
(Eusebius, Kirchengeschichte, Kap. III.4 — „τὴν τῶν ἀποστόλων διαδοχὴν")
(Blumenberg, Die Legitimität der Neuzeit [1966], Kap. 2.1 — „die Selbstbehauptung der Vernunft")
```

---

### ADR-013: Crash-sichere Backup-Strategie für LanceDB (Februar 2026)

**Kontext:** Die LanceDB-Datenbank für 670+ Bücher umfasst ca. 243.000 Chunks und belegt ~13 GB auf der Festplatte. Batch-Indexierung läuft über Stunden bis Tage. Ein Abbruch durch Systemabsturz, Stromausfall oder CTRL+C darf nicht zum Datenverlust führen.

**Entscheidung:** `SafeIndexer` (`scripts/safe_indexer.py`) erstellt periodische Kopien der LanceDB und begrenzt die Anzahl aufbewahrter Backups.

**Ursprüngliche Konfiguration:** Backup alle 10 Bücher, maximal 5 Backups.

**Problem:** Bei ~13 GB pro Backup und 5 aufbewahrten Kopien können bis zu 65 GB Backup-Daten anfallen. In der Praxis füllte dies die Festplatte während eines 3-tägigen Batch-Laufs über 445 Bücher.

**Korrigierte Konfiguration:** Backup alle 50 Bücher, maximal 2 Backups (~26 GB Maximum).

**Begründung der neuen Werte:**
- **Intervall 50:** Ein Verlust von maximal 50 Büchern (~75 Minuten Arbeit) ist bei einem Non-Production-System akzeptabel. Die `progress.db` (SQLite) trackt den Fortschritt buchgenau, sodass ein Neustart exakt dort fortsetzt, wo der Abbruch war – die Backups schützen nur gegen Korruption der LanceDB selbst.
- **Maximum 2:** Das vorletzte Backup dient als Fallback, falls das letzte Backup selbst korrupt sein sollte (z.B. bei Abbruch während des Backup-Vorgangs). Mehr als 2 Generationen bringen keinen zusätzlichen Schutz.

**Konsequenz:** Der `SafeIndexer` bleibt als Sicherheitsnetz erhalten, ist aber kein Engpass mehr. Für die Zukunft wäre ein inkrementelles Backup-Konzept denkbar (nur geänderte Lance-Fragmente kopieren), aber bei der aktuellen Datenbankgröße ist die einfache Kopie-Strategie ausreichend.

### ADR-016: ChromaDB vollständig entfernt (28. Februar 2026)

**Kontext:** ChromaDB war nach der LanceDB-Migration (ADR-001) und der Annotation-Konsolidierung (ADR-012) nur noch als leere Hülle vorhanden: `annotations_indexer.py` (850+ Zeilen) existierte im Code, wurde aber seit dem 18. Februar 2026 nicht mehr gefüllt. `search_annotations` routete weiterhin gegen ChromaDB – also gegen einen leeren Index.

**Entscheidung:** Vollständige Entfernung von ChromaDB aus dem Projekt.

**Änderungen:**
- `src/calibre_mcp/annotations_indexer.py` gelöscht (850+ Zeilen ChromaDB-Logik)
- `chromadb==0.4.22` aus `requirements.txt` entfernt
- `rank-bm25==0.2.2` aus `requirements.txt` entfernt (LanceDB hat native FTS)
- `search_annotations`-Tool auf LanceDB umgestellt: sucht jetzt in `chunk_type='annotation'` und `chunk_type='calibre_comment'` via neuem Kombinationsfilter `'annotations_and_comments'` in `LanceDBStore._build_filter()`
- `index_annotations`-Tool aus MCP-Server entfernt (Annotationen werden im regulären Indexierungslauf automatisch gespeichert)
- `get_index_stats`-Tool aus MCP-Server entfernt (war ChromaDB-spezifisch; LanceDB-Stats über `get_index_status` verfügbar)
- `chroma_db/` aus `.gitignore` entfernt
- ChromaDB-Kompatibilitäts-Shim (`ChromaDBCorruptionError = LanceDBError`) aus `rag_demo.py` entfernt

**Begründung:** Eine tote Dependency mit 850 Zeilen totem Code ist ein aktives Wartungsproblem. Der ChromaDB-Index war nie in die LanceDB-Architektur integriert – das war eine Schuld, die seit ADR-012 angewachsen war. Die Entfernung schließt die Migration ab und reduziert die Installationsgröße und Komplexität erheblich.

**Konsequenz:** `search_annotations` nutzt jetzt denselben Hybrid-Search-Pfad wie `search_books_with_citations` – mit BGE-M3-Embeddings, BM25-Keyword-Matching und RRF-Fusion. Annotationen, die vor dem 18. Februar 2026 in ChromaDB gespeichert waren, sind verloren, sofern sie nicht im LanceDB-Lauf vom 18. Februar erfasst wurden. Eine Neu-Indexierung mit `--reindex-before 2026-02-19` stellt sie wieder her.

### ADR-017: `--cleanup-orphans` – Stale-Index-Einträge entfernen (28. Februar 2026)

**Kontext:** Wenn ein Buch aus Calibre gelöscht wird, verbleiben seine Chunks in LanceDB – der Index wächst mit toten Einträgen. Es fehlte ein Mechanismus, um diese Orphans zu bereinigen.

**Entscheidung:** Neues CLI-Flag `--cleanup-orphans` in `batch_index.py`.

**Implementierung:** `get_all_calibre_ids()` liest alle Book-IDs direkt aus Calibres `metadata.db` (ohne Tag/Autor-Filter, um nicht Bücher aus anderen Tags fälschlicherweise als Orphans zu werten). `cleanup_orphans()` vergleicht die LanceDB-IDs gegen die Calibre-IDs und löscht Chunks zu nicht mehr vorhandenen Büchern. Das Flag kann standalone verwendet werden, ohne `--tag`/`--author`/`--all` anzugeben.

**Begründung:** Ein wachsender Index mit toten Einträgen schadet der Suchqualität (False Positives) und verschwendet Speicher. Der Dry-Run-Modus erlaubt sichere Inspektion vor dem Löschen.

### ADR-018: `--prefer-format` – Dateiformat-Präferenz bei Batch-Indexierung (28. Februar 2026)

**Kontext:** Viele Bücher in Calibre liegen in mehreren Formaten vor (z.B. PDF + EPUB). Die bisherige Strategie (PDF-Vorrang hardcodiert) bevorzugte Seitenzahlen, ignorierte aber die erheblichen Vorteile strukturierter EPUB-Extraktion.

**Entscheidung:** Neues CLI-Flag `--prefer-format` mit Optionen `pdf`, `epub`, `mobi`, `azw3` (Standard: `pdf`). Ist das bevorzugte Format nicht vorhanden, greift automatisch das nächste verfügbare Format.

**Abwägung:**

| Format | Vorteil | Nachteil |
|--------|---------|----------|
| PDF | Exakte Seitenzahlen, wissenschaftliche Zitierbarkeit | OCR-Rauschen bei gescannten PDFs; Headers/Footers in Chunks |
| EPUB | Saubere Chunks (HTML-Struktur), schnellere Indexierung | Keine Seitenzahlen; Kapitel-Zitate statt Seiten-Zitate |

**Begründung:** Die Format-Wahl ist ein echtes Qualitäts-Trade-off, der vom Nutzer je nach Primärzweck (wissenschaftliches Zitieren vs. thematische Recherche) getroffen werden soll. EPUBs sind aufgrund der HTML-basierten Struktur schneller zu indexieren und produzieren semantisch kohärentere Chunks, was die Suchqualität bei konzeptuellen Fragen verbessert. PDFs bleiben für akademische Arbeit mit Seitenreferenzen vorzuziehen.

**Umstellen bereits indexierter Bücher:** Die Format-Präferenz wird nicht automatisch auf bereits indexierte Bücher angewendet. Für einen vollständigen Wechsel: `--prefer-format epub --reindex-before 2099-01-01`.

### ADR-019: `set_research_interests` – Keyword-Boosting ohne Re-Indexierung (März 2026)

**Kontext:** Nutzer arbeiten über Wochen oder Monate an spezifischen Forschungsprojekten. Innerhalb eines Projekts sind bestimmte Eigennamen, Konzepte und Fachbegriffe durchgehend relevant (z.B. "Josephus", "Mithras", "priestly elite"). Die Suchergebnisse sollten diese Prioritäten reflektieren, ohne dass der Nutzer bei jeder Anfrage explizite Filter setzt oder den Index neu aufbauen muss.

**Entscheidung:** Einführung von `set_research_interests` als dediziertes MCP-Tool. Es registriert eine Liste von Boost-Keywords in einer JSON-Datei im Library-Ordner (`research_interests.json`). Bei jeder Suchanfrage werden Treffer, die mindestens eines dieser Keywords im Text oder in den Metadaten enthalten, mit einem konfigurierbaren additiven Faktor hochgestuft (Standard: +0,15 pro übereinstimmendem Keyword). Das Tool erlaubt `action: 'get'` (aktuelle Interessen anzeigen), `action: 'set'` (neue Keywords setzen) und `action: 'clear'` (zurücksetzen).

**Begründung:** Die Alternative – explizite Tag-Filter bei jeder Anfrage – ist für Nutzer im aktiven Forschungsfluss unpraktisch. Fine-Tuning oder Re-Indexierung für dasselbe Ziel wäre unverhältnismäßig teuer. Das Boosting-Modell ist adressierbar ohne Architektureingriff: Die Gewichte werden am Abruf-Zeitpunkt angewendet, nicht beim Indexaufbau. Das unterscheidet es fundamental von einem Embedding-basierten Ansatz.

**Abgrenzung zum Tag-Filter:** Tag-Filter sind explizit pro Anfrage und schließen nicht getaggte Ergebnisse aus. Research-Interest-Boosting ist implizit und dauerhaft für alle Anfragen aktiv – es unterdrückt keine Ergebnisse, sondern priorisiert sie. Beide Mechanismen sind kombinierbar.

**Implementierungsstand:** `set_research_interests_tool()` in `src/calibre_mcp/server.py`. Keywords werden im Service-Layer geladen und bei der Ergebnisaufbereitung in `ArchillesService` angewendet.

### ADR-020: `list_books_by_author` – Direkter Metadaten-Zugriff als eigenständiges Tool (März 2026)

**Kontext:** `search_books_with_citations` ist ein Volltext- und Vektorsuchsystem, kein Metadaten-Abfragesystem. Autornamen tauchen in kurzen Texten (Artikel, Buchkapitel in Sammelbänden) oft nur auf der Titelseite auf – die entweder kein eigener Chunk im Index ist oder bei der Extraktion leer war. Ein Historiker, der alle Artikel eines bestimmten Autors in seiner Bibliothek finden will, bekommt über Vektorsuche unzuverlässige Ergebnisse.

**Entscheidung:** Einführung von `list_books_by_author` als dediziertes MCP-Tool. Es fragt direkt gegen Calibres `metadata.db` ab (nicht gegen den LanceDB-Index) und gibt alle Titel eines Autors mit vollständigen Metadaten zurück. Unterstützt Partial-Match (case-insensitive), optionale Tag-Filter (AND-Logik), Jahresbereich-Filter und Sortierung nach Titel oder Jahr.

**Begründung:** Der Unterschied zwischen "Suche nach Inhalten" und "Suche nach Titeln" ist für geisteswissenschaftliche Arbeit fundamental. Bibliographische Abfragen – wer hat was wann veröffentlicht – sind Metadaten-Aufgaben, keine Retrieval-Aufgaben. Die Trennung gehört in die Tool-Architektur des MCP-Servers, nicht nur in die Dokumentation. Das Tool ist auch die richtige Antwort auf eine häufige Nutzeranfrage: "Welche Artikel von Mason habe ich zu Josephus?" – eine Frage, die weder Vektorsuche noch Volltext-BM25 zuverlässig beantworten kann.

**Implementierungsstand:** `list_books_by_author_tool()` in `src/calibre_mcp/server.py`. Direkter SQL-Zugriff auf `metadata.db` via `src/calibre_db.py`.

### ADR-021: Erweiterte Batch-Indexierungsoptionen (März 2026)

**Kontext:** Im Betrieb mit einer voll entwickelten Bibliothek von 8.000+ Titeln entstehen Szenarien, die über einfaches Tag-basiertes Batch-Indexieren hinausgehen: selektive Re-Indexierung einzelner Bücher via ID, Qualitätsfilterung nach Calibre-Rating, Autoren-Kreuzfilter innerhalb von Tag-Auswahlen, nicht-interaktiver Betrieb in gescripteten Workflows.

**Entscheidungen:**

- `--all`: Alle Bücher der Bibliothek indexieren (ohne Tag-Voraussetzung). Für den initialen Vollaufbau oder System-Migrationen.
- `--ids 1234,5678`: Einzelne Bücher via Calibre-ID. Für gezielte Re-Indexierung nach Metadaten-Korrekturen oder Format-Wechseln.
- `--filter-author NAME`: Sekundärfilter innerhalb einer `--tag`- oder `--all`-Auswahl. Erlaubt z.B. "alle Bücher der Leit-Literatur von Arendt oder Benjamin" ohne eine eigene Tag-Hierarchie.
- `--min-rating N` / `--rating N`: Qualitätsfilter über Calibre-Sternebewertungen. Für selektives Indexieren des als besonders relevant bewerteten Bestands.
- `--exclude-tag TAG` (wiederholbar): Gezielte Ausnahmen innerhalb einer Selektion. Die Default-Ausschlussliste (`exclude`, `Übersetzung`) ist hartcodiert; `--exclude-tag` ergänzt sie für den einzelnen Lauf.
- `--include-excluded`: Hebt den Default-Ausschluss auf. Für Fälle, in denen Übersetzungen oder andersweitig markierte Bücher dennoch indexiert werden sollen.
- `--non-interactive`: Unterdrückt Bestätigungsabfragen. Für Cronjobs, automatisierte Workflows und Remote-Ausführung.
- `--reindex-missing-labels`: Selektive Re-Indexierung von Büchern, bei denen die Page-Label-Extraktion in einem früheren Lauf fehlschlug (z.B. weil der Extractor-Code verbessert wurde). Vermeidet teures Vollständig-Re-Indexieren.

**Begründung:** Diese Flags sind keine Feature-Creep, sondern die logische Vervollständigung eines ernst gemeinten Batch-Systems. Jeder fortgeschrittene Nutzer mit einer großen Bibliothek braucht mindestens einen davon. Die Alternative – jedes Szenario manuell über Tag-Hierarchien abzubilden – verlegt die Komplexität in Calibre, wo sie nicht hingehört.

### ADR-022: Apple Silicon MPS Support (März 2026)

**Kontext:** BGE-M3 Embedding-Inferenz und der optionale Cross-Encoder Reranker profitieren erheblich von GPU-Beschleunigung. Während CUDA für Windows/Linux-Nutzer der Standardfall ist, haben macOS-Nutzer (Apple Silicon: M1–M4) keinen CUDA-Zugriff, aber Metal Performance Shaders (MPS) als GPU-Backend.

**Entscheidung:** Automatische MPS-Erkennung in der Hardware-Detection-Schicht (`src/archilles/hardware.py`). Fallback-Kette: CUDA → MPS → CPU. Alle drei Profile (minimal/balanced/maximal) funktionieren auf MPS.

**Begründung:** Apple Silicon Macs sind ein relevantes Segment der geisteswissenschaftlichen Nutzerbasis – Forschende an europäischen Universitäten arbeiten häufig mit MacBook Pro. MPS-Support ist keine große Implementierungsarbeit (PyTorch unterstützt MPS seit 1.12), aber ohne explizite Erkennung fällt das System auf CPU zurück und hinterlässt erhebliches Performance-Potenzial ungenutzt. Die Entscheidung, MPS als vollwertiges unterstütztes Backend zu dokumentieren und zu testen, ist eine Aussage über den Anspruch: ARCHILLES ist kein Windows-only-Tool.

### ADR-023: Stop-Word-Removal für mehrere Sprachen (März 2026)

**Kontext:** BM25 (Keyword-Suche) behandelt ohne Stop-Word-Filterung häufige Funktionswörter ("der", "die", "das", "the", "in", "de", "et") als relevante Terme und verschlechtert das Ranking. Für eine mehrsprachige Bibliothek mit Texten in Deutsch, Englisch, Latein, Altgriechisch und weiteren Sprachen ist eine rein englische Stop-Word-Liste unzureichend.

**Entscheidung:** Multi-Language Stop-Word-Removal, angewendet bei der Indexierung (BM25-FTS-Aufbau) und bei der Query-Verarbeitung. Unterstützte Sprachen: EN, DE, FR, ES, IT, PT, NL, LA, RU, EL, HE, AR. Implementierung auf Basis von Lingua-erkannten Sprach-Codes pro Chunk.

**Begründung:** Für eine historisch-geisteswissenschaftliche Bibliothek sind lateinische und griechische Funktionswörter ("in", "et", "de", "τῆς", "τοῦ") besonders problematisch: Sie erscheinen in fast jedem Chunk, erzeugen aber keine Relevanz-Information. Eine sprach-agnostische Stop-Word-Liste würde semantisch bedeutsame Terme in anderen Sprachen als Stop-Words misklassifizieren. Die pro-Chunk-Spracherkennung über Lingua ermöglicht sprachgerechtes Filtering ohne globalen Kompromiss.

### ADR-024: Progress.db – Crash-sicheres Checkpoint-System für Batch-Indexierung (März 2026)

**Kontext:** Lange Batch-Indexierungsläufe (50–500 Bücher, mehrere Stunden) können durch Systemabsturz, Stromausfall, Speichermangel oder manuelle Unterbrechung abgebrochen werden. Das `IndexingCheckpoint`-System in `src/archilles/indexer/checkpoint.py` verfolgt den Fortschritt auf Book-Level. Für noch feinkörnigere Crash-Sicherheit und zuverlässiges Resume wurde ein separates SQLite-Tracking eingeführt.

**Entscheidung:** `progress.db` (SQLite) im `.archilles`-Ordner der Bibliothek als sekundäres Fortschritts-Log. Speichert pro Buch: Calibre-ID, Indexierungsstatus (pending/processing/done/failed), Timestamp, Chunk-Anzahl, ggf. Fehler-Trace. `--skip-existing` nutzt dieses Log für schnelles Pre-Filtering, ohne alle Bücher gegen die LanceDB abgleichen zu müssen.

**Begründung:** LanceDB-Abfragen für jeden einzelnen Titel beim Startup wären bei 8.000+ Büchern inakzeptabel langsam. Eine SQLite-Tabelle mit dem Indexierungsstatus ist eine O(1)-Abfrage statt O(n)-Scan der Vektordatenbank. Das Checkpoint-System schützt außerdem gegen einen selten aber real auftretenden Datenverlust: Wird der LanceDB-Schreibvorgang mitten in einem Buch unterbrochen, kann der Eintrag inkonsistent sein. Progress.db ermöglicht das Erkennen und Bereinigen solcher Halbzustände.

**Ergänzung: Backup-Rotation.** Parallel zu Progress.db wurde automatische Backup-Rotation implementiert: alle 50 Bücher wird ein LanceDB-Snapshot angelegt, 2 Backups werden aufbewahrt. Das begrenzt den maximalen Datenverlust bei Korruption auf 50 Bücher, ohne Disk-Space durch unbegrenzte Backup-Akkumulation zu verbrauchen.

---

## III. Produktstrategie und Geschäftsmodell

### Zielgruppe: Individuelle Forscher, keine Institutionen

**Entscheidung:** ARCHILLES adressiert primär einzelne Wissenschaftler mit persönlichen Calibre-Bibliotheken, nicht institutionelle Kunden.

**Begründung:** Die Primary Targets sind technisch versierte Akademiker aus den Geisteswissenschaften – Geschichte, Literatur, Philosophie –, die große, kuratierte Bibliotheken pflegen und Wert auf Privacy und lokale Datenkontrolle legen. Institutionelle Kunden (Universitätsbibliotheken, Forschungsinstitute) erfordern Compliance-Prozesse, Ausschreibungen und Support-Strukturen, die für ein Solo-Projekt in der Aufbauphase nicht leistbar sind. Die Tür wird offengehalten (Scoped Knowledge Bases als Feature-Option, institutionelle Lizenzen in der Roadmap), aber der Fokus bleibt auf dem individuellen Nutzer.

### Freemium mit Special Editions

**Entscheidung:** Freemium-Modell mit großzügigem Free Tier und kostenpflichtigen disziplinspezifischen Erweiterungen.

**Begründung:** Die Marktanalyse zeigt, dass DEVONthink (499 €) und Polar (299 $) als Einmalkauf-Modelle erfolgreich bei Wissenschaftlern sind. Abo-Müdigkeit ist in der Zielgruppe verbreitet. Das Free Tier bietet die komplette Basisfunktionalität ohne Bibliotheksbeschränkung, um eine Nutzerbasis aufzubauen. Die Premium-Erweiterungen sind inhaltlich differenziert:

Die **Historical Edition** als erste geplante Special Edition bringt LightRAG für Graph-basiertes Retrieval, Zeitreferenz-Extraktion, chronologische Visualisierung und spezialisierte Embeddings für historische Texte. Weitere geplante Editions sind Literary, Legal und Musical, jeweils mit disziplinspezifischen Optimierungen. Die modulare Pipeline-Architektur (ADR-004) ist die technische Voraussetzung für diese Trennung.

### ARCHILLATOR als Lead-Magnet

**Kontext (Januar 2026):** Parallel zu ARCHILLES entstand ARCHILLATOR, ein akademisches Übersetzungstool, das Bücher absatzweise über verschiedene LLM-Provider (Gemini, OpenAI, Claude) übersetzt und dabei EPUB-Formatierung erhält.

**Entscheidung:** ARCHILLATOR wird als eigenständiges, kostenloses Tool veröffentlicht, bevor ARCHILLES selbst bereit für den Community-Release ist.

**Begründung:** Das Tool löst ein konkretes, weit verbreitetes Problem (Bücher in Fremdsprachen schnell lesbar machen) und demonstriert die technische Kompetenz hinter dem ARCHILLES-Projekt. Es dient als Lead-Magnet für die Community-Phase: Nutzer, die den ARCHILLATOR schätzen, werden auf ARCHILLES aufmerksam. Das Tool unterstützt Checkpoint-basiertes Resume (Übersetzung kann unterbrochen und fortgesetzt werden, auch mit Provider-Wechsel), was die Robustheit für lange Dokumente sicherstellt.

**Abgrenzung:** ARCHILLATOR ist kein ARCHILLES-Feature, sondern ein separates Tool. Es nutzt keine RAG-Infrastruktur und teilt keinen Code mit ARCHILLES. Die Verbindung ist rein strategisch.

### Privacy als politisch neutrale Positionierung: Datensouveränität

**Entscheidung:** "Datensouveränität" als zentraler Wert, nicht als technisches Feature.

**Begründung:** Die Analyse der politischen Dimension ergab, dass Datenschutz als Wert überparteilich anschlussfähig ist: Linke sehen Überwachungskritik, Konservative Misstrauen gegenüber Tech-Monopolen, Liberale individuelle Autonomie. Die Positionierung als "Privacy by Design" (nicht durch nachträgliche Compliance) spricht die gesamte Zielgruppe an. ARCHILLES verarbeitet keine Nutzerdaten, betreibt keine Telemetrie und kommuniziert nicht mit externen Servern, sofern der Nutzer dies nicht explizit wählt. Der Nutzer ist sein eigener Datenverarbeiter – das vereinfacht die DSGVO-Compliance auf das Triviale.

### MCP-Native als strategische Wette

**Entscheidung:** Vollständige Implementierung als MCP-Server (Model Context Protocol) statt als standalone Anwendung mit eigener GUI.

**Begründung:** MCP wurde im November 2025 als der wichtigste Differenzierungsvorteil für 2025/26 identifiziert. Das Protokoll löst elegant das Kerndilemma der Zielgruppe: Sie wollen die besten Cloud-Modelle (Claude, GPT-4o) nutzen, aber ihre sensiblen Daten nicht hochladen. Ein lokaler MCP-Server exponiert die Bibliothek dynamisch für kompatible KI-Agenten, ohne dass ein Byte den Rechner verlässt. Ressourcen werden mit URIs referenziert, die automatisch in akademische Zitationsformate (BibTeX, APA, Chicago) umgewandelt werden können.

Das Risiko: MCP ist ein junger Standard, und seine Durchsetzung hängt von Anthropics und OpenAIs fortgesetzter Unterstützung ab. Die Wette ist, dass MCP zum Industriestandard für LLM-Tool-Integration wird – eine Wette, die durch die rasche Adoption (OpenAI im März 2025, wachsendes Ökosystem mit 80+ offiziellen Servern) gestützt wird.

**Ergänzende Interfaces:** Neben dem MCP-Server existieren ein Web-UI (Streamlit, für Nutzer ohne Claude Desktop) und ein CLI (für Batch-Operationen und Debugging). Beide sind bewusst als Companion-Tools positioniert, nicht als primäre Interfaces. Seit der Service-Layer-Refaktorierung (ADR-009) nutzen alle drei Clients denselben Code-Pfad.

---

## IV. Bewusst aufgeschobene Entscheidungen

### MCPB Desktop Extension: Erst nach stabilem MVP

**Kontext (Dezember 2025):** Anthropics neues Desktop Extension Format (.mcpb) verspricht Ein-Klick-Installation für Claude Desktop. Für ARCHILLES wäre das ein potenzieller Game-Changer, weil es die Einstiegshürde für nicht-technische Nutzer drastisch senken würde.

**Technische Analyse:** ARCHILLES' Python-Stack mit kompilierten Abhängigkeiten (LanceDB, PyTorch/Sentence-Transformers) lässt sich nicht portabel in ein .mcpb bündeln. Die realistische Lösung wäre ein Thin-Client-Ansatz: ein leichtgewichtiger Node.js MCP-Server als .mcpb, der mit einem separat installierten Python-Backend kommuniziert.

**Entscheidung:** Aufschub bis nach MVP-Fertigstellung und Beta-Test.

**Begründung:** Die Zielgruppe der Beta-Phase (technisch versierte Akademiker, Calibre-Power-User) kann manuelle JSON-Konfiguration handhaben. Eine vorzeitige Architekturspaltung in Node.js-Frontend und Python-Backend würde die Feature-Entwicklung bremsen, weil jede Änderung in zwei Codebases synchronisiert werden müsste. Die Einstiegshürde senken wir erst, wenn es etwas Stabiles gibt, in das man einsteigen kann.

### LightRAG / Graph RAG: Evaluation vor Implementation

**Kontext (Dezember 2025):** Für die Historical Special Edition wurde zunächst Neo4j als Graph-Datenbank erwogen, dann LightRAG als leichtere Alternative identifiziert.

**Entscheidung:** LightRAG wird als Graph-RAG-Ansatz vorgesehen, aber erst nach systematischer Evaluation (geplant Q2 2026) implementiert.

**Begründung:** LightRAG bietet Dual-Level Retrieval (Low-Level für Details, High-Level für Konzepte) und inkrementelle Updates ohne komplettes Graph-Rebuilding. Allerdings erfordert die Graph-Extraktion LLM-Aufrufe während der Indexierung, was API-Kosten verursacht. Vor der Implementation muss ein Testkorpus definiert und Metriken für den Vergleich mit reinem Vektor-RAG festgelegt werden. Bestehende Wissensgraphen (Wikidata, Wikipedia) könnten als Seed-Quellen dienen, statt vom Nutzer manuelle Entitätspflege zu verlangen.

### Uncertainty Quantification: Forschungsziel, keine aktive Planung

**Kontext:** Die Fähigkeit, widersprüchliche Aussagen in verschiedenen Quellen zu erkennen und transparent zu machen, passt ideal zur Projektphilosophie einer "eigenen, in Teilen unkonventionellen Geschichtsinterpretation", bei der das Nebeneinander verschiedener Deutungen produktiv sein soll.

**Entscheidung:** Als langfristiges Forschungsziel (2027+) dokumentiert.

**Begründung:** Technisch ambitioniert (erfordert Natural Language Inference, Entitätsabgleich über Quellen hinweg), möglicherweise als Kooperation mit akademischen Partnern (NFDI-Konsortien) realisierbar. Für den MVP und die erste Produktversion irrelevant.

### Kollaboration: Minimal, aber vorbereitet

**Kontext (Januar 2026):** Die Analyse kollaborativer Workflows in den Geisteswissenschaften ergab, dass sich Humanities-Kooperation fundamental von STEM unterscheidet: Einzelautorschaft dominiert, aber Betreuer-Studierende-Beziehungen und geteilte Literatursammlungen sind zentrale Kollaborationsmuster.

**Entscheidung:** Keine Echtzeit-Kollaborationsfeatures. Stattdessen minimale, aber nützliche Export- und Austauschfunktionen.

**Begründung:** Geisteswissenschaftliche Teams teilen Referenzen, Annotationen und kuratierte Sammlungen – sie brauchen keine Google-Docs-artige Echtzeitbearbeitung. Exportierbare Annotationssets und thematische Sammlungen als geteilte Bibliographien decken den realen Bedarf ab, ohne die Architektur zu verkomplizieren.

### Chunking-Intelligenz: Small-to-Big und Parent-Child

**Kontext (November 2025 – Februar 2026):** Die parallel über Gemini, Grok und ChatGPT durchgeführte Chunking-Intelligence-Analyse identifizierte hierarchisches Chunking als den größten einzelnen Qualitätshebel für RAG-Systeme. Die aktuelle Konfiguration (RecursiveCharacterTextSplitter mit 1000 Token / 200 Overlap) liefert solide Ergebnisse, verschenkt aber Potenzial bei langen argumentativen Passagen.

**Entscheidung:** Small-to-Big Retrieval und Parent-Child-Hierarchien werden implementiert, Semantic-Hybrid-Chunking mit dynamischen Thresholds wird evaluiert.

**Begründung:** Die Grundidee: Indexiere kleine Chunks (Absatzebene) für hohe Retrieval-Präzision, aber liefere dem LLM den größeren Kontext (Kapitel oder erweiterte Passage). Das löst das Kernproblem, das Geisteswissenschaftler an RAG-Systemen frustriert: Sätze, die mitten im Argument abreißen. Die Chunking-Intelligence-Analyse ergab, dass selbst einfaches Recursive Hierarchical Chunking bereits 80% des Qualitätsgewinns gegenüber flachem Chunking bringt, während Semantic-Hybrid-Varianten mit Agglomerative Clustering weitere 20-30% liefern, aber signifikant mehr Implementierungsaufwand erfordern. Die Reihenfolge ist daher: erst Parent-Child über bestehende Recursive-Struktur, dann optional Semantic-Hybrid als Upgrade-Pfad.

---

## V. Branding und Kommunikation

### Rebranding: Achilles → ARCHILLES

**Zeitpunkt:** November 2025

**Begründung:** Der Name "ARCHILLES" verbindet die Archiv-Assoziation ("ARCH") mit dem mythologischen Helden. Subtile Schichten: "ARCH" referenziert sowohl "archive" als auch "research" aus dem Tagline; "ILLES" erscheint rückwärts gelesen in "intELLIgent"; "A" und "I" zusammen ergeben "AI". Der Tagline "Your Intelligent Research Archive" liefert alle Bestandteile. Domains archilles.de, archilles.net und archilles.org wurden gesichert.

### Tone of Voice: Intellektuell, aber nicht elitär

Das Kommunikationsprinzip "While others build snake games, we enable serious scholarship" positioniert ARCHILLES als Werkzeug für ernsthafte Wissensarbeit, ohne Gatekeeping zu betreiben. Die Formulierung respektiert sowohl die KI-Technologie als auch die akademische Arbeit der Nutzer. Der Kern-Claim lautet: "Other AI tools question books. ARCHILLES questions your library."

### Vendor-Neutralität in der Kommunikation

In der externen Kommunikation wird von "frontier models" gesprochen, nicht ausschließlich von "Claude" – obwohl die MCP-Integration aktuell primär auf Claude Desktop zielt. Das verhindert Vendor-Lock-in in der Wahrnehmung und hält die Tür offen für andere MCP-kompatible Clients.

---

## VI. Rechtliche Rahmenbedingungen

### EU AI Act: Wahrscheinlich nicht anwendbar

**Analyse (November 2025):** ARCHILLES ist ein lokales Tool für persönlichen Gebrauch. Es klassifiziert keine Personen, trifft keine automatisierten Entscheidungen und verarbeitet keine biometrischen Daten. Die Risikoklassifizierung des EU AI Act trifft auf ein lokales Retrieval-Tool nicht zu. Monitoring bleibt dennoch sinnvoll, weil Regulierung sich weiterentwickelt.

### Urheberrecht und Text & Data Mining

§ 60d UrhG (Deutschland) und die DSM-Richtlinie (EU) erlauben Text & Data Mining für Forschungszwecke. ARCHILLES ist ein Tool, kein Content-Provider – vergleichbar mit Calibre selbst oder VLC Media Player. Die Verantwortung für die Rechtmäßigkeit der indexierten Bibliothek liegt beim Nutzer. DRM-geschützte E-Books sind explizit Nutzerverantwortung.

### Lizenzierung: MIT, mit Optionen

Die Basisversion wird unter MIT-Lizenz veröffentlicht (maximal permissiv für Adoption). Spätere Versionen oder Special Editions können restriktivere Lizenzen nutzen, falls nötig. Dual Licensing (Open Source + Commercial) bleibt als Option für die Editions-Strategie vorbehalten.

---

## VII. Zusammenfassung: Leitprinzipien

Die Entscheidungen folgen konsistent einigen Grundprinzipien, die das Projekt prägen:

**Privacy ist kein Feature, sondern die Architektur.** Daten bleiben lokal, Datensouveränität ist das Fundament, nicht ein Checkbox-Item.

**Modulare Erweiterbarkeit vor Featurefülle.** Die auf ein Registry-Pattern hin angelegte Architektur, die Plugin-fähigen Schnittstellen und die definierten Erweiterungszonen (`.archilles`-Ordner) sind wichtiger als jedes einzelne Feature.

**Akademischer Anspruch als Differenzierung.** Exakte Zitationen, transparentes Retrieval und disziplinspezifische Optimierungen unterscheiden ARCHILLES von generischen RAG-Lösungen – nicht die Menge der Features.

**Aufschub als bewusste Strategie.** MCPB, LightRAG, Uncertainty Quantification und institutionelle Features werden nicht vergessen, sondern zum richtigen Zeitpunkt implementiert. Ein funktionierendes MVP hat Vorrang vor einer vorzeitig aufgeblähten Architektur.

**Weniger Code, mehr Architektur.** Wo eine architektonische Lösung (wie Section-Filtering auf DB-Ebene) bessere Ergebnisse liefert als eine code-intensive Heuristik, wird die Architektur gewählt – selbst wenn das einen größeren initialen Umbau bedeutet.

---

*Nächste geplante Aktualisierungen:*
- *ADR-025: HTTP/SSE-Transport für MCP-Server (LLM-Agnostizismus; geplant v1.0)*
- *ADR-026: Inkrementelle Indexierung mit Index-Queue (geplant v1.0)*
- *ADR-027: Markdown-Output via Docling als Extraktionsziel (nach Beta-Feedback)*
- *ADR-028: VLM-basiertes OCR (LightOnOCR-2 / olmOCR-2; geplant v1.2)*
- *Ergebnis der LightRAG-Evaluation (geplant Q2 2026)*
- *Entscheidung über MCPB-Implementation (nach Beta-Feedback)*
- *ADR für Übersetzungs-Pipeline (NLLB lokal / MADLAD-400 API)*
- *ADR für Cross-Encoder-Reranking (nach Benchmark gegen aktuelle Hybrid-Search)*
- *Aktualisierung der Wettbewerbsanalyse (Calibre 8.x Weiterentwicklung, MCP-Ökosystem)*
- *CLI-Erfahrung verbessern: Die lokale Kommandozeilen-Abfrage (rag_demo.py) liefert unbefriedigende Ergebnisse im Vergleich zur MCP-Integration, wo Claude den Kontext intelligent interpretiert. Mögliche Ansätze: bessere Prompt-Templates, automatische Query-Expansion, oder ein lokales LLM als Interpretation-Layer.*
- *Schema-Migrations-Framework: Der aktuelle add_columns()-Mechanismus funktioniert, ist aber ad-hoc. Bei wachsender Feldanzahl lohnt sich ein formales Migrations-System mit Versionsnummern.*
- *Citation-Modul in Service-Layer und MCP-Server integrieren: CitationConfig aus config.json laden und format_bibliography_instruction() in den System-Prompt einspeisen.*
- *citeproc-py als optionale Dependency: formatter.py für Offline-Rendering und Zotero-Export, wenn citeproc-py installiert ist.*
