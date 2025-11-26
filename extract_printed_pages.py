"""
Extract printed page numbers from chunk headers/footers.

This script analyzes existing chunks and extracts printed page numbers
from headers/footers (first/last 200 chars), then updates the metadata.

Supports:
- Arabic numerals: 123
- With markers: 123*, A-12
- With prefixes: S. 123, p. 123, Seite 123
- Roman numerals: xiv, XXIII
- Confidence scoring based on continuity
"""

import chromadb
import re
from typing import Optional, List, Tuple, Dict
from collections import defaultdict


class PrintedPageExtractor:
    """Extract printed page numbers from text headers/footers."""

    # Patterns for different page number formats
    PATTERNS = [
        # Appendix/Beilage markers with asterisk (highest priority for von Harnack)
        (r'(?:^|\s)(\d+)\*', 'appendix_asterisk', 10),

        # Roman numerals (common in prefaces)
        (r'(?:^|\s)([ivxlcdm]{2,})\s*(?:\n|$)', 'roman', 8),

        # With German prefix
        (r'(?:S\.|Seite)\s*(\d+)', 'german_prefix', 7),

        # With English prefix
        (r'(?:p\.|page)\s*(\d+)', 'english_prefix', 7),

        # Standalone number at start/end of line
        (r'^(\d+)\s*[\*\.]?\s*$', 'standalone', 5),

        # Author name + page (e.g., "v. Harnack: Marcion. 10*")
        (r':\s*\w+\.\s*(\d+\*?)', 'author_page', 9),
    ]

    def __init__(self, header_chars: int = 200, footer_chars: int = 200):
        self.header_chars = header_chars
        self.footer_chars = footer_chars

    def extract_from_text(self, text: str) -> List[Tuple[str, str, int]]:
        """
        Extract potential page numbers from text.

        Returns:
            List of (page_number, pattern_type, confidence) tuples
        """
        results = []

        # Check header
        header = text[:self.header_chars]
        for pattern, pattern_type, base_confidence in self.PATTERNS:
            matches = re.findall(pattern, header, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                results.append((match, f'header_{pattern_type}', base_confidence))

        # Check footer
        footer = text[-self.footer_chars:]
        for pattern, pattern_type, base_confidence in self.PATTERNS:
            matches = re.findall(pattern, footer, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                results.append((match, f'footer_{pattern_type}', base_confidence))

        # Sort by confidence (descending)
        results.sort(key=lambda x: x[2], reverse=True)

        return results

    def normalize_page_number(self, page_num: str) -> str:
        """Normalize page number for display."""
        # Keep asterisks, roman numerals as-is
        return page_num.strip()

    def validate_sequence(
        self,
        page_numbers: Dict[int, str]
    ) -> Dict[int, Tuple[str, float]]:
        """
        Validate page number sequence and assign confidence scores.

        Args:
            page_numbers: Dict mapping PDF page → extracted page number

        Returns:
            Dict mapping PDF page → (page_number, confidence_score)
        """
        validated = {}

        sorted_pages = sorted(page_numbers.keys())

        for i, pdf_page in enumerate(sorted_pages):
            page_num = page_numbers[pdf_page]
            confidence = 0.5  # Base confidence

            # Try to parse as integer (for numeric pages)
            try:
                current_val = int(page_num.rstrip('*'))
                has_asterisk = page_num.endswith('*')

                # Check previous page
                if i > 0:
                    prev_pdf = sorted_pages[i - 1]
                    prev_num = page_numbers[prev_pdf]
                    try:
                        prev_val = int(prev_num.rstrip('*'))
                        prev_asterisk = prev_num.endswith('*')

                        # Continuity check
                        if current_val == prev_val + 1 and has_asterisk == prev_asterisk:
                            confidence += 0.3
                    except ValueError:
                        pass

                # Check next page
                if i < len(sorted_pages) - 1:
                    next_pdf = sorted_pages[i + 1]
                    next_num = page_numbers[next_pdf]
                    try:
                        next_val = int(next_num.rstrip('*'))
                        next_asterisk = next_num.endswith('*')

                        # Continuity check
                        if next_val == current_val + 1 and has_asterisk == next_asterisk:
                            confidence += 0.3
                    except ValueError:
                        pass

            except ValueError:
                # Roman numerals or other formats
                # TODO: Add roman numeral validation
                confidence = 0.6

            validated[pdf_page] = (page_num, min(confidence, 1.0))

        return validated


def main():
    """Extract printed page numbers for all chunks."""

    client = chromadb.PersistentClient(path="./archilles_rag_db")
    collection = client.get_collection("archilles_books")

    extractor = PrintedPageExtractor()

    # Get all von_Harnack chunks
    print("Fetching von_Harnack chunks...")
    all_chunks = collection.get(
        where={"book_id": "von_Harnack"},
        include=["documents", "metadatas"]
    )

    print(f"Found {len(all_chunks['ids'])} chunks\n")

    # Extract page numbers
    page_numbers = {}  # pdf_page → printed_page
    extraction_details = {}  # pdf_page → (candidates, chosen)

    for chunk_id, text, meta in zip(all_chunks['ids'], all_chunks['documents'], all_chunks['metadatas']):
        pdf_page = meta.get('page')
        if not pdf_page:
            continue

        candidates = extractor.extract_from_text(text)

        if candidates:
            # Take highest confidence candidate
            best_candidate = candidates[0]
            page_num = extractor.normalize_page_number(best_candidate[0])
            page_numbers[pdf_page] = page_num
            extraction_details[pdf_page] = (candidates, best_candidate)

    print(f"Extracted page numbers from {len(page_numbers)} chunks\n")

    # Validate sequence
    print("Validating sequence continuity...")
    validated = extractor.validate_sequence(page_numbers)

    # Show results
    print("\n" + "="*80)
    print("EXTRACTED PRINTED PAGE NUMBERS (with confidence)")
    print("="*80 + "\n")

    for pdf_page in sorted(validated.keys())[:20]:  # Show first 20
        printed_page, confidence = validated[pdf_page]
        candidates, chosen = extraction_details[pdf_page]

        status = "✓" if confidence > 0.7 else "?" if confidence > 0.5 else "✗"
        print(f"{status} PDF page {pdf_page:3d} → {printed_page:>6s}  (confidence: {confidence:.2f})")

        if confidence < 0.7:
            print(f"    Candidates: {[c[:2] for c in candidates[:3]]}")

    print(f"\n... ({len(validated) - 20} more pages)")

    # Show statistics
    high_conf = sum(1 for _, conf in validated.values() if conf > 0.7)
    med_conf = sum(1 for _, conf in validated.values() if 0.5 < conf <= 0.7)
    low_conf = sum(1 for _, conf in validated.values() if conf <= 0.5)

    print(f"\n" + "="*80)
    print("STATISTICS")
    print("="*80)
    print(f"High confidence (>0.7): {high_conf}")
    print(f"Medium confidence (0.5-0.7): {med_conf}")
    print(f"Low confidence (<0.5): {low_conf}")
    print(f"Total: {len(validated)}")

    # Ask user if they want to update the database
    print(f"\n" + "="*80)
    print("UPDATE DATABASE?")
    print("="*80)
    print(f"This will add 'printed_page' metadata to {len(validated)} chunks.")

    response = input("Proceed? [y/N]: ").strip().lower()

    if response == 'y':
        print("\nUpdating database...")

        # Update each chunk
        for pdf_page, (printed_page, confidence) in validated.items():
            # Find chunks with this pdf_page
            chunks = collection.get(
                where={"$and": [{"book_id": "von_Harnack"}, {"page": pdf_page}]},
                include=["metadatas"]
            )

            for chunk_id, meta in zip(chunks['ids'], chunks['metadatas']):
                # Add printed_page to metadata
                meta['printed_page'] = printed_page
                meta['printed_page_confidence'] = confidence

                # Update
                collection.update(
                    ids=[chunk_id],
                    metadatas=[meta]
                )

        print(f"✓ Updated {len(validated)} chunks with printed page numbers!")
    else:
        print("Cancelled. No changes made.")


if __name__ == "__main__":
    main()
