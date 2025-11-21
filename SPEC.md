# Pflichtenheft: Achilles RAG-System für wissenschaftliche Textsammlungen

**Version:** 1.0
**Datum:** 22. November 2025
**Auftraggeber:** Tom (Geschichtswissenschaft, Philosophie, Theologie)
**Auftragnehmer:** Claude Code
**Projektname:** Achilles
**Ziel:** Lokales, GDPR-konformes RAG-System für Geisteswissenschaftler

---

## EXECUTIVE SUMMARY

**Vision:** Das DevonThink für das KI-Zeitalter – plattformübergreifend, GDPR-by-design, 100% offline

**Alleinstellungsmerkmale:**
1. Perfekte Calibre-Integration mit Annotations-Sync
2. Exakte Zitatpflicht (jeder Satz → klickbare PDF-Stelle)
3. Geisteswissenschaften-Optimierung (Hierarchical Retrieval, Timeline-View)
4. MCP-Server für Claude Desktop / andere Clients
5. 100% lokal, keine Cloud-Abhängigkeit

**Zielgruppe:** Deutsche/europäische Geisteswissenschaftler, besonders:
- Geschichtswissenschaft
- Philosophie
- Theologie
- Altphilologie
- Mythenforschung

**Monetarisierung:** 299 € Einmalkauf + optional 99 €/Jahr Updates

**Zeitrahmen:** 4-6 Wochen zum verkaufsfähigen MVP

---

## PHASE 1: FOUNDATION MVP (WOCHEN 1-2)
### Priorität: 🔴 KRITISCH – Ohne das läuft nichts

### 1.1 EMBEDDING-UPGRADE ⚡ **HÖCHSTE PRIORITÄT**

**Ziel:** Von all-mpnet-base-v2 auf BGE-M3 upgraden für bessere deutsche Texte

**Anforderungen:**
- BGE-M3 (1024-dim, multilingual) installieren und testen
- Alle 10.151 bestehenden Annotations re-indexieren
- A/B-Test: Retrieval-Qualität alt vs. neu dokumentieren
- Performance-Messung: Indexing-Zeit, Query-Zeit, RAM-Nutzung

**Technische Spezifikation:**
```python
# Requirements
sentence-transformers==2.3.1
BAAI/bge-m3

# Erwartete Verbesserungen
- Deutsch-Englisch-Mischtext: +25-40% Recall
- Fachbegriffe (theologisch/philosophisch): +30% Precision
- Latein/Griechisch (wenn vorhanden): +15-20% Recall

# Performance-Ziele
- Indexing: <2 Stunden für 10.151 Annotations
- Query-Zeit: <1 Sekunde (wie bisher)
- RAM: <8 GB für komplette Vektordatenbank
```

**Deliverables:**
- [ ] `scripts/upgrade_to_bge_m3.py` – Re-Indexing-Skript
- [ ] `scripts/compare_embeddings.py` – A/B-Test-Report
- [ ] `EMBEDDING_UPGRADE_REPORT.md` – Dokumentation mit Metriken

**Akzeptanzkriterien:**
- ✅ BGE-M3 läuft stabil auf Toms Hardware
- ✅ Alle 10.151 Annotations erfolgreich re-indexiert
- ✅ Mindestens 20% Verbesserung bei deutschen Queries (3-5 Test-Queries)
- ✅ Keine Performance-Verschlechterung (<1s Response-Zeit)

**Zeitschätzung:** 2-3 Tage
**Abhängigkeiten:** Keine

---

### 1.2 PDF-TEXT-EXTRAKTION MIT METADATEN

**Ziel:** Robuste PDF-Verarbeitung mit exakten Quellenangaben

**Anforderungen:**
- Text-Extraktion aus PDFs (nicht nur aus bestehenden Annotations)
- Seitenzahlen, Kapitel-Informationen erfassen
- Fallback-Chain: pdfplumber → pymupdf → OCR (Tesseract)
- Metadaten pro Chunk: book_id, title, author, page, char_start, char_end

**Technische Spezifikation:**
```python
# Stack
pdfplumber==0.11.0
pymupdf==1.23.8
pytesseract==0.3.10  # für OCR-Fallback

# Chunk-Strategie
chunk_size = 512 tokens
overlap = 128 tokens
strategy = "semantic" (respektiere Absatzgrenzen)

# Metadaten-Schema
{
    "text": str,
    "book_id": int,
    "title": str,
    "author": str,
    "year": int,
    "page": int,  # exakte Seitenzahl
    "page_label": str,  # z.B. "xiv" für röm. Ziffern
    "char_start": int,
    "char_end": int,
    "chapter": str,  # wenn aus TOC extrahierbar
    "source_file": str  # Pfad zum PDF
}
```

