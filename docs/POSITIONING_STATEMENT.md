# ARCHILLES — Positioning Statement
**Arbeitsfassung:** März 2026 (Rev. 4)
**Phase:** 3 von 6 (Positionierung & USP)
**Bearbeitungsstand:** Vierte Fassung nach Feedback-Runde

> Dieses Dokument ist das strategische Fundament für alle nachfolgenden Kommunikationsarbeiten (Phase 4–6). Es definiert, was ARCHILLES ist, für wen es ist, wogegen es sich abgrenzt und warum jemand es wählen sollte. Änderungen hier wirken durch in README, Website, PR-Texte, Channel-Strategie.

---

## 1. Formales Positioning Statement

**Für** Forscher und Wissenschaftler in Geistes-, Rechts- und Sozialwissenschaften — sowie für alle, die über Jahre eine strukturierte digitale Bibliothek aufgebaut haben und beginnen, KI-Assistenten in ernsthafte Wissensarbeit zu integrieren —

**die** das Problem kennen, dass ihre kuratierten Bestände für KI unsichtbar sind, dass ihre Annotationen nirgendwo hin führen, und dass flache KI-Wissensarchitekturen den Unterschied zwischen Primärquelle und KI-Synthese nicht respektieren,

**ist ARCHILLES** eine lokale, plattformunabhängige semantische Wissensinfrastruktur —

**die** den eigenen Forschungsbestand epistemisch geschichtet erschließt, den Forscher mit seinem eigenen akkumulierten Wissen verbindet, und das Denken in zwei Räumen organisiert: dem kuratierten Bestand anderer (Bib) und dem eigenen Denken (Lab) —

**im Unterschied zu** flachen KI-Wissenspools (Open Brain, Mem.ai, Notion AI), generalistischen KI-Agenten (OpenClaw, ChatGPT) und bloßen Bibliotheksverwaltungsprogrammen (Calibre, Zotero allein) —

**weil** ARCHILLES als einziges System die epistemische Schichtung von Forschungswissen strukturell bewahrt, lokal und ohne Cloud-Abhängigkeit arbeitet, bibliotheksagnostisch ist (Calibre, Zotero, beliebige Ordnerstruktur), und mit dem Archilles Lab einen schreibfähigen Denk- und Produktionsraum bietet, der strukturell vom Read-Only-Bestand getrennt ist.

---

## 2. Kategoriedefinition: Was ist ARCHILLES?

ARCHILLES gehört zu keiner bestehenden Kategorie — und das ist die eigentliche Kommunikationsaufgabe.

Es ist kein Bibliotheksprogramm. Calibre und Zotero *verwalten* Bestände. ARCHILLES *erschließt* sie semantisch.

Es ist kein KI-Agent. OpenClaw, Moltbot und ihre Nachfolger handeln für den Nutzer. ARCHILLES stellt Wissen bereit, damit der Nutzer besser handeln kann — und bleibt Werkzeug in dessen Hand.

Es ist kein Knowledge-Management-Tool im Consumer-Sinne. Notion AI, Obsidian, Mem.ai sammeln alles gleichberechtigt. ARCHILLES unterscheidet zwischen Primärquelle, kuratierten Annotationen und KI-generierten Synthesen — und hält diese Schichten strukturell getrennt.

Es ist kein herkömmliches RAG-System. Generische RAG-Lösungen indexieren Dokumente und geben Chunks zurück. ARCHILLES kennt den Unterschied zwischen einer Primärquelle, einer Sekundärquelle, einer eigenen Randnotiz und einem KI-generierten Synthesetext — und hält diese epistemischen Ebenen über den gesamten Workflow hinweg getrennt.

**ARCHILLES ist die semantische Schicht zwischen dem Forschungsbestand und den KI-Werkzeugen, die der Forscher einsetzt.**

### Anmerkung zur Zwei-Räume-Architektur

Die bisherige "hemisphärische Architektur"-Metapher (nach McGilchrist) wird aus der *öffentlichen* Kommunikation herausgehalten. Gründe: zu esoterisch für unbekannte Zielgruppen, lädt zur Anfechtung ein, riskiert Arroganz-Wahrnehmung.

