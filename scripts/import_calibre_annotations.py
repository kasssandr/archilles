#!/usr/bin/env python3
"""
ARCHILLES - Import Calibre Annotations from Bridge Plugin

Imports annotations exported by the ARCHILLES Bridge Calibre plugin
into a separate ChromaDB collection for fast semantic search.

Usage:
    # Import from latest export
    python scripts/import_calibre_annotations.py

    # Import from specific file
    python scripts/import_calibre_annotations.py --file "path/to/export.json"

    # Replace existing annotations
    python scripts/import_calibre_annotations.py --replace
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


def find_latest_export(calibre_config_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find the latest annotation export from the Bridge plugin.

    Args:
        calibre_config_dir: Path to Calibre config directory (auto-detected if None)

    Returns:
        Path to all_annotations_latest.json or None if not found
    """
    if calibre_config_dir is None:
        # Auto-detect Calibre config directory
        if sys.platform == 'win32':
            calibre_config_dir = Path(os.environ.get('APPDATA', '')) / 'calibre'
        else:
            calibre_config_dir = Path.home() / '.config' / 'calibre'

    export_dir = calibre_config_dir / 'archilles_exports'
    latest_file = export_dir / 'all_annotations_latest.json'

    if latest_file.exists():
        return latest_file

    # Try to find any export file
    if export_dir.exists():
        export_files = sorted(export_dir.glob('all_annotations_*.json'), reverse=True)
        if export_files:
            return export_files[0]

    return None