**Spezielle Anforderungen für Geisteswissenschaften:**
- Fußnoten separat markieren (nicht im Haupt-Text-Chunk)
- Römische Seitenzahlen (Vorwort) korrekt erfassen
- Mehrspaltige Layouts (kritische Editionen) erkennen
- Griechische/lateinische Passagen nicht beschädigen

**Deliverables:**
- [ ] `src/pdf_extractor.py` – PDF-Verarbeitungs-Pipeline
- [ ] `src/metadata_schema.py` – Metadaten-Definitionen
- [ ] `tests/test_pdf_extraction.py` – Unit-Tests
- [ ] `docs/PDF_EXTRACTION.md` – Dokumentation

**Akzeptanzkriterien:**
- ✅ 5 Test-PDFs aus Toms Bibliothek erfolgreich verarbeitet
- ✅ Seitenzahlen zu 95%+ korrekt extrahiert
- ✅ Fußnoten separat erfasst
- ✅ Keine Textverfälschungen bei Sonderzeichen (griechisch/lateinisch)
- ✅ Fallback auf OCR bei gescannten PDFs funktioniert

**Zeitschätzung:** 3-5 Tage
**Abhängigkeiten:** Keine

---

### 1.3 CHROMADB-SETUP MIT ERWEITERTEN METADATEN

**Ziel:** Vektordatenbank mit allen Metadaten für spätere Filter-Funktionen

**Anforderungen:**
- ChromaDB mit BGE-M3 Embeddings
- Alle Metadaten aus 1.2 speichern
- Filter-fähig nach: author, year, book_id, page_range
- Persistent Storage (SQLite-Backend)

**Technische Spezifikation:**
```python
# Stack
chromadb==0.4.22

# Collection-Setup
collection = client.create_collection(
    name="achilles_main",
    metadata={
        "hnsw:space": "cosine",
        "embedding_model": "BAAI/bge-m3"
    }
)

# Indexing-Performance-Ziele
- 10.151 Annotations: <2 Stunden
- 2.408 Bücher (wenn voll-indexiert): <48 Stunden
- Inkrementelles Update: <5 Minuten für 1 Buch

# Speicherplatz
- Erwartete DB-Größe: 500 MB - 2 GB
- Backup-fähig (simple Datei-Kopie)
```

**Deliverables:**
- [ ] `src/vector_store.py` – ChromaDB Wrapper
- [ ] `scripts/init_chromadb.py` – Initiales Setup
- [ ] `scripts/index_calibre_library.py` – Bulk-Indexing
- [ ] `tests/test_vector_store.py` – Tests

**Akzeptanzkriterien:**
- ✅ ChromaDB läuft stabil mit BGE-M3
- ✅ 10.151 Annotations erfolgreich indexiert
- ✅ Metadata-Filter funktionieren (test: "author='Josephus'")
- ✅ Query-Performance <1s
- ✅ Persistent Storage funktioniert (Neustart möglich)

**Zeitschätzung:** 2-3 Tage
**Abhängigkeiten:** 1.1 (BGE-M3 muss fertig sein)

---

### 1.4 OLLAMA-INTEGRATION (LOKALES LLM)

**Ziel:** Lokale LLM-Antworten auf RAG-Queries

**Anforderungen:**
- Ollama installiert und läuft
- Llama-3.1-8B als primäres Modell
- Mistral-7B als Alternative (schneller)
- Einfache Query → Context → LLM → Answer Pipeline

**Technische Spezifikation:**
```python
# Stack
ollama==0.1.22
ollama-python==0.1.5

# Modelle
primary: llama3.1:8b
fallback: mistral:7b-instruct

# Prompt-Template (wissenschaftlicher Fokus)
"""
Du bist ein wissenschaftlicher Forschungsassistent für Geisteswissenschaften.
Beantworte die Frage NUR basierend auf dem bereitgestellten Kontext.

STRIKTE REGELN:
1. Nutze KEIN externes Wissen – nur den Kontext
2. Zitiere IMMER mit [Quelle X, S. Y]
3. Wenn die Antwort nicht im Kontext ist: "Keine Information hierzu gefunden"
4. Ton: neutral, formal, wissenschaftlich

KONTEXT:
{retrieved_chunks}

FRAGE:
{user_query}

ANTWORT:
"""

# Performance-Ziele
- Response-Zeit: <10s für 8B-Modell
- RAM: <16 GB
- Tokens: 512-1024 Output, 4096 Input (Context)
```

