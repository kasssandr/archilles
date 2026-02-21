# ARCHILLES_SKILL.md — Nutzungsanleitung für KI-Assistenten

> **Für wen ist dieses Dokument?**  
> Für jedes KI-Modell, das über MCP mit ARCHILLES verbunden ist – von Haiku bis Opus.  
> Es erklärt, was ARCHILLES ist, was in der Datenbank steckt, welche Werkzeuge es gibt und wie man damit forscht.  
> Es ist absichtlich generisch gehalten und gilt für jeden ARCHILLES-Nutzer.  
> Nutzerspezifische Ergänzungen gehören in ARCHILLES_USER.md.

---

## 1. Was ist ARCHILLES?

ARCHILLES ist ein semantisches Recherchesystem für eine persönliche Calibre-Bibliothek. Es macht tausende Titel durch natürlichsprachige Suche erschließbar: im Volltext der Bücher, in den vom Nutzer kuratierten Metadaten und in seinen persönlichen Annotationen.

Das System verwendet BGE-M3-Embeddings mit hybrider Vektor- und BM25-Suche. Ergebnisse werden mit vollständigen Zitatangaben geliefert (Autor, Titel, Jahr, Seitenzahl oder Kapitel) und sind für wissenschaftliche Verwendung geeignet.

**ARCHILLES ist ein Werkzeug zum Denken *mit* einer Forschungsbibliothek.** Das bedeutet: Nicht jede Anfrage erwartet eine fertig synthetisierte Antwort. Manchmal ist eine gut strukturierte Materialliste das Richtige, manchmal eine vergleichende Analyse, manchmal ein einziger gezielter Fund. Das Modell soll sich nicht aufdrängen – es stellt Material bereit und denkt mit, wenn es gefragt wird.

---

## 2. Die Inhaltstypen – was steckt in der Datenbank?

ARCHILLES nutzt **eine einzige LanceDB-Datenbank** mit verschiedenen Inhaltsklassen (`chunk_type`). Es gibt keine getrennten Datenbanken – die Unterscheidung erfolgt durch Filterung innerhalb der gemeinsamen Tabelle.

| chunk_type | Was es enthält | Epistemischer Status |
|---|---|---|
| `content` | Volltext der Bücher (Kapitel, Abschnitte) | Was *im Buch steht* |
| `calibre_comment` | Verlagstexte, Klappentexte, Kritiken, Rezensionen, NotebookLM-Analysen, Übersetzungen einzelner Artikel oder Kapitel, persönliche Exzerpte und Notizen des Nutzers | Was der Nutzer über das Buch gesammelt oder selbst gedacht hat – kuratiertes Wissen zweiter Ordnung |
| `annotation` | Highlights und handschriftliche Notizen aus dem Calibre-Viewer (EPUB) und PDF-Readern | Was der Nutzer beim Lesen als relevant markiert hat – kuratiertes Wissen erster Ordnung |

**Zur Gewichtung:** Das Vorhandensein eines `calibre_comment`-Eintrags ist ein schwaches Signal für Nutzerinteresse an einem Titel. Der *Umfang* dieses Felds ist kein zuverlässiger Indikator – er kann durch kopierte Verlagstexte, übersetzte Sekundärtexte oder andere nicht-wertende Inhalte beeinflusst sein, die nichts über das tatsächliche Gewicht aussagen, das der Nutzer dem Buch beimisst. Keine automatische Gewichtung nach Feldumfang vornehmen.

Annotationen repräsentieren in der Regel kuratiertes Wissen höherer Qualität als Verlagstexte: Sie zeigen, was der Nutzer beim aktiven Lesen für bedeutsam gehalten hat. Beachte aber, dass das `calibre_comment`-Feld auch persönliche Exzerpte und eigene Gedanken des Nutzers enthalten kann – es ist also epistemisch nicht weniger wertvoll als Annotationen, nur heterogener.

---

## 3. Die verfügbaren MCP-Werkzeuge

### 3.1 Hauptsuche im Buchinhalt

**`search_books_with_citations`**

Hybride Suche über den gesamten Buchinhalt mit zitierfähigen Ergebnissen.

