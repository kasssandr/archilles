#!/usr/bin/env python3
"""
Full-Text Search Engine using SQLite FTS5
For Calibre Quote Tracker
"""

import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SearchEngine:
    """
    Full-text search engine using SQLite FTS5
    """

    def __init__(self, db_path="quote_search_index.db"):
        """
        Initialize search engine

        Args:
            db_path: Path to SQLite database for search index
        """
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._initialize_db()

    def _initialize_db(self):
        """Create FTS5 virtual table if it doesn't exist"""
        cursor = self.conn.cursor()

        # Create FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS book_texts USING fts5(
                book_id,
                author,
                title,
                format,
                full_text,
                tokenize='porter unicode61'
            )
        """)

        # Create metadata table for additional info
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS book_metadata (
                book_id INTEGER PRIMARY KEY,
                author TEXT,
                title TEXT,
                format TEXT,
                text_length INTEGER,
                indexed_date TEXT
            )
        """)

        self.conn.commit()

    def index_book(self, book_id, author, title, format, full_text):
        """
        Index a book's full text

        Args:
            book_id: Calibre book ID
            author: Book author
            title: Book title
            format: File format (PDF, EPUB)
            full_text: Full text content
        """
        cursor = self.conn.cursor()

        # Check if already indexed
        cursor.execute("SELECT book_id FROM book_metadata WHERE book_id = ?", (book_id,))
        if cursor.fetchone():
            logger.info(f"Book {book_id} already indexed, skipping")
            return

        # Insert into FTS5 table
        cursor.execute("""
            INSERT INTO book_texts (book_id, author, title, format, full_text)
            VALUES (?, ?, ?, ?, ?)
        """, (book_id, author, title, format, full_text))

        # Insert metadata
        from datetime import datetime
        cursor.execute("""
            INSERT INTO book_metadata (book_id, author, title, format, text_length, indexed_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (book_id, author, title, format, len(full_text), datetime.now().isoformat()))

        self.conn.commit()
        logger.info(f"Indexed book {book_id}: {title} by {author}")

    def search(self, query, limit=50):
        """
        Search for query in indexed books

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            list: List of matching results with snippets
        """
        cursor = self.conn.cursor()

        # Escape query for FTS5 to avoid syntax errors
        # Split into terms and quote each one to prevent column name interpretation
        terms = query.split()
        # Quote each term to make it safe for FTS5
        quoted_terms = [f'"{term}"' for term in terms]
        # Join with OR to find any of the terms (more results)
        fts5_query = ' OR '.join(quoted_terms)

        # Use FTS5 MATCH for full-text search
        # snippet() function extracts relevant context
        cursor.execute("""
            SELECT
                book_id,
                author,
                title,
                format,
                snippet(book_texts, 4, '<mark>', '</mark>', '...', 64) as snippet,
                rank
            FROM book_texts
            WHERE book_texts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts5_query, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                'book_id': row['book_id'],
                'author': row['author'],
                'title': row['title'],
                'format': row['format'],
                'snippet': row['snippet'],
                'rank': row['rank']
            })

        return results

    def get_context_around_match(self, book_id, query, context_type='sentences', context_size=3):
        """
        Get detailed context around search matches

        Args:
            book_id: Book ID to search in
            query: Search query
            context_type: 'sentences' or 'words'
            context_size: Number of sentences/words before and after

        Returns:
            list: List of context snippets with match highlighted
        """
        cursor = self.conn.cursor()

        # Get full text
        cursor.execute("SELECT full_text FROM book_texts WHERE book_id = ?", (book_id,))
        row = cursor.fetchone()

        if not row:
            return []

        full_text = row['full_text']
        results = []

        # Simple regex search for query terms
        # Split query into terms
        query_terms = query.lower().split()

        # Find all positions where any query term appears
        matches = []
        for term in query_terms:
            for match in re.finditer(re.escape(term), full_text, re.IGNORECASE):
                matches.append((match.start(), match.end(), term))

        # Sort by position
        matches.sort(key=lambda x: x[0])

        # Extract context for each match
        for start_pos, end_pos, term in matches:
            if context_type == 'sentences':
                context = self._extract_sentence_context(full_text, start_pos, end_pos, context_size)
            else:  # words
                context = self._extract_word_context(full_text, start_pos, end_pos, context_size)

            results.append({
                'match_term': term,
                'context': context,
                'position': start_pos
            })

        return results

    def _extract_sentence_context(self, text, match_start, match_end, num_sentences):
        """
        Extract context with N sentences before and after match

        Args:
            text: Full text
            match_start: Start position of match
            match_end: End position of match
            num_sentences: Number of sentences before/after

        Returns:
            str: Context with match highlighted
        """
        # Simple sentence splitting (can be improved with NLTK)
        sentences = re.split(r'[.!?]+\s+', text)

        # Find which sentence contains the match
        current_pos = 0
        match_sentence_idx = -1

        for idx, sentence in enumerate(sentences):
            sentence_start = current_pos
            sentence_end = current_pos + len(sentence)

            if sentence_start <= match_start < sentence_end:
                match_sentence_idx = idx
                break

            current_pos = sentence_end + 2  # Account for delimiter + space

        if match_sentence_idx == -1:
            return ""

        # Extract sentences around match
        start_idx = max(0, match_sentence_idx - num_sentences)
        end_idx = min(len(sentences), match_sentence_idx + num_sentences + 1)

        context_sentences = sentences[start_idx:end_idx]
        context = '. '.join(context_sentences)

        # Highlight match in context
        match_text = text[match_start:match_end]
        context = context.replace(match_text, f"<mark>{match_text}</mark>")

        return context

    def _extract_word_context(self, text, match_start, match_end, num_words):
        """
        Extract context with N words before and after match

        Args:
            text: Full text
            match_start: Start position of match
            match_end: End position of match
            num_words: Number of words before/after

        Returns:
            str: Context with match highlighted
        """
        # Split into words
        words_before = text[:match_start].split()
        match_text = text[match_start:match_end]
        words_after = text[match_end:].split()

        # Extract context words
        context_before = ' '.join(words_before[-num_words:]) if words_before else ''
        context_after = ' '.join(words_after[:num_words]) if words_after else ''

        # Build context
        parts = []
        if context_before:
            parts.append(context_before)
        parts.append(f"<mark>{match_text}</mark>")
        if context_after:
            parts.append(context_after)

        return ' '.join(parts)

    def get_stats(self):
        """Get statistics about indexed books"""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM book_metadata")
        total_books = cursor.fetchone()['total']

        cursor.execute("SELECT SUM(text_length) as total_chars FROM book_metadata")
        total_chars = cursor.fetchone()['total_chars'] or 0

        cursor.execute("SELECT format, COUNT(*) as count FROM book_metadata GROUP BY format")
        formats = [dict(row) for row in cursor.fetchall()]

        return {
            'total_books': total_books,
            'total_characters': total_chars,
            'formats': formats
        }

    def clear_index(self):
        """Clear all indexed data"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM book_texts")
        cursor.execute("DELETE FROM book_metadata")
        self.conn.commit()
        logger.info("Search index cleared")

    def close(self):
        """Close database connection"""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class HybridSearchEngine:
    """
    Hybrid search engine combining keyword (FTS5) and semantic (ChromaDB) search
    """

    def __init__(self, fts_db_path="quote_search_index.db", chroma_db_path="./chroma_db", collection_name="quote_tracker"):
        """
        Initialize hybrid search engine

        Args:
            fts_db_path: Path to FTS5 database
            chroma_db_path: Path to ChromaDB storage
            collection_name: Name of the ChromaDB collection to use
        """
        self.keyword_engine = SearchEngine(fts_db_path)

        # Lazy load semantic engine (only when needed)
        self.semantic_engine = None
        self.chroma_db_path = chroma_db_path
        self.collection_name = collection_name
        self._semantic_available = False

    def _init_semantic(self):
        """Initialize semantic search engine (lazy loading)"""
        if self.semantic_engine is None:
            try:
                from semantic_search import SemanticSearchEngine
                self.semantic_engine = SemanticSearchEngine(
                    chroma_db_path=self.chroma_db_path,
                    collection_name=self.collection_name
                )
                self._semantic_available = True
                logger.info(f"Semantic search initialized (collection: {self.collection_name})")
            except Exception as e:
                logger.warning(f"Semantic search not available: {e}")
                self._semantic_available = False

    def search_keyword(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Keyword-based search using FTS5

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of results
        """
        return self.keyword_engine.search(query, limit)

    def search_semantic(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Semantic search using embeddings

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of results with normalized format
        """
        self._init_semantic()

        if not self._semantic_available:
            logger.warning("Semantic search not available, falling back to keyword")
            return self.search_keyword(query, limit)

        results = self.semantic_engine.search(query, limit)

        # Normalize results format for UI consistency
        for result in results:
            result['source'] = 'semantic'
            # Use similarity as the primary score
            if 'similarity' in result:
                result['relevance_score'] = result['similarity']
            # Add format field if missing
            if 'format' not in result:
                result['format'] = 'SEMANTIC'

        return results

    def search_hybrid(self, query: str, limit: int = 50, keyword_weight: float = 0.5) -> List[Dict]:
        """
        Hybrid search combining keyword and semantic results

        Args:
            query: Search query
            limit: Maximum results
            keyword_weight: Weight for keyword results (0-1), semantic gets (1-weight)

        Returns:
            Combined and ranked results
        """
        self._init_semantic()

        # Get keyword results
        keyword_results = self.search_keyword(query, limit=limit * 2)

        # Get semantic results (if available)
        if self._semantic_available:
            semantic_results = self.search_semantic(query, limit=limit * 2)
        else:
            semantic_results = []

        # Combine results
        combined = self._combine_results(
            keyword_results,
            semantic_results,
            keyword_weight,
            limit
        )

        return combined

    def _combine_results(
        self,
        keyword_results: List[Dict],
        semantic_results: List[Dict],
        keyword_weight: float,
        limit: int
    ) -> List[Dict]:
        """
        Combine and rank keyword + semantic results

        Args:
            keyword_results: Results from FTS5
            semantic_results: Results from semantic search
            keyword_weight: Weight for keyword (0-1)
            limit: Maximum results

        Returns:
            Combined results sorted by hybrid score
        """
        semantic_weight = 1.0 - keyword_weight

        # Create lookup by book_id
        combined_map = {}

        # Add keyword results
        for idx, result in enumerate(keyword_results):
            book_id = result['book_id']
            # Normalize keyword rank (inverse, smaller rank = better)
            keyword_score = 1.0 / (idx + 1)

            combined_map[book_id] = {
                **result,
                'keyword_score': keyword_score,
                'semantic_score': 0.0,
                'hybrid_score': keyword_score * keyword_weight,
                'source': 'keyword'
            }

        # Add/merge semantic results
        for idx, result in enumerate(semantic_results):
            book_id = result['book_id']
            # Use similarity score from semantic search
            semantic_score = result.get('similarity', 1.0 / (idx + 1))

            if book_id in combined_map:
                # Merge with existing keyword result
                combined_map[book_id]['semantic_score'] = semantic_score
                combined_map[book_id]['hybrid_score'] = (
                    combined_map[book_id]['keyword_score'] * keyword_weight +
                    semantic_score * semantic_weight
                )
                combined_map[book_id]['source'] = 'hybrid'
                # Prefer semantic text if available (often has better context)
                if 'text' in result:
                    combined_map[book_id]['snippet'] = result['text']
            else:
                # New result from semantic only
                combined_map[book_id] = {
                    'book_id': book_id,
                    'author': result.get('author', ''),
                    'title': result.get('title', ''),
                    'format': result.get('metadata', {}).get('format', ''),
                    'snippet': result.get('text', ''),
                    'keyword_score': 0.0,
                    'semantic_score': semantic_score,
                    'hybrid_score': semantic_score * semantic_weight,
                    'source': 'semantic',
                    'rank': 0
                }

        # Sort by hybrid score (descending)
        sorted_results = sorted(
            combined_map.values(),
            key=lambda x: x['hybrid_score'],
            reverse=True
        )

        return sorted_results[:limit]

    def get_stats(self) -> Dict:
        """Get statistics from both engines"""
        keyword_stats = self.keyword_engine.get_stats()

        semantic_stats = {}
        if self._semantic_available and self.semantic_engine:
            semantic_stats = self.semantic_engine.get_stats()

        return {
            'keyword': keyword_stats,
            'semantic': semantic_stats,
            'semantic_available': self._semantic_available
        }

    def close(self):
        """Close both engines"""
        self.keyword_engine.close()
        if self.semantic_engine:
            # ChromaDB doesn't need explicit closing
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    # Simple test
    print("Testing SearchEngine...")

    with SearchEngine("test_search.db") as engine:
        # Test indexing
        engine.index_book(
            book_id=1,
            author="Test Author",
            title="Test Book",
            format="PDF",
            full_text="This is a test document. It contains some interesting information about ancient history. The Romans were fascinating people."
        )

        # Test search
        results = engine.search("ancient history")
        print(f"\nSearch results for 'ancient history': {len(results)} found")
        for r in results:
            print(f"  - {r['title']} by {r['author']}")
            print(f"    Snippet: {r['snippet']}\n")

        # Test stats
        stats = engine.get_stats()
        print(f"Index stats: {stats}")

    print("Test completed!")
