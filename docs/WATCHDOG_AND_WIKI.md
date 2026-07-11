# Watchdog & Wiki — Spezifikation

| | |
|---|---|
| **Status Teil I (Watchdog)** | Dokumentation des Ist-Stands — produktiv seit April 2026; beschreibt den Code-Stand `e944349` (2026-07-08) |
| **Status Teil II (Wiki-Generator)** | Ausgelagert (2026-07-11) → `archilles-scriptor/docs/internal/KONZEPT_wiki_zitatgraph_v1.md`; hier nur Kontrakt-Kurzfassung |
| **Stand** | 2026-07-11 (Teil II ausgelagert, inkl. §II.12 Hypertext-Ausbaustufe) |
| **Bezüge** | ROADMAP.md (v1.0 Watchdog, v1.5 Wiki), ADR-011 (metadata_hash), ADR-025 (Scheduled Routines), ADR-028 (Hardware-Tiers / full-external) |

---

# Teil I — Watchdog (Ist-Stand)

## I.1 Zweck

Der Watchdog hält LanceDB mit den Quellbibliotheken synchron, ohne Daemon und
ohne Schreibzugriff auf die Quellen. Er ist ein **idempotenter Scan**: beliebig
oft aufrufbar, Hash-Vergleiche überspringen Unverändertes. Implementierung:
`src/archilles/watchdog.py` (`WatchdogScanner` für Calibre,
`ZoteroWatchdogScanner` für Zotero).

Aufrufwege:

- `scripts/watchdog.py` — Standalone-CLI (direkt, cron, Windows Task Scheduler)
- MCP-Tool `watchdog_scan` in `src/calibre_mcp/server.py` (Claude Routines)
- Windows-Scheduler-Tasks (OnLogon) für die tägliche Routine (ADR-025)

## I.2 Drei Änderungstypen

| Typ | Erkennung | Reaktion |
|---|---|---|
| `new_books` | Calibre-ID in `metadata.db`, aber nicht in LanceDB | Queue (`index_queue.json`) oder sofortige Indexierung |
| `metadata_changed` | `metadata_hash` (Titel, Autor, Tags, Comments, Publisher — ADR-011) weicht ab | Delta-Update via `index_book()` (~1–3 s/Buch) |
| `annotations_changed` | `annotation_hash` weicht ab | Delta-Update via `index_book()` |

Die Hash-Berechnung liegt zentral in `src/archilles/hashing.py`; der
Metadaten-Scan ist reines SQLite-I/O (kein Buch wird geöffnet). Für
Annotationen hält ein `(mtime_ns, size)`-Signatur-Cache
(`watchdog_annotation_cache.json`) die Wiederholungs-Scans im Sekundenbereich:
nur Bücher mit veränderter Signatur werden erneut geöffnet.

## I.3 Scan-Phasen

1. **Fast Scan** — SQLite lesen, Hashes vergleichen, Änderungen klassifizieren.
   Bücher mit ausgeschlossenen Tags (`config.get_excluded_tags`) werden
   übersprungen. Schlägt das Laden der gespeicherten Hashes fehl, bricht der
   Scan die Folgephasen ab, statt die ganze Bibliothek für „neu" zu halten.
2. **Delta-Updates** — Metadaten-/Annotations-Änderungen anwenden.
3. **Neue Bücher** — je nach Flags: nur queuen (`queue_new`), sofort voll
   indexieren (`--index-new`) oder als schnellen Metadaten-Stub anlegen
   (`--index-metadata-only`, Phase A der Zwei-Phasen-Indexierung).
4. **Volltext-Backlog** — `--index-fulltext-pending` (Phase B) füllt Bücher
   auf, die bisher nur einen `PHASE1_METADATA`-Stub haben.

Phasen 3 und 4 sind checkpoint-gestützt (`IndexingCheckpoint`), unterstützen
Graceful Shutdown (CTRL+C stoppt nach dem laufenden Buch, Checkpoint bleibt)
und priorisieren die Reihenfolge: explizite Prioritätslisten
(`first_authors` / `first_tags` / `first_titles`), dann Rating (5★, 4★, Rest),
dann Aktualität (jüngste Calibre-ID zuerst).

Unter `mode: full-external` (ADR-028) werden neue Titel provisorisch flach
lokal indexiert und `pending_external` markiert; ein späterer externer
Embed-Lauf wertet sie auf.

