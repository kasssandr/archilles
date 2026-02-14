# ARCHILLES – Entscheidungsarchiv

**Dokumenttyp:** Lebende Referenz für strategische und technische Entscheidungen  
**Erstfassung:** 13. Februar 2026  
**Zweck:** Jede neue Claude-Session, jeder künftige Contributor und Tom selbst in drei Monaten sollen verstehen, *warum* ARCHILLES so gebaut ist, wie es gebaut ist.

---

## Was dieses Dokument ist und was nicht

Dieses Dokument hält die wesentlichen Entscheidungen fest, die das Projekt geformt haben – nicht als lückenlose Chronik, sondern als destillierte Begründungssammlung. Es erklärt Architekturentscheidungen, Marktpositionierung, bewusst aufgeschobene Optionen und verworfene Alternativen. Die technische Implementierung wird separat in ARCHITECTURE.md beschrieben; hier geht es um das *Warum*.

Die Entscheidungen sind nach inhaltlicher Logik gruppiert, nicht chronologisch. Wo es zum Verständnis beiträgt, sind Zeitpunkte angegeben.

---

## I. Marktpositionierung und Validierung

### Die Grundthese: Humanities-Forscher sind unterversorgt

Im November 2025 wurde der RAG-Markt parallel über fünf verschiedene KI-Modelle (ChatGPT, Claude Opus, Google Gemini, Grok 4.1 und LMArena) analysiert. Die Modelle konvergierten auf mehreren Befunden, die zur strategischen Grundlage des Projekts wurden.

Der Gesamtmarkt für RAG-Systeme wächst von ca. 300 Mio. USD (2024) auf projizierte 2,5 Mrd. USD (2030). Innerhalb dieses Marktes existiert eine strukturelle Lücke: Geisteswissenschaftler, Historiker und Forscher mit großen persönlichen Textsammlungen werden von existierenden Lösungen nicht bedient. Cloud-basierte Systeme wie Elicit, Consensus oder Scite setzen auf ihre eigenen Korpora oder institutionelle Zugänge; lokale Open-Source-Frameworks wie LlamaIndex, LangChain oder AnythingLLM sind generisch und liefern keine zitierfähigen Quellenangaben in akademischem Format.

Der europäische Markt zeigt dabei eine 2-3x höhere Zahlungsbereitschaft für datenschutzkonforme Lösungen als der US-Markt, weil die DSGVO-Anforderungen das Bedürfnis nach lokaler Datenverarbeitung verstärken.

### Warum RAG und nicht Fine-Tuning

Eine Analyse im Januar 2026 bestätigte, dass echtes LLM-Fine-Tuning mit Kosten von 50-90 Mio. USD für Training von Grund auf und erheblichem ML-Engineering-Aufwand selbst für domänenspezifische Anpassungen fest im Enterprise-Bereich verankert bleibt. RAG ist kein Kompromiss, sondern die technisch angemessene Lösung für individuelle Forscher, die ihre vorhandenen Bibliotheken mit LLM-Fähigkeiten verbinden wollen, ohne Machine-Learning-Infrastruktur betreiben zu müssen. Diese Erkenntnis gibt ARCHILLES ein Zeitfenster von mindestens 12-18 Monaten, bevor günstigere Fine-Tuning-Methoden die Nische bedrohen könnten.

### Calibre 8.16: Validierung durch Wettbewerbsanalyse

Im Dezember 2025 führte Calibre Version 8.16 eigene AI-Features ein: KI-gestützte Buchdiskussionen, Ähnlichkeitsempfehlungen und lokale Modellunterstützung über LM Studio/Ollama. Systematische Tests mit verschiedenen Dokumenttypen ergaben:

Lokale Modelle wie Gemma3 produzierten bei einem PDF, das nur ein Inhaltsverzeichnis enthielt (Hans Blumenberg, *Die Genesis der kopernikanischen Welt*), umfangreiche Halluzinationen – erfundene Kapitel und Inhalte. Googles Gemini-Modelle lieferten bessere Ergebnisse, stützten sich dabei aber auf Web-Grounding: Sie durchsuchten externe Quellen wie dandelon.com, einen europäischen Bibliothekskatalog-Anreicherungsdienst. Bei einem unveröffentlichten Manuskript (Skriptum zur Deutschen Rechtsgeschichte) konnte Gemini nur generische Beschreibungen liefern, weil kein Web-Grounding verfügbar war.

