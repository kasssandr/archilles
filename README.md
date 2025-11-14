# Achilles - Calibre Quote Tracker

Ein umfassendes Tool zur Analyse von Calibre-Bibliotheken und zur systematischen Suche nach Zitaten und Argumenten in wissenschaftlichen Texten.

## Überblick

Achilles besteht aus zwei Hauptkomponenten:

1. **Calibre Metadata Analyzer**: Analysiert Bibliotheksmetadaten und liefert Statistiken
2. **Quote Tracker (NEU)**: Durchsucht Volltexte nach Zitaten, Argumenten und relevanten Passagen

Mit dem Quote Tracker können Sie:
- Systematisch nach Zitaten in Ihrer gesamten Bibliothek suchen
- Relevante Passagen mit Kontext extrahieren
- Fundstellen für wissenschaftliche Argumentationen sammeln
- Thesen mit Textnachweisen belegen

## Features

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

- Python 3.6 oder höher
- Zugriff auf Ihre Calibre-Bibliothek (metadata.db Datei)

## Installation

1. Klonen Sie das Repository:
```bash
git clone <repository-url>
cd achilles
```

2. Das Tool benötigt nur die Python-Standardbibliothek, keine zusätzlichen Abhängigkeiten erforderlich.

3. Machen Sie das Skript ausführbar (Linux/Mac):
```bash
chmod +x calibre_analyzer.py
```

## Verwendung

### Basis-Verwendung

Zeige eine übersichtliche Zusammenfassung Ihrer Bibliothek:

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

## Hinweise

- Das Tool liest nur Daten und ändert Ihre Calibre-Bibliothek nicht
- Für große Bibliotheken kann die Analyse einige Sekunden dauern
- Die metadata.db Datei sollte nicht geöffnet sein, während Calibre läuft (empfohlen)

---

# Quote Tracker - Volltextsuche für Zitate

## Überblick

Der Quote Tracker ermöglicht die Volltextsuche über Ihre gesamte Calibre-Bibliothek. Perfekt für wissenschaftliches Arbeiten, wenn Sie Zitate und Argumente aus verschiedenen Quellen sammeln möchten.

## Features (Phase 1 - MVP)

- ✅ **Volltextsuche**: Durchsucht PDF und EPUB Dateien
- ✅ **Intelligente Kontext-Extraktion**: Zeigt ±3 Sätze oder ±N Wörter um den Treffer
- ✅ **Web-Interface**: Benutzerfreundliches Streamlit UI
- ✅ **CLI-Interface**: Für Automatisierung und Scripting
- ✅ **Performante FTS5-Suche**: SQLite Full-Text Search für schnelle Ergebnisse
- ✅ **Relevanz-Ranking**: Ergebnisse nach Relevanz sortiert

## Installation Quote Tracker

### 1. Dependencies installieren

```bash
pip install -r requirements.txt
```

Dies installiert:
- `PyMuPDF` - PDF-Textextraktion
- `ebooklib` - EPUB-Parsing
- `beautifulsoup4` - HTML/XML-Verarbeitung
- `streamlit` - Web-Interface
- `nltk` - Natural Language Processing

### 2. NLTK-Daten herunterladen (optional)

```bash
python -c "import nltk; nltk.download('punkt')"
```

## Verwendung Quote Tracker

### Web-Interface (empfohlen)

1. **Starten Sie das Web-UI:**
```bash
streamlit run quote_search_web.py
```

2. **Öffnen Sie Browser:** `http://localhost:8501`

3. **Konfiguration:**
   - Geben Sie den Pfad zu Ihrer Calibre-Bibliothek ein
   - Navigieren Sie zum Tab "Indizierung"

4. **Bibliothek indizieren:**
   - Optional: Tag-Filter eingeben (z.B. "Leit-Literatur")
   - Anzahl Bücher wählen
   - "Indizierung starten" klicken

5. **Suchen:**
   - Navigieren Sie zum Tab "Suche"
   - Geben Sie Suchbegriff ein (z.B. "Josephus", "Testimonium Flavianum")
   - Wählen Sie Kontext-Optionen
   - Klicken Sie "Suchen"

### CLI-Interface

#### Bibliothek indizieren:

```bash
# Gesamte Bibliothek (limitiert auf 100 Bücher für Test)
python quote_search_cli.py ~/Calibre-Library --index --limit 100

# Nur bestimmte Tags
python quote_search_cli.py ~/Calibre-Library --index --tag "Leit-Literatur"

# Vollständige Bibliothek (kann lange dauern!)
python quote_search_cli.py ~/Calibre-Library --index --limit 10000
```

#### Suchen:

```bash
# Einfache Suche
python quote_search_cli.py ~/Calibre-Library --search "Josephus"

# Mit Satz-Kontext (±3 Sätze)
python quote_search_cli.py ~/Calibre-Library --search "ancient Rome" --context-type sentences --context-size 3

# Mit Wort-Kontext (±200 Wörter)
python quote_search_cli.py ~/Calibre-Library --search "Testimonium Flavianum" --context-type words --context-size 200

# Mehr Ergebnisse anzeigen
python quote_search_cli.py ~/Calibre-Library --search "Judaea" --max-results 50
```

#### Statistiken anzeigen:

```bash
python quote_search_cli.py ~/Calibre-Library --stats
```

#### Index löschen:

```bash
python quote_search_cli.py ~/Calibre-Library --clear
```

## Architektur

### Komponenten

1. **text_extractor.py**: Extrahiert Volltext aus PDF und EPUB
2. **search_engine.py**: SQLite FTS5-basierte Suchmaschine mit Kontext-Extraktion
3. **quote_search_cli.py**: Kommandozeilen-Interface
4. **quote_search_web.py**: Streamlit Web-Interface

### Datenfluss

```
Calibre Library
    ├─ metadata.db → Buch-Metadaten (calibre_analyzer.py)
    └─ Book Files (PDF/EPUB) → Volltext-Extraktion (text_extractor.py)
        ↓
    FTS5 Index (quote_search_index.db) → Volltextsuche (search_engine.py)
        ↓
    Suchergebnisse mit Kontext
        ├─ CLI (quote_search_cli.py)
        └─ Web-UI (quote_search_web.py)
```

## Performance

- **Indizierung**: ~5-30 Minuten für 100 Bücher (abhängig von Dateigröße)
- **Suche**: <1 Sekunde pro Query
- **Speicherplatz**: ~10-50 MB Index pro 100 Bücher

## Geplante Features (Phase 2-4)

### Phase 2: Persistente Zitat-Speicherung
- [ ] Zitate mit einem Klick speichern
- [ ] Eigene Notizen zu Zitaten hinzufügen
- [ ] Gespeicherte Zitate verwalten und durchsuchen

### Phase 3: Thesen-Management
- [ ] Thesen/Argumentationsstränge anlegen
- [ ] Zitate Thesen zuordnen
- [ ] Übersicht: Alle Zitate pro These
- [ ] Multi-Zuordnung (ein Zitat → mehrere Thesen)

### Phase 4: Export & Erweiterte Suche
- [ ] Export als Markdown, HTML, DOCX
- [ ] Boolesche Operatoren (AND, OR, NOT)
- [ ] Phrasensuche
- [ ] Proximity-Suche
- [ ] Relevanz-Scoring verfeinern

## Beispiel-Workflows

### Workflow 1: Historische Forschung

```bash
# 1. Bibliothek mit historischen Quellen indizieren
python quote_search_cli.py ~/Calibre-Library --index --tag "Antike-Quellen"

# 2. Nach relevanten Passagen suchen
python quote_search_cli.py ~/Calibre-Library --search "Flavius Josephus"

# 3. Ergebnisse im Web-UI durchsehen und annotieren
streamlit run quote_search_web.py
```

### Workflow 2: Thematische Recherche

```bash
# 1. Indiziere Fachbibliothek
python quote_search_cli.py ~/Calibre-Library --index --tag "Theologie"

# 2. Suche nach Konzept
python quote_search_cli.py ~/Calibre-Library --search "apologetik" --context-size 5

# 3. Relevante Zitate notieren
# (In Phase 2: Zitate direkt im UI speichern)
```

## Troubleshooting

### Fehler: "No module named 'fitz'"

```bash
pip install PyMuPDF
```

### Fehler: "Unable to extract text from PDF"

- PDFs können Scans sein (keine Textebene)
- Versuchen Sie OCR-Vorverarbeitung (außerhalb des Scopes)
- Oder nutzen Sie EPUB-Versionen

### Fehler: "Database is locked"

- Schließen Sie Calibre
- Oder verwenden Sie eine Kopie der metadata.db

### Performance-Optimierung

Für sehr große Bibliotheken (>1000 Bücher):
1. Indizieren Sie schrittweise mit `--tag` Filter
2. Verwenden Sie `--limit` für Tests
3. Erwägen Sie separate Indices für verschiedene Sammlungen

## Lizenz

MIT License

## Beitragen

Beiträge sind willkommen! Bitte erstellen Sie ein Issue oder Pull Request.

## Kontakt & Support

Bei Fragen oder Problemen erstellen Sie bitte ein GitHub Issue.
