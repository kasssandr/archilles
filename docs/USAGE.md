# Archilles Nutzungsanleitung

Praktische Anleitung für den täglichen Gebrauch von Archilles.

---

## Inhaltsverzeichnis

1. [Übersicht: Zwei Suchsysteme](#übersicht-zwei-suchsysteme)
2. [CLI-Befehle](#cli-befehle)
3. [MCP-Tools für Claude Desktop](#mcp-tools-für-claude-desktop)
4. [Typische Workflows](#typische-workflows)
5. [Tipps & Best Practices](#tipps--best-practices)

---

## Übersicht: Zwei Suchsysteme

Archilles bietet zwei komplementäre Suchsysteme:

| System | Durchsucht | Tool | Anwendung |
|--------|-----------|------|-----------|
| **Volltext-Suche** | PDF/EPUB-Inhalte (Chunks) | `search_books_with_citations` | "Was steht in meinen Büchern über X?" |
| **Annotations-Suche** | Calibre Highlights/Notizen | `search_annotations` | "Was habe ich zu X markiert/notiert?" |

Beide Systeme nutzen:
- **Semantische Suche**: Findet konzeptuell ähnliche Inhalte
- **Keyword-Suche**: Findet exakte Wortübereinstimmungen
- **Hybrid-Modus**: Kombiniert beide (empfohlen)

---

## CLI-Befehle

### Indexierung

#### Einzelnes Buch indexieren
```bash
python scripts/rag_demo.py index "D:\Calibre-Bibliothek\Autor\Buch (ID)\datei.pdf"
```

Mit benutzerdefinierter ID:
```bash
python scripts/rag_demo.py index "pfad/zum/buch.pdf" --book-id "Arendt_VitaActiva"
```

#### Batch-Indexierung nach Tag
```bash
# Vorschau (was würde indexiert?)
python scripts/batch_index.py --tag "Leit-Literatur" --dry-run

# Tatsächlich indexieren
python scripts/batch_index.py --tag "Leit-Literatur"

# Mit Logging
python scripts/batch_index.py --tag "Geschichte" --log indexing_log.json

# Nur erste N Bücher (zum Testen)
python scripts/batch_index.py --tag "Philosophie" --limit 5

# Fortsetzen nach Unterbrechung
python scripts/batch_index.py --tag "Leit-Literatur" --skip-existing
```

#### Batch-Indexierung nach Autor
```bash
python scripts/batch_index.py --author "Arendt"
python scripts/batch_index.py --author "Foucault" --dry-run
```

#### Dateiformat-Präferenz (`--prefer-format`)

Hat ein Buch mehrere Formate (z.B. PDF + EPUB), bestimmt `--prefer-format`, welches indexiert wird. Standard ist `pdf`.

```bash
# PDF bevorzugen (Standard) — exakte Seitenzahlen, wissenschaftliche Zitierbarkeit
python scripts/batch_index.py --tag "Leit-Literatur"

# EPUB bevorzugen — schnellere Indexierung, sauberere Chunks
python scripts/batch_index.py --tag "Leit-Literatur" --prefer-format epub
```

**PDF** liefert exakte Seitenzahlen für wissenschaftliche Zitationen (`S. 47`) und entspricht der gedruckten Ausgabe. Nachteil: Gescannte PDFs erzeugen OCR-Rauschen; mehrspaltige Layouts und Kopf-/Fußzeilen werden oft in die Chunks gemischt, was die Suchqualität mindert.

**EPUB** liefert sauberere Chunks, da der Text als semantisches HTML vorliegt — Absätze bleiben Absätze, Kapitelgrenzen werden erkannt, und die Extraktion ist deutlich schneller. Nachteil: Seitenzahlen sind nicht verfügbar; Zitate verweisen auf Kapitel statt auf Seiten.

Ist das bevorzugte Format nicht vorhanden, greift automatisch das nächste verfügbare Format.

**Umstellen bereits indexierter Bücher:** Die Format-Präferenz wird beim nächsten Lauf nicht automatisch angewendet — bereits indexierte Bücher werden übersprungen. Für einen vollständigen Wechsel auf EPUB:
```bash
python scripts/batch_index.py --tag "Leit-Literatur" --prefer-format epub --reindex-before 2099-01-01
```

#### Index-Statistiken
```bash
python scripts/rag_demo.py stats
```

---

### Suche

#### Grundlegende Suche
```bash
# Hybrid (Standard, empfohlen)
python scripts/rag_demo.py query "politische Legitimation im Mittelalter"

# Nur semantisch (konzeptbasiert)
python scripts/rag_demo.py query "Herrschaft und Macht" --mode semantic

# Nur Keyword (exakte Wörter)
python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword
```

#### Exakte Phrasensuche
Besonders wichtig für Latein, Zitate, Fachbegriffe:
```bash
python scripts/rag_demo.py query "evangelista et a presbyteris" --exact
```

#### Sprachfilter
```bash
# Nur deutsche Texte
python scripts/rag_demo.py query "König" --language de

# Nur lateinische Texte
python scripts/rag_demo.py query "Rex" --language la

# Mehrere Sprachen
python scripts/rag_demo.py query "king" --language de,en,la
```

#### Tag-Filter
```bash
python scripts/rag_demo.py query "Bewusstsein" --tag-filter Philosophie
python scripts/rag_demo.py query "Handel" --tag-filter Geschichte Wirtschaft
```

#### Mehr Ergebnisse
```bash
python scripts/rag_demo.py query "Reformation" --top-k 20
```

#### Export nach Markdown
Für Joplin, Obsidian oder andere Markdown-Apps:
```bash
python scripts/rag_demo.py query "Spätantike Senatoren" --export recherche.md
```

---

## MCP-Tools für Claude Desktop

Nach korrekter Konfiguration stehen folgende Tools in Claude Desktop zur Verfügung:

### Volltext-Suche: `search_books_with_citations`

Durchsucht die indexierten PDF/EPUB-Inhalte.

**Beispiel-Prompts:**
- *"Suche in meinen Büchern nach Diskussionen über politische Legitimation"*
- *"search_books_with_citations query='Konstantin Senat' mode='hybrid'"*
- *"Finde Passagen über mittelalterlichen Handel, nur auf Deutsch"*

**Parameter:**
- `query`: Suchbegriff (Pflicht)
- `top_k`: Anzahl Ergebnisse (Standard: 5)
- `mode`: 'hybrid', 'semantic', oder 'keyword'
- `language`: Sprachfilter ('de', 'en', 'la', etc.)

### Annotations-Suche: `search_annotations`

Durchsucht deine Calibre-Highlights und Notizen.

**Beispiel-Prompts:**
- *"Suche in meinen Annotationen nach 'Bewusstsein'"*
- *"Was habe ich zum Thema Freiheit markiert?"*
- *"search_annotations query='aristocracy' use_semantic=true"*

**Parameter:**
- `query`: Suchbegriff (Pflicht)
- `use_semantic`: true für semantische Suche, false für Text-Match
- `max_results`: Maximale Ergebnisse (Standard: 10)
- `max_per_book`: Max. Treffer pro Buch (verhindert Dominanz eines Buchs)

### Weitere MCP-Tools

| Tool | Funktion |
|------|----------|
| `list_annotated_books` | Zeigt alle Bücher mit Annotationen |
| `get_index_stats` | Statistiken zum Annotations-Index |
| `index_annotations` | Indexiert/reindexiert Annotationen |
| `get_book_annotations` | Annotationen eines spezifischen Buchs |
| `detect_duplicates` | Findet Buch-Dubletten in der Bibliothek |

---

## Typische Workflows

### Workflow 1: Neue Buchsammlung erschließen

```bash
# 1. Bücher mit relevantem Tag identifizieren (Dry-Run)
python scripts/batch_index.py --tag "Projekt-Dissertation" --dry-run

# 2. Indexierung starten (ggf. über Nacht)
python scripts/batch_index.py --tag "Projekt-Dissertation" --log diss_index.json

# 3. Nach Abschluss: Claude Desktop neu starten

# 4. In Claude Desktop recherchieren
# "Suche in meinen Büchern nach [Forschungsfrage]"
```

### Workflow 2: Thematische Recherche

In Claude Desktop:
```
1. "Suche in meinen Büchern nach 'Verhältnis von Kirche und Staat im Mittelalter'"
2. "Zeige mir auch, was ich dazu annotiert habe"
3. "Exportiere die relevantesten Passagen als Markdown"
```

### Workflow 3: Zitat finden

```bash
# Exakte Phrase suchen (z.B. lateinisches Zitat)
python scripts/rag_demo.py query "in necessariis unitas" --exact

# Oder in Claude Desktop:
# "Finde das genaue Zitat 'in necessariis unitas' in meinen Büchern"
```

### Workflow 4: Vergleichende Analyse

In Claude Desktop:
```
1. "Was schreibt Arendt über Macht?" (mit --book-id Filter wenn indexiert)
2. "Und was schreibt Foucault dazu?"
3. "Vergleiche die beiden Positionen basierend auf den gefundenen Passagen"
```

---

## Tipps & Best Practices

### Indexierung

- **Format wählen**: PDF für präzise Seitenzitate, EPUB für schnellere Indexierung und sauberere Chunks (siehe `--prefer-format`)
- **Über Nacht laufen lassen**: ~10 Min pro Buch, 67 Bücher ≈ 11 Stunden
- **`--skip-existing` nutzen**: Bei Unterbrechung einfach fortsetzen
- **Tags strategisch nutzen**: Indexiere thematische Sammlungen statt alles

### Suche

- **Hybrid-Modus für allgemeine Fragen**: Kombiniert Konzepte + exakte Wörter
- **Keyword-Modus für Fachbegriffe**: "Herrschaftslegitimation", "Prosopographie"
- **Exakt-Modus für Zitate**: Lateinische Phrasen, wörtliche Zitate
- **Sprachfilter bei mehrsprachiger Bibliothek**: Reduziert Rauschen

### Claude Desktop

- **Nach Indexierung neu starten**: MCP-Server lädt DB beim Start
- **Klare Anweisungen geben**: "Suche in meinen Büchern" vs. "Suche in Annotationen"
- **Ergebnisse validieren**: Seitenzahlen prüfen, besonders bei alten PDFs

### Datenorganisation

```
D:\Calibre-Bibliothek\
├── .archilles\
│   ├── rag_db\          # LanceDB-Index (Volltexte + Annotationen)
│   └── config.json      # Optionale Konfiguration
├── Autor 1\
│   └── Buch (ID)\
└── Autor 2\
    └── Buch (ID)\
```

---

## Fehlerbehebung

### "Tool ran without output"
→ MCP Response-Format-Problem. Stelle sicher, dass du die aktuelle Version hast.

### Suche liefert keine Ergebnisse
→ Prüfe mit `python scripts/rag_demo.py stats`, ob Bücher indexiert sind.
→ Prüfe den DB-Pfad (sollte in `.archilles/rag_db` sein).

### Claude Desktop findet Tools nicht
→ Prüfe `claude_desktop_config.json` Syntax.
→ Starte Claude Desktop komplett neu.
→ Prüfe Log: `~/.archilles/mcp_server.log`

### Indexierung bricht ab
→ Mit `--skip-existing` fortsetzen.
→ Prüfe Speicherplatz und RAM.

---

## Weiterführende Dokumentation

- [README.md](../README.md) - Projektübersicht
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technische Details
- [MCP_GUIDE.md](MCP_GUIDE.md) - Claude Desktop Konfiguration
- [FAQ.md](FAQ.md) - Häufige Fragen
