# Routine-Cockpit — Technisches Briefing

**Datum:** 19. Mai 2026
**Adressat:** Claude Design / Implementierungs-Sitzung
**Status:** Entwurf, nicht implementiert

---

## 1. Zweck und Scope

Eine kleine lokale Webapp für Überblick und Steuerung der Archilles-Automatismen. Ziel: nicht mehr nach `Get-ScheduledTask`, `routine.log` und `routine_history.jsonl` greifen müssen, wenn man wissen will, was gerade läuft oder einen Task spontan triggern will.

**Single-User, single-host.** Läuft auf demselben Rechner wie die Watchdogs selbst. Keine Cloud, keine Multi-User-Auth.

**Was es NICHT ist:** keine Such-UI für die RAG-Datenbank (dafür gibt es die Streamlit-UI in `scripts/web_ui.py` und den MCP-Server). Kein Ersatz für den Windows Task Scheduler — das Cockpit liest und steuert ihn, übernimmt aber nicht die Timer-Logik selbst.

---

## 2. Funktionsumfang

### 2.1 Lesen

| Bereich | Inhalt |
|---|---|
| **Lock-Status** | Aktueller Halter (`script_name`, `PID`, `seit`), mtime-Alter (= Heartbeat-Frische), Stale ja/nein |
| **Scheduled Tasks** | Pro Task (`Archilles-Routine-Calibre`, `…-Calibre-B`, `…-Lab`, `…-Zotero`, `Archilles-Weekly-Mail` etc.): aktiviert/deaktiviert, letzter Run, nächster geplanter Run, Status (Idle/Running/Failed) |
| **Source-Status** | Pro Source aus `~/.archilles/config.json`: letzter erfolgreicher Run (aus Marker-Datei), Phase-1-Stub-Backlog (LanceDB `has_content=False`-Count), neueste Stats |
| **History** | `routine_history.jsonl` pro Source, gefiltert auf z. B. letzte 7 Tage, in Tabellenform |
| **Logs** | Live-Tail auf `<lib>/.archilles/routine.log`, scroll-/such-bar |

### 2.2 Steuern (mit Bestätigungs-Dialog)

| Aktion | Implementierung |
|---|---|
| Lock manuell freigeben | `Path("~/.archilles/routine.lock").unlink(missing_ok=True)` |
| Task aktivieren | PowerShell `Enable-ScheduledTask -TaskName <name>` |
| Task deaktivieren | PowerShell `Disable-ScheduledTask -TaskName <name>` |
| Task ad-hoc starten | PowerShell `Start-ScheduledTask -TaskName <name>` |
| Force-Run aus Cockpit | `subprocess.Popen([python, run_routine.py, --source, …, --force])` mit Live-stdout-Stream |

### 2.3 Spätere Erweiterung (News-Agent)

- GPU-Slot-Indikator: ist gerade jemand "schwer" auf der Karte? Quelle: dasselbe Lockfile + `script_name`-Pattern-Match.
- Briefing-Ansicht: tagesaktuelle News-Zusammenfassung lesen.

---

## 3. Datenquellen

| Quelle | Typ | Wo (Beispielpfad) |
|---|---|---|
| Lockfile | Text | `~/.archilles/routine.lock` |
| Master-Config | JSON | `~/.archilles/config.json` |
| Per-Source Marker (Phase A) | Text (ISO) | `<lib>/.archilles/last_routine_run_phaseA.txt` |
| Per-Source Marker (Phase B) | Text (ISO) | `<lib>/.archilles/last_routine_run_phaseB.txt` |
| Per-Source Marker (Nicht-Calibre) | Text (ISO) | `<lib>/.archilles/last_routine_run.txt` |
| Per-Source History | JSON-Lines | `<lib>/.archilles/routine_history.jsonl` |
| Per-Source Log | Plain text | `<lib>/.archilles/routine.log` |
| Phase-3-Checkpoint | JSON | `<lib>/.archilles/index_new_checkpoint.json` |
| Phase-4-Checkpoint | JSON | `<lib>/.archilles/index_fulltext_checkpoint.json` |
| Vault-Linker History | JSON-Lines | `<lib>/.archilles/vault_linker_history.jsonl` |
| Weekly-Mail Marker | Text (ISO) | `~/.archilles/last_weekly_mail.txt` |
| Scheduled Tasks | Windows Task Scheduler | via `Get-ScheduledTask` (PowerShell, JSON) |
| Phase-1-Backlog-Count | LanceDB | `chunks`-Tabelle, `WHERE has_content=False` (über `lancedb_store.get_hashes_for_indexed_books()`) |

