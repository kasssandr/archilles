# Achilles - Calibre MCP Server & Tools

Ein umfassendes Toolset für Calibre-Bibliotheken mit MCP Server-Integration, Annotations-Management und semantischer Suche.

## Überblick

Achilles bietet drei Hauptkomponenten:

1. **Calibre MCP Server**: Model Context Protocol Server für Calibre-Integration mit Claude Desktop
2. **Annotations Management**: Intelligente Verarbeitung von Highlights und Notizen mit TOC-Filterung
3. **Metadata Analyzer**: Detaillierte Statistiken über Ihre E-Book-Sammlung

## Features

### 🚀 Calibre MCP Server

- **Annotations-Zugriff**: Lesen von Highlights, Notizen und Bookmarks aus Calibre Viewer
- **PDF-Support**: Extrahierung von PDF-internen Annotations (via PyMuPDF)
- **Intelligente Filterung**: Automatische Erkennung und Filterung von TOC-Markern
- **Semantische Suche**: ChromaDB-basierte Embeddings für intelligente Annotation-Suche
- **MCP-Integration**: Nahtlose Integration mit Claude Desktop und anderen MCP-Clients

### 📝 Annotations Management

- **Multi-Source**: Calibre Viewer Annotations + PDF-interne Annotations
- **TOC-Filterung**: Intelligent TOC-Marker und technische Highlights ausfiltern
- **Positionsfilter**: Annotations aus erstem X% des Buchs ausschließen
- **Längenfilter**: Minimale Textlänge für Annotations konfigurierbar
- **Typ-Filter**: Nach Highlight, Note oder Bookmark filtern

### 🔍 Semantische Suche

- **Embeddings**: Sentence-Transformers für semantische Ähnlichkeitssuche
- **ChromaDB**: Persistent Vector Store für schnelle Suche
- **Indexierung**: Automatische oder manuelle Indexierung aller Annotations
- **Metadaten-Filter**: Suche nach Annotation-Typ, Quelle, etc.

### 📊 Metadata Analyzer

- 📚 **Bibliotheksübersicht**: Gesamtzahl der Bücher
- 👥 **Autoren-Statistiken**: Top-Autoren und Anzahl ihrer Werke
- 🏢 **Verlags-Statistiken**: Häufigste Verlage
- 🏷️ **Tag-Analyse**: Meistgenutzte Tags und Genres
- 🌍 **Sprachverteilung**: Sprachen in Ihrer Bibliothek
- 📖 **Serien-Informationen**: Übersicht über Buchserien
- ⭐ **Bewertungsverteilung**: Wie Sie Ihre Bücher bewertet haben
- 📅 **Veröffentlichungsjahre**: Zeitliche Verteilung der Publikationen
- 📄 **Dateiformat-Statistiken**: Übersicht der E-Book-Formate (EPUB, PDF, MOBI, etc.)
- ⚠️ **Unvollständige Metadaten**: Bücher mit fehlenden Informationen

## Voraussetzungen

- Python 3.7 oder höher
- Zugriff auf Ihre Calibre-Bibliothek (metadata.db Datei)
- Optional: PyMuPDF für PDF-Annotations
- Optional: ChromaDB für semantische Suche

## Installation

1. Klonen Sie das Repository:
```bash
git clone <repository-url>
cd achilles
```

2. Installieren Sie die Dependencies:

**Minimal (nur Metadata Analyzer):**
```bash
# Keine zusätzlichen Dependencies erforderlich
```

**Standard (mit PDF-Support):**
```bash
pip install -r requirements.txt
# oder nur:
pip install PyMuPDF
```

**Komplett (mit semantischer Suche):**
```bash
pip install -r requirements.txt
# Dies installiert:
# - PyMuPDF (PDF-Annotations)
# - chromadb (Semantische Suche)
# - sentence-transformers (Embeddings)
```

3. Machen Sie die Skripte ausführbar (Linux/Mac):
```bash
chmod +x calibre_analyzer.py
chmod +x sync_annotations_to_comments.py
```

