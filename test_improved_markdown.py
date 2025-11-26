"""
Test script to demonstrate improved Markdown export format.
Shows the new metadata (author, year, direct links).
"""

from datetime import datetime
from pathlib import Path

# Simulate a query result with full metadata
test_results = [
    {
        'rank': 1,
        'similarity': 0.100,
        'metadata': {
            'book_title': 'Marcion: Das Evangelium vom fremden Gott',
            'author': 'Adolf von Harnack',
            'year': 1924,
            'printed_page': '11*',
            'printed_page_confidence': 1.0,
            'language': 'la',
            'subject': 'Early Christianity, Gnosticism',
            'source_file': r'D:\Calibre-Bibliothek\Adolf von Harnack\Marcion_ Das Evangelium vom fremden (8322)\Marcion_ Das Evangelium vom fre - Adolf von Harnack.pdf',
            'page': 329
        },
        'text': '''n der entstellten Form, M. sei von ^Johannes
verworfen worden) schon in einer Quelle des Filastrius nachweisen
können. Dieser schreibt (haer. 45) : ,. (Marcion) devictus atque fugatus a
beato Iohanne evangelista et a presbyteris de civitate Efesi Romae hanc
haeresim semina- bat." Hier sieht man, wie es scheint, noch das Werden
der Fälschung: „a presbyteris" hat es ursprünglich geheißen und „a beat'''
    }
]

# Simulate the export
query_text = "evangelista et a presbyteris"
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_file = f"test_improved_export_{timestamp}.md"

lines = []

# Header
lines.append(f"# archilles RAG - Suchergebnisse")
lines.append(f"")
lines.append(f"**Query:** `{query_text}`  ")
lines.append(f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
lines.append(f"**Ergebnisse:** {len(test_results)}")
lines.append(f"")
lines.append(f"---")
lines.append(f"")

# Results
for result in test_results:
    rank = result['rank']
    similarity = result['similarity']
    metadata = result['metadata']
    text = result['text']

    # Build citation with author and year
    book_title = metadata.get('book_title', 'Unknown')
    author = metadata.get('author', '')
    year = metadata.get('year', '')

    if author and year:
        header = f"## [{rank}] {author}: {book_title} ({year})"
    elif author:
        header = f"## [{rank}] {author}: {book_title}"
    else:
        header = f"## [{rank}] {book_title}"

    lines.append(header)

    # Page number
    printed_page = metadata.get('printed_page')
    printed_conf = metadata.get('printed_page_confidence', 0.0)

    if printed_page and printed_conf >= 0.8:
        page_str = f"S. {str(printed_page)}"
        if printed_conf < 1.0:
            page_str += f" (Konfidenz: {printed_conf:.2f})"
    elif metadata.get('page'):
        page_str = f"PDF S. {metadata['page']}"
    else:
        page_str = ""

    if page_str:
        lines.append(f"**Seite:** {page_str}  ")

    # Relevanz
    lines.append(f"**Relevanz:** {similarity:.3f}  ")

    # Direct link
    source_file = metadata.get('source_file')
    if source_file:
        # Normalize path separators to forward slashes for URLs
        url_path = source_file.replace('\\', '/')

        # Add file:/// prefix
        if url_path.startswith('/'):
            # Unix path
            file_url = f"file://{url_path}"
        else:
            # Windows path (e.g., D:/...)
            file_url = f"file:///{url_path}"

        # Extract filename
        if '/' in url_path:
            filename = url_path.split('/')[-1]
        else:
            filename = url_path

        lines.append(f"**Quelle:** [{filename}]({file_url})  ")

    lines.append(f"")

    # Quote
    snippet = "...a beato Iohanne evangelista et a presbyteris de civitate Efesi..."
    lines.append(f"> {snippet}")
    lines.append(f"")

    # Additional metadata
    meta_lines = []
    if metadata.get('language'):
        meta_lines.append(f"Sprache: {metadata['language']}")
    if metadata.get('subject'):
        meta_lines.append(f"Thema: {metadata['subject']}")

    if meta_lines:
        lines.append(f"*{' • '.join(meta_lines)}*  ")

    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

# Footer with tags
tags = ["#archilles", "#rag", "#suche", "#latein"]
lines.append(f"")
lines.append(" ".join(tags))

# Write file
content = "\n".join(lines)
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✅ Test Markdown exported to: {output_file}")
print(f"\nContent preview:")
print("=" * 60)
print(content)
