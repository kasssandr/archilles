#!/usr/bin/env python3
"""
Calibre Annotation Hash Calculator

This tool calculates the correct hash for Calibre annotation files.

IMPORTANT: Calibre uses SHA256 of the FILE PATH, not the file content!

This is the correct way Calibre calculates the annotation file hash:
    hash = sha256(path.encode('utf-8')).hexdigest()

NOT this (which is wrong):
    hash = sha256(file_content).hexdigest()
"""

import hashlib
import os
import json
from pathlib import Path
from typing import Optional, Dict, List


def compute_annotation_hash(book_path: str) -> str:
    """
    Compute the hash used by Calibre for annotation filenames.

    CRITICAL: Calibre hashes the FILE PATH, not the file content!

    Args:
        book_path: Full path to the book file

    Returns:
        SHA256 hash of the path (64 character hex string)
    """
    # Convert path to bytes and compute SHA256
    path_bytes = book_path.encode('utf-8')
    return hashlib.sha256(path_bytes).hexdigest()


def compute_wrong_hash(book_path: str) -> str:
    """
    WRONG method - hashes file content instead of path.
    This is included only for comparison/debugging.
    """
    sha256_hash = hashlib.sha256()
    with open(book_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def find_annotation_file(
    book_path: str,
    annotations_dir: str
) -> Optional[str]:
    """
    Find the annotation file for a given book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Path to Calibre's annotations directory

    Returns:
        Path to annotation file if found, None otherwise
    """
    correct_hash = compute_annotation_hash(book_path)
    annotation_file = Path(annotations_dir) / f"{correct_hash}.json"

    if annotation_file.exists():
        return str(annotation_file)
    return None


def diagnose_book(
    book_path: str,
    annotations_dir: str
) -> Dict:
    """
    Diagnose annotation lookup issues for a book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Path to Calibre's annotations directory

    Returns:
        Diagnostic information
    """
    result = {
        "book_path": book_path,
        "book_exists": os.path.exists(book_path),
        "annotations_dir": annotations_dir,
        "annotations_dir_exists": os.path.exists(annotations_dir),
    }

    if not result["book_exists"]:
        result["error"] = "Book file not found"
        return result

    if not result["annotations_dir_exists"]:
        result["error"] = "Annotations directory not found"
        return result

    # Calculate both hashes for comparison
    correct_hash = compute_annotation_hash(book_path)
    wrong_hash = compute_wrong_hash(book_path)

    result["correct_hash_path_based"] = correct_hash
    result["wrong_hash_content_based"] = wrong_hash
    result["hashes_match"] = correct_hash == wrong_hash

    # Check for annotation files
    correct_file = Path(annotations_dir) / f"{correct_hash}.json"
    wrong_file = Path(annotations_dir) / f"{wrong_hash}.json"

    result["correct_annotation_file"] = str(correct_file)
    result["correct_file_exists"] = correct_file.exists()

    result["wrong_annotation_file"] = str(wrong_file)
    result["wrong_file_exists"] = wrong_file.exists()

    if result["correct_file_exists"]:
        result["status"] = "OK"
        result["message"] = "Annotation file found with correct path-based hash"

        # Load and show annotation count
        try:
            with open(correct_file, 'r', encoding='utf-8') as f:
                annotations = json.load(f)
                if isinstance(annotations, list):
                    result["annotation_count"] = len(annotations)
                elif isinstance(annotations, dict):
                    result["annotation_count"] = sum(
                        len(v) if isinstance(v, list) else 1
                        for v in annotations.values()
                    )
        except Exception as e:
            result["annotation_load_error"] = str(e)

    elif result["wrong_file_exists"]:
        result["status"] = "HASH_MISMATCH"
        result["message"] = (
            "Annotation file exists but was looked up with wrong hash! "
            "The MCP server is using content-based hash instead of path-based hash."
        )
    else:
        result["status"] = "NOT_FOUND"
        result["message"] = "No annotation file found for this book"

        # List similar files for debugging
        annots_path = Path(annotations_dir)
        if annots_path.exists():
            all_files = list(annots_path.glob("*.json"))
            result["total_annotation_files"] = len(all_files)

    return result


def list_all_annotations(annotations_dir: str) -> List[Dict]:
    """
    List all annotation files in the directory.

    Args:
        annotations_dir: Path to Calibre's annotations directory

    Returns:
        List of annotation file information
    """
    annots_path = Path(annotations_dir)
    results = []

    for json_file in annots_path.glob("*.json"):
        try:
            stat = json_file.stat()
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            count = 0
            if isinstance(data, list):
                count = len(data)
            elif isinstance(data, dict):
                count = sum(
                    len(v) if isinstance(v, list) else 1
                    for v in data.values()
                )

            results.append({
                "filename": json_file.name,
                "hash": json_file.stem,
                "size_bytes": stat.st_size,
                "annotation_count": count
            })
        except Exception as e:
            results.append({
                "filename": json_file.name,
                "hash": json_file.stem,
                "error": str(e)
            })

    return sorted(results, key=lambda x: x.get("annotation_count", 0), reverse=True)


def main():
    """Main entry point with example usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Calibre Annotation Hash Calculator and Diagnostic Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Calculate correct hash for a book
  %(prog)s hash "D:\\Calibre\\Book.epub"

  # Diagnose annotation lookup issues
  %(prog)s diagnose "D:\\Calibre\\Book.epub" "C:\\Users\\X\\AppData\\Roaming\\calibre\\viewer\\annots"

  # List all annotation files
  %(prog)s list "C:\\Users\\X\\AppData\\Roaming\\calibre\\viewer\\annots"
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Hash command
    hash_parser = subparsers.add_parser('hash', help='Calculate annotation hash for a book')
    hash_parser.add_argument('book_path', help='Path to the book file')

    # Diagnose command
    diag_parser = subparsers.add_parser('diagnose', help='Diagnose annotation lookup issues')
    diag_parser.add_argument('book_path', help='Path to the book file')
    diag_parser.add_argument('annotations_dir', help='Path to annotations directory')

    # List command
    list_parser = subparsers.add_parser('list', help='List all annotation files')
    list_parser.add_argument('annotations_dir', help='Path to annotations directory')

    args = parser.parse_args()

    if args.command == 'hash':
        correct = compute_annotation_hash(args.book_path)
        print(f"Book path: {args.book_path}")
        print(f"Correct hash (path-based): {correct}")
        print(f"Expected annotation file: {correct}.json")

        if os.path.exists(args.book_path):
            wrong = compute_wrong_hash(args.book_path)
            print(f"\nWrong hash (content-based): {wrong}")
            if correct != wrong:
                print("\nWARNING: These hashes are different!")
                print("If the MCP server uses content-based hash, it will fail to find annotations.")

    elif args.command == 'diagnose':
        result = diagnose_book(args.book_path, args.annotations_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == 'list':
        results = list_all_annotations(args.annotations_dir)
        print(f"Found {len(results)} annotation files:\n")
        for item in results[:20]:  # Show top 20
            print(f"  {item['hash'][:16]}... - {item.get('annotation_count', '?')} annotations")
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