Parameter:
- `query` (Pflicht): Natürlichsprachige Suchanfrage. Präzise inhaltliche Formulierungen liefern bessere Ergebnisse als reine Schlagwortlisten.
- `mode`: `hybrid` (Standard, empfohlen), `semantic` (konzeptuell, gut für verwandte Begriffe und thematische Suchen), `keyword` (exakte Übereinstimmung, gut für Namen, Titel, Termini)
- `top_k`: Anzahl Ergebnisse (Standard: 5; für breite Recherchen 10–15 empfohlen)
- `tags`: Filter nach Calibre-Tags, z.B. `["Frühchristentum", "Geschichte"]`
- `language`: Sprachfilter, z.B. `"de"`, `"en"`, `"la"`
- `expand_context`: Bei `true` werden größere Textpassagen um die Fundstelle herum geliefert (Small-to-Big Retrieval)

Dieses Werkzeug durchsucht standardmäßig nur Haupttexte (`section_filter: main`), keine Bibliographien, Register oder Vorworte. Das ist gewollt.

**Wichtige Einschränkung:** `search_books_with_citations` ist eine *Volltext- und Semantiksuche*, keine Metadaten-Abfrage. Ein Autor wird nur dann gefunden, wenn sein Name in einem indizierten Textabschnitt vorkommt. Für kurze Texte (Artikel, Buchkapitel in Sammelbänden) steht der Autorenname oft nur auf dem Titelblatt – das ist im Index möglicherweise nicht als separater Chunk enthalten. Für Metadaten-Anfragen (alle Bücher eines Autors, alle Titel mit einem Tag) sind andere Werkzeuge besser geeignet – siehe 3.3.

### 3.2 Annotationen durchsuchen

**`search_annotations`**

Durchsucht die Highlights und Notizen des Nutzers semantisch oder per Textsuche.

Parameter:
- `query`: Suchanfrage
- `use_semantic` (Standard: `false`): Auf `true` setzen für konzeptuelle Suche

Annotationen sind oft der aufschlussreichste Einstiegspunkt: Sie zeigen, was der Nutzer als relevant erachtet hat, und können die Ausrichtung einer Volltext-Suche informieren – ohne sie zu determinieren.

### 3.3 Bibliotheksnavigation und Metadaten

Diese Werkzeuge arbeiten direkt gegen die Calibre-Metadaten, nicht gegen den Vektorindex. Für Fragen wie „alle Bücher von Autor X" oder „alle Titel mit Tag Y" sind sie der richtige Ansatz – nicht `search_books_with_citations`.

**`list_books_by_author`** — Alle Titel eines Autors direkt aus der Calibre-Datenbank. Partieller Namens-Match (case-insensitive), optionaler Tag- und Jahresfilter. *Dies ist das schnellste und zuverlässigste Werkzeug für die Frage „Welche Bücher von Autor X habe ich?"* – besonders wichtig für kurze Texte (Artikel, Buchkapitel), die in der Vektorsuche leicht übersehen werden, weil der Autorenname nicht in indizierten Chunks vorkommt.

Parameter:
- `author` (Pflicht): Autorenname, partieller Match (z.B. „Mason" findet „Steve Mason")
- `tags` (optional): Liste von Tags als AND-Filter (z.B. `["Artikel"]`)
- `year_from` / `year_to` (optional): Erscheinungsjahr-Bereich
- `sort_by`: `title` (Standard, alphabetisch) oder `year` (absteigend)

**`export_bibliography`** — Literaturverzeichnis in BibTeX, RIS, EndNote, JSON oder CSV. Filterbar nach Autor (partieller Name), Tag und Erscheinungsjahr. Exportiert strukturierte bibliographische Daten für die Weiterverarbeitung in Literaturverwaltungsprogrammen. Für eine einfache Autorenliste ist `list_books_by_author` schneller; `export_bibliography` ist die richtige Wahl, wenn ein formatiertes Literaturverzeichnis benötigt wird.

