# ARCHILLES — Positioning Statement
**Arbeitsfassung:** Juni 2026 (Rev. 5)
**Phase:** 3 von 6 (Positionierung & USP) — Neufassung
**Vorgänger:** Rev. 4 (März 2026)

> Dieses Dokument ist das strategische Fundament für alle nachfolgenden Kommunikationsarbeiten. Es definiert, was ARCHILLES ist, für wen es ist, wogegen es sich abgrenzt und warum jemand es wählt. Änderungen hier wirken durch in README, Website (archilles.org), PR-Texte, Channel-Strategie.

> **Was Rev. 5 ändert.** Drei Dinge sind seit März passiert. Erstens: Die Live-Site ist schärfer geworden als das Positioning-Dokument — sie verkauft *Informed RAG* und zitierfähige Antworten, ohne Lab/McGilchrist. Zweitens: Bib/Lab ist nicht länger Zukunftsmusik, sondern funktional gelöst — Obsidian als Lab, Zotero und Calibre als angereicherte, GraphRAG-artige Bib. Drittens: Die Forschung an der Schicht zwischen Modelltraining und Aufgabe (besseres RAG, GraphRAG, vorab verdichtete Kontext-Repräsentationen) bewegt sich schnell. Rev. 5 nutzt diese Bewegung zur Standortbestimmung — sie bestätigt die Grundannahme des Projekts, statt sie infrage zu stellen.

---

## 0. Standortbestimmung: die Zwischenschicht (Juni 2026)

Zwischen dem, was ein Modell im Training gelernt hat, und der konkreten Aufgabe, die es lösen soll, fehlt eine Schicht. Heute wird sie behelfsmäßig gefüllt: Man kippt Dokumente ins Kontextfenster und hofft, dass das Modell das Richtige findet. Das skaliert schlecht — je größer der Kontext, desto teurer und desto unschärfer die Antwort. Der eigene Bestand wird bei jeder Anfrage neu eingelesen und nach dem Schließen des Chats wieder vergessen.

Der ernsthafte Versuch, diese Schicht zu bauen, heißt RAG: Statt alles ins Kontextfenster zu kippen, werden nur die relevanten Passagen geholt und dem Modell gereicht. Richtig gedacht — aber meist naiv gebaut. Naives RAG ist strukturblind: Alles geht als Chunk hinein, alles kommt als Chunk heraus. Eine Fußnote wiegt so viel wie eine These; Tags, Querverweise, Inhaltsverzeichnisse, Kapitelgrenzen verschwinden. Wo der Forscher die Schicht am schärfsten bräuchte — im eigenen Fach —, bleibt sie stumpf.

Also wird nach Abhilfe gesucht. GraphRAG und verwandte Ansätze versuchen, Beziehungen zwischen Quellen wiederherzustellen, statt nur Textbrocken zu vergleichen. Selbst der RAG-Marktführer steuert um und kompiliert Struktur, bevor er retrieved. Und die jüngste Forschung verdichtet ganze Korpora vorab zu kompakten, ladbaren Repräsentationen, die das Kontextfenster entlasten. So verschieden diese Wege sind — sie suchen alle dasselbe: eine bessere Schicht zwischen Modell und Aufgabe.

Diese Bewegung nutze ich zur Standortbestimmung von ARCHILLES — nicht, um die Kommunikation darauf umzustellen. Denn sie bestätigt die Grundannahme des Projekts. ARCHILLES' Antwort auf das naive RAG ist *Informed RAG*: die Struktur nutzen, die im Bestand des Forschers längst liegt — innen die Architektur des Textes (Inhaltsverzeichnis, Kapitel, Überschriften), außen die Kuratierung des Forschers (Tags, Highlights, Querverweise, Gewichtungen). Niemand muss diese Struktur neu erfinden; sie ist das Ergebnis jahrelanger Arbeit.

Und der entscheidende Punkt liegt unter all diesen Wegen: **Der eigene, kuratierte Bestand ist die richtige Einheit.** Ob eine KI ihn präzise *retrieved* oder zu einer ladbaren Repräsentation *verdichtet* — beides braucht dasselbe Fundament: einen geschichteten, gewichteten, selbst kuratierten Bestand. Nicht den von fremden Gatekeepern gemittelten Durchschnitt, sondern: *Hier — benutze das. Mein Wissen.*

