# Why Archilles

A scholar's working material lives in several places at once: a reference manager, an e-book collection, a vault of notes. Every AI retrieval tool on the market opens up one of these and is blind to the rest. Archilles indexes Zotero, Calibre and Obsidian — or any folder of documents — as one library, searchable with one query.

It also indexes what other systems do not treat as searchable material at all: the annotations. Highlights, margin notes and comments enter the index as objects in their own right, so a query can return not only what a source says, but what its reader thought of it.

Every result points to page, chapter and section of a document on the scholar's own disk. What cannot be pointed at is not asserted.

Beneath this lies one design decision. A curated library already contains the structure that generic retrieval tries to reconstruct after the fact — the scholar's tags and cross-references around the documents, the chapters and headings within them. Archilles indexes that structure instead of flattening it, and it keeps the layers apart: what the sources say, what the scholar noted, what a machine generated. That distinction is scholarly method, and the index preserves it.

Documents and index stay on the machine; indexing and retrieval run entirely locally. The reasoning goes to the model the scholar chooses — a cloud assistant by deliberate decision, or a local model. There is no account, no subscription, no telemetry, no training on your material. Archilles is model-agnostic via MCP: it runs natively with clients that launch local servers (Claude Desktop, Claude Code, Cursor, Codex CLI, Windsurf, Cline, Cherry Studio); ChatGPT and Gemini connect through an SSE bridge, documented in the MCP guide.

Archilles is open source under the MIT license, written by a single maintainer for his own library, and developed under a fixed charter: local-first, source-true, the scholar as the acting subject. Contributions are welcome within that charter; beyond it, the license invites forks.

A library is years of judgement made explicit. Archilles treats that judgement as signal.
