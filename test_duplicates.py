#!/usr/bin/env python3
"""
Test script for duplicate detection functionality.

This script demonstrates how to use the duplicate detection features
in both the CLI and MCP server.
"""

import sys
from pathlib import Path
from calibre_analyzer import CalibreAnalyzer
from src.calibre_mcp.server import CalibreMCPServer
import json


def test_cli_duplicates(db_path):
    """Test duplicate detection using CalibreAnalyzer directly"""
    print("=" * 70)
    print("Testing Duplicate Detection - CLI Mode")
    print("=" * 70)
    print()

    with CalibreAnalyzer(db_path) as analyzer:
        # Test different methods
        methods = ['title_author', 'isbn', 'exact_title']

        for method in methods:
            print(f"\nTesting method: {method}")
            print("-" * 70)
            result = analyzer.detect_duplicates(method=method)

            print(f"Duplicate groups found: {result['total_duplicate_groups']}")
            print(f"Total duplicate books: {result['total_duplicate_books']}")
            print(f"Books tagged with 'Doublette': {result['doublette_count']}")

            if result['duplicate_groups']:
                print(f"\nFirst duplicate group:")
                group = result['duplicate_groups'][0]
                print(f"  Match type: {group['match_type']}")
                print(f"  Books in group: {group['count']}")
                for book in group['books']:
                    authors = ', '.join(book['authors']) if book['authors'] else 'Unknown'
                    print(f"    - ID {book['id']}: {book['title']} by {authors}")


def test_mcp_server_duplicates(library_path):
    """Test duplicate detection using MCP Server"""
    print("\n\n")
    print("=" * 70)
    print("Testing Duplicate Detection - MCP Server Mode")
    print("=" * 70)
    print()

    # Initialize server
    server = CalibreMCPServer(library_path=library_path)

    # Test detect_duplicates_tool
    print("Testing detect_duplicates_tool with 'title_author' method:")
    print("-" * 70)
    result = server.detect_duplicates_tool(method='title_author')

    if 'error' in result:
        print(f"Error: {result['error']}")
    else:
        print(json.dumps({
            'method': result['method'],
            'total_duplicate_groups': result['total_duplicate_groups'],
            'total_duplicate_books': result['total_duplicate_books'],
            'doublette_count': result['doublette_count']
        }, indent=2))

        # Show first duplicate group if exists
        if result['duplicate_groups']:
            print("\nFirst duplicate group details:")
            print(json.dumps(result['duplicate_groups'][0], indent=2))

    # Test get_book_details_tool
    print("\n\nTesting get_book_details_tool:")
    print("-" * 70)
    if result.get('duplicate_groups') and result['duplicate_groups'][0]['books']:
        book_id = result['duplicate_groups'][0]['books'][0]['id']
        book_details = server.get_book_details_tool(book_id)
        print(f"Details for book ID {book_id}:")
        print(json.dumps(book_details, indent=2))


def main():
    """Main test function"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_duplicates.py <path_to_calibre_library>")
        print("  or")
        print("  python test_duplicates.py <path_to_metadata.db>")
        print()
        print("Examples:")
        print("  python test_duplicates.py ~/Calibre\\ Library")
        print("  python test_duplicates.py ~/Calibre\\ Library/metadata.db")
        sys.exit(1)

    library_path = sys.argv[1]
    library_path_obj = Path(library_path)

    # Determine database path
    if library_path_obj.name == 'metadata.db':
        db_path = str(library_path_obj)
        library_dir = str(library_path_obj.parent)
    else:
        db_path = str(library_path_obj / 'metadata.db')
        library_dir = library_path

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")
    print(f"Library directory: {library_dir}")
    print()

    # Run tests
    test_cli_duplicates(db_path)
    test_mcp_server_duplicates(library_dir)

    print("\n\n")
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print()
    print("All tests completed successfully!")
    print()
    print("To use duplicate detection:")
    print()
    print("1. CLI mode:")
    print(f"   python calibre_analyzer.py {db_path} --duplicates")
    print(f"   python calibre_analyzer.py {db_path} --duplicates --duplicate-method isbn")
    print()
    print("2. JSON output:")
    print(f"   python calibre_analyzer.py {db_path} -o json -f duplicates")
    print()
    print("3. MCP Server:")
    print("   Use the 'detect_duplicates' tool with your MCP client")
    print()


if __name__ == '__main__':
    main()