**Deliverables:**
- [ ] `src/llm_interface.py` – Ollama-Wrapper
- [ ] `src/rag_pipeline.py` – Query → Retrieval → LLM → Response
- [ ] `prompts/scientific_rag.txt` – System-Prompt
- [ ] `tests/test_llm_integration.py` – Tests

**Akzeptanzkriterien:**
- ✅ Ollama läuft auf Toms System
- ✅ Llama-3.1-8B antwortet auf Test-Queries
- ✅ Citations im Format [Quelle, S. X] funktionieren
- ✅ Keine Halluzinationen bei 5 Test-Queries (manuell prüfen)
- ✅ Response-Zeit <10s

**Zeitschätzung:** 2-3 Tage
**Abhängigkeiten:** 1.3 (ChromaDB muss Daten liefern können)

---

### 1.5 ENDE-ZU-ENDE-TEST (MVP FUNKTIONSFÄHIG)

**Ziel:** Kompletter RAG-Workflow funktioniert

**Test-Szenario:**
```
USER: "Was sagt Josephus über die jüdischen Könige?"

SYSTEM:
1. Query → BGE-M3 Embedding
2. ChromaDB Semantic Search → Top 5 Chunks
3. Chunks + Query → Ollama (Llama-3.1-8B)
4. Output:
   "Josephus beschreibt die jüdischen Könige als... [Josephus,
   Antiquitates, S. 142]. Er betont besonders... [ebd., S. 156]."
```

**Akzeptanzkriterien für Phase 1 Abschluss:**
- ✅ 10 Test-Queries laufen komplett durch
- ✅ Alle Antworten enthalten Citations
- ✅ Keine technischen Fehler (Crashes, Timeouts)
- ✅ Performance: Query → Answer in <15s
- ✅ Tom kann das System selbst nutzen (CLI)

**Deliverables:**
- [ ] `demo_queries.md` – 10 Test-Queries mit erwarteten Outputs
- [ ] `PHASE1_COMPLETION_REPORT.md` – Abschlussbericht

**Zeitschätzung:** 1 Tag (Integration + Testing)
**Abhängigkeiten:** 1.1-1.4 alle fertig

---

## PHASE 2: WISSENSCHAFTLICHE QUALITÄT (WOCHEN 3-4)
### Priorität: 🟡 HOCH – Macht es wissenschaftlich nutzbar

### 2.1 EXAKTE ZITATPFLICHT MIT KLICKBAREN LINKS ⭐⭐⭐

**Ziel:** Jede Antwort verlinkt auf exakte PDF-Stelle (wie NotebookLM)

**Anforderungen:**
- PDF-Koordinaten (page, x, y, width, height) für jeden Chunk speichern
- Calibre-URI-Schema nutzen: `calibre://view/<book_id>#page=<N>`
- Klickbarer Link in Ausgabe: `[Josephus, S. 142] (calibre://...)`
- Alternative: PDF öffnen an exakter Stelle via externe Tools

**Technische Spezifikation:**
```python
# Metadaten-Erweiterung
{
    # ... bestehende Metadaten ...
    "pdf_coords": {
        "page": int,
        "x": float,
        "y": float,
        "width": float,
        "height": float
    },
    "calibre_uri": str  # z.B. "calibre://view/123#page=42"
}

# Output-Format
citation_format = "[{author}, {title} ({year}), S. {page}]({calibre_uri})"
```

**Spezielle Herausforderungen:**
- PDF-Koordinaten aus pdfplumber extrahieren (nicht immer verfügbar)
- Calibre-Annotations haben bereits Koordinaten → diese nutzen!
- Fallback: Nur Seitenzahl wenn Koordinaten fehlen

**Deliverables:**
- [ ] `src/citation_builder.py` – Citation-Generator
- [ ] `src/pdf_coordinates.py` – Koordinaten-Extraktion
- [ ] Update `src/metadata_schema.py`
- [ ] `docs/CITATION_SYSTEM.md` – Dokumentation