Das strukturelle Prinzip selbst bleibt unverändert und ist kommunikativ einfacher zu fassen als **Bibliothek & Labor** (oder: **Archiv & Werkstatt**):
- *Archilles Bib* — kuratierter Bestand anderer, Read-Only, Erschließung
- *Archilles Lab* — eigenes Denken, schreibfähig, Produktion

McGilchrist bleibt *Subtext* für Leser, die ihn erkennen. Als tragendes Kommunikationselement: nein.

Diese Kategorie hat noch keinen etablierten Namen. Mögliche Formulierungen:
- *Semantic research layer* — technisch, für GitHub/Hacker News
- *Knowledge infrastructure for researchers* — für akademische Zielgruppen
- *Research memory system* — emotional, zugänglich, nah an der Nutzererfahrung

Empfehlung: Im Einstieg "semantic search" verwenden (verständlich), schrittweise zum tieferen Konzept führen. Nicht mit Kategorie-Etiketten beginnen.

### Strategische Richtung: ARCHILLES als Wissensschicht für Agenten

OpenClaw, Moltbot und kommende Agentensysteme sind keine Gegner — sie sind potenzielle Abnehmer der ARCHILLES-Infrastruktur. Ein Agent, der Zugriff auf den ARCHILLES-Index hat, kennt das Fachgebiet des Forschers. Das ist kein Zufall, das ist Architektur.

**Implementierungsziel (nah):** ARCHILLES als MCP-Wissensquelle für agentenbasierte Workflows. Technischer Pfad: bestehende MCP-Tools (12 Tools, lokal) → HTTP/SSE-Transport (v1.3) → Zugriff durch beliebige MCP-kompatible Agenten.

Kommunikativ: "ARCHILLES ist die Wissensschicht, auf der Agenten aufsetzen können." Das ist die Antwort auf OpenClaw — nicht Konkurrenz, sondern Infrastruktur.

**Wichtig — Sicherheits-sensible Nutzer nicht abschrecken:** Die Mehrheit der anvisierten Forscher hat massive Sicherheitsbedenken gegenüber Agentensystemen wie OpenClaw — zu Recht. Die Kommunikation darf diese Gruppe nicht verlieren.

Argumentationslinie: ARCHILLES wird nicht für den heutigen Zustand entwickelt, sondern für den absehbaren Zustand, wenn die eklatanten Sicherheitsprobleme agentenbasierter Systeme gelöst sind. Jetzt ARCHILLES zu nutzen bedeutet: den eigenen Bestand erschließen, auf gesicherter lokaler Infrastruktur. Wenn Agenten sicher genug sind, ist die Infrastruktur bereits da — und der Forscher hat sie unter Kontrolle.

Der entscheidende Unterschied auch heute schon: ARCHILLES gibt Agenten strukturierten, kuratierten, epistemisch geordneten Zugriff — kein unkontrolliertes Durchwühlen. *Strict harness*, keine Carte blanche.

---

## 3. Wettbewerblicher Rahmen

### Gegen wen positionieren wir uns?

**Das Prinzip des flachen Wissenspools** — repräsentiert durch:
- "Open Brain"-Ansätze (alles gleichberechtigt in einem Pool — YouTuber, Blogposts, eigene Notizen, KI-Synthesen, ungeprüfte Quellen)
- Allgemeine RAG-Lösungen ohne epistemische Schichtung
- ChatGPT Memory, Notion AI, Mem.ai

*Hinweis intern:* Keine namentliche Nennung von Einzelpersonen (keine öffentlichen Figuren) in PR-Texten. Konzept beschreiben, nicht Namen.

**Das Problem dieser Systeme:** Sie vermischen alles — Primärquellen, KI-Synthesen, Meetingnotizen, ungeprüfte Blogartikel. Das mag für persönliches Knowledge Management taugen. Für Wissensarbeit, die auf epistemische Qualität angewiesen ist, ist das ein Strukturfehler.

Wissenschaftliches Arbeiten bedeutet: Quellen nach Qualität und Seriosität hierarchisieren. Gesichertes Wissen als gesichert behandeln und respektieren. Primärquellen stehen über Sekundärliteratur, Sekundärliteratur über Meinungen, Meinungen über Rauschen. Ein System, das diese Hierarchie einebnet, ist für Forschungsarbeit nicht geeignet — egal wie "smart" die Suche ist.

