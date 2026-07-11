# Design: Zotero-Indexierung auf Calibre-Parität bringen

**Datum:** 2026-07-11
**Status:** Genehmigt (Design), bereit für Planung
**Betroffene Bereiche:** `scripts/run_routine.py`, `scripts/watchdog.py`, `src/archilles/watchdog.py`

## Problem

Die Zotero-Routine indexiert neue Titel **grundsätzlich nie**. Über alle
protokollierten Läufe hinweg steigt `new_books` (476 → 523), während
`new_indexed` konstant `0` bleibt. Neue Items werden nur *queued* und gezählt.

**Ursache:** `run_routine.py` `_build_command` fügt die Index-Flags
(`--index-new` / `--index-metadata-only` / `--index-fulltext-pending`) nur im
Zweig `if adapter == "calibre"` hinzu. Für Zotero läuft ein nacktes
`watchdog.py --json`; da `--index-new` in `watchdog.py` per Default aus ist
(`--queue-new` an), werden neue Zotero-Items nie eingebettet — unabhängig vom
Modus.

Zusätzlich fehlt dem `ZoteroWatchdogScanner` die Priorisierungs-Ergonomie des
Calibre-Scanners (`max_new`-Cap, Prioritäts-Sortierung).

## Ziel

Zotero soll **nach außen möglichst gleichwertig zu Calibre** funktionieren
(Zotero ist im akademischen Umfeld das verbreitetere Tool). Das umfasst:

1. Neue Zotero-Titel werden von der Routine tatsächlich indexiert.
2. Saubere Integration in den externen Embedding-Lauf (`full-external`-Modus).
3. Der lokale Indexierungspfad **und** der Watchdog funktionieren korrekt für
   OSS-Nutzer, die *kein* externes Embedding verwenden (Produktqualität).
4. Prioritäts-gesteuerte Indexierung mit **Zotero-nativen** Konzepten.

## Nicht-Ziele

- Kein A/B-Phasenmodell für Zotero. Zotero kennt keinen
  `PHASE1_METADATA`-Stub-Zwischenzustand — ein Item ist voll indexiert oder
  „neu". Der Calibre-Begriff „Phase A" bildet sich auf Zotero *nicht* ab.