def import_annotations(
    export_file: Path,
    db_path: str,
    model_name: str = "BAAI/bge-m3",
    collection_name: str = "calibre_annotations",
    replace: bool = False
) -> Dict[str, Any]:
    """
    Import annotations from Bridge plugin export into ChromaDB.

    Args:
        export_file: Path to the JSON export file
        db_path: Path to ChromaDB storage directory
        model_name: Embedding model to use (default: BGE-M3)
        collection_name: Name for the annotations collection
        replace: If True, delete existing collection before import

    Returns:
        Dictionary with import statistics
    """
    print(f"📚 ARCHILLES ANNOTATION IMPORTER")
    print(f"{'='*60}\n")

    # Load export data
    print(f"📂 Loading export: {export_file}")
    with open(export_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    export_info = data.get('export_info', {})
    annotations = data.get('annotations', [])

    print(f"   Source library: {export_info.get('calibre_library', 'Unknown')}")
    print(f"   Export date: {export_info.get('export_timestamp', 'Unknown')}")
    print(f"   Total annotations: {export_info.get('total_annotations', len(annotations))}")
    print(f"   Unique books: {export_info.get('unique_books', '?')}\n")

    # Initialize embedding model
    print(f"🔧 Loading embedding model: {model_name}")
    print(f"   (First time: ~500 MB download)")
    embedding_model = SentenceTransformer(model_name)
    print(f"   ✅ Model loaded\n")

    # Initialize ChromaDB
    print(f"💾 Initializing ChromaDB")
    print(f"   Database: {db_path}")
    chroma_client = chromadb.PersistentClient(path=db_path)

    # Handle replace option
    if replace:
        try:
            chroma_client.delete_collection(collection_name)
            print(f"   🗑️  Deleted existing collection: {collection_name}")
        except Exception:
            pass  # Collection didn't exist

    # Get or create collection
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={
            "hnsw:space": "cosine",
            "description": "Calibre annotations indexed by ARCHILLES",
            "source": "calibre_bridge_plugin"
        }
    )
    print(f"   ✅ Collection ready: {collection_name}\n")

    # Import annotations
    stats = {
        'total': len(annotations),
        'imported': 0,
        'skipped': 0,
        'errors': 0,
        'by_book': {},
        'start_time': datetime.now().isoformat()
    }

    print(f"🔄 Importing annotations...\n")

    # Batch processing for speed
    batch_size = 32
    ids_batch = []
    embeddings_batch = []
    documents_batch = []
    metadatas_batch = []

    for annot in tqdm(annotations, desc="Processing"):
        try:
            # Extract text
            text = annot.get('searchable_text', '').strip()
            if not text:
                stats['skipped'] += 1
                continue

            # Get book metadata
            book_meta = annot.get('book_metadata', {})
            book_id = book_meta.get('book_id')
            if not book_id:
                stats['skipped'] += 1
                continue

            # Track per-book count
            stats['by_book'][book_id] = stats['by_book'].get(book_id, 0) + 1

            # Create document ID
            annot_id = annot.get('id', 'unknown')
            doc_id = f"calibre_annot_{annot_id}_{book_id}"

            # Build metadata (minimal, for display/filtering)
            metadata = {
                'source': 'calibre_annotation',
                'annot_type': annot.get('annot_type', 'highlight'),
                'book_id': str(book_id),
                'title': book_meta.get('title', 'Unknown'),
                'authors': ', '.join(book_meta.get('authors', [])),
                'tags': ', '.join(book_meta.get('tags', [])),
                'format': annot.get('format', ''),
                'timestamp': annot.get('timestamp') or '',
                'indexed_at': datetime.now().isoformat()
            }

            # Add user note if present
            annot_data = annot.get('annot_data', {})
            if isinstance(annot_data, dict) and annot_data.get('notes'):
                metadata['user_note'] = annot_data['notes'][:500]  # Limit length

            # Generate embedding
            embedding = embedding_model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False
            ).tolist()

            # Add to batch
            ids_batch.append(doc_id)
            embeddings_batch.append(embedding)
            documents_batch.append(text)
            metadatas_batch.append(metadata)

            # Commit batch when full
            if len(ids_batch) >= batch_size:
                collection.add(
                    ids=ids_batch,
                    embeddings=embeddings_batch,
                    documents=documents_batch,
                    metadatas=metadatas_batch
                )
                stats['imported'] += len(ids_batch)
                ids_batch = []
                embeddings_batch = []
                documents_batch = []
                metadatas_batch = []

        except Exception as e:
            stats['errors'] += 1
            print(f"   ⚠️  Error importing annotation {annot.get('id')}: {e}")

    # Commit remaining batch
    if ids_batch:
        collection.add(
            ids=ids_batch,
            embeddings=embeddings_batch,
            documents=documents_batch,
            metadatas=metadatas_batch
        )
        stats['imported'] += len(ids_batch)

    stats['end_time'] = datetime.now().isoformat()

    # Print summary
    print(f"\n{'='*60}")
    print(f"✅ IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Total annotations: {stats['total']}")
    print(f"  Successfully imported: {stats['imported']}")
    print(f"  Skipped (no text/book_id): {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Unique books: {len(stats['by_book'])}")
    print(f"  Collection size: {collection.count()} documents")
    print(f"{'='*60}\n")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Import Calibre annotations from Bridge plugin export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import from latest export (auto-detected)
  python scripts/import_calibre_annotations.py

  # Import from specific file
  python scripts/import_calibre_annotations.py --file "export.json"

  # Replace existing annotations
  python scripts/import_calibre_annotations.py --replace

  # Specify database location
  python scripts/import_calibre_annotations.py --db-path "D:\\Calibre-Bibliothek\\.archilles\\rag_db"
        """
    )

    parser.add_argument('--file', metavar='PATH',
                        help='Path to annotation export file (default: auto-detect latest)')
    parser.add_argument('--db-path', default=None,
                        help='ChromaDB path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    parser.add_argument('--replace', action='store_true',
                        help='Replace existing annotations (delete collection first)')
    parser.add_argument('--collection', default='calibre_annotations',
                        help='Collection name (default: calibre_annotations)')

    args = parser.parse_args()

    # Determine database path
    if args.db_path is None:
        calibre_library = os.environ.get('CALIBRE_LIBRARY_PATH')
        if not calibre_library:
            print("\n" + "="*60)
            print("ERROR: CALIBRE_LIBRARY_PATH not set")
            print("="*60 + "\n")
            print("Please set the environment variable:\n")
            print("  Windows (PowerShell):")
            print('    $env:CALIBRE_LIBRARY_PATH = "C:\\path\\to\\Calibre-Library"\n')
            print("  Or use --db-path to specify database location\n")
            sys.exit(1)
        args.db_path = str(Path(calibre_library) / ".archilles" / "rag_db")

    # Find export file
    if args.file:
        export_file = Path(args.file)
    else:
        export_file = find_latest_export()

    if not export_file or not export_file.exists():
        print(f"\n❌ Export file not found!")
        print(f"   Looked for: {export_file}")
        print(f"\nPlease:")
        print(f"  1. Run the ARCHILLES Bridge plugin in Calibre to create an export")
        print(f"  2. Or specify the export file with --file\n")
        sys.exit(1)

    # Import annotations
    try:
        stats = import_annotations(
            export_file=export_file,
            db_path=args.db_path,
            collection_name=args.collection,
            replace=args.replace
        )

        # Exit with error if nothing was imported
        if stats['imported'] == 0:
            print("⚠️  No annotations were imported!")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