ARCHILLES schichtet den flachen Pool. Strukturiert die Befüllung. Macht Ordnung zum Prozess. Unter voller menschlicher Kontrolle.

```
Flache Wissenspools:   [Alles] ←→ [KI] — undifferenziert.

ARCHILLES:             [Bestand anderer] ←(Erschließung)── [KI] ──(Mustererkennung)→ [Eigenes Denken]
                       Bestand geschützt. Eigenes Denken versammelt. KI dient in beiden.
```

### Gegen wen positionieren wir uns *nicht*?

**Nicht gegen OpenClaw/Moltbot.** OpenClaw ist ein Handlungsagent — "KI, die Dinge erledigt". ARCHILLES ist Wissensinfrastruktur — "KI, die deinen Bestand kennt". Sie sind komplementär. Wenn ein OpenClaw-ähnlicher Agent Zugriff auf den ARCHILLES-Index hat, wird er smarter. Das ist kein Widerspruch, das ist ein Use Case.

Kommunikativ: Nicht kämpfen. Einordnen.

**Nicht gegen Calibre/Zotero.** Diese lösen andere Probleme. ARCHILLES braucht Calibre oder Zotero als Backend — es ersetzt sie nicht. "Calibre raushalten" bedeutet: Calibre nicht als Einstiegspunkt in die Kommunikation verwenden. Nicht: Calibre verleugnen.

### Wer ist der eigentliche Gegner?

Das Muster. Der Zustand, in dem ein Forscher mit tausenden durchgelesenen Büchern, Hunderten von Annotationen und Jahrzehnten akkumulierter Expertise *trotzdem* in jedem KI-Chat bei Null anfängt.

---

## 4. Zielgruppensegmente

*Prioriät für Launch-Phase:* Der Digital Humanist / technikaffine Forscher ist die Early-Adopter-Zielgruppe. Er ist auf GitHub, kennt RAG, versteht MCP, sucht aktiv nach Lösungen. Er wird ARCHILLES erproben, darüber schreiben und es an die Old-School-Kollegen weitergeben. Klassische Diffusionskurve: Early Adopters zuerst, dann über Empfehlung in die breitere Forschungsgemeinschaft.

### Primär (Launch): Der technikaffine Forscher / Digital Humanist

Digital Humanists, Computerlinguisten, informationswissenschaftlich orientierte Forscher, Forscher mit GitHub-Präsenz. Kennt RAG, versteht MCP, ist offen für Self-Hosting. Interessiert sich für Architekturentscheidungen. Will wissen, was unter der Haube passiert.

*Schmerz:* Bestehende RAG-Lösungen sind entweder zu generisch (für beliebige Dokumente) oder zu aufwändig (eigene Pipeline bauen). Keine Lösung respektiert die epistemische Struktur einer Forschungsbibliothek.
*Ziel:* Eine saubere, kontrollierbare Architektur, die meinen Bestand semantisch erschließt und sich in meinen KI-Workflow integriert.

### Sekundär: Der Forscher mit Tiefenbestand

Historiker, Philologen, Philosophen, Rechtswissenschaftler, Soziologen — mit substanziellen, über Jahre kuratierten digitalen Bibliotheken (300–5.000+ Titel). Offen für KI-Werkzeuge, aber skeptisch gegenüber Hype. Schätzen Quellenintegrität. Kommen über Empfehlung der Early Adopters.

*Schmerz:* Tausende Bücher, Hunderte Annotationen — und in jedem KI-Gespräch wird alles ignoriert. Der Forscher fängt bei Null an, obwohl er jahrzehntelange Expertise mitbringt.
*Ziel:* Mein akkumuliertes Wissen soll endlich zugänglich sein — für mein Denken und für die KI-Werkzeuge, die ich einsetze.

### Tertiär: Der ambitionierte Praktiker

Journalist mit archivarischem Selbstverständnis, Rechtsanwalt mit komplexer Fallakten-Bibliothek, unabhängiger Forscher ohne institutionellen Zugang.

*Schmerz:* Kein professionelles System adressiert meine Art zu arbeiten.
*Ziel:* Meinen Bestand semantisch erschließen und mit KI verbinden — ohne Cloud, ohne Datenweitergabe.

