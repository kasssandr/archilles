# Duplicate Detection Feature

Die `detect_duplicates` Funktion hilft dir, doppelte Bücher in deiner Calibre-Bibliothek zu finden. Diese Funktion ist sowohl über die Kommandozeile als auch über den MCP-Server verfügbar.

## Features

- **Mehrere Erkennungsmethoden**:
  - `title_author`: Normalisiert Titel + Autor (entfernt Artikel, Interpunktion) - **am gründlichsten**
  - `isbn`: Findet Duplikate anhand der ISBN - **am genauesten**
  - `exact_title`: Findet exakte Titel-Übereinstimmungen

- **Integration mit "Doublette"-Tag**: Zeigt automatisch Bücher an, die du bereits mit dem Tag "Doublette" markiert hast

- **Detaillierte Ergebnisse**: Jedes Duplikat zeigt:
  - Buch-ID (für weitere Aktionen)
  - Titel und Autoren
  - Tags
  - Formate (EPUB, PDF, etc.)
  - Dateipfad

## Verwendung

### 1. Kommandozeile (CLI)

#### Einfache Duplikat-Erkennung
```bash
python calibre_analyzer.py /path/to/metadata.db --duplicates
```

#### Mit spezifischer Methode
```bash
# ISBN-basierte Erkennung (sehr genau)
python calibre_analyzer.py /path/to/metadata.db --duplicates --duplicate-method isbn

# Nur exakte Titel
python calibre_analyzer.py /path/to/metadata.db --duplicates --duplicate-method exact_title

# Normalisierter Titel + Autor (Standard)
python calibre_analyzer.py /path/to/metadata.db --duplicates --duplicate-method title_author
```

#### Als Teil der Filter-Option
```bash
python calibre_analyzer.py /path/to/metadata.db -f duplicates
```

#### JSON-Ausgabe
```bash
python calibre_analyzer.py /path/to/metadata.db -o json -f duplicates > duplicates.json
```

### 2. MCP Server

Der MCP-Server stellt drei neue Tools bereit:

#### `detect_duplicates`
Findet Duplikate in der Bibliothek.

**Parameter:**
- `method` (optional): `title_author` (default), `isbn`, oder `exact_title`
- `include_doublette_tag` (optional): `true` (default) oder `false`

**Beispiel Verwendung:**
```python
from src.calibre_mcp.server import CalibreMCPServer

server = CalibreMCPServer(library_path="/path/to/calibre/library")
result = server.detect_duplicates_tool(method='title_author')

print(f"Gefundene Duplikat-Gruppen: {result['total_duplicate_groups']}")
print(f"Gesamt Duplikate: {result['total_duplicate_books']}")
print(f"Mit 'Doublette' markiert: {result['doublette_count']}")
```

#### `get_book_details`
Holt detaillierte Informationen zu einem bestimmten Buch.

**Parameter:**
- `book_id` (erforderlich): Calibre Buch-ID

**Beispiel:**
```python
book = server.get_book_details_tool(book_id=123)
print(f"Titel: {book['title']}")
print(f"Autoren: {', '.join(book['authors'])}")
print(f"Tags: {', '.join(book['tags'])}")
```

#### `get_doublette_tag_instruction`
Gibt Anweisungen zum Hinzufügen des "Doublette"-Tags.

**Parameter:**
- `book_id` (erforderlich): Buch-ID zum Markieren

**Beispiel:**
```python
instruction = server.get_doublette_tag_instruction_tool(book_id=123)
print(instruction['instruction'])
# Ausgabe: To add "Doublette" tag, run: calibredb set_metadata 123 --field tags:"+Doublette"
```

### 3. Python API

```python
from calibre_analyzer import CalibreAnalyzer

with CalibreAnalyzer('/path/to/metadata.db') as analyzer:
    # Duplikate finden
    result = analyzer.detect_duplicates(method='title_author')

    # Ergebnisse durchgehen
    for group in result['duplicate_groups']:
        print(f"\nDuplikat-Gruppe: {group['match_value']}")
        print(f"  Anzahl: {group['count']} Bücher")
        for book in group['books']:
            print(f"  - ID {book['id']}: {book['title']}")

    # Bücher mit "Doublette"-Tag anzeigen
    for book in result['doublette_tagged_books']:
        print(f"Doublette: {book['title']} (ID: {book['id']})")
```

## Ausgabeformat