Die Schlussfolgerung: Calibres AI-Features lösen ein fundamental anderes Problem als ARCHILLES. Calibre bietet ein Gesprächsinterface für einzelne Bücher, das auf externem Wissen basiert. ARCHILLES ermöglicht semantische Suche über die gesamte persönliche Bibliothek mit verifizierbaren Quellenangaben aus den tatsächlichen Dokumenten. Die beiden Ansätze sind komplementär, nicht konkurrierend.

### Direkte Konkurrenz: überschaubar und schwach

Die Wettbewerbsanalyse zum Jahreswechsel 2025/26 identifizierte als direktesten Konkurrenten das Projekt calibre-rag-mcp-nodejs von ispyridis (veröffentlicht Dezember 2025, FAISS + Xenova Transformers, Windows-optimiert). Es fehlen exakte Zitationen, Annotationssuche und hybrides Retrieval; die Adoption lag bei 2 GitHub-Stars. Im Zotero-Ökosystem existieren reifere Lösungen (zotero-mcp, PapersGPT, mcp-research), die aber auf Referenzverwaltung statt Volltextsuche spezialisiert sind.

ARCHILLES' Alleinstellungsmerkmale bleiben bestätigt: exakte Zitationsfähigkeit mit Seitenangaben, Annotations-Indexierung, hybrides Retrieval (semantisch + keyword) und vollständig lokaler Betrieb.

---

## II. Technische Architekturentscheidungen

### ADR-001: LanceDB statt ChromaDB (Februar 2026)

**Kontext:** ARCHILLES lief produktiv mit ChromaDB und 46.354 Chunks aus ca. 87 Büchern. Die Analyse ergab, dass ChromaDB ab ca. 100.000 Chunks Performance-Degradation zeigt. Bei durchschnittlich 533 Chunks pro Buch bedeutet das ein Maximum von ca. 188 Büchern – weit unter dem Ziel von 500-1.000 Leit-Titeln aus einer Gesamtbibliothek von 8.000+.

**Entscheidung:** Migration zu LanceDB.

**Begründung:** LanceDB bringt native Hybrid-Search (dense + sparse Vectors) mit, die den separaten BM25-Code und die Reciprocal-Rank-Fusion-Logik überflüssig macht. Die IVF-PQ-Indexstruktur ist für Millionen von Chunks optimiert und optional GPU-beschleunigbar. Die Migration wurde bewusst früh durchgeführt, als die Datenbank noch klein und ein Re-Indexing unkompliziert war.

**Konsequenzen:** Der gesamte Storage-Layer, Indexer und Retriever mussten umgeschrieben werden. Die ca. 87 Bücher wurden neu indexiert. Der Code wurde schlanker, weil weniger selbst implementierte Suchlogik nötig ist. Das Architekturprinzip dabei: "Wir bauen ein Chassis, in das wir später bessere Motoren einbauen können – und verlegen jetzt schon Kabel zu Steckplätzen, an denen wir künftig erwartbare neue Geräte einstecken können." Die Parameter-Ebene im Code wurde von Beginn an auf Diversifizierung und Erweiterbarkeit ausgerichtet.

### ADR-002: BGE-M3 als Embedding-Modell

**Kontext:** Für ein System, das Texte in Deutsch, Englisch, Latein, Altgriechisch und weiteren Sprachen verarbeiten muss, ist ein multilinguales Embedding-Modell entscheidend. Die Zielgruppe arbeitet mit historischen und modernen Quellen in wechselnden Sprachen.

**Entscheidung:** BGE-M3 von BAAI als primäres Embedding-Modell (1024 Dimensionen, multilingual).

**Begründung:** BGE-M3 wurde in der Marktanalyse über mehrere KI-Modelle hinweg als einer der Spitzenreiter für multilinguales Retrieval identifiziert. Es bietet native Unterstützung für Dense-, Sparse- und ColBERT-Retrieval in einem einzigen Modell. Die Chunking-Intelligence-Analyse (parallel über Gemini, Grok und ChatGPT durchgeführt) bestätigte die Eignung für wissenschaftliche Texte.

**Offene Frage:** Evaluation von multilingual-e5 und jina-embeddings-v3 als Alternativen für den Mid-term (Q2 2026).

### ADR-003: PyMuPDF als primärer PDF-Extraktor

**Kontext:** Die Qualität der Textextraktion bestimmt die Qualität der Suchergebnisse. Verschiedene PDF-Extraktionsbibliotheken wurden evaluiert.