**`list_tags`** — Alle Calibre-Tags mit Buchzählungen. Nützlich zur Orientierung über die Erschließungsstruktur der Bibliothek und zum Finden geeigneter Filter für gezielte Suchen. Vor einer tag-gefilterten Suche empfehlenswert, um die exakte Schreibweise des Tags zu prüfen.

**`list_annotated_books`** — Alle Bücher mit vorhandenen Annotationen. Gibt einen schnellen Überblick über den aktiven Lesefundus.

**`get_book_annotations`** — Alle Annotationen zu einem spezifischen Buch (Pfadangabe erforderlich).

**`get_book_details`** — Vollständige Calibre-Metadaten eines Titels anhand der Calibre-ID. Nützlich, wenn eine Calibre-ID aus einem anderen Suchergebnis bekannt ist.

### 3.4 Systemstatus

**`get_index_stats`** — Indexierungsstatistiken (Chunks, Bücher, Datenbankgröße). Nützlich zur Orientierung am Beginn einer Session oder nach Indexierungsläufen.

**`detect_duplicates`** — Findet doppelt vorhandene Titel in der Bibliothek.

---

## 4. Werkzeugwahl: Metadaten vs. Volltext

Das ist die wichtigste Entscheidung zu Beginn einer Anfrage:

| Frage | Richtiges Werkzeug |
|---|---|
| „Was steht in meinen Büchern über X?" | `search_books_with_citations` |
| „Alle Bücher von Autor X" | `list_books_by_author` |
| „Alle Artikel von Autor X" | `list_books_by_author` (tags: `["Artikel"]`) |
| „Alle Titel mit Tag Y" | `export_bibliography` (tag-Filter) |
| „Alle Titel mit Tag Y von Autor X" | `list_books_by_author` (author + tags) |
| „Literaturverzeichnis als BibTeX exportieren" | `export_bibliography` |
| „Was habe ich zu X annotiert?" | `search_annotations` |
| „Welche Tags gibt es?" | `list_tags` |
| „Welche Bücher habe ich aktiv gelesen?" | `list_annotated_books` |

**Faustregel:** Sobald eine Anfrage mit „alle", „welche", „liste mir auf" oder einem Autorennamen ohne inhaltliche Frage beginnt, ist `list_books_by_author` oder `export_bibliography` der richtige Einstieg – nicht die Vektorsuche. `list_books_by_author` ist bevorzugt, wenn ein Autorenname bekannt ist; `export_bibliography` wenn ein formatiertes Literaturverzeichnis oder ein reiner Tag-Filter ohne Autor benötigt wird.

---

## 5. Vor dem Recherchieren: Absicht klären

Bevor du mit einer Suche beginnst, kläre kurz, was der Nutzer in dieser Session braucht – es sei denn, seine Absicht geht eindeutig aus der Anfrage hervor.

**Frage nach:**

*Was ist das Ziel dieser Recherche?*
- (a) Überblick über ein Thema gewinnen
- (b) Konkretes Argument oder eine These prüfen
- (c) Material für einen Text zusammentragen
- (d) Metadaten-Abfrage: alle Titel eines Autors, alle Titel mit einem Tag
- (e) Einen spezifischen inhaltlichen Fund suchen
- (f) Anderes – bitte beschreiben

*Welche Inhalte sollen bevorzugt durchsucht werden?*
- (a) Zuerst eigene Vorarbeit (Annotationen + Kommentare), dann Volltext
- (b) Direkt in den Volltext der Bibliothek
- (c) Metadaten (Autor, Tag, Jahr) – ohne Volltext

*Welches Format soll die Antwort haben?*
- (a) Synthese mit Interpretation
- (b) Materialliste mit Zitaten
- (c) Nur Fundstellen und Zitatangaben, ohne Kommentar

Nicht alle drei Fragen müssen immer gestellt werden. Bei klaren Anfragen reicht eine kurze Bestätigung oder Einzelrückfrage. Das Ziel ist Klarheit, nicht Bürokratie.

---

## 6. Recherche-Strategien

### Zweiphasen-Recherche (empfohlen bei offenen inhaltlichen Fragen)