**Index-Pflege (seit 2026-07-07, `d491093`):** Nach jedem Lauf, der Zeilen
geschrieben hat, ruft `_refresh_search_indexes()` `ensure_vector_index()` +
`optimize_indexes()` auf. Hintergrund: Die Watchdog-Pfade indexierten via
`index_book()` und refreshten — anders als batch_index/embed_prepared — nie
einen Index; wochenlange Routine-Läufe ließen so 1,2 Mio. Zeilen außerhalb
des FTS-Index auflaufen, und jede Keyword-/Hybrid-Suche scannte sie
brute-force (>5 min statt <1 s, Cowork-MCP-Timeouts). Die Pflege wirft nie —
sie darf einen erfolgreichen Scan nicht scheitern lassen.

## I.4 Zotero-Scanner

Gleiches Muster, angepasste Signale: Metadaten-Hash über Titel/Autoren/Tags/
Abstract/Datum; Annotations-Änderungen über das `dateModified` des Attachments
als Proxy. Der Scanner liest `zotero.sqlite` read-only (WAL-Snapshot) und
re-indexiert über den `ZoteroAdapter`.

## I.5 Änderungsprotokoll

Jeder Lauf schreibt einen strukturierten Block nach
`<archilles_dir>/watchdog.log` (Zeitstempel, Zähler pro Änderungstyp,
Buch-IDs, Fehler, Laufzeiten). **Dieses Protokoll ist die Datenquelle für die
inkrementellen Wiki-Updates in Teil II** — der Watchdog weiß als einziger
Baustein zuverlässig, *welche* Bücher sich seit dem letzten Lauf geändert
haben.

## I.6 Bekannte offene Fäden

Bewusst zurückgestellt (Stand /simplify-Durchgang 2026-07-07), damit dieser
Teil den Ist-Stand nicht schöner beschreibt, als er ist:

- **`ZoteroWatchdogScanner` ist ein struktureller Klon** des Calibre-Scanners
  (~330 Zeilen Copy-Paste-Verwandtschaft). Scanner-Basisklasse und die
  Vereinigung der Phase-3/4-Loops gehören als Ganzes zur
  Watchdog-Generalisierung „Schritt B" (ROADMAP, nach v1.0) und werden dort
  gebündelt — nicht häppchenweise.
- **Annotation-Hash-Berechnung ist Calibre-verdrahtet:** Der Scanner (wie der
  Indexer) ruft hart `get_combined_annotations` statt
  `adapter.get_annotations` (Rest von Review-Befund 4.1a). Der Umzug muss mit
  der Hash-Berechnung im Indexer koordiniert erfolgen — eigene Session.
- **Watchdog-SQL vs. Adapter-Batch-Fetcher:** `_calibre_metadata_for_hash`
  dupliziert die Feld-Konvention des Adapters per SQL. Zusammenführung ist
  wegen des Hash-Contracts riskant (eine stille Format-Abweichung löst einen
  Reindex-Sturm aus) und bleibt zurückgestellt.

---

# Teil II — Wiki-Generator (ausgelagert)

> **Ausgelagert am 2026-07-11.** Der vollständige Wiki-Generator-Entwurf ist
> als Teil B in das Konzeptpapier
> `archilles-scriptor/docs/internal/KONZEPT_wiki_zitatgraph_v1.md`
> umgezogen und wird dort weitergeführt — zusammen mit den neuen Schichten
> Typklassifikation, LLM-Parsing-Stufenleiter, Referenz-Resolution,
> Hypertext und Föderation (Zitatgraph). Hier verbleibt nur die
> repo-übergreifend normative Kurzfassung des Zitier-Kontrakts
> (vormals §II.5); externe Verweise auf »§II.5« bleiben damit gültig.

## II.5 Zitier-Kontrakt (normative Kurzfassung)

- Beleganker-Syntax: `[src: <chunk_id> · p. <seite>]`; mehrere Anker mit
  `; ` in einer Klammer; greppbar über `\[src: `.
- `<seite>` ist das `page_label` des Chunks — das **gedruckte** Seitenlabel,
  zitierfähig, römisch erlaubt (`xiv`) —, Fallback `page_number` (physische
  PDF-Seite); ohne Seitenbezug trägt der Anker die Sektion. Das ist exakt
  die `[p. NN]`-Semantik des Scriptor-Liefertexts: Scriptor und Wiki sind
  die beiden Enden derselben Zitierbarkeits-Pipeline und dürfen bei
  »was heißt Seite« nicht auseinanderdriften.
- Chunk-IDs (`{book_id}_chunk_{i}`) sind index-basiert und können bei
  Reindex verschieben; Anker sind deshalb redundant angelegt (book_id +
  Seite/Sektion bleiben menschlich und maschinell auflösbar, auch wenn der
  `chunk_index` verschoben ist); ein Verifikationspass (`verify_citation`)
  kann veraltete Anker über Buch + Seite + Textabgleich re-lokalisieren,
  statt sie nur als tot zu melden.