**Akzeptanzkriterien:**
- ✅ 95% der Chunks haben Seitenzahl
- ✅ 70% der Chunks haben PDF-Koordinaten (besser: 90% für Calibre-Annotations)
- ✅ Calibre-Links funktionieren (öffnet PDF an richtiger Stelle)
- ✅ Citations im Format [Autor, Werk, S. X] in allen Outputs

**Zeitschätzung:** 3-4 Tage
**Abhängigkeiten:** 1.2 (PDF-Extraktion)

---

### 2.2 TRANSPARENTER RETRIEVAL-PROZESS

**Ziel:** Nutzer versteht WARUM diese Chunks ausgewählt wurden

**Anforderungen:**
- Relevance Score (0.0-1.0) für jeden Chunk anzeigen
- Alternative Passagen zeigen (Rank 6-10)
- Keyword-Highlighting im Chunk-Text
- "Warum wurde dieser Chunk gewählt?" Erklärung

**Technische Spezifikation:**
```python
# Erweiterte Response-Struktur
{
    "answer": str,  # LLM-Antwort
    "sources": [
        {
            "chunk_text": str,
            "metadata": dict,
            "relevance_score": float,
            "matched_keywords": List[str],
            "explanation": str  # z.B. "Enthält 'Josephus' und 'Könige'"
        }
    ],
    "alternative_chunks": [...]  # Rank 6-10
}
```

**UI-Konzept (für CLI erstmal):**
```
ANTWORT:
Josephus beschreibt die jüdischen Könige als... [Quelle 1, S. 142]

QUELLEN:
[1] Josephus, Antiquitates (Bd. 2), S. 142
    Relevanz: 0.87 (sehr hoch)
    Gefunden wegen: "jüdische Könige", "Herrschaft"
    [Link zum PDF]

ALTERNATIVE PASSAGEN:
[2] Josephus, Bellum Judaicum, S. 78 (Relevanz: 0.76)
...
```

**Deliverables:**
- [ ] `src/retrieval_explainer.py` – Erklärungs-Logik
- [ ] Update `src/rag_pipeline.py` – Erweiterte Response
- [ ] `templates/response_format.txt` – Output-Template

**Akzeptanzkriterien:**
- ✅ Alle Responses zeigen Relevance Scores
- ✅ Matched Keywords werden highlighted
- ✅ Alternative Passagen verfügbar (Rank 6-10)
- ✅ Explanations sind verständlich

**Zeitschätzung:** 2-3 Tage
**Abhängigkerien:** 1.4 (RAG-Pipeline muss funktionieren)

---

### 2.3 METADATEN-VOLLSTÄNDIGKEIT AUS CALIBRE

**Ziel:** Alle relevanten Calibre-Metadaten nutzen

**Anforderungen:**
- Author, Title, Year, ISBN, Tags aus Calibre-DB extrahieren
- Language-Detection (wichtig für multilinguale Sammlungen)
- Custom Columns (falls Tom welche nutzt)
- Series-Information (z.B. "Loeb Classical Library, Bd. 4")

**Technische Spezifikation:**
```python
# Calibre-DB-Schema (relevante Tabellen)
- books (id, title, sort, timestamp, ...)
- authors (id, name, sort, ...)
- books_authors_link
- publishers
- tags
- books_tags_link
- languages
- books_languages_link
- custom_columns

# Erweiterte Book-Metadaten
{
    "calibre_id": int,
    "title": str,
    "author": str,
    "co_authors": List[str],
    "year": int,
    "publisher": str,
    "isbn": str,
    "tags": List[str],
    "language": str,  # ISO code: "deu", "lat", "grc"
    "series": str,
    "series_index": float,
    "custom_fields": dict  # falls vorhanden
}
```

**Deliverables:**
- [ ] `src/calibre_metadata.py` – Metadaten-Extraktor
- [ ] Update `src/vector_store.py` – Erweiterte Metadaten speichern
- [ ] `tests/test_calibre_metadata.py`

**Akzeptanzkriterien:**
- ✅ Alle 2.408 Bücher haben vollständige Metadaten
- ✅ Tags werden korrekt extrahiert (z.B. "Leit-Literatur")
- ✅ Language-Detection funktioniert (wichtig für Filter)
- ✅ Filter-Queries möglich: "author='Josephus' AND year<100"

**Zeitschätzung:** 2 Tage
**Abhängigkeiten:** Calibre-DB-Zugriff (bereits vorhanden)

---