**Entscheidung:** PyMuPDF (fitz) als primärer Extraktor, mit Multi-Tier-Fallback-System.

**Begründung:** PyMuPDF bietet die beste Kombination aus Geschwindigkeit und Extraktionsqualität für die Mehrzahl der Dokumente. Es liefert zuverlässiges Seitenzahlen-Mapping, das für zitierfähige Quellenangaben unerlässlich ist. Die ursprünglich als primärer Extraktor vorgesehene Bibliothek pdfplumber wurde auf eine Fallback-Rolle zurückgestuft. Für problematische PDFs (historische Scans, komplexe Layouts) steht ein Fallback-System bereit, das bei Qualitätsproblemen alternative Extraktoren einschaltet.

**Verworfene Alternativen:** Marker (LLM-gestützter Korrekturmodus) wurde als bedarfsgesteuertes Feature für die Zukunft notiert, nicht als aktive Planung. Die Entscheidung fällt nach Beta-Feedback über die tatsächliche Extraktionsqualität.

### ADR-004: Registry-Pattern für modulare Pipeline

**Kontext:** ARCHILLES soll verschiedene Parser, Chunker und Embedder unterstützen können – sowohl für verschiedene Dateiformate als auch für künftige Special Editions mit disziplinspezifischen Optimierungen.

**Entscheidung:** Modulare Pipeline-Architektur mit Registry-Pattern. Parser, Chunker und Embedder sind als austauschbare Komponenten implementiert, die sich über ein Registry-System registrieren und auswählen lassen.

**Begründung:** Das Pattern ermöglicht die spätere Erweiterung um neue Extraktoren (etwa für DJVU, OCR-intensive Dokumente oder proprietäre Formate), neue Chunking-Strategien (semantisch vs. fixed-size vs. hybrid) und neue Embedding-Modelle, ohne den Kern des Systems zu modifizieren. Es ist zudem die technische Voraussetzung für das Freemium-Modell: Die Basisversion nutzt Standard-Komponenten, Special Editions können optimierte Varianten einsetzen.

### ADR-005: Keine direkte Modifikation von Calibres metadata.db

**Kontext:** Metadaten-Anreicherung durch LLM-Extraktion aus Volltexten wurde als Feature diskutiert – etwa fehlende Autoren, Erscheinungsjahre oder Schlagworte automatisch ergänzen.

**Entscheidung:** Calibres metadata.db wird nie direkt modifiziert.

**Begründung:** Calibre-Nutzer verlassen sich auf die Integrität ihrer Datenbank. Direkte Modifikation birgt das Risiko von Datenbeschädigung und verletzt das Vertrauen der Nutzer. Stattdessen wird der `.archilles`-Ordner als definierte Erweiterungszone genutzt. Externe Metadaten können in einer separaten JSON- oder SQLite-Datei gespeichert und zur Laufzeit mit Calibre-Metadaten zusammengeführt werden.

### ADR-006: Hybride Suche mit Reciprocal Rank Fusion

**Kontext:** Rein semantische Suche findet konzeptionell verwandte Passagen, versagt aber bei exakten Begriffen – Eigennamen, Jahreszahlen, Fachterminologie. Reine Keyword-Suche findet exakte Treffer, versteht aber keine Bedeutung.

**Entscheidung:** Hybride Suche, die BGE-M3-Vektorembeddings mit BM25-Keyword-Matching über Reciprocal Rank Fusion kombiniert. (Hinweis: LanceDB bringt Hybrid-Search nativ mit, was die Implementierung vereinfacht.)

**Begründung:** Geisteswissenschaftler suchen sowohl nach Konzepten ("Legitimation von Herrschaft im Mittelalter") als auch nach konkreten Referenzen ("Eusebius von Caesarea" oder "325 n. Chr."). Die hybride Suche bedient beide Suchmodi. RRF als Fusionsmethode wurde in der Wettbewerbsanalyse (Dezember 2025) als algorithmisch einfach, ohne neue Dependencies und mit messbarer Qualitätsverbesserung bewertet.

### ADR-007: OCR-Strategie – Tesseract als Basis, modularer Ausbau

**Kontext:** Ein erheblicher Teil akademischer Bibliotheken besteht aus gescannten PDFs, für die Textextraktion nur über OCR möglich ist. Die Qualitätsanforderungen sind hoch, weil fehlerhafte OCR-Ergebnisse das gesamte Retrieval kompromittieren.