### CLI-Ausgabe
```
============================================================
DUPLICATE DETECTION RESULTS
============================================================

Detection method: title_author
Duplicate groups found: 3
Total duplicate books: 7

Duplicate Groups:
------------------------------------------------------------

Group 1: title_author - mohammed and charlemagne by ('henri pirenne',)
  2 books:
    • ID 6700: Mohammed and Charlemagne
      Authors: Henri Pirenne
      Tags: History, Medieval
      Formats: EPUB
      Path: Henri Pirenne/Mohammed and Charlemagne (6700)
    • ID 6701: Mohammed and Charlemagne (Duplicate)
      Authors: Henri Pirenne
      Tags: History, Doublette
      Formats: PDF
      Path: Henri Pirenne/Mohammed and Charlemagne Duplicate (6701)

============================================================
Books tagged with 'Doublette': 1
------------------------------------------------------------
  • ID 6701: Mohammed and Charlemagne (Duplicate)
    Authors: Henri Pirenne
    Path: Henri Pirenne/Mohammed and Charlemagne Duplicate (6701)

============================================================
```

### JSON-Ausgabe
```json
{
  "method": "title_author",
  "duplicate_groups": [
    {
      "match_type": "title_author",
      "match_value": "mohammed and charlemagne by ('henri pirenne',)",
      "books": [
        {
          "id": 6700,
          "title": "Mohammed and Charlemagne",
          "authors": ["Henri Pirenne"],
          "tags": ["History", "Medieval"],
          "formats": ["EPUB"],
          "path": "Henri Pirenne/Mohammed and Charlemagne (6700)"
        }
      ],
      "count": 2
    }
  ],
  "total_duplicate_groups": 1,
  "total_duplicate_books": 2,
  "doublette_tagged_books": [...],
  "doublette_count": 1
}
```

## Erkennungsmethoden im Detail

### `title_author` (Empfohlen)
- **Normalisiert Titel**: Entfernt Artikel (der, die, das, the, le, etc.), Interpunktion und extra Leerzeichen
- **Case-insensitive**: "The Book" = "book"
- **Vergleicht Autoren**: Sortiert und normalisiert Autorennamen
- **Am gründlichsten**: Findet auch Duplikate mit leichten Titelabweichungen

**Beispiel-Treffer:**
- "The Art of War" ≈ "Art of War"
- "Das Kapital" ≈ "Kapital"
- "Le Petit Prince" ≈ "Petit Prince"

### `isbn`
- **Sehr genau**: Vergleicht ISBN-10, ISBN-13
- **Zuverlässig**: ISBNs sind eindeutig pro Edition
- **Limitiert**: Funktioniert nur, wenn ISBNs vorhanden sind

### `exact_title`
- **Einfach**: Exakter Titelvergleich (case-insensitive)
- **Schnell**: Keine Normalisierung
- **Konservativ**: Findet nur exakte Übereinstimmungen

## Workflow: Duplikate bereinigen

1. **Duplikate finden:**
   ```bash
   python calibre_analyzer.py metadata.db --duplicates > duplicates.txt
   ```

2. **Duplikate überprüfen:**
   - Schau dir die Ergebnisse an
   - Notiere IDs der zu behaltenden/löschenden Bücher

3. **Optional: Doublette-Tag setzen** (für spätere Bearbeitung):
   ```bash
   calibredb set_metadata 6701 --field tags:"+Doublette"
   ```

4. **Bücher löschen:**
   ```bash
   # Mit Calibre GUI oder:
   calibredb remove 6701
   ```

## Test-Skript

Ein vollständiges Test-Skript ist verfügbar:

```bash
python test_duplicates.py /path/to/calibre/library
```

Dies testet alle Erkennungsmethoden und zeigt Beispiel-Ausgaben.

## Wichtige Hinweise

- **Nur Lesen**: Die `detect_duplicates` Funktion liest nur aus der Datenbank, sie ändert nichts
- **Tag-Management**: Das Setzen von Tags muss über `calibredb` erfolgen (siehe Beispiele oben)
- **Performance**: Bei großen Bibliotheken (>10.000 Bücher) kann die Erkennung einige Sekunden dauern
- **Backup**: Erstelle immer ein Backup deiner Calibre-Bibliothek, bevor du Bücher löschst

## Integration mit deinem Workflow

Da du bereits den Tag "Doublette" verwendest, kannst du:

1. **Bestehende Doubletten überprüfen:**
   ```bash
   python calibre_analyzer.py metadata.db --duplicates
   ```
   Zeigt alle automatisch gefundenen Duplikate + bereits markierte Doubletten

2. **Neue Duplikate markieren:**
   - Nutze die Ausgabe, um neue Duplikate zu identifizieren
   - Markiere sie mit dem "Doublette"-Tag für spätere Bearbeitung
   - Beim nächsten Lauf werden sie automatisch mit angezeigt

3. **Bereinigung in Ruhe:**
   - Sammle Duplikate über Zeit mit dem Tag
   - Bearbeite sie gebündelt, wenn du Zeit hast
   - Nutze die Buch-IDs für gezielte Aktionen

## Unterstützung

Bei Problemen oder Fragen:
1. Prüfe die Log-Ausgabe
2. Teste mit `test_duplicates.py`
3. Prüfe, ob `metadata.db` zugänglich ist