---

## 5. Kernbotschaften (nach Segment)

> **Tonalitätsprinzip für alle Segmente:** Der Forscher ist stets das grammatische Subjekt. ARCHILLES ist Werkzeug. KI steht nie im Aktiv — sie handelt nicht, sie wird eingesetzt. "Die KI macht..." ist grundsätzlich falsch. "Du greifst auf... zu", "du verbindest...", "du findest wieder..." ist richtig.

### Schlüsselbotschaft übergreifend: Der Paradigmenshift

Heute beginnen KI-Prompts so: *"Du bist ein Senior-Forscher mit 15 Jahren Berufserfahrung in..."*

Mit ARCHILLES beginnst du so: *"Hier ist das erschlossene Wissen aus 15 Jahren Forschungsarbeit in meiner Bibliothek."*

Das ist kein Stilmittel. Das ist ein grundlegender Unterschied: zwischen synthetischer Persona und realem akkumulierten Wissen. KI-Systeme können vorgeben, Experten zu sein. Aber sie können nicht deine 800 markierten Bücher, deine Randnotizen und deine jahrelang kuratierten Sekundärquellen kennen — es sei denn, du stellst sie vor.

Diese Botschaft ist der Einstieg des Launch-Artikels.

**Kandidaten für den englischen Artikel-Opener:**

> *"Your library is who you are, intellectually. Until now, your AI had no idea."*

> *"You didn't collect books. You built a knowledge system. ARCHILLES connects it to AI."*

Beide setzen auf die Investition, nicht auf das Lesen als Aktivität — das vermeidet die Falle der "Kulturtechnik"-Philosophie im Einstieg, ohne sie zu verleugnen. Die Kulturtechnik-Dimension kann im dritten Absatz entfaltet werden, wenn der Leser bereits engagiert ist.

---

### Für den technikaffinen Forscher / Digital Humanist (Primär, Launch)

"Local-first RAG für Forschungsbibliotheken: BGE-M3 (1024-dim, multilingual), LanceDB, Hybrid Search mit RRF-Fusion, optionales Cross-Encoder Reranking. Adapter-Architektur für Calibre, Zotero, beliebige Ordnerstruktur. 12 MCP-Tools für Claude Desktop. HTTP/SSE-Transport auf dem Roadmap."

Der Unterschied zu generischen RAG-Lösungen: ARCHILLES kennt die epistemische Schichtung von Forschungsmaterial. Nicht alle Chunks sind gleich — eine Fußnote ist keine Kernthese, ein Kommentar des Autors ist keine Primärquelle, eine KI-Synthese ist kein Beleg.

*Proof points:*
- Hybrid Search (dense vector + BM25, RRF fusion)
- Optional: Cross-Encoder Reranking (BAAI/bge-reranker-v2-m3)
- Adapter-Architektur (SourceAdapter Interface) — nicht an ein Bibliotheksprogramm gebunden
- Drei Chunk-Typen: `content` (Primärtext) / `annotation` (eigene Markierungen) / `calibre_comment` (kuratierte Sekundärquellen)
- Progress.db für crash-sicheres Batch-Indexing
- MIT-Lizenz, Open Source, vollständig lokal

### Für den Forscher mit Tiefenbestand (Sekundär)

"Du hast jahrelang gelesen, markiert, kommentiert — und trotzdem fängst du in jedem KI-Gespräch bei Null an. Mit ARCHILLES verbindest du deine Bibliothek mit deinen KI-Werkzeugen. Dein eigenes akkumuliertes Wissen — durchsuchbar, zitierfähig, strukturell erhalten."

*Reformulierungsprinzip:* Nicht "ARCHILLES erinnert dich" — sondern "du findest wieder, was du weißt." KI ist Werkzeug, nicht Akteur. Du steuerst, was die KI sieht.

*Proof points:*
- Epistemische Schichtung: Primärquelle ≠ Annotation ≠ KI-Synthese — strukturell getrennt
- Archilles Lab: eigenes Denken und eigene Produktion, getrennt vom kuratierten Bestand
- Zitierfähige Ergebnisse mit Seitenangabe
- Lokal, kein Abonnement, keine Datenweitergabe