- Keine Scanner-Basisklasse (das ist Watchdog-Schritt B, ein eigenes Vorhaben).
- Kein `--rating` für Zotero: Zotero hat kein natives Rating-Feld (nur via
  Plugin/„Extra"-Feld). `--rating` bleibt Calibre-only.

## Prioritätsmodell für Zotero (ersetzt Calibres Rating)

Ein Zotero-Item landet in **Gruppe 0 (Vorrang)**, wenn es einen der
Prioritäts-Filter trifft (case-insensitive Substring, wie Calibres `--first-tag`
heute):

- `--first-tag` — Zotero-Tags
- `--first-author` — Zotero-Creators (Autoren)
- `--first-title` — Titel
- `--first-collection` — **neu:** Zotero-Sammlungen (Collections)

**Sortierschlüssel (Tupel, lexikografisch):**

```
(gruppe, secondary_order, recency)
  gruppe          0 = Prioritäts-Treffer, 1 = Rest
  secondary_order Calibre: Rating-Ordnung (5★/4★/Rest); Zotero: immer 0
  recency         neuestes zuerst (Zotero: dateAdded; Calibre: -calibre_id)
```

**Konfliktregel (Variante A, bewusst gewählt):** Explizite Priorität schlägt
Recency. Ein alter, aber getaggter/in einer Sammlung liegender Titel wird vor
neuen, ungetaggten Titeln indexiert. Recency ist voll wirksam, aber als
Ordnungskriterium *innerhalb* jeder Gruppe (Tie-Breaker). Begründung: Ein
Tag/eine Collection ist ein bewusstes „das brauche ich jetzt"-Signal — stärker
als das implizite „neu = wahrscheinlich relevant". Neu-Hinzugekommenes ohne Tag
steht trotzdem sofort ganz vorne in Gruppe 1.

## Änderungen

### `src/archilles/watchdog.py`

1. **`_zotero_metadata_for_scan`**
   - `dateAdded` in den Items-SELECT aufnehmen (für Recency-Sortierung).
   - Eine zusätzliche Batch-Query über `collections` + `collectionItems` →
     `collections: list[str]` je Item (gleiches Ein-Pass-Batch-Muster wie die
     bestehenden Tag-/Creator-/Feld-Queries).

2. **Prioritäts-Helper generalisieren** (`_index_priority_key`)
   - In einen datenmodell-agnostischen Kern aufteilen: der Matcher prüft
     Autoren/Tags/Titel/**Collections** (Substring, case-insensitive) und liefert
     `is_priority`; der Sortier-Tie-Breaker ergibt sich aus `(is_priority,
     secondary_order, recency)`.
   - Calibre reicht `secondary_order` aus dem Rating; Zotero reicht `0`.
   - Der **Calibre-Pfad bleibt verhaltensgleich** (Regression-Tests grün).

3. **`ZoteroWatchdogScanner.scan()`**
   - Neue Parameter: `max_new`, `first_authors`, `first_tags`, `first_titles`,
     `first_collections`.
   - Neue Items nach Prioritäts-Key sortieren, dann auf `max_new` cappen.
   - Full-external-Verhalten (`mark_pending` → `pending_external`) bleibt
     unverändert.
   - **Kein separater Checkpoint** (siehe Resumability).

### `scripts/watchdog.py` (CLI)

- Neues `--first-collection` (append-Flag).
- `max_new` / `first_authors` / `first_tags` / `first_titles` /
  `first_collections` künftig auch für Zotero in `scan_kwargs` durchreichen
  (heute Calibre-only Block).
- `--rating` bleibt Calibre-only: bei Zotero wird es ignoriert und gibt eine
  `WARNING` auf stderr aus (analog zum bestehenden `--phase`-Hinweis für
  Nicht-Calibre-Adapter).

### `scripts/run_routine.py` (`_build_command`)

- Für Zotero `--index-new` ergänzen.
- Dieselben Prioritäts-/Cap-Flags durchreichen, die heute schon gefädelt werden
  (`--first-tag`, `max_new`), erweitert um `--first-collection`.

## Fehlerbehandlung & Resumability

- **Kein separater Zotero-Checkpoint** (bewusste Entscheidung): Zotero hat keinen
  Stub-Zwischenzustand. Bei CTRL+C beendet das laufende Item, dann Stopp;
  nicht-indexierte Items sind beim nächsten Lauf wieder „neu" → natürliches
  Fortschreiten. `index_book(force=False)` ist idempotent → kein Doppelaufwand.
- `max_new` begrenzt die Lauflänge; die Prioritäts-Sortierung stellt sicher, dass
  bei einem gecappten Lauf die wichtigsten Items zuerst indexiert werden.
- Orphan-Cleanup, Leer-Snapshot-Guard und Hash-Load-Guard sind im
  Zotero-Scanner bereits vorhanden und bleiben unangetastet.

## Tests

- **Prioritäts-Key (Unit):** Calibre-Rating-Pfad unverändert; Zotero-Pfad ordnet
  Collection-/Tag-/Autor-/Titel-Treffer vor den Rest, dann nach Recency;
  Variante-A-Konflikt (alter getaggter vs. neuer ungetaggter Titel) explizit
  getestet.
- **`_zotero_metadata_for_scan`:** liefert `collections` + `dateAdded`.
- **`ZoteroWatchdogScanner.scan(index_new=…)`:** Items werden indexiert,
  `max_new` gecappt, Prioritätsreihenfolge korrekt, full-external markiert
  `pending_external`.
- **`run_routine`:** baut das korrekte Zotero-Kommando mit `--index-new`.
- **Regression:** bestehende Calibre-Scanner-Tests bleiben grün.

## Verifikation (OSS-Produktqualität)

End-to-End-Verifikation des lokalen Pfads (`embed_local=True`): ein frischer
Nutzer ohne externes Embedding bekommt funktionierende Zotero-Indexierung —
neue Items werden indexiert und sind durchsuchbar.

## Umsetzungsreihenfolge

1. **Schritt 1 (klein, zuerst — läuft heute):** `--index-new` in die
   Zotero-Routine verdrahten, optional mit `max_new`-Cap (kleinste
   Signatur-Erweiterung von `ZoteroWatchdogScanner.scan`). Bringt die ~523 neuen
   Titel sofort zum Fließen; Reihenfolge zunächst per natürlicher
   Recency/Reihenfolge, verifizierbar mit einem gecappten Real-Lauf.
   Achtung: `--first-tag` wird heute nur an den Calibre-Scanner durchgereicht —
   echte Prioritäts-Sortierung für Zotero kommt erst mit Schritt 2.
2. **Schritt 2:** volle Prioritäts-Parität — `--first-tag`/`--first-author`/
   `--first-title`/`--first-collection` für Zotero durchreichen,
   `dateAdded`-Recency, Helper-Generalisierung + vollständige Tests.
