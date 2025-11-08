# Calibre Metadata Analyzer

Ein Tool zur Analyse und Auswertung von Calibre-Bibliotheksmetadaten.

## Überblick

Der Calibre Metadata Analyzer ist ein Python-basiertes Kommandozeilen-Tool, das Ihre Calibre-Bibliothek analysiert und detaillierte Statistiken über Ihre E-Book-Sammlung liefert.

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

## Lizenz

MIT License

## Beitragen

Beiträge sind willkommen! Bitte erstellen Sie ein Issue oder Pull Request.
