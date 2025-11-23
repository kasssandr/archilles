#!/usr/bin/env python3
"""
Achilles RAG System with Hybrid Search

Features:
1. Extract text from books (30+ formats: PDF, EPUB, DJVU, MOBI, etc.)
2. BGE-M3 embeddings (multilingual, optimized for German/Latin/Greek)
3. BM25 keyword search (exact word matching)
4. Hybrid search (semantic + keyword via Reciprocal Rank Fusion)
5. Language filtering (auto-detected: de, en, la, fr, etc.)
6. ChromaDB local storage (100% offline)

Search Modes:
- hybrid (default): Best of both worlds - finds concepts AND exact words
- semantic: Concept-based search using BGE-M3 embeddings
- keyword: Exact word matching using BM25 (great for Latin phrases, custom terms)

Usage:
    # Index a book
    python scripts/rag_demo.py index "path/to/book.pdf" --book-id "Josephus"

    # Hybrid search (recommended - combines semantic + keyword)
    python scripts/rag_demo.py query "evangelista et a presbyteris"

    # Keyword-only (exact word matching)
    python scripts/rag_demo.py query "Judenkönige" --mode keyword

    # With language filter
    python scripts/rag_demo.py query "Rex" --language la --mode hybrid
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Literal
import time
import pickle
import re

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors import UniversalExtractor
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False


class AchillesRAG:
    """
    Simple RAG system for academic books.

    Features:
    - BGE-M3 embeddings (1024 dimensions, multilingual)
    - ChromaDB local storage
    - Exact page citations
    - Semantic search
    """

    def __init__(
        self,
        db_path: str = "./achilles_rag_db",
        model_name: str = "BAAI/bge-m3"
    ):
        """
        Initialize RAG system.

        Args:
            db_path: Path to ChromaDB storage
            model_name: Sentence transformer model (default: BGE-M3)
        """
        print(f"🚀 Initializing Achilles RAG...")
        print(f"  Database: {db_path}")
        print(f"  Model: {model_name}")

        # Initialize extractor
        self.extractor = UniversalExtractor(
            chunk_size=512,
            overlap=128
        )

        # Initialize embedding model
        print(f"  Loading embedding model... (first time: ~500 MB download)")
        self.embedding_model = SentenceTransformer(model_name)
        print(f"  ✓ Model loaded: {model_name}")

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=db_path)

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="achilles_books",
            metadata={"hnsw:space": "cosine"}
        )

        print(f"  ✓ ChromaDB ready")
        print(f"  Current index: {self.collection.count()} chunks")

        # Initialize BM25 index for hybrid search
        self.db_path = Path(db_path)
        self.bm25_index = None
        self.bm25_docs = None
        self.bm25_ids = None
        self._load_bm25_index()

        if BM25_AVAILABLE and self.bm25_index:
            print(f"  ✓ BM25 keyword search ready\n")
        elif not BM25_AVAILABLE:
            print(f"  ⚠ BM25 not available (install: pip install rank-bm25)\n")
        else:
            print(f"  ⚠ BM25 index empty (will be built on first indexing)\n")

    def index_book(self, book_path: str, book_id: str = None) -> Dict[str, Any]:
        """
        Extract and index a book.

        Args:
            book_path: Path to book file
            book_id: Optional book ID (default: filename)

        Returns:
            Dictionary with indexing statistics
        """
        book_path = Path(book_path)

        if not book_path.exists():
            raise FileNotFoundError(f"Book not found: {book_path}")

        book_id = book_id or book_path.stem

        print(f"📚 INDEXING BOOK: {book_path.name}")
        print(f"  Book ID: {book_id}\n")

        # Step 1: Extract text
        print("  [1/3] Extracting text...")
        start_time = time.time()
        extracted = self.extractor.extract(book_path)
        extract_time = time.time() - start_time

        print(f"    ✓ Extracted {len(extracted.chunks)} chunks in {extract_time:.1f}s")
        print(f"    ✓ {extracted.metadata.total_words:,} words, {extracted.metadata.total_pages or 'N/A'} pages\n")

        # Step 2: Generate embeddings
        print("  [2/3] Generating embeddings...")
        start_time = time.time()

        texts = [chunk['text'] for chunk in extracted.chunks]
        embeddings = []

        # Batch process for speed
        batch_size = 32
        for i in tqdm(range(0, len(texts), batch_size), desc="    Embedding"):
            batch = texts[i:i+batch_size]
            batch_embeddings = self.embedding_model.encode(
                batch,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            embeddings.extend(batch_embeddings.tolist())

        embed_time = time.time() - start_time
        print(f"    ✓ Generated {len(embeddings)} embeddings in {embed_time:.1f}s\n")

        # Step 3: Index in ChromaDB
        print("  [3/3] Indexing in ChromaDB...")
        start_time = time.time()

        # Prepare data
        ids = []
        documents = []
        metadatas = []

        for i, (chunk, embedding) in enumerate(zip(extracted.chunks, embeddings)):
            chunk_id = f"{book_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk['text'])

            # Metadata for citation
            metadata = {
                'book_id': book_id,
                'book_title': extracted.metadata.file_path.stem,
                'chunk_index': i,
                'format': extracted.metadata.detected_format,
            }

            # Add page info if available
            if 'metadata' in chunk and chunk['metadata'].get('page'):
                metadata['page'] = chunk['metadata']['page']

            # Add chapter info if available
            if 'metadata' in chunk and chunk['metadata'].get('chapter'):
                metadata['chapter'] = chunk['metadata']['chapter']

            # Add language info if available
            if 'metadata' in chunk and chunk['metadata'].get('language'):
                metadata['language'] = chunk['metadata']['language']

            metadatas.append(metadata)

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

        index_time = time.time() - start_time
        print(f"    ✓ Indexed {len(ids)} chunks in {index_time:.1f}s\n")

        # Summary
        total_time = extract_time + embed_time + index_time
        print(f"✅ INDEXING COMPLETE")
        print(f"  Total time: {total_time:.1f}s")
        print(f"  Collection size: {self.collection.count()} chunks\n")

        # Update BM25 index after indexing
        if BM25_AVAILABLE:
            self._rebuild_bm25_index()

        return {
            'book_id': book_id,
            'chunks_indexed': len(ids),
            'total_words': extracted.metadata.total_words,
            'total_pages': extracted.metadata.total_pages,
            'extraction_time': extract_time,
            'embedding_time': embed_time,
            'indexing_time': index_time,
            'total_time': total_time,
        }

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenizer for BM25.

        Lowercases and splits on word boundaries.
        Academic-friendly: keeps hyphens, apostrophes.
        """
        # Lowercase
        text = text.lower()
        # Split on whitespace and punctuation (but keep hyphens, apostrophes)
        tokens = re.findall(r"[\w'-]+", text)
        return tokens

    def _load_bm25_index(self):
        """Load BM25 index from disk if available."""
        bm25_path = self.db_path / "bm25_index.pkl"

        if not bm25_path.exists():
            return

        try:
            with open(bm25_path, 'rb') as f:
                data = pickle.load(f)
                self.bm25_index = data['index']
                self.bm25_docs = data['docs']
                self.bm25_ids = data['ids']
        except Exception as e:
            print(f"  ⚠ Could not load BM25 index: {e}")

    def _save_bm25_index(self):
        """Save BM25 index to disk."""
        if not self.bm25_index:
            return

        bm25_path = self.db_path / "bm25_index.pkl"
        bm25_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(bm25_path, 'wb') as f:
                pickle.dump({
                    'index': self.bm25_index,
                    'docs': self.bm25_docs,
                    'ids': self.bm25_ids
                }, f)
        except Exception as e:
            print(f"  ⚠ Could not save BM25 index: {e}")

    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from ChromaDB documents."""
        if not BM25_AVAILABLE:
            return

        # Get all documents from ChromaDB
        all_data = self.collection.get()

        if not all_data['ids']:
            return

        # Tokenize all documents
        self.bm25_ids = all_data['ids']
        self.bm25_docs = all_data['documents']
        tokenized_docs = [self._tokenize(doc) for doc in self.bm25_docs]

        # Build BM25 index
        self.bm25_index = BM25Okapi(tokenized_docs)

        # Save to disk
        self._save_bm25_index()

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        mode: Literal['semantic', 'keyword', 'hybrid'] = 'hybrid',
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant passages.

        Args:
            query_text: Search query
            top_k: Number of results to return
            mode: Search mode - 'semantic' (BGE-M3), 'keyword' (BM25), or 'hybrid' (both)
            language: Filter by language (e.g., 'de', 'en', 'la') or comma-separated list
            book_id: Filter by specific book ID
            exact_phrase: Use exact phrase matching (for Latin quotes, etc.)

        Returns:
            List of relevant chunks with metadata and scores
        """
        # Build filter message
        filters = []
        if language:
            filters.append(f"language={language}")
        if book_id:
            filters.append(f"book={book_id}")
        if exact_phrase:
            filters.append("exact phrase")

        filter_msg = f" ({', '.join(filters)})" if filters else ""
        mode_emoji = {"semantic": "🧠", "keyword": "🔤", "hybrid": "🔀"}
        print(f"{mode_emoji.get(mode, '🔍')} QUERY [{mode.upper()}]: \"{query_text}\"{filter_msg}")
        print(f"  Searching {self.collection.count()} chunks...\n")

        # Route to appropriate search method
        if mode == 'semantic':
            results = self._semantic_search(query_text, top_k, language, book_id)
        elif mode == 'keyword':
            results = self._keyword_search(query_text, top_k, language, book_id, exact_phrase=exact_phrase)
        elif mode == 'hybrid':
            results = self._hybrid_search(query_text, top_k, language, book_id, exact_phrase=exact_phrase)
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'semantic', 'keyword', or 'hybrid'")

        return results

    def _semantic_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None
    ) -> List[Dict[str, Any]]:
        """Semantic search using BGE-M3 embeddings."""
        # Generate query embedding
        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        ).tolist()

        # Build where clause for filtering
        where_clause = self._build_where_clause(language, book_id)

        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause
        )

        # Format results
        return self._format_results(results, score_type='semantic')

    def _keyword_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """Keyword search using BM25 or exact phrase matching."""
        if not BM25_AVAILABLE:
            print("  ⚠ BM25 not available. Install with: pip install rank-bm25")
            return []

        # Build BM25 index on-the-fly if not available
        if not self.bm25_index:
            print("  Building BM25 index on-the-fly...")
            self._rebuild_bm25_index()
            if not self.bm25_index:
                print("  ⚠ Could not build BM25 index (no documents?)")
                return []

        # For exact phrase matching, use different approach
        if exact_phrase:
            return self._exact_phrase_search(query_text, top_k, language, book_id)

        # Tokenize query
        query_tokens = self._tokenize(query_text)

        # Get BM25 scores
        scores = self.bm25_index.get_scores(query_tokens)

        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k * 10]  # Get more for filtering

        # Get metadata for filtering
        all_metadata = self.collection.get(ids=self.bm25_ids)['metadatas']

        # Filter by language/book_id
        filtered_results = []
        for idx in top_indices:
            metadata = all_metadata[idx]

            # Apply filters
            if language:
                langs = [l.strip() for l in language.split(',')] if ',' in language else [language]
                if metadata.get('language') not in langs:
                    continue

            if book_id and metadata.get('book_id') != book_id:
                continue

            filtered_results.append({
                'rank': len(filtered_results) + 1,
                'text': self.bm25_docs[idx],
                'metadata': metadata,
                'score': scores[idx],
                'similarity': min(scores[idx] / 10.0, 1.0),  # Normalize BM25 score to 0-1
            })

            if len(filtered_results) >= top_k:
                break

        return filtered_results

    def _exact_phrase_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Exact phrase matching (case-insensitive).

        Finds documents that contain the EXACT phrase, not just the words.
        Critical for Latin phrases like "evangelista et a presbyteris".

        IMPORTANT: Normalizes whitespace to handle line breaks!
        "evangelista\net a presbyteris" matches "evangelista et a presbyteris"
        """
        import re

        # Normalize query: lowercase + collapse whitespace (newlines, tabs, multiple spaces → single space)
        query_normalized = re.sub(r'\s+', ' ', query_text.lower().strip())

        # Get all documents
        all_data = self.collection.get(ids=self.bm25_ids)

        # Find exact matches
        matches = []
        for idx, (doc_id, doc_text, metadata) in enumerate(zip(
            all_data['ids'],
            all_data['documents'],
            all_data['metadatas']
        )):
            # Apply filters first
            if language:
                langs = [l.strip() for l in language.split(',')] if ',' in language else [language]
                if metadata.get('language') not in langs:
                    continue

            if book_id and metadata.get('book_id') != book_id:
                continue

            # Normalize document text: lowercase + collapse whitespace
            # This handles line breaks! "evangelista\net a presbyteris" → "evangelista et a presbyteris"
            doc_normalized = re.sub(r'\s+', ' ', doc_text.lower())

            # Check for exact phrase in normalized text
            if query_normalized in doc_normalized:
                # Count occurrences for scoring
                count = doc_normalized.count(query_normalized)

                matches.append({
                    'rank': 0,  # Will be set later
                    'text': doc_text,  # Keep ORIGINAL text (with line breaks)
                    'metadata': metadata,
                    'score': count,  # More occurrences = higher score
                    'similarity': min(count / 10.0, 1.0),  # Normalize
                })

        # Sort by score (number of occurrences)
        matches.sort(key=lambda x: x['score'], reverse=True)

        # Assign ranks
        for i, match in enumerate(matches[:top_k]):
            match['rank'] = i + 1

        return matches[:top_k]

    def _hybrid_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining semantic (BGE-M3) and keyword (BM25).

        Uses Reciprocal Rank Fusion (RRF) to combine scores.

        IMPORTANT: If exact_phrase=True, ONLY returns exact phrase matches (no semantic mixing!)
        """
        # For exact phrase matching, skip semantic search entirely
        # We want ONLY exact matches, not semantically similar results!
        if exact_phrase:
            return self._keyword_search(query_text, top_k, language, book_id, exact_phrase=True)

        # Get results from both methods (request more to have enough after fusion)
        semantic_results = self._semantic_search(query_text, top_k * 2, language, book_id)
        keyword_results = self._keyword_search(query_text, top_k * 2, language, book_id, exact_phrase=False)

        if not BM25_AVAILABLE or not keyword_results:
            # Fallback to semantic-only
            return semantic_results[:top_k]

        # Reciprocal Rank Fusion (RRF)
        # RRF score = sum(1 / (k + rank)) for each result
        k = 60  # RRF constant (standard value)
        rrf_scores = {}

        # Add semantic scores
        for result in semantic_results:
            doc_id = result['metadata'].get('chunk_index', id(result['text']))
            rrf_scores[doc_id] = {
                'score': 1 / (k + result['rank']),
                'result': result
            }

        # Add keyword scores (accumulate if already present)
        for result in keyword_results:
            doc_id = result['metadata'].get('chunk_index', id(result['text']))
            if doc_id in rrf_scores:
                rrf_scores[doc_id]['score'] += 1 / (k + result['rank'])
            else:
                rrf_scores[doc_id] = {
                    'score': 1 / (k + result['rank']),
                    'result': result
                }

        # Sort by RRF score
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1]['score'], reverse=True)

        # Format final results
        final_results = []
        for i, (doc_id, data) in enumerate(sorted_results[:top_k]):
            result = data['result'].copy()
            result['rank'] = i + 1
            result['similarity'] = min(data['score'], 1.0)  # Normalize
            final_results.append(result)

        return final_results

    def _build_where_clause(self, language: str = None, book_id: str = None):
        """Build ChromaDB where clause for filtering."""
        if not (language or book_id):
            return None

        where_conditions = {}

        if language:
            # Support comma-separated languages
            if ',' in language:
                langs = [l.strip() for l in language.split(',')]
                where_conditions['language'] = {'$in': langs}
            else:
                where_conditions['language'] = language

        if book_id:
            where_conditions['book_id'] = book_id

        # Combine conditions with AND
        if len(where_conditions) > 1:
            return {'$and': [{k: v} for k, v in where_conditions.items()]}
        elif where_conditions:
            return where_conditions
        return None

    def _format_results(self, results: Dict, score_type: str = 'semantic') -> List[Dict[str, Any]]:
        """Format ChromaDB results into standard format."""
        formatted_results = []

        if not results['ids'] or len(results['ids'][0]) == 0:
            return formatted_results

        for i in range(len(results['ids'][0])):
            result = {
                'rank': i + 1,
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i],
                'similarity': 1 - results['distances'][0][i],  # Convert distance to similarity
                'score_type': score_type
            }
            formatted_results.append(result)

        return formatted_results

    def _get_context_snippet(self, text: str, query_text: str, context_chars: int = 200) -> str:
        """
        Extract a relevant snippet from text that contains query terms.

        For keyword/hybrid searches, this shows WHERE the match was found.
        Much better UX than showing first 300 chars which might not contain the match!

        IMPORTANT: Handles line breaks in phrases!
        If query is "evangelista et a presbyteris" and text has line break:
        "...evangelista\net a presbyteris..." → still finds it!

        Args:
            text: Full chunk text
            query_text: Original query
            context_chars: Characters of context around match (default: 200)

        Returns:
            Snippet with "..." prefix/suffix if truncated
        """
        import re

        text_lower = text.lower()
        query_lower = query_text.lower()
        best_match_pos = len(text)  # Default: end of text

        # Strategy 1: Try to find the ENTIRE query phrase first (exact phrase matching)
        # This is critical for Latin quotes like "evangelista et a presbyteris"
        phrase_pos = text_lower.find(query_lower)
        if phrase_pos != -1:
            best_match_pos = phrase_pos
        else:
            # Strategy 1b: Try regex matching with flexible whitespace
            # This handles line breaks! "evangelista\s+et\s+a\s+presbyteris" matches "evangelista\net a presbyteris"
            # Escape special regex chars in query, then replace spaces with \s+
            query_escaped = re.escape(query_lower)
            query_pattern = re.sub(r'\\ ', r'\\s+', query_escaped)  # Replace escaped spaces with \s+

            match = re.search(query_pattern, text_lower, re.IGNORECASE)
            if match:
                best_match_pos = match.start()
            else:
                # Strategy 2: Fallback to individual token matching
                # This works for partial matches or when query is multiple concepts
                query_tokens = self._tokenize(query_text)

                if not query_tokens:
                    # No tokens found, show beginning
                    return text[:300] + ('...' if len(text) > 300 else '')

                # Find first occurrence of any query token
                for token in query_tokens:
                    pos = text_lower.find(token.lower())
                    if pos != -1 and pos < best_match_pos:
                        best_match_pos = pos

        # If no match found (shouldn't happen), show beginning
        if best_match_pos == len(text):
            return text[:300] + ('...' if len(text) > 300 else '')

        # Calculate snippet boundaries
        start = max(0, best_match_pos - context_chars)
        end = min(len(text), best_match_pos + context_chars)

        # Extract snippet
        snippet = text[start:end]

        # Add ellipsis if truncated
        if start > 0:
            snippet = '...' + snippet
        if end < len(text):
            snippet = snippet + '...'

        return snippet

    def print_results(self, results: List[Dict[str, Any]], query_text: str = ""):
        """Pretty print search results with context snippets."""
        if not results:
            print("❌ No results found.\n")
            return

        print(f"📊 TOP {len(results)} RESULTS:\n")
        print("=" * 80)

        for result in results:
            rank = result['rank']
            similarity = result['similarity']
            metadata = result['metadata']
            text = result['text']

            # Build citation with printed page numbers
            citation_parts = []
            if metadata.get('book_title'):
                citation_parts.append(metadata['book_title'])

            # Check for printed page number with confidence
            printed_page = metadata.get('printed_page')
            printed_conf = metadata.get('printed_page_confidence', 0.0)
            page_warning = None

            if printed_page and printed_conf >= 0.8:
                # Use printed page number (high confidence)
                citation_parts.append(f"S. {printed_page}")

                # Add warning if confidence < 0.9
                if printed_conf < 0.9:
                    page_warning = f"Seitenzahl-Konfidenz: {printed_conf:.2f} - bitte verifizieren"
            elif metadata.get('page'):
                # Fallback to PDF page number
                citation_parts.append(f"PDF S. {metadata['page']}")

                # Add warning if printed page exists but low confidence
                if printed_page:
                    page_warning = f"⚠ Gedruckte Seitenzahl unsicher (Konfidenz: {printed_conf:.2f})"
            elif metadata.get('chapter'):
                citation_parts.append(metadata['chapter'])

            citation = ', '.join(citation_parts) if citation_parts else metadata.get('book_id', 'Unknown')

            print(f"\n[{rank}] {citation}")
            print(f"    Relevanz: {similarity:.3f} ({'sehr hoch' if similarity > 0.8 else 'hoch' if similarity > 0.6 else 'mittel'})")

            # Show page number warning if applicable
            if page_warning:
                print(f"    📄 {page_warning}")

            # Show context snippet with query terms (if available)
            if query_text:
                snippet = self._get_context_snippet(text, query_text)
            else:
                snippet = text[:300] + ('...' if len(text) > 300 else '')

            print(f"    Text: {snippet}")

        print("\n" + "=" * 80 + "\n")


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="Achilles Mini-RAG: Semantic search in academic books",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index Josephus Antiquitates
  python scripts/rag_demo.py index "D:/Calibre-Bibliothek/Flavius Josephus/Judische Altertumer_...pdf"

  # Query (hybrid mode by default - combines semantic + keyword)
  python scripts/rag_demo.py query "evangelista et a presbyteris"

  # Search modes
  python scripts/rag_demo.py query "Judenkönige" --mode hybrid     # Best: semantic + keyword (default)
  python scripts/rag_demo.py query "Judenkönige" --mode keyword    # Exact word matching (BM25)
  python scripts/rag_demo.py query "Judenkönige" --mode semantic   # Concept search (BGE-M3)

  # Filter by language
  python scripts/rag_demo.py query "kings" --language de
  python scripts/rag_demo.py query "Rex" --language la
  python scripts/rag_demo.py query "kings" --language de,en

  # Filter by book
  python scripts/rag_demo.py query "Marcion" --book-id "von_Harnack"

  # More results
  python scripts/rag_demo.py query "Jewish kings" --top-k 10
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index a book')
    index_parser.add_argument('book_path', help='Path to book file')
    index_parser.add_argument('--book-id', help='Optional book ID (default: filename)')
    index_parser.add_argument('--db-path', default='./achilles_rag_db', help='Database path')

    # Query command
    query_parser = subparsers.add_parser('query', help='Search indexed books')
    query_parser.add_argument('query', help='Search query')
    query_parser.add_argument('--top-k', type=int, default=5, help='Number of results (default: 5)')
    query_parser.add_argument('--mode', choices=['semantic', 'keyword', 'hybrid'], default='hybrid',
                              help='Search mode: semantic (BGE-M3), keyword (BM25), or hybrid (both, default)')
    query_parser.add_argument('--exact', action='store_true',
                              help='Exact phrase matching (case-insensitive) - critical for Latin quotes')
    query_parser.add_argument('--language', help='Filter by language (e.g., de, en, la) or comma-separated')
    query_parser.add_argument('--book-id', help='Filter by specific book ID')
    query_parser.add_argument('--db-path', default='./achilles_rag_db', help='Database path')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show index statistics')
    stats_parser.add_argument('--db-path', default='./achilles_rag_db', help='Database path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        # Initialize RAG
        rag = AchillesRAG(db_path=args.db_path)

        if args.command == 'index':
            # Index a book
            stats = rag.index_book(args.book_path, args.book_id)

        elif args.command == 'query':
            # Search
            results = rag.query(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                language=args.language,
                book_id=args.book_id,
                exact_phrase=args.exact
            )
            rag.print_results(results, query_text=args.query)

        elif args.command == 'stats':
            # Show stats
            print(f"📊 INDEX STATISTICS\n")
            print(f"  Total chunks: {rag.collection.count()}")
            print(f"  Database path: {args.db_path}\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