### 2.4 HIERARCHICAL RETRIEVAL (GEISTESWISSENSCHAFTEN-OPTIMIERUNG)

**Ziel:** Argumentative Bögen nicht zerstören (wie von Grok analysiert)

**Problem:** Standard-Chunking zerstört Kontext bei langen philosophischen/theologischen Texten

**Lösung: Parent-Document-Retrieval**
```
1. Grob-Retrieval: Kapitel-Ebene
2. Fein-Retrieval: Absatz-Ebene im relevanten Kapitel
3. Context-Erweiterung: ±2 Absätze für Kontext
```

**Technische Spezifikation:**
```python
# Zwei-Ebenen-Indexierung
parent_chunks = []  # Kapitel-Level (2000-4000 tokens)
child_chunks = []   # Absatz-Level (256-512 tokens)

# Retrieval-Strategie
1. Query → Parent-Embeddings → Top 3 Kapitel
2. Query → Child-Embeddings (nur in Top-3-Kapiteln) → Top 10 Absätze
3. Für jeden Absatz: Hole ±2 Nachbar-Absätze (Context-Window)
4. LLM bekommt: 10 Absätze + jeweils Kontext

# Vorteil für Geschichtswissenschaft
- Josephus-Zitat bleibt im Kontext der Argumentation
- Merowinger-Chroniken behalten narrative Struktur
```

**Deliverables:**
- [ ] `src/hierarchical_retrieval.py` – Parent-Child-Retriever
- [ ] Update `src/pdf_extractor.py` – TOC-Extraktion für Kapitel
- [ ] `docs/HIERARCHICAL_RETRIEVAL.md` – Konzept-Doku

**Akzeptanzkriterien:**
- ✅ TOC (Inhaltsverzeichnis) aus 5 Test-PDFs extrahiert
- ✅ Parent-Child-Indexierung funktioniert
- ✅ Context-Window (±2 Absätze) wird korrekt geholt
- ✅ Test-Query zeigt Verbesserung (manuell: besserer Kontext in Antwort)

**Zeitschätzung:** 3-4 Tage
**Abhängigkeiten:** 1.2 (PDF-Extraktion), 1.3 (ChromaDB)

---

### 2.5 PHASE 2 ABSCHLUSS-TEST

**Test-Szenarien:**
```
1. Query: "Vergleiche Josephus und Eusebius zur Frage der Judenkönige"
   → Erwartung: Antwort mit 4-6 Citations, alle klickbar, Kontext klar

2. Query: "Was sagt Blumenberg über den Mythos?"
   → Erwartung: Lange Textpassagen bleiben im argumentativen Kontext

3. Filter-Query: "Suche in lateinischen Quellen vor 500 n.Chr."
   → Erwartung: Nur relevante Bücher (language='lat', year<500)
```

**Akzeptanzkriterien Phase 2:**
- ✅ Alle Test-Queries erfolgreich
- ✅ Citations zu 95%+ klickbar und korrekt
- ✅ Retrieval-Transparenz: Tom versteht warum welche Quelle
- ✅ Hierarchical Retrieval zeigt besseren Kontext als vorher
- ✅ System ist "wissenschaftlich nutzbar" (Toms Urteil)

**Deliverables:**
- [ ] `PHASE2_COMPLETION_REPORT.md`

**Zeitschätzung:** 1 Tag (Integration + Testing)

---

## PHASE 3: PRODUKT-POLISH (WOCHEN 5-6)
### Priorität: 🟢 MITTEL – Macht es verkaufbar

### 3.1 SIMPLE GUI (GRADIO-PROTOTYP)

**Ziel:** Kein CLI mehr – normale Nutzer können es bedienen

**Anforderungen:**
- Webbasierte GUI mit Gradio (einfachster Weg)
- Suchfeld + Ergebnis-Anzeige
- Citations klickbar (öffnet PDF in Calibre)
- Settings: Modell-Wahl, Filter, Retrieval-Parameter

**Technische Spezifikation:**
```python
# Stack
gradio==4.10.0

# UI-Layout
- Tab 1: "Search" (Hauptfunktion)
  - Textfeld: Query
  - Button: "Search"
  - Output: Antwort + Quellen (Markdown)

- Tab 2: "Settings"
  - Dropdown: Embedding-Modell
  - Dropdown: LLM (llama3.1:8b, mistral:7b)
  - Slider: Top-K Results (5-20)
  - Checkboxen: Filter (Sprache, Jahr, Tags)

- Tab 3: "Stats"
  - Indexed Books: 2.408
  - Indexed Chunks: X
  - Query History (letzte 10)
```