**Entscheidung:** Tesseract als Basismodul, mit vorbereitetem Ausbau auf bessere Modelle.

**Begründung:** Tesseract ist frei verfügbar, gut etabliert und ausreichend für moderne Druckschriften. Für die anspruchsvolleren Fälle – historische Frakturschrift, handschriftliche Marginalien, schlecht gescannte Vorlagen – wird der modulare Ausbau vorbereitet, ohne dass die Basisversion davon abhängt. Die strategische Analyse (Februar 2026) ergab, dass sich die OCR-Landschaft rasant entwickelt und eine zu frühe Festlegung auf ein spezifisches Premium-System riskant wäre. Besser: die Schnittstelle sauber definieren und das beste verfügbare Modell einsetzen, wenn es soweit ist.

---

## III. Produktstrategie und Geschäftsmodell

### Zielgruppe: Individuelle Forscher, keine Institutionen

**Entscheidung:** ARCHILLES adressiert primär einzelne Wissenschaftler mit persönlichen Calibre-Bibliotheken, nicht institutionelle Kunden.

**Begründung:** Die Primary Targets sind technisch versierte Akademiker aus den Geisteswissenschaften – Geschichte, Literatur, Philosophie –, die große, kuratierte Bibliotheken pflegen und Wert auf Privacy und lokale Datenkontrolle legen. Institutionelle Kunden (Universitätsbibliotheken, Forschungsinstitute) erfordern Compliance-Prozesse, Ausschreibungen und Support-Strukturen, die für ein Solo-Projekt in der Aufbauphase nicht leistbar sind. Die Tür wird offengehalten (Scoped Knowledge Bases als Feature-Option, institutionelle Lizenzen in der Roadmap), aber der Fokus bleibt auf dem individuellen Nutzer.

### Freemium mit Special Editions

**Entscheidung:** Freemium-Modell mit großzügigem Free Tier und kostenpflichtigen disziplinspezifischen Erweiterungen.

**Begründung:** Die Marktanalyse zeigt, dass DEVONthink (499 €) und Polar (299 $) als Einmalkauf-Modelle erfolgreich bei Wissenschaftlern sind. Abo-Müdigkeit ist in der Zielgruppe verbreitet. Das Free Tier bietet die komplette Basisfunktionalität ohne Bibliotheksbeschränkung, um eine Nutzerbasis aufzubauen. Die Premium-Erweiterungen sind inhaltlich differenziert:

Die **Historical Edition** als erste geplante Special Edition bringt LightRAG für Graph-basiertes Retrieval, Zeitreferenz-Extraktion, chronologische Visualisierung und spezialisierte Embeddings für historische Texte. Weitere geplante Editions sind Literary, Legal und Musical, jeweils mit disziplinspezifischen Optimierungen. Das Plugin-System der modularen Architektur (Registry-Pattern) ist die technische Voraussetzung für diese Trennung.

### Privacy als politisch neutrale Positionierung: Datensouveränität

**Entscheidung:** "Datensouveränität" als zentraler Wert, nicht als technisches Feature.

**Begründung:** Die Analyse der politischen Dimension ergab, dass Datenschutz als Wert überparteilich anschlussfähig ist: Linke sehen Überwachungskritik, Konservative Misstrauen gegenüber Tech-Monopolen, Liberale individuelle Autonomie. Die Positionierung als "Privacy by Design" (nicht durch nachträgliche Compliance) spricht die gesamte Zielgruppe an. ARCHILLES verarbeitet keine Nutzerdaten, betreibt keine Telemetrie und kommuniziert nicht mit externen Servern, sofern der Nutzer dies nicht explizit wählt. Der Nutzer ist sein eigener Datenverarbeiter – das vereinfacht die DSGVO-Compliance auf das Triviale.

### MCP-Native als strategische Wette

**Entscheidung:** Vollständige Implementierung als MCP-Server (Model Context Protocol) statt als standalone Anwendung mit eigener GUI.

**Begründung:** MCP wurde im November 2025 als der wichtigste Differenzierungsvorteil für 2025/26 identifiziert. Das Protokoll löst elegant das Kerndilemma der Zielgruppe: Sie wollen die besten Cloud-Modelle (Claude, GPT-4o) nutzen, aber ihre sensiblen Daten nicht hochladen. Ein lokaler MCP-Server exponiert die Bibliothek dynamisch für kompatible KI-Agenten, ohne dass ein Byte den Rechner verlässt. Ressourcen werden mit URIs referenziert, die automatisch in akademische Zitationsformate (BibTeX, APA, Chicago) umgewandelt werden können.

