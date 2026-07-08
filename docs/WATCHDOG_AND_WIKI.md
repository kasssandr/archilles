# Watchdog & Wiki — Spezifikation

| | |
|---|---|
| **Status Teil I (Watchdog)** | Dokumentation des Ist-Stands — produktiv seit April 2026; beschreibt den Code-Stand `e944349` (2026-07-08) |
| **Status Teil II (Wiki-Generator)** | Entwurf — geplant für v1.5 (Community-Release) |
| **Stand** | 2026-07-08 |
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

# Teil II — Wiki-Generator (Entwurf)

## II.1 Zweck und Einordnung

Ein LLM-gestützter Generator, der aus dem indexierten Bestand ein
navigierbares Markdown-Wiki destilliert: **Buch-Seiten** (ab konfigurierbarem
Rating-Schwellwert), **Entitäten-Seiten** (Personen, Orte, Konzepte) und
**Themen-Seiten**. Das Wiki ist ein leichtgewichtiger Wissensgraph in
Textform — die menschenlesbare Vorstufe des formalen Graph RAG (v2.0).

Das Architekturmuster ist extern bestätigt: Anthropics Claude Science
(Juni 2026) setzt dieselbe Zwischenschicht ein — Sub-Agenten extrahieren aus
tausenden Papers Claims und Kernbefunde in eine *evidence state database*, aus
der Reviews sektionsweise generiert und von einem Reviewer-Agenten auf
Zitattreue geprüft werden. Das Wiki ist das geisteswissenschaftliche Pendant
dieser Schicht: strukturierte, quellenverankerte Destillate zwischen Retrieval
und Prosa. Daraus folgen zwei Gattungsmerkmale, die dieser Entwurf normativ
setzt:

1. **Jede destillierte Aussage trägt einen Beleganker** (§II.5). Was in den
   Naturwissenschaften Reproduzierbarkeit heißt, heißt hier Belegbarkeit —
   Auditierbarkeit ist kein Komfort, sondern konstitutiv.
2. **Ein optionaler Verifikationspass** prüft nach der Generierung gegen den
   LanceDB-Index, ob zitierte Passagen an der behaupteten Stelle stehen
   (§II.7, Actor-Critic-Muster).

## II.2 Zielformat: Open Knowledge Format (OKF) v0.1

Der Generator emittiert ein **OKF-konformes Bundle**
(Spec: <https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf>).
OKF formalisiert genau das Muster, das der Wiki ohnehin geplant hatte
(Verzeichnis von Markdown-Dateien, eine Datei pro Konzept, YAML-Frontmatter,
Links als Graphkanten) — der Mehraufwand gegenüber einem proprietären Layout
ist minimal, der Gewinn ist Standard-Kompatibilität: jeder OKF-Consumer
(Visualizer, fremde Agenten, künftige Kataloge) kann das Wiki lesen. ARCHILLES
positioniert sich damit als einer der ersten OKF-*Producer* für persönliche
Bibliotheken statt Enterprise-Datenkatalogen.

**Architekturprinzip (übernommen aus der Scriptor-v2-Konzeption, §9 Q1):**
Die Laufzeit-Wahrheit ist nicht die Markdown-Datei, sondern ein strukturiertes
internes Modell (Seiten-Objekte mit Claims, Ankern, Links). OKF ist ein
**Serialisierungs-Codec** über diesem Modell. Ändert OKF v0.2 die Frontmatter,
wird ein Codec angepasst, kein Datenmodell. Schreiben *und* (für inkrementelle
Updates) Wiederlesen laufen durch dieses Modell, nie über Ad-hoc-Regex.

**Obsidian-Kompatibilität ohne `[[Wikilinks]]`:** Es werden ausschließlich
normale Markdown-Links emittiert (relativ bzw. bundle-absolut mit führendem
`/`, wie von OKF definiert). Obsidian löst Standard-Markdown-Links nativ auf;
`[[Wikilinks]]` versteht außerhalb von Obsidian fast niemand. Eine
konfigurierbare Doppel-Emission ist Vorratsbau und entfällt (YAGNI).
„Obsidian-kompatibel, aber nicht -abhängig" heißt konkret: OKF-konform.