## Verwendung

### 1. Calibre MCP Server

**Grundlegende Verwendung:**

```python
from src.calibre_mcp.server import CalibreMCPServer

# Minimale Konfiguration
server = CalibreMCPServer(
    library_path="/path/to/Calibre Library"
)

# Mit semantischer Suche
server = CalibreMCPServer(
    library_path="/path/to/Calibre Library",
    enable_semantic_search=True,
    chroma_persist_dir="./chroma_data"
)
```

**MCP Tools:**

```python
# Get annotations für ein Buch
result = server.get_book_annotations_tool(
    book_path="/path/to/book.epub",
    exclude_toc_markers=True,
    include_pdf=True,
    min_length=20
)

# Annotations durchsuchen (text-basiert)
results = server.search_annotations_tool(
    query="Desposynoi",
    case_sensitive=False
)

# Annotations durchsuchen (semantisch)
results = server.search_annotations_tool(
    query="political ambitions of Jesus' relatives",
    use_semantic=True,
    max_results=10
)

# Annotations indexieren
stats = server.index_annotations_tool(
    force_reindex=False,
    exclude_toc_markers=True
)

# Index-Statistiken abrufen
stats = server.get_index_stats_tool()
```

### 2. Annotations Indexer (Standalone)

**CLI-Verwendung:**

```bash
# Alle Annotations indexieren
python -m src.calibre_mcp.annotations_indexer --chroma-dir ./chroma_data

# Force reindex
python -m src.calibre_mcp.annotations_indexer --chroma-dir ./chroma_data --reindex

# Statistiken anzeigen
python -m src.calibre_mcp.annotations_indexer --chroma-dir ./chroma_data --stats

# Suchen
python -m src.calibre_mcp.annotations_indexer --chroma-dir ./chroma_data --search "Desposynoi"
```

**Python-API:**

```python
from src.calibre_mcp.annotations_indexer import AnnotationsIndexer

# Indexer erstellen
indexer = AnnotationsIndexer(
    chroma_persist_dir="./chroma_data"
)

# Alle Annotations indexieren
stats = indexer.index_all_annotations(
    exclude_toc_markers=True,
    min_length=20
)
print(f"Indexed {stats['total_annotations']} annotations from {stats['total_books']} books")

# Suchen
results = indexer.search_annotations(
    query="political ambitions",
    n_results=5
)

for result in results:
    print(f"Text: {result['text']}")
    print(f"Book: {result['metadata']['book_path']}")
    print(f"Relevance: {1 - result['distance']:.2%}\n")
```

### 3. Sync Annotations to Comments

**Annotations in Calibre Comments-Feld synchronisieren:**

```bash
# Alle Bücher mit einem bestimmten Tag
python sync_annotations_to_comments.py ~/Calibre\ Library --tag Judenkönige

# Spezifische Bücher nach ID
python sync_annotations_to_comments.py ~/Calibre\ Library --book-ids 123,456,789

# Dry run (Preview)
python sync_annotations_to_comments.py ~/Calibre\ Library --tag Judenkönige --dry-run

# Ohne Backup (nicht empfohlen)
python sync_annotations_to_comments.py ~/Calibre\ Library --tag Judenkönige --no-backup
```

**⚠️ WICHTIG:**
- Schließen Sie Calibre vor dem Ausführen des Sync-Tools
- Das Tool erstellt automatisch ein Backup von `metadata.db`
- Nutzen Sie `--dry-run` für einen Preview

### 4. Metadata Analyzer

**Basis-Verwendung:**

```bash
python calibre_analyzer.py /pfad/zur/Calibre/metadata.db
```

### Beispiele

**Standardausgabe (Zusammenfassung):**
```bash
python calibre_analyzer.py ~/Calibre\ Library/metadata.db
```

**JSON-Ausgabe für weitere Verarbeitung:**
```bash
python calibre_analyzer.py metadata.db --output json
```