Das Risiko: MCP ist ein junger Standard, und seine Durchsetzung hängt von Anthropics und OpenAIs fortgesetzter Unterstützung ab. Die Wette ist, dass MCP zum Industriestandard für LLM-Tool-Integration wird – eine Wette, die durch die rasche Adoption (OpenAI im März 2025, wachsendes Ökosystem mit 80+ offiziellen Servern) gestützt wird.

---

## IV. Bewusst aufgeschobene Entscheidungen

### MCPB Desktop Extension: Erst nach stabilem MVP

**Kontext (Dezember 2025):** Anthropics neues Desktop Extension Format (.mcpb) verspricht Ein-Klick-Installation für Claude Desktop. Für ARCHILLES wäre das ein potenzieller Game-Changer, weil es die Einstiegshürde für nicht-technische Nutzer drastisch senken würde.

**Technische Analyse:** ARCHILLES' Python-Stack mit kompilierten Abhängigkeiten (LanceDB, PyTorch/Sentence-Transformers) lässt sich nicht portabel in ein .mcpb bündeln. Die realistische Lösung wäre ein Thin-Client-Ansatz: ein leichtgewichtiger Node.js MCP-Server als .mcpb, der mit einem separat installierten Python-Backend kommuniziert.

**Entscheidung:** Aufschub bis nach MVP-Fertigstellung und Beta-Test.

**Begründung:** Die Zielgruppe der Beta-Phase (technisch versierte Akademiker, Calibre-Power-User) kann manuelle JSON-Konfiguration handhaben. Eine vorzeitige Architekturspaltung in Node.js-Frontend und Python-Backend würde die Feature-Entwicklung bremsen, weil jede Änderung in zwei Codebases synchronisiert werden müsste. Die Einstiegshürde senken wir erst, wenn es etwas Stabiles gibt, in das man einsteigen kann.

### LightRAG / Graph RAG: Evaluation vor Implementation

**Kontext (Dezember 2025):** Für die Historical Special Edition wurde zunächst Neo4j als Graph-Datenbank erwogen, dann LightRAG als leichtere Alternative identifiziert.

**Entscheidung:** LightRAG wird als Graph-RAG-Ansatz vorgesehen, aber erst nach systematischer Evaluation (geplant Q2 2026) implementiert.

**Begründung:** LightRAG bietet Dual-Level Retrieval (Low-Level für Details, High-Level für Konzepte) und inkrementelle Updates ohne komplettes Graph-Rebuilding. Allerdings erfordert die Graph-Extraktion LLM-Aufrufe während der Indexierung, was API-Kosten verursacht. Vor der Implementation muss ein Testkorpus definiert und Metriken für den Vergleich mit reinem Vektor-RAG festgelegt werden.

### Uncertainty Quantification: Forschungsziel, keine aktive Planung

**Kontext:** Die Fähigkeit, widersprüchliche Aussagen in verschiedenen Quellen zu erkennen und transparent zu machen, passt ideal zur Projektphilosophie einer "eigenen, in Teilen unkonventionellen Geschichtsinterpretation", bei der das Nebeneinander verschiedener Deutungen produktiv sein soll.

**Entscheidung:** Als langfristiges Forschungsziel (2027+) dokumentiert.

**Begründung:** Technisch ambitioniert (erfordert Natural Language Inference, Entitätsabgleich über Quellen hinweg), möglicherweise als Kooperation mit akademischen Partnern (NFDI-Konsortien) realisierbar. Für den MVP und die erste Produktversion irrelevant.

### Kollaboration: Minimal, aber vorbereitet

**Kontext (Januar 2026):** Die Analyse kollaborativer Workflows in den Geisteswissenschaften ergab, dass sich Humanities-Kooperation fundamental von STEM unterscheidet: Einzelautorschaft dominiert, aber Betreuer-Studierende-Beziehungen und geteilte Literatursammlungen sind zentrale Kollaborationsmuster.

**Entscheidung:** Keine Echtzeit-Kollaborationsfeatures. Stattdessen minimale, aber nützliche Export- und Austauschfunktionen.

**Begründung:** Geisteswissenschaftliche Teams teilen Referenzen, Annotationen und kuratierte Sammlungen – sie brauchen keine Google-Docs-artige Echtzeitbearbeitung. Exportierbare Annotationssets und thematische Sammlungen als geteilte Bibliographien decken den realen Bedarf ab, ohne die Architektur zu verkomplizieren.