**Deliverables:**
- [ ] `app.py` – Gradio-App
- [ ] `static/` – CSS für Branding (optional)
- [ ] `docs/USER_GUIDE.md` – Nutzer-Dokumentation

**Akzeptanzkriterien:**
- ✅ GUI läuft auf `localhost:7860`
- ✅ Alle Kern-Funktionen (Search, Settings) funktionieren
- ✅ Citations sind klickbar und öffnen Calibre
- ✅ Nicht-technischer Tester kann es bedienen

**Zeitschätzung:** 3-4 Tage
**Abhängigkeiten:** Phase 1+2 komplett

---

### 3.2 MCP-SERVER (BASIS-IMPLEMENTATION)

**Ziel:** Claude Desktop, AnythingLLM etc. können auf Achilles zugreifen

**Anforderungen:**
- MCP-Server exposiert Calibre-Bibliothek
- Tools: `search_books`, `get_context`, `get_annotations`
- Resources: Bücher als `file://` oder `calibre://` URIs

**Technische Spezifikation:**
```python
# Stack
mcp-python-sdk==0.2.1

# MCP-Server-Definition
@server.tool("search_books")
async def search_books(query: str, top_k: int = 10):
    """Semantische Suche in Calibre-Bibliothek"""
    return await rag_pipeline.search(query, top_k)

@server.tool("get_book_context")
async def get_book_context(book_id: int, page: int):
    """Hole spezifische Seite aus Buch"""
    return extract_page(book_id, page)

@server.resource("calibre://library")
async def get_library_info():
    """Übersicht über Bibliothek"""
    return {
        "total_books": 2408,
        "indexed_chunks": X,
        "languages": ["deu", "lat", "grc", "eng"]
    }
```

**Deliverables:**
- [ ] `mcp_server.py` – MCP-Server
- [ ] `config/mcp_config.json` – Claude Desktop Config
- [ ] `docs/MCP_INTEGRATION.md` – Setup-Anleitung

**Akzeptanzkriterien:**
- ✅ MCP-Server läuft auf `localhost:8000`
- ✅ Claude Desktop kann Tools sehen und aufrufen
- ✅ `search_books` funktioniert aus Claude Desktop
- ✅ Keine Daten werden hochgeladen (lokal bleibt lokal)

**Zeitschätzung:** 3-5 Tage
**Abhängigkeiten:** Phase 1+2, MCP-SDK-Kenntnisse

---

### 3.3 CALIBRE-ANNOTATIONS-SYNC (BIDIREKTIONAL)

**Ziel:** Markierungen in Achilles → automatisch in Calibre gespeichert

**Anforderungen:**
- Neue Highlights aus Achilles → Calibre `annotations` Tabelle
- Bidirektional: Neue Calibre-Highlights → Achilles re-indexiert
- Tags aus Achilles → Calibre-Tags synchronisiert

**Technische Spezifikation:**
```python
# Calibre Annotations Schema
INSERT INTO annotations (
    book, format, user_type, user, timestamp,
    annot_id, annot_type, annot_data
) VALUES (...)

# Sync-Strategie
- Achilles hält lokale Kopie der annotations
- Periodischer Check (alle 60s): Neue Calibre-Annotations?
- User markiert in Achilles → sofort in Calibre schreiben
```

**Deliverables:**
- [ ] `src/calibre_sync.py` – Sync-Engine
- [ ] Background-Task: Periodisches Polling
- [ ] `docs/CALIBRE_SYNC.md`

**Akzeptanzkriterien:**
- ✅ Neue Highlights in Achilles erscheinen in Calibre Viewer
- ✅ Neue Calibre-Highlights werden von Achilles erkannt (60s delay)
- ✅ Keine Duplikate, keine Datenverluste
- ✅ Sync läuft im Hintergrund ohne User-Intervention

**Zeitschätzung:** 4-5 Tage
**Abhängigkeiten:** Calibre-DB-Schema-Kenntnisse

---

### 3.4 PACKAGING & DISTRIBUTION

**Ziel:** One-Click-Installer für Windows/Mac/Linux

**Anforderungen:**
- PyInstaller oder Briefcase für Executable
- Ollama automatisch mitinstallieren (oder Installations-Check)
- Alle Dependencies gebündelt
- Installer-Wizard mit Calibre-Path-Auswahl

