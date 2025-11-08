#!/usr/bin/env python3
"""
Example usage of the Calibre Metadata Analyzer as a Python module
"""

from calibre_analyzer import CalibreAnalyzer
import json


def example_basic_usage(db_path):
    """Basic usage example"""
    print("=== Basic Usage Example ===\n")

    with CalibreAnalyzer(db_path) as analyzer:
        # Get total books
        total = analyzer.get_total_books()
        print(f"Total books in library: {total}\n")

        # Get top authors
        print("Top 5 Authors:")
        authors = analyzer.get_authors_stats()
        for i, author in enumerate(authors[:5], 1):
            print(f"{i}. {author['name']}: {author['book_count']} books")
        print()


def example_detailed_analysis(db_path):
    """Example showing detailed analysis"""
    print("=== Detailed Analysis Example ===\n")

    with CalibreAnalyzer(db_path) as analyzer:
        # Get complete analysis
        analysis = analyzer.get_complete_analysis()

        print(f"Library Statistics:")
        print(f"- Total Books: {analysis['total_books']}")
        print(f"- Number of Authors: {len(analysis['authors'])}")
        print(f"- Number of Publishers: {len(analysis['publishers'])}")
        print(f"- Number of Tags: {len(analysis['tags'])}")
        print(f"- Number of Series: {len(analysis['series'])}")
        print(f"- Languages: {len(analysis['languages'])}")
        print()

        # Check data quality
        incomplete = analysis['incomplete_metadata']
        if incomplete:
            print(f"Data Quality Alert:")
            print(f"- {len(incomplete)} books have incomplete metadata")
            print(f"  (missing authors, tags, publishers, or dates)")
        else:
            print("Data Quality: All books have complete metadata!")
        print()


def example_export_to_json(db_path, output_file='library_analysis.json'):
    """Example of exporting analysis to JSON"""
    print("=== Export to JSON Example ===\n")

    with CalibreAnalyzer(db_path) as analyzer:
        analysis = analyzer.get_complete_analysis()

        # Save to JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)

        print(f"Analysis exported to: {output_file}")
        print(f"File size: {len(json.dumps(analysis))} bytes")
        print()


def example_find_incomplete_books(db_path):
    """Example of finding books with missing metadata"""
    print("=== Find Incomplete Metadata Example ===\n")

    with CalibreAnalyzer(db_path) as analyzer:
        incomplete = analyzer.get_books_without_metadata()

        if incomplete:
            print(f"Found {len(incomplete)} books with incomplete metadata:\n")
            for book in incomplete[:10]:  # Show first 10
                missing = ', '.join(book['missing_fields'])
                print(f"- '{book['title']}'")
                print(f"  Missing: {missing}\n")

            if len(incomplete) > 10:
                print(f"... and {len(incomplete) - 10} more")
        else:
            print("All books have complete metadata!")
        print()


def example_ratings_analysis(db_path):
    """Example of analyzing ratings"""
    print("=== Ratings Analysis Example ===\n")

    with CalibreAnalyzer(db_path) as analyzer:
        ratings = analyzer.get_ratings_distribution()

        if ratings:
            total_rated = sum(r['book_count'] for r in ratings)
            total_books = analyzer.get_total_books()

            print(f"Rating Statistics:")
            print(f"- Rated books: {total_rated}/{total_books}")
            print(f"- Unrated books: {total_books - total_rated}")
            print()

            print("Rating Distribution:")
            for rating in ratings:
                stars = int(rating['rating_stars'])
                bar = '█' * int(rating['book_count'] / 10)  # Simple bar chart
                print(f"  {'★' * stars} ({rating['rating_stars']:.1f}): "
                      f"{rating['book_count']:3d} {bar}")
        else:
            print("No ratings found in library")
        print()


def example_format_analysis(db_path):
    """Example of analyzing file formats"""
    print("=== Format Analysis Example ===\n")

    with CalibreAnalyzer(db_path) as analyzer:
        formats = analyzer.get_format_stats()

        if formats:
            total_files = sum(f['count'] for f in formats)
            print(f"Total files: {total_files}\n")

            print("Format Distribution:")
            for fmt in formats:
                percentage = (fmt['count'] / total_files) * 100
                print(f"  {fmt['format']:8s}: {fmt['count']:4d} files ({percentage:5.1f}%)")
        else:
            print("No format information found")
        print()


def main():
    """Main example runner"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python example_usage.py <path_to_metadata.db>")
        print("\nThis script demonstrates various ways to use the CalibreAnalyzer.")
        sys.exit(1)

    db_path = sys.argv[1]

    try:
        # Run all examples
        example_basic_usage(db_path)
        example_detailed_analysis(db_path)
        example_find_incomplete_books(db_path)
        example_ratings_analysis(db_path)
        example_format_analysis(db_path)
        # example_export_to_json(db_path)  # Uncomment to export

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