ARCHILLES baut diese Schicht heute in ihrer kontrollierbaren Form: lokal, quellentreu, geschichtet. Was die Aufgabe braucht, wird bereitgestellt — nicht der ganze Bestand auf einmal, sondern das Relevante, mit Beleg.

> **Nicht das ganze Wissen ins Kontextfenster. Nicht das ganze Wissen ins Modellgewicht.**
> **Sondern eine Schicht dazwischen — informiert durch die Struktur, die der Forscher längst gelegt hat, belegbar und ihm gehörend.**

---

## 1. Formales Positioning Statement

**Für** Forscher und Wissenschaftler in Geistes-, Rechts- und Sozialwissenschaften — und für alle, die über Jahre eine strukturierte digitale Bibliothek aufgebaut haben und beginnen, KI in ernsthafte Wissensarbeit einzubinden —

**die** das Problem kennen, dass ihre kuratierten Bestände für KI unsichtbar sind, dass ihre Annotationen nirgendwohin führen, und dass flache KI-Wissensarchitekturen den Unterschied zwischen Primärquelle und Synthese nicht respektieren,

**ist ARCHILLES** eine lokale, plattformunabhängige semantische Wissensinfrastruktur —

**die** den eigenen Bestand epistemisch geschichtet erschließt, zitierfähig und quellentreu, und zwei Räume verbindet: den kuratierten Bestand anderer (Bib) und das eigene Denken (Lab) —

**im Unterschied zu** naivem RAG (strukturblind, alles als Chunk), flachen KI-Wissenspools (Notion AI, generische Memory-Systeme) und reinen Bibliotheksverwaltungen (Zotero, Calibre allein) —

**weil** ARCHILLES die epistemische Schichtung von Forschungswissen strukturell bewahrt, jede Antwort an eine prüfbare Quelle bindet, vollständig lokal arbeitet, bibliotheksagnostisch ist (Zotero, Calibre, Obsidian, beliebige Ordner) — und dem Forscher die Kontrolle über seinen Bestand lässt.

---

## 2. Kategoriedefinition: Was ist ARCHILLES?

ARCHILLES gehört zu keiner etablierten Kategorie — und das ist die eigentliche Kommunikationsaufgabe.

Es ist **kein Bibliotheksprogramm.** Zotero und Calibre *verwalten* Bestände. ARCHILLES *erschließt* sie semantisch.

Es ist **kein KI-Agent.** Agentensysteme handeln für den Nutzer. ARCHILLES stellt Wissen bereit, damit der Nutzer besser handelt — und bleibt Werkzeug in dessen Hand.

Es ist **kein Knowledge-Management-Tool im Consumer-Sinne.** Notion AI und generische Memory-Systeme sammeln alles gleichberechtigt. ARCHILLES unterscheidet zwischen Primärquelle, kuratierter Annotation und Synthese — und hält diese Schichten strukturell getrennt.

Es ist **kein gewöhnliches RAG-System.** Generisches RAG indexiert Dokumente und gibt Chunks zurück. ARCHILLES kennt den Unterschied zwischen einer Primärquelle, einer Sekundärquelle, einer eigenen Randnotiz und einer Synthese — und trägt diese Unterscheidung durch den gesamten Workflow.

Und es ist **kein Modell, das deinen Kontext internalisiert.** Die neuere Forschung verdichtet Korpora vorab zu ladbaren Repräsentationen, die das Kontextfenster entlasten — ein verwandtes Ziel, anderer Ort. ARCHILLES lässt das Wissen in den Quellen und macht es abrufbar, mit Beleg. Das eine verschmilzt, das andere erschließt; das eine verliert die Quelle aus dem Blick, das andere zeigt auf sie. Beide Wege brauchen dieselbe Voraussetzung: einen kuratierten, geschichteten Bestand.

> **ARCHILLES ist die semantische Schicht zwischen dem Forschungsbestand und den KI-Werkzeugen, die der Forscher einsetzt.**

### Die Zwei-Räume-Architektur — jetzt funktional, nicht mehr konzeptuell