---

## V. Branding und Kommunikation

### Rebranding: Achilles → ARCHILLES

**Zeitpunkt:** November 2025

**Begründung:** Der Name "ARCHILLES" verbindet die Archiv-Assoziation ("ARCH") mit dem mythologischen Helden. Subtile Schichten: "ARCH" referenziert sowohl "archive" als auch "research" aus dem Tagline; "ILLES" erscheint rückwärts gelesen in "intELLIgent"; "A" und "I" zusammen ergeben "AI". Der Tagline "Your Intelligent Research Archive" liefert alle Bestandteile. Domains archilles.de, archilles.net und archilles.org wurden gesichert.

### Tone of Voice: Intellektuell, aber nicht elitär

Das Kommunikationsprinzip "While others build snake games, we enable serious scholarship" positioniert ARCHILLES als Werkzeug für ernsthafte Wissensarbeit, ohne Gatekeeping zu betreiben. Die Formulierung respektiert sowohl die KI-Technologie als auch die akademische Arbeit der Nutzer. Der Kern-Claim lautet: "Other AI tools question books. ARCHILLES questions your library."

### Vendor-Neutralität in der Kommunikation

In der externen Kommunikation wird von "frontier models" gesprochen, nicht ausschließlich von "Claude" – obwohl die MCP-Integration aktuell primär auf Claude Desktop zielt. Das verhindert Vendor-Lock-in in der Wahrnehmung und hält die Tür offen für andere MCP-kompatible Clients.

---

## VI. Rechtliche Rahmenbedingungen

### EU AI Act: Wahrscheinlich nicht anwendbar

**Analyse (November 2025):** ARCHILLES ist ein lokales Tool für persönlichen Gebrauch. Es klassifiziert keine Personen, trifft keine automatisierten Entscheidungen und verarbeitet keine biometrischen Daten. Die Risikoklassifizierung des EU AI Act trifft auf ein lokales Retrieval-Tool nicht zu. Monitoring bleibt dennoch sinnvoll, weil Regulierung sich weiterentwickelt.

### Urheberrecht und Text & Data Mining

§ 60d UrhG (Deutschland) und die DSM-Richtlinie (EU) erlauben Text & Data Mining für Forschungszwecke. ARCHILLES ist ein Tool, kein Content-Provider – vergleichbar mit Calibre selbst oder VLC Media Player. Die Verantwortung für die Rechtmäßigkeit der indexierten Bibliothek liegt beim Nutzer. DRM-geschützte E-Books sind explizit Nutzerverantwortung.

### Lizenzierung: MIT, mit Optionen

Die Basisversion wird unter MIT-Lizenz veröffentlicht (maximal permissiv für Adoption). Spätere Versionen oder Special Editions können restriktivere Lizenzen nutzen, falls nötig. Dual Licensing (Open Source + Commercial) bleibt als Option für die Editions-Strategie vorbehalten.

---

## VII. Zusammenfassung: Leitprinzipien

Die Entscheidungen folgen konsistent einigen Grundprinzipien, die das Projekt prägen:

**Privacy ist kein Feature, sondern die Architektur.** Daten bleiben lokal, Datensouveränität ist das Fundament, nicht ein Checkbox-Item.

**Modulare Erweiterbarkeit vor Featurefülle.** Das Registry-Pattern, die Plugin-fähige Architektur und die definierten Erweiterungszonen (`.archilles`-Ordner) sind wichtiger als jedes einzelne Feature.

**Akademischer Anspruch als Differenzierung.** Exakte Zitationen, transparentes Retrieval und disziplinspezifische Optimierungen unterscheiden ARCHILLES von generischen RAG-Lösungen – nicht die Menge der Features.

**Aufschub als bewusste Strategie.** MCPB, LightRAG, Uncertainty Quantification und institutionelle Features werden nicht vergessen, sondern zum richtigen Zeitpunkt implementiert. Ein funktionierendes MVP hat Vorrang vor einer vorzeitig aufgeblähten Architektur.

---

*Nächste geplante Aktualisierungen:*
- *Ergebnis der LightRAG-Evaluation (geplant Q2 2026)*
- *Entscheidung über MCPB-Implementation (nach Beta-Feedback)*
- *ADR für Übersetzungs-Pipeline (NLLB lokal / MADLAD-400 API)*
