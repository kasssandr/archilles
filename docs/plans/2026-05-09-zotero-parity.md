# Plan-Draft: Zotero auf Calibre-Niveau bringen

**Status:** Entwurf, 2026-05-09 — Umsetzung ab Dienstag (≥2026-05-12)
**Voraussetzung für:** strukturbewusstes Reranking (`source_type` als Scoring-Signal)
**Begründung:** Vor Reranking-Arbeit muss Zotero auf Augenhöhe mit Calibre erschlossen sein, sonst gewichten wir auf einer Datenbasis, die Zotero-Inhalte falsch labelt oder gar nicht erfasst.

## Designentscheidungen (aus Konversation 2026-05-09)

| Aspekt | Entscheidung |
|---|---|
| Zotero-Abstract | Eigener `ChunkType.ZOTERO_ABSTRACT`. Genau **ein Chunk pro Abstract**. Kein HTML-Parsing, kein Section-Split — wissenschaftliche Abstracts sind ein Absatz. Begründung: Abstracts gibt es in Calibre konzeptuell nicht; in Zotero sind sie ein dediziertes Feld (`abstractNote`) mit klar anderer epistemischer Qualität als ein Calibre-Klappentext. |
| Zotero-Notiz | Eigener `ChunkType.ZOTERO_NOTE`. **Strikt analog zu Calibre-Comments** behandeln: HTML-Parsing, Section-Split an Headlines (H1/H2/H3). Pro Zotero-Item können mehrere Notizen existieren — jede wird einzeln verarbeitet. |
| Zotero-Annotation | **KEIN eigener chunk_type.** Bleibt `ChunkType.ANNOTATION` mit `annotation_source="zotero"` (wie bereits jetzt). Provenienz steckt im Source-Feld; Reranking-Gewicht ist identisch zu Calibre-/Kindle-Annotations. |
| Calibre-Pfad | Bleibt unverändert. `calibre_comment` und Calibres Annotation-Behandlung werden nicht angefasst. |
| Schema-Migration für Bestand | Nicht nötig (Zotero-Index aktuell nur Test-Inhalt) — Re-Index reicht. |

## Wertvolle HTML-Elemente in Zotero-Notizen

Zotero-Notizen erlauben: H1, H2, H3, Absatz, Code/Nichtproportional, Aufzählung, Nummerierung, Blockzitat, Mathematik-Block.

Behandlung beim Chunking:

| Element | Behandlung |
|---|---|
| H1, H2, H3 | **Sektionsgrenze** — wie bei Calibre-Comments (`parse_html_comment`-Logik) |
| Absatz (`<p>`) | Normaler Body, kann zwischen Sektionen aggregiert werden |
| Blockzitat (`<blockquote>`) | **Atomar halten** — niemals über Blockzitat hinweg splitten. Im Chunk-Text mit Marker `> …` kennzeichnen, damit das Zitat-Schema im Reranking erkennbar bleibt |
| Aufzählung / Nummerierung (`<ul>`, `<ol>`) | Atomar — die Liste als Block in einem Chunk halten, nicht zerschneiden |
| Mathematik-Block | Atomar — keinesfalls splitten |
| Code / Nichtproportional (`<pre>`, `<code>`) | Atomar |

**Regel:** Sektionsgrenzen NUR an H1–H3; alle anderen Block-Elemente sind innerhalb einer Sektion atomare Units, über die der Word-Counter beim Splitting nicht trennen darf.

## Aufgaben

### A1 — Konstanten erweitern
**Datei:** `src/archilles/constants.py`