Alle JSONL-Dateien sind append-only — der Cockpit darf sie ausschließlich **lesen**.

---

## 4. Technologie-Empfehlung

### Backend

**FastAPI** (passt zur News-Agenten-Architektur).

```
pip install fastapi uvicorn[standard] python-multipart
```

- Bind: `127.0.0.1:8765` (nur localhost, kein Auth nötig).
- Endpoints (REST + SSE für Live-Output):
  - `GET  /api/status`                       → Lock + alle Sources + Scheduler-Tasks
  - `GET  /api/source/{name}`                → Detail-View pro Source
  - `GET  /api/source/{name}/history?days=7` → Geparste History-Einträge
  - `GET  /api/source/{name}/log?tail=200`   → Letzte N Zeilen
  - `POST /api/lock/release`                 → Lock freigeben (Body: `{"confirm": true}`)
  - `POST /api/task/{name}/enable`
  - `POST /api/task/{name}/disable`
  - `POST /api/task/{name}/start`
  - `POST /api/run/{source}`                 → Force-Run, gibt `run_id` zurück
  - `GET  /api/run/{run_id}/stream`          → SSE-Stream der Subprocess-Ausgabe

### Frontend

**Vanilla HTML/JS + htmx.** Drei Views, je < 200 Zeilen. Kein npm-Build, kein Framework.

Falls man modern haben will: **htmx 2 + Pico.css** — bedeutet, Server rendert HTML-Fragmente, htmx ersetzt Teile des DOMs bei Klicks. Sehr leichtgewichtig.

Live-Updates für Lock-Heartbeat und laufende Subprocesses: `EventSource` (SSE) oder htmx' `hx-sse`.

### Persistenz

Vorerst **keine eigene DB** nötig. Alle Datenquellen sind im Filesystem oder im Task Scheduler. Wenn das Cockpit später eigene Settings braucht (gepinnte Sources, letzter Tab), genügt eine `~/.archilles/cockpit.json`.

### Boot

- Manueller Start: `python scripts/cockpit.py` → Browser auf `http://127.0.0.1:8765`.
- Optional als Autostart-Task im Scheduler (`OnLogon`, `pythonw.exe scripts/cockpit.py`).
- Browser-Bookmark.

---

## 5. Datei-Layout

```
src/archilles/cockpit/
├── __init__.py
├── server.py             # FastAPI-App + Routes
├── status.py             # Lock + Scheduler + Source-Status zusammensammeln
├── history.py            # routine_history.jsonl parsen, aggregieren
├── scheduler.py          # PowerShell-Wrapper: Get-/Enable-/Disable-/Start-ScheduledTask
├── runner.py             # subprocess.Popen für Force-Run, SSE-Stream
├── templates/            # Jinja-Snippets für htmx-Fragmente (falls htmx)
│   ├── status.html
│   ├── source_card.html
│   └── log_lines.html
└── static/
    ├── index.html        # Skelett-Seite
    ├── app.js            # (falls Vanilla JS) WebSocket-/SSE-Wiring
    └── style.css         # oder pico.min.css

scripts/cockpit.py        # Entry-Point: uvicorn-Aufruf
tests/test_cockpit_*.py   # Unit-Tests pro Modul, FastAPI-TestClient
```

---

## 6. Wiederverwendung dessen, was schon da ist

| Funktion | Vorhandenes Modul | Verwendung im Cockpit |
|---|---|---|
| Lockfile lesen | `src/archilles/runtime_lock.py` (Konstanten `LOCK_FILE`, `STALE_AFTER_S`) | `LOCK_FILE.read_text()` + `time.time() - LOCK_FILE.stat().st_mtime` |
| Master-Config | `src.archilles.config.load_master_config()` | direkt aufrufen |
| Phase-1-Backlog-Count | `src.storage.lancedb_store.LanceDBStore.get_hashes_for_indexed_books()` | nur Aggregat (`sum(1 for h in hashes.values() if not h['has_content'])`) |
| History parsen | bisher inline in `scripts/weekly_status_mail.py:_read_history` | nach `cockpit/history.py` extrahieren, beide nutzen |