**JSON-Ausgabe in Datei speichern:**
```bash
python calibre_analyzer.py metadata.db --output json > analysis.json
```

**Nur spezifische Statistiken anzeigen:**
```bash
# Nur Autoren
python calibre_analyzer.py metadata.db --filter authors

# Nur Tags
python calibre_analyzer.py metadata.db --filter tags

# Nur Bücher mit unvollständigen Metadaten
python calibre_analyzer.py metadata.db --filter incomplete
```

### Kommandozeilen-Optionen

```
usage: calibre_analyzer.py [-h] [-o {summary,json}]
                          [-f {authors,publishers,tags,languages,series,ratings,years,formats,incomplete}]
                          database

positional arguments:
  database              Pfad zur Calibre metadata.db Datei

optional arguments:
  -h, --help            Hilfe anzeigen
  -o, --output {summary,json}
                        Ausgabeformat (Standard: summary)
  -f, --filter {authors,publishers,tags,languages,series,ratings,years,formats,incomplete}
                        Nur spezifische Statistiken anzeigen
```

## Wo finde ich die metadata.db?

Die `metadata.db` Datei befindet sich im Hauptverzeichnis Ihrer Calibre-Bibliothek:

- **Linux**: `~/Calibre Library/metadata.db`
- **macOS**: `~/Library/Calibre Library/metadata.db`
- **Windows**: `C:\Users\[Username]\Calibre Library\metadata.db`

## Ausgabe-Beispiel

```
============================================================
CALIBRE LIBRARY ANALYSIS
============================================================

📚 Total Books: 1234

👥 Top 10 Authors:
  • Isaac Asimov: 45 books
  • Terry Pratchett: 38 books
  • Stephen King: 32 books
  ...

🏢 Top 10 Publishers:
  • Penguin Random House: 234 books
  • HarperCollins: 156 books
  ...

🏷️  Top 10 Tags:
  • Science Fiction: 345 books
  • Fantasy: 287 books
  • Thriller: 198 books
  ...

⭐ Ratings Distribution:
  ★★★★★ (5.0): 234 books
  ★★★★ (4.0): 456 books
  ★★★ (3.0): 123 books
  ...
============================================================
```

## Als Python-Modul verwenden

Sie können den Analyzer auch in eigenen Python-Skripten verwenden:

```python
from calibre_analyzer import CalibreAnalyzer

# Analyzer initialisieren
with CalibreAnalyzer('/pfad/zur/metadata.db') as analyzer:
    # Gesamtzahl der Bücher
    total = analyzer.get_total_books()
    print(f"Total books: {total}")

    # Autoren-Statistiken
    authors = analyzer.get_authors_stats()
    for author in authors[:10]:
        print(f"{author['name']}: {author['book_count']} books")

    # Vollständige Analyse
    analysis = analyzer.get_complete_analysis()

    # Unvollständige Metadaten finden
    incomplete = analyzer.get_books_without_metadata()
```

## Verfügbare Methoden

- `get_total_books()` - Gesamtzahl der Bücher
- `get_authors_stats()` - Autoren-Statistiken
- `get_publishers_stats()` - Verlags-Statistiken
- `get_tags_stats()` - Tag-Statistiken
- `get_languages_stats()` - Sprach-Statistiken
- `get_series_stats()` - Serien-Informationen
- `get_ratings_distribution()` - Bewertungsverteilung
- `get_publication_years()` - Publikationsjahre
- `get_format_stats()` - Dateiformat-Statistiken
- `get_books_without_metadata()` - Bücher mit fehlenden Metadaten
- `get_complete_analysis()` - Vollständige Analyse (alle obigen kombiniert)

## Architektur & Design-Entscheidungen

### Read-Only MCP Server

Der Calibre MCP Server ist bewusst **READ-ONLY** designt:

**Warum?**
- ✅ Sicherheit: Verhindert versehentliche Datenbank-Korruption
- ✅ MCP Best Practice: Server sollten primär Daten bereitstellen
- ✅ Komplexität: Vermeidet Transaktionen, Locks, Error-Recovery
- ✅ Kompatibilität: Kein Konflikt mit parallel laufendem Calibre

**Write-Operations:**
- Nutzen Sie das separate `sync_annotations_to_comments.py` Script
- Manuell ausführbar, wenn gewünscht
- Erstellt automatisch Backups

### Annotations-Quellen

1. **Calibre Viewer Annotations**:
   - Speicherort: `%APPDATA%/calibre/viewer/annots/` (Windows)
   - Format: JSON-Dateien mit SHA256-Hash des Buchpfads als Namen
   - WICHTIG: Hash basiert auf FILE PATH, nicht Dateiinhalt

2. **PDF-interne Annotations**:
   - Extrahiert via PyMuPDF
   - Unterstützt Highlights, Underlines, Notes
   - Kombinierbar mit Calibre Viewer Annotations

### TOC-Marker Filterung

Intelligente Erkennung von technischen Highlights:
- Sehr kurze Texte (< 20 Zeichen)
- TOC-Keywords (Inhaltsverzeichnis, Contents, etc.)
- Annotations in ersten 5% des Buchs
- Konfigurierbar über Parameter

### Semantische Suche

- **Embeddings**: Sentence-Transformers (all-MiniLM-L6-v2)
- **Vector Store**: ChromaDB mit persistentem Storage
- **Incremental**: Neue Annotations werden beim Indexieren automatisch hinzugefügt
- **Metadaten**: Book hash, path, type, source, page, timestamp

## Best Practices

### Für Annotations-Management

1. **Indexierung**:
   ```bash
   # Initiales Indexing
   python -m src.calibre_mcp.annotations_indexer --chroma-dir ./chroma_data

   # Periodisches Re-Indexing (z.B. wöchentlich)
   python -m src.calibre_mcp.annotations_indexer --chroma-dir ./chroma_data --reindex
   ```

2. **Sync zu Comments**:
   ```bash
   # Immer mit dry-run testen
   python sync_annotations_to_comments.py ~/Calibre\ Library --tag MyTag --dry-run

   # Dann actual sync
   python sync_annotations_to_comments.py ~/Calibre\ Library --tag MyTag
   ```

3. **Filter-Tuning**:
   - Passen Sie `min_length` an Ihre Nutzung an (Standard: 20)
   - `exclude_first_percent` für Bücher mit langen Vorwörtern erhöhen
   - Bei zu vielen False-Positives: TOC-Keywords in `annotations.py` erweitern

### Für MCP Server Integration

```python
# In Ihrer MCP-Konfiguration (z.B. Claude Desktop)
{
  "mcpServers": {
    "calibre": {
      "command": "python",
      "args": ["-m", "src.calibre_mcp.server"],
      "env": {
        "CALIBRE_LIBRARY": "/path/to/Calibre Library",
        "ENABLE_SEMANTIC_SEARCH": "true",
        "CHROMA_DIR": "./chroma_data"
      }
    }
  }
}
```

## Hinweise

### Metadata Analyzer
- Liest nur Daten, ändert Calibre-Bibliothek nicht
- Für große Bibliotheken kann Analyse einige Sekunden dauern
- `metadata.db` sollte nicht geöffnet sein, während Calibre läuft (empfohlen)

### Annotations Tools
- **Calibre Viewer**: Annotations werden automatisch gespeichert
- **PDF**: Nur wenn Annotations direkt im PDF eingebettet sind
- **Hash-Berechnung**: Basiert auf vollständigem Dateipfad (case-sensitive!)

### Sync Tool
- **WICHTIG**: Calibre muss geschlossen sein
- Erstellt automatisch Backup (außer mit `--no-backup`)
- Verwendet Markdown-Format für Comments
- Erhält bestehende Sections in Comments

## Lizenz

MIT License

## Beitragen

Beiträge sind willkommen! Bitte erstellen Sie ein Issue oder Pull Request.