```python
class ChunkType:
    ...
    CALIBRE_COMMENT = "calibre_comment"
    ZOTERO_ABSTRACT = "zotero_abstract"   # neu
    ZOTERO_NOTE     = "zotero_note"       # neu
    ANNOTATION      = "annotation"        # bleibt — quellenübergreifend (Calibre/Kindle/Zotero/PDF)

    NON_CONTENT_TYPES = frozenset({
        CALIBRE_COMMENT, ZOTERO_ABSTRACT, ZOTERO_NOTE,
        ANNOTATION,
        PHASE1_METADATA, PARENT,
    })

    # Reranking-Gleichgewichtsklassen (für später, wenn structure-aware reranking kommt)
    COMMENT_TYPES = frozenset({CALIBRE_COMMENT, ZOTERO_NOTE})  # User-Kommentare/Notizen
    # ZOTERO_ABSTRACT erhält eigenes Gewicht (höher als COMMENT_TYPES)
    # ANNOTATION ist eigenes Gewicht (Provenienz via annotation_source-Feld)
```

**Aufwand:** 15 min

### A2 — Zotero-Adapter: comments_html befüllen
**Datei:** `src/adapters/zotero_adapter.py`, Methode `_build_metadata`

Zotero-Abstract ist Plaintext — `comments_html` bleibt leer. Aber: der Adapter muss explizit signalisieren, dass es sich um eine Zotero-Quelle handelt, damit der Indexing-Pfad den richtigen chunk_type wählt. Optionen:

- **Variante a:** Adapter setzt nichts Neues; der Indexing-Pfad in rag_demo erkennt den Adapter-Typ über `adapter.adapter_type == "zotero"` und routet entsprechend. **Empfohlen** — keine Schema-Änderung nötig.
- Variante b: Neues Feld `comment_kind` in `DocumentMetadata`. Mehr Aufwand, kein klarer Vorteil hier.

**Aufwand:** 0 min (Variante a) — Logik wandert nach A3.

### A3 — Zotero-Notes als separate Quelle im Adapter
**Datei:** `src/adapters/zotero_adapter.py`

Neue Methode `get_notes(doc_id) -> list[ZoteroNote]`:
- Liest `itemNotes WHERE parentItemID = ?`
- Gibt Liste von `(note_id, html, dateModified)` zurück (HTML, **nicht** stripped — wir brauchen die Struktur fürs Chunking)
- Datenklasse `ZoteroNote(note_id: str, html: str, modified_at: str)` in `src/adapters/base.py`

**Wichtig für Hash-Stabilität:** `compute_metadata_hash` muss alle Note-HTMLs einbeziehen, sonst erkennt der Watchdog Note-Änderungen nicht. Konkret: in `compute_metadata_hash` bei Zotero zusätzlich Hashes der Note-HTMLs (sortiert nach `note_id`) in das `relevant`-Dict einfügen.

**Aufwand:** 1–1,5 h

### A4 — Indexing-Pfad: Zotero-Comment-/Note-/Abstract-Builder
**Datei:** `scripts/rag_demo.py`

`_build_comment_chunks` ist auf Calibre-HTML zugeschnitten. Nicht erweitern, sondern **drei neue Builder** anlegen, die Calibres Logik wiederverwenden, wo sinnvoll:

1. **`_build_zotero_abstract_chunk(book_metadata, book_id, ...)`**
   - Genau ein Chunk: `text = book_metadata['comments']` (Plaintext-Abstract)
   - `chunk_type = ChunkType.ZOTERO_ABSTRACT`
   - Kein Section-Header, kein `[CALIBRE_COMMENT]`-Prefix
   - Optional Prefix `[ABSTRACT]` für Lesbarkeit in Suchergebnissen