**Phase 1 – Vorverständnis rekonstruieren:** Mit `search_annotations` und `search_books_with_citations` erfassen, was der Nutzer zu diesem Thema bereits erarbeitet hat. Das ergibt ein Bild seines bestehenden Forschungsstands.

**Phase 2 – Korpus explorieren:** Mit `search_books_with_citations` im Volltext suchen. Dabei explizit offen bleiben für Inhalte, die Phase 1 *nicht* vorspurt. Die Annotationen und Kommentare zeigen, was der Nutzer bereits kennt – Phase 2 sucht auch das, was er noch nicht gefunden hat.

**Wichtig:** Phase 1 darf Phase 2 nicht einengen. Wer nur in Richtungen sucht, die seine eigenen Markierungen vorgeben, zirkuliert in einem Spiegel seiner bisherigen Erkenntnisse. Die eigene Vorarbeit ist ein Ausgangspunkt, keine Grenze.

### Metadaten-Recherche (für bibliographische Übersichten)

`list_books_by_author` für Autoren-Abfragen (mit optionalem Tag-Filter). `export_bibliography` für reine Tag-Abfragen oder wenn ein formatiertes Literaturverzeichnis (BibTeX, RIS, etc.) benötigt wird. Beide Werkzeuge arbeiten direkt gegen die Calibre-Datenbank – zuverlässiger als die Volltext-Suche nach Autorennamen.

Empfohlene Reihenfolge: zuerst `list_tags` aufrufen, um die genaue Schreibweise des gesuchten Tags zu verifizieren, dann `list_books_by_author` oder `export_bibliography` mit den verifizierten Parametern.

### Direkte Volltext-Recherche (für spezifische inhaltliche Fragen)

`search_books_with_citations` mit präziser Query, `mode: hybrid`, `top_k: 10`. Bei Eigennamen, Fachbegriffen oder Titeln alternativ `mode: keyword` testen.

### Sprachübergreifende Suche

BGE-M3 ist multilingual. Anfragen auf Deutsch, Englisch, Latein und anderen Sprachen funktionieren ohne expliziten Sprachfilter. Für gezielte Eingrenzung: `language`-Parameter setzen.

---

## 7. Ergebnisformate – was wann passt

ARCHILLES ist ein Werkzeug zum Denken *mit* einer Bibliothek. Sehr unterschiedliche Ausgabeformate sind gleichermaßen legitim:

Eine **reine Materialliste mit Zitaten** ist sinnvoll, wenn der Nutzer selbst weiterdenken möchte. Das Modell liefert strukturiertes Rohmaterial ohne interpretativen Überbau – das ist nicht weniger, sondern oft mehr.

Eine **Synthese mit Interpretation** ist sinnvoll, wenn der Nutzer eine Einschätzung, einen Überblick oder eine Einordnung wünscht. Hier führt das Modell die Quellen zusammen, benennt Übereinstimmungen und Widersprüche und zeigt Zusammenhänge.

Eine **Zitatsammlung** (nur Fundstellen und Seitenangaben) ist sinnvoll für die unmittelbare Arbeit am eigenen Text.

Das Modell soll nicht selbst entscheiden, welches Format das richtige ist – es fragt (→ Abschnitt 5) oder orientiert sich an der expliziten Anfrage. Den Nutzer in seiner Interpretation vorwegnehmen ist ein Fehler.

**Zitierstil für ARCHILLES-Quellen:**
```
(Autor, Titel [Jahr], S. Seitenzahl)       — für PDF-Quellen
(Autor, Titel [Jahr], Kap. Kapitelname)    — für EPUB-Quellen ohne Seitenzahl
```

**Pflicht bei EPUB-Quellen – Originalsprachen-Zitat für Auffindbarkeit:**

EPUB-Dateien haben keine physischen Seitenzahlen. Eine Kapitelangabe allein reicht nicht, um die Passage im Dokument wiederzufinden. Deshalb gilt:

Bei jeder Zitation aus einer EPUB-Quelle (und jeder anderen Quelle ohne physische Seitenzahl) **muss** ein kurzes wörtliches Zitat in der **Originalsprache des Textes** mitgeliefert werden. Das Zitat muss hinreichend distinktiv sein (5–15 Wörter), damit der Nutzer es mit der Suchfunktion (Strg+F) im E-Book-Reader findet und exakt an der Stelle landet.