**Technische Spezifikation:**
```bash
# PyInstaller
pyinstaller --onefile --windowed app.py

# Erwartete Größe
- Windows: ~300 MB (inkl. Python-Runtime)
- macOS: ~250 MB
- Linux: ~200 MB

# Installation Flow
1. User wählt Calibre-Bibliothek-Pfad
2. Achilles indexiert Bibliothek (Progress-Bar)
3. Ollama-Check: Installiert? Wenn nein: Download-Link
4. Fertig: GUI öffnet sich
```

**Deliverables:**
- [ ] `build/installers/` – Windows .exe, macOS .dmg, Linux .deb
- [ ] `INSTALL_GUIDE.md` – Installations-Anleitung
- [ ] `scripts/build_release.sh` – Build-Skript

**Akzeptanzkriterien:**
- ✅ Installer funktioniert auf allen 3 Plattformen
- ✅ Erster Start: Indexierung läuft automatisch
- ✅ Ollama-Warning wenn nicht installiert
- ✅ Beta-Tester kann installieren ohne Code-Kenntnisse

**Zeitschätzung:** 3-4 Tage
**Abhängigkerien:** Alle Features von Phase 3 fertig

---

### 3.5 BETA-TESTER-PROGRAMM

**Ziel:** 10-20 Geisteswissenschaftler testen Achilles

**Anforderungen:**
- Rekrutierung: r/AskHistorians, H-Soz-Kult, Zotero-Forum
- Feedback-Formular (Google Forms oder Typeform)
- Support: Discord-Server oder Email
- Incentive: Kostenlose Pro-Lizenz bei Launch

**Feedback-Fokus:**
```
1. Installation: War es einfach? (1-5)
2. Retrieval-Qualität: Findet es relevante Stellen? (1-5)
3. Citations: Sind sie korrekt und klickbar? (1-5)
4. Performance: Läuft es flüssig? (1-5)
5. Killer-Feature: Was fehlt am meisten?
6. Zahlungsbereitschaft: Wie viel würden Sie zahlen?
```

**Deliverables:**
- [ ] Beta-Tester-Email-Template
- [ ] Feedback-Formular
- [ ] `BETA_FEEDBACK_REPORT.md` – Zusammenfassung

**Akzeptanzkriterien:**
- ✅ 10+ Beta-Tester rekrutiert
- ✅ Durchschnittliche Zufriedenheit >4.0/5
- ✅ Keine kritischen Bugs mehr
- ✅ Feature-Requests priorisiert für Phase 4

**Zeitschätzung:** 2 Wochen (parallel zu 3.1-3.4)
**Abhängigkeiten:** Installer muss fertig sein

---

## PHASE 4: LANGFRISTIGE ROADMAP (MONATE 3-12)
### Priorität: 🔵 NIEDRIG – Differenzierung & Skalierung

**Übersicht (nicht granular):**

### 4.1 Graph RAG (Monate 3-4)
- Neo4j-Integration
- Entitäten: Person, Werk, Ort, Konzept, Epoche
- Relationen: "zitiert", "widerspricht", "beeinflusst"
- Timeline-Visualisierung

### 4.2 Altsprachen-Support (Monate 4-5)
- CLTK für Latein/Griechisch-Lemmatisierung
- Fine-tuned Embeddings für klassische Sprachen
- Parallel-Ansicht: Original + Übersetzung

### 4.3 Multimodal RAG (Monate 5-6)
- Llama-3.2-Vision für Handschriften/Karten
- OCR-Layer: Transkribus-API für mittelalterliche Texte
- Bild-Text-Verknüpfung

### 4.4 Desktop-App Professional (Monate 7-9)
- Tauri statt Gradio (native Performance)
- PDF-Viewer integriert (keine externe Calibre-Abhängigkeit)
- Export-Features: BibTeX, Markdown, Word

### 4.5 Kollaboration & Institutionen (Monate 10-12)
- Multi-User-Support (PostgreSQL)
- Team-Features: Shared Collections, Comments
- Institutional Licensing

---

## TECHNISCHER STACK (FINAL)

### Core
```
Python: 3.11+
Embeddings: sentence-transformers (BGE-M3)
Vector DB: ChromaDB 0.4.22
LLM: Ollama (llama3.1:8b, mistral:7b)
```

### PDF-Processing
```
pdfplumber 0.11.0
pymupdf 1.23.8
pytesseract 0.3.10
```

