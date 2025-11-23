"""
Robust printed page number extraction with cross-validation.

Uses multiple sources:
1. Table of Contents (TOC) - for structure and ranges
2. Headers/Footers - for exact page numbers
3. Cross-validation - to verify consistency

Confidence scoring:
- High (>0.8): Both TOC and header agree
- Medium (0.5-0.8): Only one source, or weak agreement
- Low (<0.5): Conflict or no data

This handles complex academic books with:
- Multiple numbering schemes (arabic, roman, appendices)
- Section resets (Beilage I: 1*, 2*, 3*...)
- OCR errors in TOC
"""

import chromadb
import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class PageNumber:
    """Printed page number with metadata."""
    value: str  # e.g., "10*", "xiv", "123"
    source: str  # "toc", "header", "footer", "validated"
    confidence: float  # 0.0-1.0
    section: Optional[str] = None  # e.g., "Beilage I", "Vorwort"


class TOCParser:
    """Parse Table of Contents for structure."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.toc_entries = []

    def extract_toc(self) -> List[Tuple[int, str, int]]:
        """
        Extract TOC from PDF.

        Returns:
            List of (level, title, page_number) tuples
        """
        try:
            doc = fitz.open(self.pdf_path)
            toc = doc.get_toc()
            doc.close()
            self.toc_entries = toc
            return toc
        except Exception as e:
            print(f"Warning: Could not extract TOC: {e}")
            return []

    def get_structure(self) -> Dict[str, Tuple[int, int]]:
        """
        Parse TOC into section ranges.

        Returns:
            Dict mapping section_name → (start_page, end_page)
        """
        if not self.toc_entries:
            return {}

        structure = {}
        for i, (level, title, start_page) in enumerate(self.toc_entries):
            # Determine end page (until next same-level or higher section)
            end_page = None
            for j in range(i + 1, len(self.toc_entries)):
                next_level, _, next_page = self.toc_entries[j]
                if next_level <= level:
                    end_page = next_page - 1
                    break

            if end_page is None:
                end_page = 9999  # Until end of book

            structure[title] = (start_page, end_page)

        return structure


class HeaderFooterExtractor:
    """Extract printed page numbers from headers/footers."""

    # Improved patterns with stricter matching
    PATTERNS = [
        # Appendix with asterisk - VERY specific to avoid false positives
        # CRITICAL: Asterisk must be INSIDE capturing group to be extracted!
        (r'^(\d+\*)', 'appendix_asterisk', 10, 'standalone_start'),
        (r'(\d+\*)\s*$', 'appendix_asterisk', 10, 'standalone_end'),
        (r':\s*\w+\.\s*(\d+\*)', 'author_appendix', 9, 'with_author'),

        # Roman numerals (preface) - must be standalone
        (r'^\s*([ivxlcdm]{2,})\s*$', 'roman', 8, 'standalone'),

        # With prefix - less likely to be false positive
        (r'(?:^|\n)(?:S\.|Seite)\s+(\d+)', 'german_prefix', 7, 'prefixed'),
        (r'(?:^|\n)(?:p\.|page)\s+(\d+)', 'english_prefix', 7, 'prefixed'),

        # Standalone numbers - ONLY at very start/end of header/footer
        (r'^(\d+)\s*$', 'standalone_number', 6, 'standalone'),
        (r'^\s*(\d+)\s*$', 'standalone_number', 5, 'standalone_padded'),
    ]

    def __init__(self, header_chars: int = 150, footer_chars: int = 150):
        """
        Initialize extractor.

        Args:
            header_chars: Characters to check at start (reduced to avoid body text)
            footer_chars: Characters to check at end
        """
        self.header_chars = header_chars
        self.footer_chars = footer_chars

    def extract_from_text(
        self,
        text: str,
        pdf_page: int
    ) -> List[PageNumber]:
        """
        Extract potential page numbers from text.

        CRITICAL: Only check FIRST LINE of header and LAST LINE of footer
        to avoid false positives from citations in body text!

        Returns:
            List of PageNumber candidates (sorted by confidence)
        """
        candidates = []

        # Extract FIRST LINE of header and LAST LINE of footer
        # This avoids false positives from citations like "siehe S. 145*" in body text
        lines = text.split('\n')

        if not lines:
            return candidates

        header_line = lines[0] if len(lines) > 0 else ""
        footer_line = lines[-1] if len(lines) > 0 else ""

        # Also check second/third lines as fallback (headers can be multi-line)
        header_lines = '\n'.join(lines[:3]) if len(lines) > 3 else '\n'.join(lines)
        footer_lines = '\n'.join(lines[-3:]) if len(lines) > 3 else '\n'.join(lines)

        # Check header (prioritize first line, then first 3 lines)
        for pattern, ptype, base_conf, variant in self.PATTERNS:
            # First line (highest priority)
            for match in re.finditer(pattern, header_line, re.IGNORECASE):
                page_val = match.group(1).strip()
                candidates.append(PageNumber(
                    value=page_val,
                    source=f'header_{ptype}',
                    confidence=(base_conf + 2) / 10.0  # Bonus for first line
                ))

            # First 3 lines (lower priority)
            if header_line not in header_lines:  # Avoid duplicates
                for match in re.finditer(pattern, header_lines, re.IGNORECASE | re.MULTILINE):
                    page_val = match.group(1).strip()
                    # Only add if not already found in first line
                    if not any(c.value == page_val and 'header' in c.source for c in candidates):
                        candidates.append(PageNumber(
                            value=page_val,
                            source=f'header_{ptype}',
                            confidence=base_conf / 10.0
                        ))

        # Check footer (prioritize last line, then last 3 lines)
        for pattern, ptype, base_conf, variant in self.PATTERNS:
            # Last line (highest priority)
            for match in re.finditer(pattern, footer_line, re.IGNORECASE):
                page_val = match.group(1).strip()
                candidates.append(PageNumber(
                    value=page_val,
                    source=f'footer_{ptype}',
                    confidence=(base_conf + 2) / 10.0  # Bonus for last line
                ))

            # Last 3 lines (lower priority)
            if footer_line not in footer_lines:  # Avoid duplicates
                for match in re.finditer(pattern, footer_lines, re.IGNORECASE | re.MULTILINE):
                    page_val = match.group(1).strip()
                    # Only add if not already found in last line
                    if not any(c.value == page_val and 'footer' in c.source for c in candidates):
                        candidates.append(PageNumber(
                            value=page_val,
                            source=f'footer_{ptype}',
                            confidence=base_conf / 10.0
                        ))

        # Sort by confidence
        candidates.sort(key=lambda x: x.confidence, reverse=True)

        return candidates


class PageNumberValidator:
    """Cross-validate page numbers from multiple sources."""

    def __init__(self):
        self.header_extractor = HeaderFooterExtractor()

    def normalize_page_value(self, value: str) -> Tuple[Optional[int], str]:
        """
        Normalize page number for comparison.

        Returns:
            (numeric_value, suffix) tuple
            e.g., "10*" → (10, "*"), "xiv" → (14, "roman")
        """
        # Asterisk numbers
        if value.endswith('*'):
            try:
                return (int(value[:-1]), '*')
            except ValueError:
                return (None, value)

        # Roman numerals
        if re.match(r'^[ivxlcdm]+$', value.lower()):
            try:
                roman_val = self.roman_to_int(value.lower())
                return (roman_val, 'roman')
            except:
                return (None, 'roman')

        # Regular numbers
        try:
            return (int(value), '')
        except ValueError:
            return (None, value)

    @staticmethod
    def roman_to_int(s: str) -> int:
        """Convert roman numeral to integer."""
        roman_map = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
        result = 0
        prev_value = 0

        for char in reversed(s.lower()):
            value = roman_map.get(char, 0)
            if value < prev_value:
                result -= value
            else:
                result += value
            prev_value = value

        return result

    def detect_outliers(
        self,
        page_numbers: Dict[int, PageNumber]
    ) -> Dict[int, PageNumber]:
        """
        Detect and penalize outliers (unrealistic page numbers).

        Outliers:
        - Very high page numbers on early PDF pages (e.g., PDF 11 → 238*)
        - Duplicate page numbers (two PDFs claiming same printed page)
        - Large jumps (>20 pages forward)

        Returns:
            Filtered page_numbers with outliers penalized
        """
        sorted_pages = sorted(page_numbers.keys())
        filtered = {}

        # Track duplicates
        printed_to_pdf = defaultdict(list)  # printed_page → [pdf_pages]

        for pdf_page, page_num in page_numbers.items():
            numeric, suffix = self.normalize_page_value(page_num.value)

            if numeric is None:
                filtered[pdf_page] = page_num
                continue

            # Rule 1: Unrealistically high page numbers for early PDF pages
            # If PDF page < 50 and printed page > 200, suspicious
            if pdf_page < 50 and numeric > 200:
                page_num.confidence *= 0.3  # Heavy penalty

            # Rule 2: Track duplicates
            printed_to_pdf[page_num.value].append(pdf_page)

            filtered[pdf_page] = page_num

        # Handle duplicates: keep only the best one
        for printed_val, pdf_pages in printed_to_pdf.items():
            if len(pdf_pages) > 1:
                # Multiple PDFs claim same printed page - keep best
                candidates = [(pdf_page, filtered[pdf_page]) for pdf_page in pdf_pages]
                candidates.sort(key=lambda x: x[1].confidence, reverse=True)

                # Keep best, penalize others
                for i, (pdf_page, page_num) in enumerate(candidates):
                    if i == 0:
                        # Keep best (maybe slight boost)
                        page_num.confidence = min(1.0, page_num.confidence + 0.05)
                    else:
                        # Penalize duplicates heavily
                        page_num.confidence *= 0.2

        return filtered

    def interpolate_missing_pages(
        self,
        page_numbers: Dict[int, PageNumber],
        min_neighbors: int = 3,
        max_gap: int = 5
    ) -> Dict[int, PageNumber]:
        """
        Interpolate missing page numbers based on neighbors.

        Only interpolates when:
        - At least min_neighbors known pages exist in a ±10 page window
        - Gap between known pages is ≤ max_gap
        - Sequence is consistent (regular increments)

        Args:
            page_numbers: Existing page numbers
            min_neighbors: Minimum known pages needed for interpolation
            max_gap: Maximum gap to interpolate

        Returns:
            page_numbers with interpolated values added
        """
        sorted_pages = sorted(page_numbers.keys())
        interpolated = dict(page_numbers)  # Copy

        for i in range(len(sorted_pages) - 1):
            prev_pdf = sorted_pages[i]
            next_pdf = sorted_pages[i + 1]

            gap = next_pdf - prev_pdf

            # Skip if gap is small (adjacent or near-adjacent pages)
            if gap <= 1:
                continue

            # Skip if gap is too large
            if gap > max_gap:
                continue

            prev_page = page_numbers[prev_pdf]
            next_page = page_numbers[next_pdf]

            # Only interpolate if same suffix (e.g., both have *)
            prev_numeric, prev_suffix = self.normalize_page_value(prev_page.value)
            next_numeric, next_suffix = self.normalize_page_value(next_page.value)

            if prev_numeric is None or next_numeric is None or prev_suffix != next_suffix:
                continue

            # Check if we have enough neighbors for confidence
            # Look at ±10 pages around the gap
            window_start = max(0, i - 10)
            window_end = min(len(sorted_pages), i + 10)
            neighbors_in_window = window_end - window_start

            if neighbors_in_window < min_neighbors:
                continue

            # Check if the sequence is regular
            expected_increment = (next_numeric - prev_numeric) / gap

            # Only interpolate if increment is close to 1 (regular pagination)
            if abs(expected_increment - 1.0) > 0.1:
                # Not a regular sequence
                continue

            # Interpolate!
            for pdf_offset in range(1, gap):
                missing_pdf = prev_pdf + pdf_offset
                interpolated_value = prev_numeric + pdf_offset

                # Format with suffix
                if prev_suffix == '*':
                    interpolated_str = f"{interpolated_value}*"
                elif prev_suffix == 'roman':
                    # Skip roman numeral interpolation (too complex)
                    continue
                else:
                    interpolated_str = str(interpolated_value)

                # Add with lower confidence
                interpolated[missing_pdf] = PageNumber(
                    value=interpolated_str,
                    source='interpolated',
                    confidence=0.7,  # Medium confidence
                    section=prev_page.section  # Inherit section
                )

        return interpolated

    def check_continuity(
        self,
        page_numbers: Dict[int, PageNumber]
    ) -> Dict[int, PageNumber]:
        """
        Check sequence continuity and adjust confidence.

        Args:
            page_numbers: Dict mapping pdf_page → PageNumber

        Returns:
            Updated page_numbers with adjusted confidence
        """
        sorted_pages = sorted(page_numbers.keys())

        for i, pdf_page in enumerate(sorted_pages):
            page_num = page_numbers[pdf_page]
            numeric, suffix = self.normalize_page_value(page_num.value)

            if numeric is None:
                continue

            # Check previous page
            continuity_score = 0.0
            if i > 0:
                prev_pdf = sorted_pages[i - 1]
                prev_page = page_numbers[prev_pdf]
                prev_numeric, prev_suffix = self.normalize_page_value(prev_page.value)

                if prev_numeric and prev_suffix == suffix:
                    # Expected: current = previous + 1
                    if numeric == prev_numeric + 1:
                        continuity_score += 0.2
                    elif abs(numeric - prev_numeric) <= 2:
                        # Close enough (might be missing page)
                        continuity_score += 0.1
                    elif abs(numeric - prev_numeric) > 20:
                        # Large jump - suspicious!
                        continuity_score -= 0.3

            # Check next page
            if i < len(sorted_pages) - 1:
                next_pdf = sorted_pages[i + 1]
                next_page = page_numbers[next_pdf]
                next_numeric, next_suffix = self.normalize_page_value(next_page.value)

                if next_numeric and next_suffix == suffix:
                    # Expected: next = current + 1
                    if next_numeric == numeric + 1:
                        continuity_score += 0.2
                    elif abs(next_numeric - numeric) <= 2:
                        continuity_score += 0.1
                    elif abs(next_numeric - numeric) > 20:
                        # Large jump - suspicious!
                        continuity_score -= 0.3

            # Update confidence (can go negative, will be clamped later)
            page_num.confidence = max(0.0, min(1.0, page_num.confidence + continuity_score))

        return page_numbers

    def cross_validate(
        self,
        toc_structure: Dict[str, Tuple[int, int]],
        header_pages: Dict[int, PageNumber]
    ) -> Dict[int, PageNumber]:
        """
        Cross-validate TOC structure with header/footer page numbers.

        Args:
            toc_structure: Section name → (start_page, end_page)
            header_pages: pdf_page → PageNumber from headers

        Returns:
            Validated page numbers with updated confidence and section info
        """
        validated = {}

        for pdf_page, page_num in header_pages.items():
            # Find which section this page belongs to (from TOC)
            section = None
            for section_name, (start, end) in toc_structure.items():
                if start <= pdf_page <= end:
                    section = section_name
                    break

            # Boost confidence if section context makes sense
            if section:
                page_num.section = section

                # Check if page number makes sense for this section
                # E.g., "Beilage" sections should have "*" suffix
                if 'beilage' in section.lower() or 'appendix' in section.lower():
                    if page_num.value.endswith('*'):
                        page_num.confidence += 0.15  # Good match!
                    else:
                        page_num.confidence -= 0.1  # Suspicious

            validated[pdf_page] = page_num

        return validated


def main():
    """Extract and validate printed page numbers."""

    print("="*80)
    print("ROBUST PAGE NUMBER EXTRACTION WITH CROSS-VALIDATION")
    print("="*80 + "\n")

    # Initialize
    client = chromadb.PersistentClient(path="./achilles_rag_db")
    collection = client.get_collection("achilles_books")

    # Get source file path
    print("Step 1: Locating source PDF...")

    # Try the known PDF location first
    known_pdf_path = r"D:\Calibre-Bibliothek\Adolf von Harnack\Marcion_ Das Evangelium vom fremden (8322)\Marcion_ Das Evangelium vom fre - Adolf von Harnack.pdf"

    if Path(known_pdf_path).exists():
        source_file = known_pdf_path
        print(f"✓ Found: {source_file}\n")
    else:
        # Fallback: check metadata
        result = collection.get(
            where={"book_id": "von_Harnack"},
            include=["metadatas"],
            limit=1
        )

        if not result['metadatas']:
            print("✗ No chunks found for von_Harnack")
            return

        meta = result['metadatas'][0]
        source_file = meta.get('source_file')

        if not source_file or not Path(source_file).exists():
            print(f"✗ Source file not found: {source_file}")
            print("Cannot extract TOC without source file.")
            print("Proceeding with header/footer extraction only...\n")
            toc_structure = {}
            source_file = None

    if source_file and Path(source_file).exists():
        # Extract TOC
        print("Step 2: Extracting Table of Contents...")
        toc_parser = TOCParser(source_file)
        toc_entries = toc_parser.extract_toc()

        if toc_entries:
            print(f"✓ Found {len(toc_entries)} TOC entries")
            toc_structure = toc_parser.get_structure()
            print(f"✓ Parsed {len(toc_structure)} sections\n")

            # Show structure
            print("TOC Structure (first 10 sections):")
            for i, (section, (start, end)) in enumerate(list(toc_structure.items())[:10]):
                end_str = str(end) if end < 9999 else "end"
                print(f"  {section[:50]:50s} → pages {start:3d}-{end_str}")
            if len(toc_structure) > 10:
                print(f"  ... ({len(toc_structure) - 10} more sections)")
            print()
        else:
            print("✗ No TOC found in PDF\n")
            toc_structure = {}
    else:
        toc_structure = {}

    # Extract from headers/footers
    print("Step 3: Extracting page numbers from headers/footers...")
    all_chunks = collection.get(
        where={"book_id": "von_Harnack"},
        include=["documents", "metadatas"]
    )

    print(f"Analyzing {len(all_chunks['ids'])} chunks...\n")

    extractor = HeaderFooterExtractor()
    header_pages = {}

    for text, meta in zip(all_chunks['documents'], all_chunks['metadatas']):
        pdf_page = meta.get('page')
        if not pdf_page:
            continue

        candidates = extractor.extract_from_text(text, pdf_page)
        if candidates:
            # Take best candidate
            header_pages[pdf_page] = candidates[0]

    print(f"✓ Extracted {len(header_pages)} page numbers from headers/footers\n")

    # Validate
    validator = PageNumberValidator()

    print("Step 4: Detecting outliers...")
    header_pages = validator.detect_outliers(header_pages)
    print("✓ Outlier detection complete\n")

    print("Step 5: Interpolating missing pages...")
    header_pages = validator.interpolate_missing_pages(header_pages, min_neighbors=3)
    print("✓ Interpolation complete\n")

    print("Step 6: Validating with continuity check...")
    header_pages = validator.check_continuity(header_pages)
    print("✓ Continuity check complete\n")

    # Cross-validate with TOC
    if toc_structure:
        print("Step 7: Cross-validating with TOC structure...")
        validated_pages = validator.cross_validate(toc_structure, header_pages)
        print("✓ Cross-validation complete\n")
    else:
        print("Step 7: Skipping cross-validation (no TOC)\n")
        validated_pages = header_pages

    # Show results
    print("="*80)
    print("RESULTS (first 30 pages)")
    print("="*80 + "\n")

    sorted_pages = sorted(validated_pages.keys())[:30]
    for pdf_page in sorted_pages:
        page_num = validated_pages[pdf_page]
        conf = page_num.confidence

        # Status indicator
        if conf > 0.8:
            status = "✓"
        elif conf > 0.5:
            status = "?"
        else:
            status = "✗"

        section_str = f" [{page_num.section[:30]}]" if page_num.section else ""
        print(f"{status} PDF {pdf_page:3d} → {page_num.value:>6s}  conf={conf:.2f}  {page_num.source:20s}{section_str}")

    if len(validated_pages) > 30:
        print(f"\n... ({len(validated_pages) - 30} more pages)")

    # Statistics
    high = sum(1 for p in validated_pages.values() if p.confidence > 0.8)
    med = sum(1 for p in validated_pages.values() if 0.5 < p.confidence <= 0.8)
    low = sum(1 for p in validated_pages.values() if p.confidence <= 0.5)

    print(f"\n" + "="*80)
    print("STATISTICS")
    print("="*80)
    print(f"High confidence (>0.8):  {high:3d} ({100*high/len(validated_pages):.1f}%)")
    print(f"Medium confidence (0.5-0.8): {med:3d} ({100*med/len(validated_pages):.1f}%)")
    print(f"Low confidence (<0.5):   {low:3d} ({100*low/len(validated_pages):.1f}%)")
    print(f"Total: {len(validated_pages)}")

    # Update database?
    print(f"\n" + "="*80)
    print("UPDATE DATABASE?")
    print("="*80)
    print(f"Add 'printed_page' metadata to {len(validated_pages)} chunks")
    print(f"High-confidence pages: {high}")

    response = input("\nProceed? [y/N]: ").strip().lower()

    if response == 'y':
        print("\nUpdating database...")

        updated = 0
        for pdf_page, page_num in validated_pages.items():
            chunks = collection.get(
                where={"$and": [{"book_id": "von_Harnack"}, {"page": pdf_page}]},
                include=["metadatas"]
            )

            for chunk_id, meta in zip(chunks['ids'], chunks['metadatas']):
                meta['printed_page'] = page_num.value
                meta['printed_page_confidence'] = page_num.confidence
                if page_num.section:
                    meta['section'] = page_num.section

                collection.update(ids=[chunk_id], metadatas=[meta])
                updated += 1

        print(f"✓ Updated {updated} chunks!")

        # Update display code to use printed_page
        print("\nNow update rag_demo.py to display printed pages in results!")
    else:
        print("Cancelled.")


if __name__ == "__main__":
    main()