**Warum Originalsprache?** Wenn der Text auf Latein, Englisch, Altgriechisch oder einer anderen Sprache verfasst ist, muss das Zitat in dieser Sprache stehen – nicht in deutscher Übersetzung. Nur so funktioniert die Textsuche im Originaldokument.

Beispiele:
```
(Eusebius, Kirchengeschichte, Kap. III.4 — „τὴν τῶν ἀποστόλων διαδοχὴν")
(Blumenberg, Die Legitimität der Neuzeit [1966], Kap. 2.1 — „die Selbstbehauptung der Vernunft")
(Gibbon, Decline and Fall [1776], Ch. XV — "the union and discipline of the Christian republic")
```

Diese Regel gilt für alle Ausgabeformate (Synthese, Materialliste, Zitatsammlung). Bei PDF-Quellen mit Seitenzahl ist das Originalzitat optional, aber empfohlen bei langen Passagen oder wenn die exakte Stelle innerhalb der Seite relevant ist.

---

## 8. Systemverhalten und Eigenheiten

**Sektionsfilterung:** Standardmäßig werden nur Haupttexte durchsucht. Bibliographien, Register, Vorworte und Anhänge sind ausgeschlossen. Das ist eine bewusste Entwurfsentscheidung gegen bibliographisches Rauschen.

**Chunk-Größe:** Ergebnisse sind Textabschnitte von typischerweise 300–600 Wörtern. Sie sind aus dem Kontext gerissen – Titel, Kapitel und Entstehungsjahr immer mitlesen und mitteilen.

**Vektorsuche ≠ Metadaten-Abfrage:** `search_books_with_citations` findet Autoren und Titel nur dann zuverlässig, wenn diese im Volltext der indizierten Chunks vorkommen. Kurze Texte (Artikel, Buchkapitel) haben den Autorennamen oft nur auf dem Titelblatt – das ist im Index möglicherweise kein eigener Chunk. Für Autoren- und Tag-Listen immer `export_bibliography` bevorzugen.

**Nicht im Index:** Bücher, die noch nicht indexiert wurden, sind nicht auffindbar. Fehlende Ergebnisse zu einem erwartbaren Thema können bedeuten, dass die entsprechenden Titel noch nicht im Index sind – nicht, dass sie nicht in der Bibliothek vorhanden sind.

**Sprachen:** BGE-M3 verarbeitet alle europäischen Sprachen sowie Latein zuverlässig.

**Boosting:** `calibre_comment`-Chunks und Tag-Treffer erhalten leicht erhöhte Relevanz-Scores. Das spiegelt wider, dass vom Nutzer kuratierte Felder in der Regel relevanter sind als Volltextrauschen.

---

## 9. Schnellstart-Protokoll

1. Ist ein **ARCHILLES_USER.md** vorhanden? Dann zuerst lesen.
2. **Art der Anfrage bestimmen:** Metadaten-Abfrage mit Autor → `list_books_by_author`. Metadaten-Abfrage nur mit Tag → `export_bibliography`. Formatiertes Literaturverzeichnis → `export_bibliography`. Inhaltliche Frage → weiter zu Schritt 3.
3. **Absicht klären** – sofern nicht eindeutig aus der Anfrage erkennbar (→ Abschnitt 5).
4. Je nach gewähltem Modus: **Phase 1** (Annotationen + Kommentare) oder direkt **Volltext-Suche**.
5. Bei Zweiphasen-Recherche: Phase 2 bewusst offen halten – nicht nur in Richtungen suchen, die Phase 1 vorgibt.
6. **Ergebnisse im gewünschten Format** ausgeben (→ Abschnitt 7).
7. Bei Unklarheiten im Verlauf: kurze Rückfrage, keine Annahmen.

---

*ARCHILLES_SKILL.md — generische Version, gültig ab v1.0*  
*Nutzerspezifische Ergänzungen → ARCHILLES_USER.md*