### Integration
```
Calibre: Direct DB access (SQLite)
MCP: mcp-python-sdk 0.2.1
GUI: Gradio 4.10.0 (Phase 3), Tauri (Phase 4)
```

### Deployment
```
PyInstaller 6.3.0
Docker (optional für Server-Deployment)
```

---

## QUALITÄTSSICHERUNG

### Tests
- Unit-Tests: pytest für alle Module
- Integration-Tests: Ende-zu-Ende-Szenarien
- Performance-Tests: <1s Query-Zeit, <15s mit LLM
- Manual Testing: 10 Test-Queries pro Phase

### Dokumentation
- Code: Docstrings (Google-Style)
- User: Markdown-Docs in `docs/`
- Developer: Architecture Decision Records (ADRs)

### Code-Qualität
- Linting: ruff
- Type-Checking: mypy (strict mode)
- Formatting: black

---

## ERFOLGSKRITERIEN (MVP NACH 6 WOCHEN)

### Funktional
- ✅ 10.151 Annotations semantisch durchsuchbar
- ✅ Exakte Citations mit klickbaren Links
- ✅ Lokales LLM antwortet wissenschaftlich korrekt
- ✅ GUI für Nicht-Techniker bedienbar
- ✅ MCP-Server für Claude Desktop funktioniert

### Performance
- ✅ Query-Zeit: <1s (Retrieval)
- ✅ Response-Zeit: <15s (mit LLM)
- ✅ Indexing: <2h für 10k Annotations
- ✅ RAM: <16 GB

### Qualität
- ✅ Keine Halluzinationen bei 10 Test-Queries
- ✅ 95%+ korrekte Citations
- ✅ Beta-Tester-Zufriedenheit >4.0/5
- ✅ Keine kritischen Bugs

### Business
- ✅ 10+ Beta-Tester
- ✅ Pricing validiert (299 € akzeptiert)
- ✅ Go-to-Market-Plan steht (Phase 4)

---

## RISIKEN & MITIGATIONEN

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Anthropic MCP-Bug nicht behoben | Mittel | Hoch | Fallback: Standalone-App priorisieren |
| Ollama zu langsam auf Toms Hardware | Niedrig | Mittel | Kleinere Modelle (Phi-3.5, Mistral-7B) |
| PDF-Koordinaten nicht extrahierbar | Mittel | Hoch | Fallback: Nur Seitenzahl (immer noch gut) |
| Beta-Tester-Rekrutierung schwierig | Niedrig | Mittel | Direkt Tom's Netzwerk nutzen |
| BGE-M3 RAM-Probleme | Niedrig | Mittel | Fallback: nomic-embed-text-v2 (kleiner) |

---

## KOMMUNIKATION & REPORTING

### Daily Standups (optional)
- Was wurde gestern gemacht?
- Was wird heute gemacht?
- Gibt es Blocker?

### Weekly Progress Reports
- Fertiggestellte Deliverables
- Nächste Woche Ziele
- Risiken & Probleme

### Phase Completion Reports
- Nach jeder Phase: Umfassender Bericht
- Demos: Tom testet neue Features
- Go/No-Go-Entscheidung für nächste Phase

---

## ANHANG: QUICK REFERENCE

### Wichtigste Commands
```bash
# Entwicklung
pip install -r requirements.txt
python -m pytest tests/
python app.py  # GUI starten

# Indexing
python scripts/index_calibre_library.py

# MCP-Server
python mcp_server.py

# Build
./scripts/build_release.sh
```

### Wichtigste Dateien
```
achilles/
├── src/
│   ├── embeddings.py         # BGE-M3 Wrapper
│   ├── vector_store.py        # ChromaDB
│   ├── pdf_extractor.py       # PDF → Text
│   ├── llm_interface.py       # Ollama
│   ├── rag_pipeline.py        # Kern-Pipeline
│   ├── citation_builder.py    # Citations
│   └── calibre_sync.py        # Calibre-Integration
├── app.py                      # GUI (Gradio)
├── mcp_server.py              # MCP-Server
└── docs/                       # Dokumentation
```

---

**Ende des Pflichtenhefts**

**Nächste Schritte:**
1. Review mit Tom: Ist das so richtig?
2. Claude Code: Phase 1, Woche 1 starten!
3. Daily Check-ins: Fortschritt tracken

**Fragen? Änderungen? Lass uns loslegen! 🚀**