2. **`_build_zotero_note_chunks(notes, book_id, ...)`** — für jede Note:
   - HTML mit `parse_html_comment`-Logik in Sektionen splitten (Wiederverwendung — eventuell die Funktion aus `CalibreDB` in ein neutrales Modul `src/archilles/html_section_split.py` verschieben, damit sie nicht „CalibreDB" heißt)
   - **Atomare Units respektieren** (siehe Tabelle oben — Blockzitate, Listen, Math, Code dürfen nicht innerhalb gesplittet werden). Falls `parse_html_comment` das aktuell nicht garantiert: prüfen + ggf. nachziehen.
   - Pro Sektion ein Chunk mit `chunk_type = ChunkType.ZOTERO_NOTE`, `section_title=headline`
   - Stabile chunk_id: `f"{book_id}_note_{note_id}_{section_index}"` (damit Re-Index identische IDs liefert)

3. ~~`_build_zotero_annotation_chunks`~~ — **entfällt.** Zotero-Annotations laufen weiter durch den bestehenden `ChunkType.ANNOTATION`-Pfad mit `annotation_source="zotero"` als Provenienz-Feld. Keine Änderung am Annotation-Indexing nötig.

**Routing:** Im `index_book`-Pfad (oder wo auch immer der Adapter aufgerufen wird):
```python
if adapter.adapter_type == "zotero":
    if book_metadata.get('comments'):
        chunks += _build_zotero_abstract_chunk(...)
    notes = adapter.get_notes(doc_id)
    if notes:
        chunks += _build_zotero_note_chunks(notes, ...)
    # Annotations: unverändert — AnnotationProvider liefert bereits annotation_source="zotero"
elif adapter.adapter_type == "calibre":
    chunks += _build_comment_chunks(...)  # unverändert
```

**Aufwand:** 3–5 h (inkl. parse_html_comment-Refactor und Atomic-Block-Check) — reduziert, da Annotation-Builder entfällt

### A5 — Annotation-Provider: Provenienz prüfen
**Datei:** `scripts/rag_demo.py` (Zeilen ~1146 und ~1694)

**Keine chunk_type-Änderung nötig.** Aber prüfen: Wird beim Chunk-Bau aus einer `Annotation` mit `source="zotero"` das Feld `annotation_source="zotero"` korrekt gesetzt? Falls ja: kein Code-Change. Falls nein: das ergänzen, damit die Provenienz im Index sichtbar bleibt.

```python
# An den Annotation-Indexing-Stellen sicherstellen:
'annotation_source': annotation.source,  # statt hartkodiert "calibre_viewer"
```

**Aufwand:** 15 min Code-Check + ggf. 15 min Fix

### A6 — Filter-Aliase im Store
**Datei:** `src/storage/lancedb_store.py`, `_build_filter` (≈ Zeile 576)

Aktuell:
```python
elif chunk_type == ChunkType.ANNOTATIONS_AND_COMMENTS:
    conditions.append(f"(chunk_type = '{ChunkType.ANNOTATION}' OR chunk_type = '{ChunkType.CALIBRE_COMMENT}')")
```

Erweitern zu:
```python
elif chunk_type == ChunkType.ANNOTATIONS_AND_COMMENTS:
    conditions.append(
        "chunk_type IN ("
        f"'{ChunkType.ANNOTATION}', "
        f"'{ChunkType.CALIBRE_COMMENT}', '{ChunkType.ZOTERO_NOTE}', "
        f"'{ChunkType.ZOTERO_ABSTRACT}'"
        ")"
    )
```

Außerdem prüfen: Hash-Logik in `_collect_indexed_books` (ab `lancedb_store.py:813`) ergänzen — `ZOTERO_NOTE` und `ZOTERO_ABSTRACT` zählen wie `CALIBRE_COMMENT` zur Metadaten-Klasse; Annotation-Logik bleibt unverändert (Quelle steckt in `annotation_source`, nicht in `chunk_type`).

**Aufwand:** 30 min + 30 min für Hash-Logik

### A7 — calibre_mcp/server.py: Filter-Erweiterung prüfen
**Datei:** `src/calibre_mcp/server.py:289`

Aktuell wird `chunk_type_filter=ChunkType.ANNOTATIONS_AND_COMMENTS` benutzt — sobald A6 erweitert ist, zieht der MCP-Server Zotero automatisch mit. **Manueller Test nötig**, dass das gewünschte Verhalten ist (oder ob es einen separaten Filter `ZOTERO_NON_CONTENT` braucht).

**Aufwand:** 15 min Test, ggf. 30 min Anpassung

### A8 — Web-UI Labels
**Datei:** `scripts/web_ui.py:225-227, 458-459`

Neue Emoji-Labels für die UI (User-Input-orientiert, nicht zwingend für MVP):
```python
ChunkType.ZOTERO_ABSTRACT: '📄 Zotero-Abstract',
ChunkType.ZOTERO_NOTE:     '📝 Zotero-Notiz',
# Annotations bleiben unter dem generischen Label; Provenienz kann optional
# über annotation_source in der Detail-Anzeige differenziert werden
```

**Aufwand:** 15 min

### A9 — Tests
**Datei:** `tests/test_zotero_adapter.py`, neue Datei `tests/test_zotero_indexing.py`

- `test_zotero_abstract_indexing`: Item mit abstractNote → genau ein Chunk, `chunk_type=zotero_abstract`
- `test_zotero_note_indexing`: Note mit H1/H2/H3 → erwartete Anzahl Sektionen, `chunk_type=zotero_note`
- `test_zotero_note_blockquote_atomic`: Note mit `<blockquote>` über mehrere Absätze → Blockquote bleibt in einem Chunk
- `test_zotero_annotation_provenance`: Annotation aus Zotero-Provider → `chunk_type=annotation`, `annotation_source="zotero"`
- `test_zotero_metadata_hash_includes_notes`: Hash ändert sich, wenn Note-HTML sich ändert
- `test_filter_alias_includes_zotero`: `chunk_type_filter=ANNOTATIONS_AND_COMMENTS` zieht Zotero-Typen mit

**Aufwand:** 2 h

## Reihenfolge der Umsetzung

```
A1 (Konstanten)
 └─> A6 (Filter)        ← parallel zu A2/A3
 └─> A2/A3 (Adapter)
      └─> A4 (Builder)
           └─> A5 (Annotation-Routing)
                └─> A7 (MCP-Test)
                └─> A8 (UI-Labels)
                └─> A9 (Tests)
```

Pragmatisch: A1+A6+A3 als ersten Commit (Schema steht), A4+A5 als zweiter (Indexing produziert die richtigen Typen), A7–A9 als dritter (Konsumenten + Tests).

## Gesamtaufwand (Phase A)

**~8–11 Stunden Code + Reindex eines Test-Sets zur Verifikation.** Verteilt über 2–3 Sessions machbar.

## Redundanz bei Annotation→Notiz-Konvertierung in Zotero

(Aus Konversation: User wandelt Annotations in eine Notiz, fügt später eine weitere hinzu, importiert erneut → zwei Notizen, zweite enthält Untermenge der ersten.)

**Auswirkung auf den Index, falls beide Notizen im Zotero-Item bleiben:**
- Beide Notizen werden indiziert → identischer Inhalt liegt mehrfach in LanceDB
- Suchergebnisse: bei Hybrid-Search ranken beide ähnlich hoch → ein Treffer wird im UI doppelt sichtbar
- Diversifikation in `archilles_service._diversify` greift auf Buch-Ebene (`max_per_book`) — sie würde die Duplikate dämpfen, aber nicht eliminieren

**Optionen für später (kein MVP-Blocker):**
1. Im Notiz-Builder Hash über den HTML-Inhalt; Notiz mit gleichem Hash wird übersprungen (innerhalb desselben Items)
2. UX: in der Doku darauf hinweisen, dass Nutzer redundante Annotations-Notes bereinigen sollten
3. Nichts tun und beobachten

**Empfehlung:** Option 2 zum Start (Doku-Hinweis), Option 1 nachrüsten, falls es in der Praxis stört.

## Phase B (optional, nach Phase A) — PDF-Abstract-Auto-Extraktion

**Idee (User, 2026-05-09):** Wissenschaftliche PDFs haben oft einen Abstract auf der ersten Seite. Diesen automatisch erkennen und in dasselbe Feld schreiben — quellenunabhängig, also auch für Calibre-PDFs, und auch dann, wenn in Zotero `abstractNote` leer ist.

**Heuristiken (kombinieren, in dieser Reihenfolge):**

1. **Section-Header-Match** auf den ersten 1–2 Seiten:
   - Regex `^\s*(Abstract|Zusammenfassung|Summary|Résumé|Resumen)\b\s*[:.]?\s*$` als eigene Zeile
   - Inhalt = Text ab dieser Zeile bis zur nächsten Section-Headline (Introduction, Keywords, 1\., I\., etc.) oder bis Seitenende
2. **Strukturelle Position** als Fallback: Block zwischen Title/Author-Block und erster nummerierter/benannter Section auf S. 1
3. **Sanity-Checks:**
   - Wortanzahl 50–500 (sonst verwerfen)
   - Keine Bullet-/Tabellen-Strukturen (deutet auf TOC oder Liste hin)
   - Sprache passt zur Dokument-Sprache (langdetect optional)

**Architektur:**
- Neuer Extraktor-Schritt `src/extractors/abstract_detector.py` mit Funktion `detect_abstract(pdf_path, first_pages_text) -> str | None`
- Aufruf im PDF-Extraktions-Pfad **nach** dem Text-Extract, **vor** dem Chunking
- Wenn detektiert UND `book_metadata['comments']` ist leer:
  - Bei Zotero-Items: in `comments` schreiben → läuft durch `_build_zotero_abstract_chunk`
  - Bei Calibre-Items: ebenfalls in `comments` schreiben → **aber** mit speziellem Marker, damit der Builder weiß, dass es ein erkannter Abstract ist und nicht ein Calibre-Klappentext. Empfohlen: zusätzliches Feld `book_metadata['detected_abstract']` und neuer chunk_type-Pfad, der `ChunkType.ZOTERO_ABSTRACT` (Name dann ggf. zu `ChunkType.ABSTRACT` umbenennen, da quellenunabhängig) erzeugt.

**Naming-Frage zu klären:** Wenn Phase B kommt, ist `ZOTERO_ABSTRACT` zu eng. Zwei Optionen:
- (a) **In Phase A bereits `ChunkType.ABSTRACT` benennen**, semantisch neutral. Vorteil: kein Rename in Phase B. Nachteil: aktuell nur Zotero füllt das Feld.
- (b) `ZOTERO_ABSTRACT` jetzt, in Phase B Migration zu `ABSTRACT`. Vorteil: Name spiegelt aktuelle Realität. Nachteil: Schema-Migration nötig.

**Empfehlung:** **(a) — direkt `ChunkType.ABSTRACT` benennen.** Kostet nichts und macht Phase B reibungslos. Im Plan ist bisher überall `ZOTERO_ABSTRACT` notiert; vor Umsetzung am Dienstag entscheiden, dann konsistent benennen.

**Aufwand Phase B:** 4–6 h (Heuristik + Tests mit 5–10 echten Papern aus deinem Bestand)

**Risiken:**
- Falsch-Positive bei Sammelbänden, Vorworten, Buchbesprechungen
- OCR-Qualität bei gescannten PDFs schlecht — Heuristiken werden unzuverlässig
- Sprachenvielfalt: User hat mehrsprachige Bibliothek (DE/EN/FR/ES?)

**Mitigation:** Nur „high-confidence" Detektionen ins Feld schreiben. Ein optionales `--detect-abstracts` CLI-Flag fürs Erst-Rollout, nicht standardmäßig aktiv.

## Was nach Phase A+B ansteht

- **Strukturbewusstes Reranking** (Ursprungsthema): Mit korrekt gelabelter Datenbasis kann dann ein Gewichtungsschema über `chunk_type` definiert werden. Vorschlag:
  - `content` (main): 1.0
  - `abstract` (= ehem. zotero_abstract, quellenunabhängig): 0.95
  - `calibre_comment`: 0.85
  - `zotero_note`: 0.85
  - `annotation`: 0.80 (quellenunabhängig — Provenienz via `annotation_source`)
  - `front_matter`: 0.7 / `back_matter`: 0.5
- **Eval-Harness** zuerst (siehe Vorgespräch): 20–30 Gold-Queries, bevor Gewichte fixiert werden.