**Hinweis:** `_read_history` aus `weekly_status_mail.py` ist ein Kandidat für eine zweite Extraktion analog zu `runtime_lock`. Wenn das Cockpit gebaut wird, lohnt sich ein gemeinsames Helper-Modul.

---

## 7. Sicherheits-Constraints

- **Bind ausschließlich auf `127.0.0.1`.** Kein `0.0.0.0`, kein Reverse-Proxy ohne explizite Auth.
- PowerShell-Aufrufe via `subprocess.run([powershell, "-NoProfile", "-Command", …])` mit **Argumentliste**, niemals String-Concatenation (Shell-Injection vermeiden).
- Scheduled-Task-Namen werden gegen eine Allowlist geprüft (nur Tasks mit Präfix `Archilles-` oder aus der Master-Config).
- Force-Run und Lock-Release nur mit explizitem POST + Confirm-Token im Body.
- Logs werden **gelesen**, nicht gelöscht — keine Schreib-Operationen auf Watchdog-Output-Dateien.
- Falls jemand das Cockpit später über das LAN nutzen will: erst dann Auth nachrüsten (Token in Konfig, Bearer-Header, HTTPS via mkcert wie schon für den MCP-Server).

---

## 8. Phasen-Roadmap

### Phase 1 — MVP "Read-Only" (~1 Wochenende)
- `GET /api/status` + Status-Hauptseite (Lock + Source-Cards + Task-Status)
- History- und Log-Views (read-only)
- htmx-Refresh alle 30 s
- Kein Schreibzugriff

### Phase 2 — Steuerung (~1 Wochenende)
- Task enable/disable/start (mit Confirm-Dialog)
- Lock-Release-Button
- Force-Run mit Live-Output (SSE)

### Phase 3 — News-Agent-Integration (~1 Wochenende, zusammen mit dem News-Agenten)
- GPU-Slot-Indikator (lichte vs. schwere Phase erkennen)
- Briefing-Anzeige
- Manueller "Briefing jetzt"-Trigger

---

## 9. Bekannte offene Fragen

1. **Tail von `routine.log` ohne wachsende Speicher-Last** — bei Phase-B-Läufen wird das Log groß (>50 MB). Server-seitiges `seek(-N*K, 2)` und nur die letzten Bytes lesen, dann auf vollständige Zeilen alignieren. Standard-Pattern, aber muss man bewusst bauen.
2. **Async vs. sync FastAPI für die LanceDB-Aggregate** — `LanceDBStore.get_hashes_for_indexed_books()` ist heute sync und kann bei großen Bibliotheken Sekunden brauchen. Lösung: ein Cache mit 60-s-TTL plus optional Refresh-Button.
3. **Wer "besitzt" die Scheduled-Task-Namen?** — heute existieren sie nur als String in `scripts/install_scheduled_routines.ps1`. Sinnvoll: Master-Config um ein `scheduled_task: "Archilles-Routine-Calibre"`-Feld pro Source erweitern, dann hat das Cockpit eine Single-Source-of-Truth.
4. **Logout/Shutdown-Verhalten** — wenn der Cockpit-Prozess beim Logout stirbt: brauchen wir einen `OnLogon`-Task, der ihn neu startet? Oder lieber als Windows-Dienst (NSSM)? Pragmatisch: erstmal OnLogon, später wenn nötig Dienst.

---

## 10. Was Claude Design jetzt entscheiden muss

1. **Backend-Stack:** FastAPI (empfohlen, weil passt zum News-Agenten) oder Streamlit (simpler, weniger UI-Code, aber weniger flexibel für Live-Streams)?
2. **Frontend-Stack:** Vanilla HTML + htmx (empfohlen) oder React (mehr Aufwand, aber falls schon vorhandene Cockpit-Komponenten aus dem News-Agenten-Entwurf wiederverwendet werden sollen)?
3. **MVP-Cutline:** wo ist Phase 1 zu Ende — reine Anzeige, oder schon mit Lock-Release? (Empfehlung: reine Anzeige, denn das ist in einem Wochenende machbar und sofort nützlich.)
4. **Integration in das ARCHILLES-Repo** oder als separates Mini-Repo? (Empfehlung: im Archilles-Repo, weil es die Master-Config, LanceDB und `runtime_lock` direkt importiert.)
