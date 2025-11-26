#!/usr/bin/env python3
"""
Example: Using ARCHILLES with XML-Formatted Prompts for Claude

Demonstrates the new Phase 1 improvements:
1. XML-Prompt structure with citation instructions
2. Inline metadata injection
3. Context expansion (Small-to-Big) - when char_offsets available

Usage:
    python scripts/example_xml_prompts.py "Was ist Herrschaftslegitimation?"
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG


def main():
    # Initialize RAG system
    rag = archillesRAG(db_path="./archilles_rag_db")

    # Example query
    query = sys.argv[1] if len(sys.argv) > 1 else "Was ist Herrschaftslegitimation?"

    print(f"🔍 Query: {query}\n")

    # Search for relevant passages
    results = rag.query(query, top_k=3, mode='hybrid')

    if not results:
        print("❌ No results found.")
        return

    # ===========================================
    # NEW: Create Claude-optimized prompt
    # ===========================================

    claude_prompt = rag.create_claude_prompt(
        results=results,
        query_text=query,
        expand_context=False  # Set to True when char_offsets are indexed
    )

    print("\n" + "=" * 80)
    print("📋 CLAUDE PROMPT PACKAGE")
    print("=" * 80 + "\n")

    print(f"📊 Stats:")
    print(f"  - Sources: {claude_prompt['num_sources']}")
    print(f"  - Approx tokens: {claude_prompt['total_tokens_approx']}")
    print()

    print("=" * 80)
    print("SYSTEM PROMPT (copy to Claude's System field):")
    print("=" * 80)
    print(claude_prompt['system'])
    print()

    print("=" * 80)
    print("USER PROMPT (copy to Claude's message):")
    print("=" * 80)
    print(claude_prompt['user'])
    print()

    print("=" * 80)
    print("✅ Now copy these prompts to Claude Desktop and ask your question!")
    print("   Claude will cite sources as [doc_1], [doc_2], etc.")
    print("=" * 80)


if __name__ == "__main__":
    main()