## II.3 Bundle-Layout

```
wiki/                          # output_dir, konfigurierbar (§II.9)
  index.md                     # Einstieg, progressive disclosure; einzige Datei
                               # mit okf_version: "0.1" in der Frontmatter
  log.md                       # Änderungshistorie (§II.8), neueste zuerst
  books/
    mommsen_roemische-geschichte.md      # type: book
  entities/
    theodor-mommsen.md                   # type: entity
  topics/
    roemische-verfassungsgeschichte.md   # type: topic
```

- Dateiname = Slug aus Autor/Titel bzw. Entitäts-/Themenname (ASCII,
  kebab-case; Umlaute transliteriert). Der Dateipfad ist die Identität des
  Konzepts (OKF-Prinzip); Slugs sind daher **stabil** — eine Titelkorrektur in
  Calibre ändert den Anzeigetitel (`title`), nicht den Slug.
- `index.md` und `log.md` sind reservierte Dateien und keine Konzepte.
- `index.md` gruppiert nach Seitentyp und verlinkt mit Ein-Satz-Beschreibungen
  (progressive disclosure für navigierende Agenten).

## II.4 Frontmatter-Mapping

OKF verlangt nur `type`; alles Weitere ist empfohlen bzw. Producer-Erweiterung
(Consumer müssen unbekannte Felder erhalten). Das Wiki nutzt:

```yaml
---
type: book                        # Pflicht: book | entity | topic
title: "Römische Geschichte"      # Anzeigename
description: "Mommsens dreibändige Darstellung der römischen Republik."
resource: "archilles://calibre/1234"   # URI des zugrundeliegenden Assets
tags: ["Geschichte", "Antike"]    # Bücher: Calibre-Tags; Entitäten: Gattung
timestamp: "2026-07-08T14:30:00+02:00"  # letzte inhaltliche Änderung
# ── Producer-Erweiterungen (Namensraum archilles_*) ──
archilles_source: "calibre"       # Adapter: calibre | zotero | obsidian | folder
archilles_source_id: "1234"       # book_id / item_key des Adapters
archilles_rating: 5               # nur type: book
archilles_language: "de"          # nur type: book
archilles_aliases: ["Mommsen, Theodor"]  # nur type: entity (Disambiguierung)
---
```

Festlegungen:

- **`type` bleibt flach** (`book` / `entity` / `topic`). Die Entitäts-Gattung
  (Person, Ort, Konzept) wandert in `tags` (z. B. `["person"]`) — OKF-Consumer
  sollen mit drei selbsterklärenden Typen auskommen, nicht mit einer Taxonomie.
- **`resource`** nutzt das Schema `archilles://<adapter>/<source_id>`. Es ist
  bewusst adapter-agnostisch; eine zusätzlich klickbare `calibre://…`-URL kann
  im Body stehen, ist aber nicht Teil des Kontrakts.
- **Beleganker stehen nicht in der Frontmatter** (§II.5): Anker gehören zur
  einzelnen Aussage, Frontmatter zum Konzept. Ein Frontmatter-Feld könnte nur
  die Belegliste der ganzen Seite tragen und entwertete den Anker.

## II.5 Beleganker (Body-Konvention)

Jede destillierte Aussage endet mit mindestens einem Anker:

```
Mommsen deutet die Gracchen-Krise als Beginn der Revolution
[src: 1234_chunk_87 · p. 312].
```

**Syntax:** `[src: <chunk_id> · p. <seite>]` — mehrere Anker mit `; ` getrennt
in einer Klammer: `[src: 1234_chunk_87 · p. 312; 1234_chunk_88 · p. 313]`.
Greppbar über `\[src: `. Das Sigil-Prinzip (kompakte, maschinenlesbare
Inline-Marke, die gegen normale Markdown-Syntax disambiguiert) entspricht der
Scriptor-Flag-Syntax `[?FN:…]`.

