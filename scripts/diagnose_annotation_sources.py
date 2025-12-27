#!/usr/bin/env python3
"""
Diagnose why all annotations show source: "unknown"
"""

import json
import os
from pathlib import Path
from collections import Counter

# Find annotations directory (Windows)
appdata = os.environ.get('APPDATA', '')
annots_dir = Path(appdata) / 'calibre' / 'viewer' / 'annots'

if not annots_dir.exists():
    print(f"ERROR: Annotations directory not found: {annots_dir}")
    exit(1)

print("=" * 80)
print("ANNOTATION SOURCE DIAGNOSIS")
print("=" * 80)
print(f"\nAnnotations Directory: {annots_dir}")

# Get all annotation files
anno_files = list(annots_dir.glob('*.json'))
print(f"Total annotation files: {len(anno_files)}\n")

# Sample first 10 files
sample_files = anno_files[:10]

sources = Counter()
types = Counter()
total_annotations = 0

print("Sample of annotation files:")
print("-" * 80)

for i, f in enumerate(sample_files, 1):
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)

        if isinstance(data, list):
            total_annotations += len(data)

            for anno in data:
                source = anno.get('source', 'MISSING_KEY')
                anno_type = anno.get('type', 'MISSING_KEY')
                sources[source] += 1
                types[anno_type] += 1

            # Show first annotation details
            if data:
                first = data[0]
                print(f"\n[{i}] File: {f.name[:30]}...")
                print(f"    Count: {len(data)} annotations")
                print(f"    First annotation:")
                print(f"      source: {first.get('source', 'MISSING')}")
                print(f"      type: {first.get('type', 'MISSING')}")
                print(f"      text: {first.get('highlighted_text', '')[:60]}...")

                # Show ALL keys to understand structure
                print(f"      Available keys: {list(first.keys())}")

    except Exception as e:
        print(f"Error reading {f.name}: {e}")

print("\n" + "=" * 80)
print("STATISTICS")
print("=" * 80)

print(f"\nTotal annotations sampled: {total_annotations}")

print(f"\nSource distribution:")
for source, count in sources.most_common():
    print(f"  {source}: {count} ({count/total_annotations*100:.1f}%)")

print(f"\nType distribution:")
for anno_type, count in types.most_common():
    print(f"  {anno_type}: {count} ({count/total_annotations*100:.1f}%)")

print("\n" + "=" * 80)
print("DIAGNOSIS")
print("=" * 80)

if 'MISSING_KEY' in sources:
    print("\n⚠️  Some annotations are MISSING the 'source' field!")
    print("   This means the annotation extraction is not setting the source.")

if sources.get('unknown', 0) > total_annotations * 0.8:
    print("\n⚠️  Most annotations have source='unknown'")
    print("   Possible causes:")
    print("   1. Annotations are from Calibre Viewer (not PDF-native)")
    print("   2. PDF annotation extraction is not working")
    print("   3. Source detection logic is broken")

if sources.get('calibre_viewer', 0) > 0:
    print(f"\n✓ {sources['calibre_viewer']} annotations from Calibre Viewer")

if sources.get('pdf', 0) > 0:
    print(f"\n✓ {sources['pdf']} annotations from PDF (native)")
else:
    print("\n⚠️  NO PDF-native annotations found!")
    print("   Check if PDF files actually have embedded annotations.")
