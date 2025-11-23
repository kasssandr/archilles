"""
Test script to demonstrate Markdown export format.
This simulates what the export would look like.
"""

# Simulate a query result
test_results = [
    {
        'rank': 1,
        'similarity': 0.100,
        'metadata': {
            'book_title': 'tmp4_nc_pxr',
            'printed_page': '11*',
            'printed_page_confidence': 1.0,
            'language': 'la',
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
from datetime import datetime

query_text = "evangelista et a presbyteris"
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
safe_query = "".join(c if c.isalnum() else "_" for c in query_text[:30])
output_file = f"achilles_search_{safe_query}_{timestamp}.md"

lines = []

# Header
lines.append(f"# Achilles RAG - Suchergebnisse")
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

    # Build citation
    book_title = metadata.get('book_title', 'Unknown')
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

    # Result header
    lines.append(f"## [{rank}] {book_title}")
    if page_str:
        lines.append(f"**Seite:** {page_str}  ")
    lines.append(f"**Relevanz:** {similarity:.3f}")
    lines.append(f"")

    # Quote
    snippet = "...a beato Iohanne evangelista et a presbyteris de civitate Efesi..."
    lines.append(f"> {snippet}")
    lines.append(f"")

    # Metadata
    if metadata.get('language'):
        lines.append(f"*Sprache: {metadata['language']}*  ")

    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

# Footer with tags
tags = ["#achilles", "#rag", "#suche", "#latein"]
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
