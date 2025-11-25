#!/usr/bin/env python3
"""
Demo script for universal text extraction.

Shows how to extract text from any e-book format supported by ARCHILLES.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors import UniversalExtractor
from src.extractors.exceptions import ExtractionError, UnsupportedFormatError
import logging
import json


def setup_logging():
    """Setup logging to see what's happening."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def demo_single_file(file_path: str):
    """Extract text from a single file."""
    print(f"\n{'='*60}")
    print(f"EXTRACTING: {file_path}")
    print(f"{'='*60}\n")

    # Initialize extractor
    extractor = UniversalExtractor(
        chunk_size=512,
        overlap=128,
        enable_ocr=False,  # Set to True if you have Tesseract installed
    )

    try:
        # Extract text
        result = extractor.extract(file_path)

        # Print statistics
        print(f"✓ Extraction successful!")
        print(f"\nSTATISTICS:")
        print(f"  Format: {result.metadata.detected_format}")
        print(f"  Method: {result.metadata.extraction_method}")
        print(f"  Pages: {result.metadata.total_pages or 'N/A'}")
        print(f"  Characters: {result.metadata.total_chars:,}")
        print(f"  Words: {result.metadata.total_words:,}")
        print(f"  Chunks: {result.metadata.total_chunks}")
        print(f"  Extraction time: {result.metadata.extraction_time:.2f}s")

        # Print warnings if any
        if result.metadata.warnings:
            print(f"\nWARNINGS:")
            for warning in result.metadata.warnings:
                print(f"  ⚠ {warning}")

        # Print first few chunks
        print(f"\nFIRST 3 CHUNKS:")
        for i, chunk in enumerate(result.chunks[:3], 1):
            print(f"\n  --- Chunk {i} ---")
            print(f"  Text: {chunk['text'][:200]}...")
            if 'metadata' in chunk:
                meta = chunk['metadata']
                if meta.get('page'):
                    print(f"  Page: {meta['page']}")
                if meta.get('chapter'):
                    print(f"  Chapter: {meta['chapter']}")

        # Print TOC if available
        if result.toc:
            print(f"\nTABLE OF CONTENTS: ({len(result.toc)} entries)")
            for entry in result.toc[:10]:  # First 10 entries
                indent = "  " * entry.get('level', 1)
                print(f"  {indent}- {entry.get('title', 'Untitled')}")
            if len(result.toc) > 10:
                print(f"  ... and {len(result.toc) - 10} more")

        # Print footnotes if any
        if result.footnotes:
            print(f"\nFOOTNOTES: {len(result.footnotes)} found")

        return result

    except UnsupportedFormatError as e:
        print(f"✗ Unsupported format: {e}")
        return None
    except ExtractionError as e:
        print(f"✗ Extraction failed: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None


def demo_batch_extraction(directory: str, pattern: str = "*.*"):
    """Extract text from all files in a directory."""
    print(f"\n{'='*60}")
    print(f"BATCH EXTRACTION: {directory}/{pattern}")
    print(f"{'='*60}\n")

    # Find all files matching pattern
    files = list(Path(directory).glob(pattern))
    print(f"Found {len(files)} files\n")

    if not files:
        print("No files found!")
        return

    # Initialize extractor
    extractor = UniversalExtractor()

    # Extract from all files
    results = extractor.extract_batch(files, skip_errors=True)

    # Print summary
    print(f"\n{'='*60}")
    print("BATCH EXTRACTION SUMMARY")
    print(f"{'='*60}\n")

    successful = [(path, result) for path, result, err in results if result]
    failed = [(path, err) for path, result, err in results if err]

    print(f"✓ Successful: {len(successful)}/{len(results)}")
    print(f"✗ Failed: {len(failed)}/{len(results)}")

    if failed:
        print(f"\nFAILED FILES:")
        for path, err in failed:
            print(f"  - {path.name}: {err}")

    if successful:
        print(f"\nSUCCESSFUL FILES:")
        total_chunks = 0
        total_words = 0
        for path, result in successful:
            print(f"  ✓ {path.name}: {result.metadata.total_chunks} chunks, {result.metadata.total_words:,} words")
            total_chunks += result.metadata.total_chunks
            total_words += result.metadata.total_words

        print(f"\n  TOTAL: {total_chunks} chunks, {total_words:,} words")


def demo_supported_formats():
    """Show all supported formats."""
    print(f"\n{'='*60}")
    print("SUPPORTED FORMATS")
    print(f"{'='*60}\n")

    extractor = UniversalExtractor()
    supported = extractor.get_supported_formats()

    print(f"NATIVE EXTRACTORS ({len(supported['native'])} formats):")
    for fmt, desc in sorted(supported['native'].items()):
        print(f"  • {fmt:10s} - {desc}")

    print(f"\nCALIBRE CONVERSION ({len(supported['calibre'])} formats):")
    if supported['calibre_available']:
        formats_list = sorted(supported['calibre'].keys())
        # Print in columns
        for i in range(0, len(formats_list), 5):
            row = formats_list[i:i+5]
            print(f"  {', '.join(f'{f:8s}' for f in row)}")
    else:
        print("  ⚠ Calibre not available. Install from: https://calibre-ebook.com/download")

    print(f"\nTOTAL: {supported['total_supported']} formats supported")


def demo_export_json(file_path: str, output_path: str):
    """Extract and export to JSON."""
    print(f"\n{'='*60}")
    print(f"EXTRACTING AND EXPORTING TO JSON")
    print(f"{'='*60}\n")

    extractor = UniversalExtractor()

    try:
        result = extractor.extract(file_path)

        # Convert to JSON
        data = result.to_dict()

        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✓ Exported to: {output_path}")
        print(f"  Chunks: {len(data['chunks'])}")
        print(f"  Size: {Path(output_path).stat().st_size:,} bytes")

    except Exception as e:
        print(f"✗ Failed: {e}")


def main():
    """Main demo function."""
    setup_logging()

    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         ACHILLES UNIVERSAL TEXT EXTRACTOR - DEMO           ║
    ║                                                            ║
    ║  Extract text from PDF, EPUB, MOBI, DJVU, DOC, and more!  ║
    ╚════════════════════════════════════════════════════════════╝
    """)

    # Show supported formats
    demo_supported_formats()

    # Check if user provided a file
    if len(sys.argv) > 1:
        file_path = sys.argv[1]

        if Path(file_path).is_file():
            # Single file extraction
            result = demo_single_file(file_path)

            # Optionally export to JSON
            if result and len(sys.argv) > 2 and sys.argv[2] == '--json':
                output_path = f"{Path(file_path).stem}_extracted.json"
                demo_export_json(file_path, output_path)

        elif Path(file_path).is_dir():
            # Batch extraction
            pattern = sys.argv[2] if len(sys.argv) > 2 else "*.*"
            demo_batch_extraction(file_path, pattern)

        else:
            print(f"Error: '{file_path}' is not a valid file or directory")
            sys.exit(1)

    else:
        print("\nUSAGE:")
        print("  # Extract single file:")
        print("  python scripts/demo_extraction.py path/to/book.pdf")
        print("")
        print("  # Extract and export to JSON:")
        print("  python scripts/demo_extraction.py path/to/book.epub --json")
        print("")
        print("  # Batch extract from directory:")
        print("  python scripts/demo_extraction.py path/to/books/")
        print("  python scripts/demo_extraction.py path/to/books/ '*.pdf'")
        print("")
        print("EXAMPLES:")
        print("  python scripts/demo_extraction.py ~/Documents/josephus.pdf")
        print("  python scripts/demo_extraction.py ~/Calibre\\ Library/")
        print("  python scripts/demo_extraction.py sample.epub --json")


if __name__ == '__main__':
    main()