**Seitenzahl-Semantik — Kontrakt mit dem Chunk-Schema:** `<seite>` ist das
`page_label` des Chunks (das *gedruckte* Seitenlabel, zitierfähig, z. B.
`xiv` oder `312`), mit Fallback auf `page_number` (physische PDF-Seite), wenn
kein Label vorliegt. Das ist exakt die Semantik, die die `[p. NN]`-Marker des
Scriptor-„Vektor"-Liefertexts beim Chunking erzeugen (das Label darf römisch
sein, `[p. xiv]`) — Scriptor und Wiki sind die beiden Enden derselben
Zitierbarkeits-Pipeline und dürfen bei „was heißt Seite" nicht
auseinanderdriften. Bei Chunks ohne Seitenbezug (EPUB ohne Print-Labels) trägt
der Anker stattdessen die Sektion: `[src: 1234_chunk_87 · Kap. „Die Gracchen"]`.

**Stabilitäts-Vorbehalt:** Chunk-IDs haben die Form `{book_id}_chunk_{i}` und
sind index-basiert — ein Reindex des Buchs kann sie verschieben. Der Anker ist
deshalb **redundant**: `book_id` (im Chunk-ID-Präfix) plus Seite/Sektion
bleiben auch bei verschobenem `chunk_index` menschlich auflösbar, und der
Verifikationspass (§II.7) kann einen veralteten Anker über Buch + Seite +
Textabgleich re-lokalisieren statt ihn nur als tot zu melden.

## II.6 Seitentypen und Erzeugung

**Buch-Seiten** (Kern, zuerst gebaut): Für jedes Buch ab
`rating_threshold` werden zusammengeführt: Calibre-Metadaten, Comments,
Annotationen (Highlights/Notizen aus der Annotation-Engine) und die semantisch
dichtesten Content-Chunks. Das LLM destilliert daraus eine strukturierte Seite
(Kernthesen, Aufbau, zentrale Begriffe/Personen, Verhältnis zu Annotationen) —
jede Aussage mit Beleganker. Links auf Entitäten- und Themen-Seiten entstehen
hier als normale Markdown-Links.

**Entitäten-Seiten:** Personen, Orte, Konzepte, die auf mehreren Buch-Seiten
vorkommen. Aggregieren die Aussagen der Buch-Seiten (mit deren Ankern) statt
neu zu retrieven — die Buch-Seite ist die Evidenzschicht, die Entitäts-Seite
die Quervernetzung. Entitäts-Extraktion in v1.5 LLM-basiert aus den
Buch-Seiten selbst; Wikidata-Disambiguierung bleibt v2.0-Evaluation.