In Rev. 4 war Bib/Lab noch eine Designidee mit aufgeschobener Schreibseite. Das ist überholt. Beide Räume existieren heute als reale Werkzeuge:

- **Archilles Bib** — der kuratierte Bestand anderer. Zotero und Calibre (künftig DEVONthink u. a.) liefern annotierte, verschlagwortete, kommentierte Bestände: Metadaten, Tags, Highlights, Querverweise. Diese Anreicherung ist beinahe graphartig — die Beziehungen sind schon da, der Forscher hat sie über Jahre gelegt. Read-only, Erschließung.
- **Archilles Lab** — das eigene Denken. Ein Obsidian-Vault, schreibfähig, produktiv: Notizen, Entwürfe, Verknüpfungen, eigene Texte. Hier entsteht Neues, hier werden Verbindungen gezogen.

Der entscheidende Punkt: Diese beiden Räume bleiben *getrennt und unter Kontrolle*. Ein Ansatz, der alles in ein Modellgewicht einschmilzt, verwischt die Grenze zwischen dem, was andere geschrieben haben, und dem, was du denkst — zwischen Beleg und Einfall. ARCHILLES hält sie. Genau diese Grenze ist das, was wissenschaftliches Arbeiten von Knowledge-Pooling unterscheidet.

> **Hinweis Kommunikation.** Die McGilchrist-/Hemisphären-Metapher bleibt *Subtext* — für tiefe Artikel und die richtige Community, nicht für Hero, README, PR. Im Einstieg führt „semantic search", dann schrittweise zur Architektur. „Bib & Lab" (oder „Archiv & Werkstatt") ist die öffentlich tragfähige Fassung des Prinzips.

### Strategische Richtung: ARCHILLES als Wissensschicht für Agenten — und für lernende Modelle

Agentensysteme sind keine Gegner, sondern potenzielle Abnehmer der Infrastruktur. Ein Agent mit Zugriff auf den ARCHILLES-Index kennt das Fachgebiet des Forschers — strukturiert, kuratiert, epistemisch geordnet. *Strict harness*, keine Carte blanche. (Die Ausformulierung des MCP-Zugangs für Agenten gehört in die Roadmap, nicht hierher.)

Dasselbe gilt, mit Pointe, für lernende Modelle. Selbst ein Modell, das den eigenen Kontext vorab verdichtet, braucht für den Long-Tail und für *belegbare* Aussagen weiterhin präzises, quellentreues Retrieval — und es braucht überhaupt erst einen kuratierten Korpus, aus dem es lernt. Niemand baut ein rein gewichtsbasiertes System. Das heißt: Die zitierfähige Erschließungsschicht verschwindet nicht — sie wird gebraucht, gerade *weil* Modelle anfangen zu lernen. ARCHILLES ist diese Schicht.

Das deckt sich mit dem Fernziel des Projekts. Der Traum ist nicht, solche Modelle zu meiden, sondern eines Tages selbst eine permanent lernende KI zu nutzen — lokal, auf dem eigenen Bestand. Heute utopisch; manche Utopien werden wahr. Was ARCHILLES jetzt tut und was diese Utopie braucht, ist dasselbe Fundament: ein selbst kuratierter, geschichteter, gewichteter Bestand. Wer ihn heute auf lokaler Infrastruktur erschließt, hat die Schicht bereits — und unter Kontrolle.

---

## 3. Wettbewerblicher Rahmen

### Achse I — die Zwischenschicht (Standortbestimmung, nicht Gegnerschaft)

Die eigentliche Bewegung im Markt ist nicht ein einzelner Akteur, sondern die Suche nach der **Schicht zwischen Modelltraining und Aufgabe** (siehe Abschnitt 0): besseres RAG, GraphRAG, vorab verdichtete Kontext-Repräsentationen, die das Kontextfenster entlasten. Diese Bewegung ist kein Gegner — sie ist der Beleg, dass ARCHILLES das richtige Problem bearbeitet.

**Der gemeinsame Nenner:** Alle diese Wege wollen einer KI den *eigenen* Kontext geben statt des gemittelten Internet-Durchschnitts. Das ist exakt ARCHILLES' Grundannahme. Der Unterschied liegt nicht im Ziel, sondern in Ort und Kontrolle:

- **Wo liegt das Wissen?** Verdichtende Ansätze ziehen den Kontext in eine Repräsentation, oft in der Cloud, oft mit der Firma als adressierter Einheit. ARCHILLES lässt ihn lokal, im Bestand des Einzelkämpfers.
- **Ist die Antwort belegbar?** Eine in Gewichte oder Caches verdichtete Repräsentation *weiß*, aber sie *zeigt nicht auf die Seite*. ARCHILLES bindet jede Antwort an eine prüfbare Quelle — für Geisteswissenschaft nicht verhandelbar.
- **Bleibt die Schichtung erhalten?** Verschmelzen ebnet Primärquelle, Kommentar und Notiz ein. ARCHILLES hält die epistemischen Ebenen getrennt.

**Die Pointe statt eines Konters:** ARCHILLES konkurriert nicht mit dieser Forschung — es liefert ihre Voraussetzung. Ob eine KI den Bestand morgen *retrieved* oder übermorgen *verdichtet*: ohne einen kuratierten, geschichteten Korpus gibt es weder gute Treffer noch eine gute Repräsentation. *Der eigene Bestand ist die richtige Einheit — erschlossen, belegt, lokal.*

### Achse II — gegen den flachen Wissenspool (bestehend)

Generische RAG-Lösungen ohne epistemische Schichtung, Notion AI, Memory-Systeme, die alles gleichberechtigt sammeln: YouTuber neben Primärquelle, ungeprüfter Blog neben Standardwerk. Für persönliches Knowledge Management mag das taugen. Für Wissensarbeit, die auf epistemische Qualität angewiesen ist, ist es ein Strukturfehler.

Wissenschaftliches Arbeiten heißt: Quellen nach Qualität hierarchisieren. Primärquelle über Sekundärliteratur, Sekundärliteratur über Meinung, Meinung über Rauschen. Ein System, das diese Ordnung einebnet, ist für Forschung untauglich — egal wie „smart" die Suche ist. ARCHILLES schichtet den flachen Pool, unter voller menschlicher Kontrolle.

### Achse III — gegen naives RAG (bestehend, technisch)

Die meisten RAG-Systeme sind blind für Struktur: Eine Fußnote wiegt so viel wie eine These; Tag-Schemata, Querverweise, Inhaltsverzeichnisse, Kapitelgrenzen sind unsichtbar. Bezeichnend: Der RAG-Marktführer hat kürzlich umgesteuert und kompiliert Struktur jetzt *vor* dem Retrieval. ARCHILLES nutzt die Struktur, die im Bestand des Forschers längst liegt — innen (Inhaltsverzeichnis, Kapitel, Überschriften) wie außen (Tags, Highlights, Querverweise, Lesenotizen).

### Gegen wen *nicht*

- **Nicht gegen Agenten.** Komplementär: ARCHILLES ist die Wissensschicht, auf der Agenten aufsetzen. Einordnen, nicht kämpfen.
- **Nicht gegen Zotero/Calibre/Obsidian.** ARCHILLES braucht sie als Backend, ersetzt sie nicht. Sie sind nicht der Einstiegspunkt der Kommunikation, aber sie werden nicht verleugnet.
- **Nicht gegen die Forschung an verdichteten Repräsentationen.** Sie teilt das Ziel — der eigene Kontext statt des Durchschnitts. Wer sie angreift, stellt sich gegen die eigene Grundannahme. Klüger: einordnen, nicht den Akteur attackieren. Über die *Idee* reden (Ort, Beleg, Kontrolle), nicht über Namen — schon gar nicht in einer Phase, in der niemand weiß, was sich durchsetzt.

### Wer ist der eigentliche Gegner?

Kein Wettbewerber. Das **Muster**: dass ein Forscher mit tausenden gelesenen Büchern, hunderten Annotationen und jahrzehntelanger Expertise *trotzdem* in jedem KI-Chat bei Null anfängt. Seine Expertise ist für die KI unsichtbar. Das ist das Problem — und ARCHILLES löst es durch Erschließen unter Kontrolle, dort, wo das Wissen liegt.

---

## 4. Zielgruppensegmente

*Launch-Priorität:* Der technikaffine Forscher / Digital Humanist ist die Early-Adopter-Gruppe — auf GitHub, kennt RAG, versteht MCP, sucht aktiv. Er erprobt ARCHILLES, schreibt darüber, trägt es zu den Old-School-Kollegen. Klassische Diffusion: Early Adopters zuerst, dann über Empfehlung in die Breite.

### Primär (Launch): Der technikaffine Forscher / Digital Humanist
Digital Humanists, Computerlinguisten, informationswissenschaftlich Orientierte, Forscher mit GitHub-Präsenz. Kennt RAG, versteht MCP, offen für Self-Hosting, interessiert an Architektur.

*Schmerz:* Bestehende RAG-Lösungen sind zu generisch oder zu aufwändig. Keine respektiert die epistemische Struktur einer Forschungsbibliothek.
*Ziel:* Eine saubere, kontrollierbare Architektur, die den Bestand semantisch erschließt und sich in den KI-Workflow fügt.
*Neu relevant:* Diese Gruppe verfolgt die Forschung an verdichteten Kontext-Repräsentationen und versteht die technische Wette sofort. Sie ist auch die Gruppe, die die Frage „läuft das lokal, und kann es belegen?" am schnellsten stellt — und teilt.

### Sekundär: Der Forscher mit Tiefenbestand
Historiker, Philologen, Philosophen, Rechts- und Sozialwissenschaftler mit substanziellen, über Jahre kuratierten Bibliotheken. Offen für KI, skeptisch gegen Hype, hält Quellenintegrität hoch.

*Schmerz:* Tausende Bücher, hunderte Annotationen — und in jedem KI-Gespräch ignoriert. Null statt Tiefe.
*Ziel:* Das akkumulierte Wissen endlich zugänglich — für das eigene Denken und für die eingesetzten KI-Werkzeuge.

### Tertiär: Der ambitionierte Praktiker
Journalist mit Archiv, Anwalt mit Fallakten-Bibliothek, unabhängiger Forscher ohne Institution.

*Schmerz:* Kein professionelles System adressiert die eigene Arbeitsweise.
*Ziel:* Bestand semantisch erschließen, mit KI verbinden — ohne Cloud, ohne Datenweitergabe.

---

## 5. Kernbotschaften (nach Segment)

> **Tonalitätsprinzip.** Der Forscher ist stets grammatisches Subjekt. KI wird eingesetzt, sie handelt nicht. „Die KI macht…" ist falsch. „Du greifst zu", „du verbindest", „du findest wieder" ist richtig. Wo andere Ansätze das Modell ins Aktiv setzen („das Modell lernt dich"), bleibt bei ARCHILLES der Forscher der Handelnde („du erschließt, was du weißt").

### Übergreifend: Der Paradigmenshift

Bisher (Rev. 4):
> Heute beginnen Prompts mit *„Du bist ein Senior-Forscher mit 15 Jahren Erfahrung in…"*. Mit ARCHILLES beginnst du mit *„Hier ist das erschlossene Wissen aus 15 Jahren in meiner Bibliothek."*

Zugespitzt auf die Zwischenschicht:
> Eine KI antwortet aus dem, was sie im Training gesehen hat — dem von fremden Gatekeepern gemittelten Durchschnitt. ARCHILLES legt eine Schicht dazwischen: *Hier — benutze das. Mein Bestand, geschichtet und belegbar.* Nicht der ganze Bestand auf einmal ins Kontextfenster, nicht in ein fremdes Modellgewicht — sondern das Relevante, mit Quelle, dort wo es bleibt: bei dir.

Englische Opener-Kandidaten:
> *„Your library is who you are, intellectually. Make it the layer your AI works from."*

> *„Don't pour your whole library into the context window. Give the model the part that matters — with the page to prove it."*

> *„The model answers from the public average. Hand it yours instead."*

### Für den technikaffinen Forscher / Digital Humanist (Primär)
„Local-first RAG für Forschungsbibliotheken: BGE-M3 (1024-dim, multilingual), LanceDB, Hybrid Search mit RRF-Fusion, optionales Cross-Encoder-Reranking. Adapter für Zotero, Calibre, Obsidian, beliebige Ordner. MCP-nativ, stdio und HTTP/SSE."

Der Unterschied zum generischen RAG: ARCHILLES kennt die epistemische Schichtung. Eine Fußnote ist keine These, ein Kommentar keine Primärquelle, eine Synthese kein Beleg.

Der Unterschied zu verdichteten Repräsentationen: Was ARCHILLES liefert, ist *prüfbar*. Jede Antwort zeigt auf Seite und Kapitel. Eine in Gewichte oder Caches verdichtete Repräsentation kann das nicht.

*Proof points:* Hybrid Search (dense + BM25, RRF) · optional Cross-Encoder (bge-reranker-v2-m3) · Adapter-Interface, nicht an ein Programm gebunden · drei Chunk-Typen (`content` / `annotation` / `comment`) · crash-sicheres Batch-Indexing · MIT, Open Source, lokal.

### Für den Forscher mit Tiefenbestand (Sekundär)
„Du hast jahrelang gelesen, markiert, kommentiert — und fängst in jedem KI-Gespräch bei Null an. ARCHILLES verbindet deine Bibliothek mit deinen KI-Werkzeugen. Dein akkumuliertes Wissen — durchsuchbar, zitierfähig, strukturell erhalten, und es bleibt deins."

*Prinzip:* Nicht „ARCHILLES erinnert dich" — sondern „du findest wieder, was du weißt." KI ist Werkzeug, nicht Akteur. Du steuerst, was sie sieht.

*Proof points:* Epistemische Schichtung (Primärquelle ≠ Annotation ≠ Synthese) · Bib (kuratierter Bestand) und Lab (eigenes Denken in Obsidian) getrennt · zitierfähige Ergebnisse mit Seitenangabe · lokal, kein Abo, keine Datenweitergabe.

### Für den ambitionierten Praktiker (Tertiär)
„Verbinde deine Bibliothek mit deinen KI-Werkzeugen — ein beliebiger Ordner oder Apps wie Zotero, Obsidian, DEVONthink. ARCHILLES indexiert lokal, gibt nichts weiter, fügt sich in den bestehenden Workflow."

*Reihenfolge:* Folder-Adapter zuerst (plattformunabhängig), dann Apps.

---

## 6. Tagline-Set (eingedampft)

Rev. 4 trug sieben Optionen. Rev. 5 reduziert auf die tragenden. Auswahlkriterium: Forscher als Subjekt, kein „die KI macht", skalierbar von Bio bis Vortrag.

| Zweck | Tagline | Herkunft |
|---|---|---|
| **Website Hero (aktuell live)** | „Ask your library. Get cited answers." | Live-Site — funktioniert, behalten |
| **Hero-Alternative (Identität)** | „Expand your thinking with your library." | Rev. 4 Option A |
| **GitHub / technisch** | „Introduce your library to your favourite AI." | Rev. 4 Option F |
| **Social / Teaser** | „Give your AI what you've actually read." | Rev. 4 Option C-Variante |
| **Sicherheitssensibel** | „Harness AI to your research. Keep the reins." | Rev. 4 Option G |
| **Philosophie / About** | Μνήσθητι σαυτοῦ. — *Erinnere dich deiner selbst.* | unverändert |

**Aus dem Rennen / nachrangig:** „Your sources. Your thinking. Your edge." (D — „edge" zu techbro), „Your research system, AI-powered." (E — generisch), „Connect your library to your AI." (C-Hauptform — funktional, kein Versprechen).