### Für den ambitionierten Praktiker

"Verbinde deine Bibliothek mit deinen KI-Werkzeugen — egal ob ein beliebiger Ordner auf deinem Rechner oder Apps wie Zotero, DEVONthink oder Obsidian. ARCHILLES indexiert lokal, gibt keine Daten weiter, und integriert sich in deinen bestehenden Workflow."

*Reihenfolge bewusst:* Folder-Adapter zuerst (plattformunabhängig), dann Apps. Calibre nicht in dieser Botschaft.

*Proof points:*
- Folder-Adapter: beliebige Verzeichnisstruktur als Bibliothek
- Adapter für Zotero, DEVONthink, Obsidian (als Ordner-Struktur)
- Lokal, kein Cloud-Upload, keine Datenweitergabe
- Erster Start ohne Terminal möglich (Roadmap: Desktop-App)

---

## 6. Tagline-Optionen

Sieben Optionen nach Feedback-Runde. Jede deckt andere Kommunikationszwecke ab.

---

**Option A (revidiert): "Expand your thinking with your library."**

Gewünschte semantische Ambiguität: (1) *Expand your thinking* — mit Hilfe von KI/ARCHILLES — *with your library* als Mittel. (2) Die bereits existierende Praxis guter Forscher: *thinking with one's library* — jetzt erweitert, ausgebaut, potenziert. Der Forscher ist grammatisches Subjekt. ARCHILLES bleibt Instrument.

*Typografische Idee:* Zeilenbruch als semantisches Signal:
```
Expand your
thinking with your library.
```
Oder als Venn-Diagramm: Zwei Kreise — "Your library" (links) und "AI" (rechts) — mit "your thinking" als Schnittmenge in der Mitte. ARCHILLES erzeugt diese Schnittmenge. Das ist die visuelle Logik des Produkts.

*Stärke:* Trifft die Produktidentität präzise. Skaliert von Twitter-Bio bis Konferenzvortrag.
*Schwäche:* Für GitHub README als Subheadline eventuell kürzen zu "Expand your thinking. With your library."

---

**Option B: ~~"Read your library. Remember your research."~~**

*Aus dem Rennen.* Vom Autor nicht als elegant bewertet. Nicht weiterentwickeln.

---

**Option C (revidiert): "Connect your library to your AI."**

"Bring your own library" hatte ein Ortsproblem — "bring wohin?" kollidierte mit der Local-first-Botschaft. "Connect" ist präziser: bidirektionale Verbindung, keine Übergabe, kein Upload. Der Forscher verbindet — er gibt nicht ab.

Alternative Variante: **"Give your AI what you've actually read."** — Kontrast zu ChatGPT-Weltwissen, direkt, provokativ, leicht polemisch. Eignet sich für Social-Media-Teaser, nicht als Primär-Tagline.

*Stärke:* Technisch klar, plattformunabhängig, für GitHub/HackerNews geeignet.
*Schwäche:* Funktional, kein emotionales Versprechen.

---

**Option D (revidiert): "Your sources. Your thinking. Your edge."**

Dreiteiler in der Richtung von Option D, aber mit "edge" statt "AI". "Edge" = der Wettbewerbsvorteil des Forschers, der seinen Bestand erschlossen hat gegenüber allen, die in jedem Gespräch bei Null anfangen. Keine inflationäre "Your AI"-Geste.

Architektur im Dreiteiler: *Sources* → Archilles Bib (kuratierter Bestand). *Thinking* → Archilles Lab (eigenes Denken). *Edge* → das Resultat.

*Stärke:* Beschreibt die Schichten-Architektur kompakt. "Edge" ist inhaltlich ehrlich — das ist der tatsächliche Nutzen.
*Schwäche:* "Edge" kann techbro-artig klingen. In akademischen Kontexten möglicherweise unpassend. Testbedürftig.

---

**Option E: "Your research system, AI-powered."**

Nicht aus dem bisherigen Kanon. Researcher-centric: "your research system" (nicht "AI for your research"). Der Forscher hat ein System — ARCHILLES gibt ihm KI-Power. Kontrolle und Besitz bleiben beim Forscher.