**Themen-Seiten:** Synthese über Bücher hinweg („Was sagt meine Bibliothek zu
X?"). Themen werden initial aus Tag-Clustern und Entitäts-Häufungen
vorgeschlagen, nicht frei halluziniert; der Nutzer kann Themen anfordern.
Als quellenverankerte Claim-Sammlung sind Themen-Seiten das natürliche
Substrat für die Behandlung widersprüchlicher Quellen in v2.0.

**Reihenfolge der Implementierung:** Buch-Seiten → `index.md`/`log.md` →
Verifikationspass → Entitäten → Themen. Jede Stufe ist für sich nützlich
(Scriptor-Prinzip „lauffähig in Etappen").

## II.7 Verifikationspass (Actor-Critic)

Ein optionaler zweiter Durchlauf nach der Generierung prüft jede
Anker-Behauptung gegen den Index. Die Prüf-Logik ist **keine
Generator-Innerei**, sondern eine eigenständige Service-Fähigkeit, deren
erster Consumer der Generator ist:

```python
verify_citation(chunk_id, page=None, quote=None) -> VerificationResult
```

Drei Prüfstufen, aufsteigend streng:

1. **Existenz** — `chunk_id` existiert im Index (`LanceDBStore.get_by_id`).
2. **Ort** — `page_label`/`page_number`/Sektion des Chunks deckt sich mit der
   Anker-Angabe.
3. **Wortlaut** — die destillierte Aussage bzw. ein wörtliches Zitat ist im
   Chunk-Text (inkl. `window_text`) fuzzy enthalten; Wiederverwendung von
   `src/archilles/text_match.py` (bereits produktiv im Annotation-Matching).

Bei Stufe-1-Fehlschlag versucht der Pass eine **Re-Lokalisierung** über
`book_id` + Seite + Textabgleich (Reindex-Fall, §II.5) und schlägt den
korrigierten Anker vor. Ergebnis ist ein Verifikationsbericht pro Seite
(bestätigt / re-lokalisiert / nicht belegbar); „nicht belegbar" führt zur
Markierung der Aussage, nie zu stiller Löschung. Das MCP-Tool
`verify_citation` ist danach eine dünne Exposition derselben Funktion —
nützlich weit über den Wiki hinaus (jede LLM-Antwort mit ARCHILLES-Zitaten
wird nachprüfbar).

## II.8 Inkrementelle Updates und `log.md`

Der Wiki wird nicht bei jedem Lauf neu erzeugt. Die Watchdog-Ergebnisse
(Teil I) liefern die Änderungsmenge:

- `metadata_changed` / `annotations_changed` / neu voll indexierte Bücher →
  betroffene Buch-Seite regenerieren (sofern über `rating_threshold`).
- Regenerierte Buch-Seiten markieren abhängige Entitäten-/Themen-Seiten als
  veraltet (`stale`); deren Regeneration kann gebündelt oder auf Anforderung
  erfolgen. Die Abhängigkeit ist aus den Links des internen Modells bekannt.
- Jeder Update-Lauf schreibt einen Eintrag in `log.md` — in der
  OKF-Konvention (ISO-Datum als Überschrift, neueste zuerst, Prosa-Einträge
  mit `**Update**`/`**Creation**`-Schlüsselwörtern). Das Watchdog-Protokoll
  und das OKF-Log sind damit ein Format-Paar: gleiche Ereignisse, einmal als
  Betriebslog (`watchdog.log`), einmal als menschenlesbare Wiki-Historie.

## II.9 Konfiguration

Neuer Block in `.archilles/config.json`:

```json
{
  "wiki": {
    "output_dir": ".archilles/wiki",
    "rating_threshold": 4,
    "verify": true,
    "llm": { "endpoint": "…", "model": "…" }
  }
}
```

- `output_dir` relativ zur Bibliothek oder absolut (z. B. in einen
  Obsidian-Vault).
- Die Prosa-Sprache der generierten Seiten folgt `languages[0]` aus der
  zentralen Sprach-Config (P3-Konvention: erste Sprache = Bedien-Sprache).
- `llm` nutzt denselben OpenAI-kompatiblen Endpunkt-Mechanismus wie der
  „Direkte Frage-Pfad" (ROADMAP v1.0) — ein Anbindungs-Mechanismus, zwei
  Consumer.

## II.10 Nicht-Ziele (YAGNI)

- **Keine `[[Wikilink]]`-Emission**, auch nicht als Option (§II.2).
- **Keine zweite Ausgabe-Sicht** (HTML, Graph-Export): OKF-Consumer übernehmen
  das; der Generator schreibt genau ein Bundle.
- **Keine Graph-Datenbank, keine formale Ontologie** — das ist v2.0; das Wiki
  ist bewusst die Textform.
- **Kein Auto-Rewrite bestehender Seiten bei unverändertem Buch** — Updates
  nur über die Watchdog-Änderungsmenge oder explizite Anforderung.
- **Keine Wikidata-Anbindung in v1.5** (Evaluation läuft separat, s. ROADMAP
  v2.0).

## II.11 Offene Fragen

1. **LLM-Wahl und Kosten:** lokales Modell (Qualität der Destillate?) vs.
   Cloud-Endpunkt (Privacy-Abwägung — es verlassen destillierte Inhalte, nicht
   nur Queries, den Rechner). Entscheidung am realen Prototyp.
2. **Claim-Granularität:** Absatz mit Sammel-Anker vs. Satz mit Einzel-Anker —
   bestimmt Lesbarkeit wie Verifizierbarkeit; am Prototyp kalibrieren.
3. **Entitäts-Kanonisierung ohne Wikidata:** Namensvarianten („Mommsen" /
   „Theodor Mommsen") über `archilles_aliases` — reicht LLM-Zuordnung, oder
   braucht es eine leichte Normalisierungstabelle?