**Hinweis:** Die in einer früheren Fassung erwogene Konter-Zeile („…not their weights.") ist gestrichen. Sie macht aus einer geteilten Sehnsucht einen Lagerstreit und verbaut rhetorisch die eigene Utopie — die lokale lernende KI, in der die verdichtete Repräsentation ja erwünscht ist, nur unter eigener Kontrolle. Die Positionierung läuft über *Ort, Beleg und Kontrolle*, nicht über die Gegenüberstellung „wir gegen die Gewichte".

---

## 7. Visuelle Identität: Das ARCH-Motiv (unverändert)

Das Kürzel ARCH trägt fünf relevante Wörter: rese**ARCH**, **ARCH**ive, **ARCH**itecture, **ARCH**aeology, **ARCH**illes. Typografisch als Block hervorheben. Dazu griechisch ἀρχή (arché) — Ursprung, Anfang, Prinzip: der intellektuelle Ursprung des eigenen Wissens. Stille Botschaft für klassisch Gebildete.

---

## 8. Narrative Struktur für PR-Texte

Die bewährte sechsstufige Linie, ergänzt um die Zwischenschicht-Stufe:

1. **Status quo** — Wie Forscher heute mit Bibliothek und KI arbeiten. Das Bekannte: Zotero, Calibre, Obsidian, Annotationen.
2. **Neue Entwicklung** — Was sich verändert: die Suche nach der Schicht zwischen Modell und Aufgabe — besseres RAG, GraphRAG, vorab verdichtete Kontext-Repräsentationen. Als Phänomen schildern, ohne einzelne Akteure zu nennen.
3. **Die Lücke** — Alle diese Wege wollen dasselbe (der eigene Kontext statt des Durchschnitts), aber die Expertise des Forschers ist für KI bislang unsichtbar. Die offene Frage: Wo liegt das Wissen, ist die Antwort belegbar, wer hat die Kontrolle?
4. **ARCHILLES als die kontrollierbare Form dieser Schicht** — Nicht Werbung, sondern Konsequenz: erschließen statt verschmelzen, belegen statt verdichten, lokal statt Cloud, beim Forscher statt anderswo.
5. **Meta: Kategorie** — Ein System wie ARCHILLES hat noch keinen etablierten Namen. Pionier-Positionierung: semantische Forschungsschicht.
6. **Funktionen & Abgrenzung** — Einstieg mit Bekanntem (semantic search), dann zur epistemischen Architektur.

---

## 9. Was ARCHILLES nicht kommuniziert

- **„Calibre für KI"** — zu eng, schließt Zotero-/Obsidian-Nutzer aus.
- **„KI, die für dich forscht"** — Gegenteil der Leitphilosophie. ARCHILLES verlängert den Forscher, automatisiert ihn nicht.
- **„Besser als ChatGPT" oder besser als ein konkreter, gut finanzierter Akteur** — falscher Vergleichsrahmen, und „besser als" verliert gegen Reichweite. Stattdessen: *anderer Weg*, andere Werte. Kontrast über die Idee (Ort, Beleg, Kontrolle), nicht über Überlegenheitsrhetorik. Namen nennen wir nicht — schon gar nicht solche, die heute prominent und morgen vergessen sein können.
- **McGilchrist** — präzises Designprinzip, intellektuell ehrlich, aber für unbekannte Zielgruppen zu esoterisch. Interne Doks, tiefe Artikel, richtige Community — nicht Landing Page, README, PR.
- **„100 % lokal" als Pauschale** — präzise bleiben: Indexierung und Retrieval laufen vollständig lokal; sobald ein externes Modell via MCP angebunden ist, verlassen die *Suchergebnisse* den Rechner — auf Initiative des Nutzers, zu dessen Modell. Diese Genauigkeit ist ein Glaubwürdigkeitsgewinn, kein Eingeständnis.

---

## 10. Der Kern

> Du hast jahrelang gelesen. Du weißt mehr, als du gerade abrufen kannst.
> ARCHILLES macht deinen Bestand zugänglich — für dein Denken und für die KI-Werkzeuge, die du einsetzt.
> Er bleibt dabei deiner, lokal und geschichtet — die Schicht zwischen dem, was du weißt, und der Aufgabe.

Philosophische Kurzform: **Μνήσθητι σαυτοῦ.** — Erinnere dich deiner selbst.

Das ist der Kern. Wenn ein Text über ARCHILLES diesen Gedanken nicht trägt — dass das Problem nicht Suche ist, sondern *Zugang zu dem, was man schon weiß, unter eigener Kontrolle* — ist er nicht fertig.

---

*POSITIONING_STATEMENT Rev. 5 — Juni 2026*
*Anlass: Standortbestimmung angesichts der Forschung an der Schicht zwischen Modell und Aufgabe (besseres RAG, GraphRAG, verdichtete Kontext-Repräsentationen); Live-Site-Abgleich; Bib/Lab funktional gelöst*
*Vorgänger: Rev. 4 (März 2026). Nächster Schritt: Roadmap (MCP-Zugang für Agenten, gewichtetes Wiki).*