*Stärke:* Deutlich gegen "KI, die für dich forscht" positioniert. Klar in der Rolle von KI als Enabler, nicht als Akteur.
*Schwäche:* "AI-powered" ist generisch. Verliert den Tiefenbestand-Aspekt.

---

---

**Option F: "Introduce your library to your favourite AI."**

Der Forscher ist grammatisches Subjekt und Handelnder. "Introduce" ist sozial — er stellt vor, kontrolliert die Verbindung, entscheidet über den Zugang. "Favourite AI" ist persönlicher als "preferred AIs" — impliziert eine bestehende Beziehung zu einem KI-Werkzeug, das jetzt Zugang zum eigenen Bestand bekommt.

Variante mit Akzentverschiebung: **"Introduce your personal thinking to your favourite AI."** — Verschiebt von der äußeren Sammlung (library) zum inneren Denken (personal thinking). Passt zur Archilles-Lab-Idee: nicht nur Bücher, sondern eigene Texte, Entwürfe, Notizen. Stärkere emotionale Bindung.

*Stärke:* Frisch, unverbraucht, researcher-centric. "Introduce" ist das stärkste Verb in dieser Gruppe — der Forscher handelt, entscheidet, kontrolliert.
*Testbedarf:* Beide Varianten auf Zielgruppe testen.

---

**Option G (revidiert): "Harness AI to your research."**

Drei Wörter, Verb-Form, Forscher ist der Handelnde. "Harness" als Verb: den Agenten einspannen, wie ein Gespann — die Kraft des Pferdes nutzen, ohne die Kontrolle abzugeben. Das Bild ist alt und ehrlich: Kraft unter Kontrolle.

Varianten:
- **"Harness AI to your research."** — kompakt, klar, stark
- **"Power your research with AI — with a strict harness."** — länger, expliziter für sicherheitssensible Zielgruppe
- **"Harness AI. Keep the reins."** — Zweiteiler, explizit über Kontrolle

*Stärke:* "Harness" ist das ehrlichste Wort für das, was ARCHILLES tut: AI strukturiert einspannen, nicht loslassen. Direkt gegen den "carte blanche"-Ansatz positioniert.
*Schwäche:* Für manche zu technisch-bildlich. In akademischen Kontexten möglicherweise unvertraut. Testbedürftig.

---

### Aktuelle Empfehlung

*Vorläufig — zur Bewertung durch den Autor nach Verarbeitung aller Änderungen (Rev. 3).*

| Kanal | Tagline | Option |
|---|---|---|
| Website Hero | "Expand your thinking with your library." | A |
| GitHub README Subheadline | "Introduce your library to your preferred AIs." | F |
| Social Media / Teaser | "Give your AI what you've actually read." | C-Variante |
| Sicherheits-sensible Zielgruppe | "Integrate AI into your research process. On your terms." | G-Kurzform |
| Konferenz / Pitch-Eröffnung | "Your sources. Your thinking. Your edge." | D |
| Philosophie-Sektion / About | Μνήσθητι σαυτοῦ. | — |

Der aktuelle README-Tagline ("Because your library deserves better than keyword search.") muss ersetzt werden. Defensiv, beschreibt ein Problem, kein Versprechen.

---

## 6b. Visuelle Identität: Das ARCH-Motiv *(Phase 5 — jetzt festhalten)*

Das Namenskürzel ARCH taucht in fünf semantisch relevanten Wörtern auf:

| Wort | ARCH-Anteil | Bedeutung für ARCHILLES |
|---|---|---|
| **reseARCH** | Suffix | Was ARCHILLES unterstützt |
| **ARCHive** | Präfix | Was es schützt und indexiert |
| **ARCHitecture** | Präfix | Was es bereitstellt |
| **ARCHaeology** | Präfix | Was es mit Beständen tut (Ausgrabung) |
| **ARCHilles** | Vollwort | Der Produktname selbst |

Typografisches Leitmotiv: ARCH immer als visueller Block hervorgehoben (Fettdruck, Farbe, Kapitälchen). Skaliert von Logo über Präsentationsfolien bis zu Social-Media-Grafiken.

Zusätzliche Ebene: Im Griechischen bedeutet ἀρχή (arché) — Ursprung, Anfang, Prinzip. Das ist der intellektuelle Ursprung des eigenen Wissens. Für Klassiker-affine Zielgruppen eine stille Botschaft.

