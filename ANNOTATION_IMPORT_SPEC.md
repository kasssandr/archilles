# Annotation Import: Externe Lesequellen → ARCHILLES

## Problem

ARCHILLES kann aktuell nur auf Metadaten, Tags, Comments und Custom Columns aus Calibre zugreifen. Die meisten Forscher lesen aber auf Kindle, Kobo oder iPad — ihre Highlights und Randnotizen liegen in externen Ökosystemen, nicht in Calibre. Damit bleibt der wertvollste Teil der Kuratierungsarbeit für ARCHILLES unsichtbar.

## Ziel

Ein Import-System, das Annotations (Highlights, Notizen, Lesezeichen) aus den gängigen Lesequellen extrahiert und in ein einheitliches Format überführt, das ARCHILLES indizieren und durchsuchen kann.

## Quellen und ihre Datenformate

### 1. Amazon Kindle
- **My Clippings.txt**: Flache Textdatei auf dem Gerät, enthält Highlights + Notizen mit Buchtitel, Position (Location), Datum
- **kindle.amazon.com/your_highlights**: Web-Export (nur eigene Bücher, nicht DRM-frei geliehene)
- **KFX/AZW3-Sidecar-Dateien**: Enthalten Annotations in einer SQLite-DB auf dem Gerät
- **Einschränkung**: Amazon begrenzt den Export bei manchen Büchern auf ~10% des Textes ("clipping limit")

### 2. Kobo
- **KoboReader.sqlite**: SQLite-Datenbank auf dem Gerät (Tabellen: `Bookmark`, `content`)
- Enthält: Highlight-Text, Position (ContentID + Offset), Annotation-Text, Erstellungsdatum
- Gut dokumentiert, kein DRM-Problem beim Auslesen der Annotations

### 3. Apple Books (iBooks)
- **AEAnnotation**: SQLite-Datenbank unter `~/Library/Containers/com.apple.iBooksX/Data/Documents/AEAnnotation/`
- Enthält: Highlight-Text, Notizen, CFI-Positionen (EPUB) oder Seitenzahlen (PDF)
- Zugriff nur auf macOS, nicht auf iOS ohne Backup-Extraktion

### 4. PDF-Annotations
- Eingebettet in der PDF-Datei selbst (Markup Annotations nach PDF-Spec)
- Calibre speichert PDFs → Annotations können direkt aus den Dateien gelesen werden
- Libraries: `PyMuPDF` (fitz), `pdfplumber`

### 5. Calibre Viewer
- SQLite-DB: `~/.config/calibre/viewer-annotations.db` (Linux) bzw. Äquivalent auf Windows/Mac
- Enthält: Highlights, Lesezeichen, Notizen mit CFI-Position
- Bereits im Calibre-Ökosystem, am einfachsten zu integrieren

## Einheitliches Annotation-Schema

```python
@dataclass
class Annotation:
    book_id: int              # Calibre book ID (Zuordnung über Titel/ISBN-Match)
    source: str               # "kindle" | "kobo" | "apple_books" | "pdf" | "calibre_viewer"
    type: str                 # "highlight" | "note" | "bookmark"
    text: str                 # Der gehighlightete Text
    note: str | None          # Nutzernotiz zum Highlight
    location: str             # Quellenspezifisch: Kindle Location, EPUB CFI, PDF-Seite
    page_estimate: int | None # Geschätzte Seitenzahl (normalisiert)
    chapter: str | None       # Kapitelname falls verfügbar
    created_at: datetime
    raw_metadata: dict        # Originaldaten für Debugging
```

## Zuordnung zum Calibre-Bestand

Das schwierigste Problem: eine Annotation aus "My Clippings.txt" dem richtigen Calibre-Buch zuordnen.

- **Exakter Match**: ISBN, ASIN oder Titel+Autor
- **Fuzzy Match**: Levenshtein-Distanz auf Titel (Kindle-Clippings haben oft abweichende Titelformate)
- **Manueller Fallback**: Nicht zuordenbare Annotations in eine Review-Queue stellen

## Implementierungsreihenfolge

1. **PDF-Annotations** — niedrigste Komplexität, Dateien liegen bereits in Calibre
2. **Calibre Viewer** — SQLite direkt zugänglich, Schema bekannt
3. **Kobo** — gut dokumentiert, SQLite, keine DRM-Hürden
4. **Kindle (My Clippings.txt)** — einfaches Textformat, aber Zuordnungsproblem
5. **Apple Books** — plattformbeschränkt (nur macOS), komplexeres Schema

## MCP-Integration

Neue/erweiterte Tools:
- `import_annotations(source, path)` — Import aus einer Quelle
- `search_annotations(query, book_id?, source?)` — Semantische Suche über Annotations
- `get_book_annotations(book_id)` — Alle Annotations eines Buchs
- `annotation_stats(book_id?)` — Übersicht (Anzahl Highlights, annotierte Bücher, etc.)

## Offene Fragen

- **Speicherort**: Eigene SQLite-DB neben dem ARCHILLES-Index? Oder in Calibres Custom Columns zurückschreiben?
- **Synchronisation**: Einmal-Import oder regelmäßiger Sync (Gerät angesteckt → Auto-Import)?
- **Embedding**: Sollen Annotations in den bestehenden Vektor-Index einfließen oder einen eigenen Index bekommen?
- **DRM**: Kindle-Annotations aus DRM-geschützten Büchern enthalten den Text — ist der Export rechtlich unbedenklich? (Vermutlich ja: eigene Fair-Use-Notizen)