Option E in diesem Licht: **"Your reseARCH ARCHitecture, powered by ARCHilles."** — typografisch stark, inhaltlich präzise, funktioniert nur als visuelle Umsetzung, nicht als Fließtext.

---

## 7. Narrative Struktur für PR-Texte (LinkedIn, Blog, Artikel)

Für alle längeren Texte (Artikel, LinkedIn-Posts, Launch-Text) gilt diese Argumentationslinie:

**1. Status quo beschreiben** — Wie Forscher heute mit Bibliotheken und KI arbeiten. Die vertrauten Strukturen: Calibre, Zotero, Annotationen. Das ist das Bekannte. Der Leser erkennt sich wieder.

**2. Neue Entwicklung benennen** — Was sich gerade verändert: KI-Assistenten, MCP, Agenten, OpenClaw. Was das bedeutet: Das Spielfeld verändert sich fundamental.

**3. Die Lücke herleiten** — Aus dem Zusammenspiel von (1) und (2) ergibt sich die Lücke: Forschende mit tiefen, kuratierten Beständen fangen trotz allem in jedem KI-Gespräch bei Null an. Ihre Expertise ist für KI unsichtbar.

**4. ARCHILLES als Lösung — abrakadabra** — Nicht als Werbebotschaft, sondern als logische Konsequenz aus der hergeleiteten Lücke. ARCHILLES macht den eigenen Bestand für KI zugänglich — epistemisch geschichtet, lokal, unter Kontrolle des Forschers.

**5. Meta-Ebene: Kategorie** — "Ein System wie ARCHILLES hat noch keinen etablierten Namen." Das schlägt eine neue Kategorie vor und positioniert ARCHILLES als Pionier. Hier: semantische Forschungsschicht, knowledge infrastructure, research memory system.

**6. Funktionen beschreiben und abgrenzen** — Einstieg mit Bekanntem (semantic search), schrittweise zur epistemischen Architektur. Was ARCHILLES ist. Was es nicht ist.

---

## 8. Was ARCHILLES nicht kommuniziert

Einige Positionierungsrisiken, die aktiv vermieden werden sollten:

**"Calibre für KI"** — zu eng, falsche Erwartungshaltung, schließt Zotero-Nutzer aus.

**"KI, die für dich forscht"** — das Gegenteil der Leitphilosophie. ARCHILLES automatisiert nicht die Forschung, es verlängert die Fähigkeiten des Forschers.

**"Besser als ChatGPT"** — falscher Vergleichsrahmen. ChatGPT ersetzt die Bibliothek des Nutzers nicht; ARCHILLES erschließt sie. Kein direkter Vergleich, keine Hierarchie.

**McGilchrist als Marketingkommunikation** — Die hemisphärische Metapher ist ein präzises Designprinzip und ein intellektuell ehrlicher Bezugsrahmen. Als Kommunikation an unbekannte Zielgruppen ist sie zu esoterisch und riskiert Arroganz-Wahrnehmung. Verwendung: interne Dokumente, tiefgehende Artikel, Community-Gespräche mit der richtigen Zielgruppe. Nicht: Landing Pages, GitHub README, PR-Texte.

---

## 8. Der Kern

> Du hast jahrelang gelesen. Du weißt mehr, als du gerade abrufen kannst.
> ARCHILLES macht deinen Bestand zugänglich — für dein Denken und für die KI-Werkzeuge, die du einsetzt.

Oder in der philosophischen Kurzform: Μνήσθητι σαυτοῦ. — Erinnere dich deiner selbst.

Das ist der Kern. Wenn ein Text über ARCHILLES diesen Gedanken nicht trägt — dass das Problem nicht Suche ist, sondern Zugang zu dem, was man schon weiß — ist er nicht fertig.

---

*POSITIONING_STATEMENT.md — Arbeitsfassung März 2026*
*Grundlage: ARCHILLES_HEMISPHERIC_ARCHITECTURE_fürCowork.md (v5), ARCHILLES_SKILL.md, Competitive Research (OpenClaw/Moltbot)*
*Nächste Phase: 4 — Messaging Architecture, README-Revision*
