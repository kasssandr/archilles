#!/usr/bin/env python3
"""
Check if highlight annotations actually contain text.
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
print("CHECKING HIGHLIGHT ANNOTATIONS FOR TEXT")
print("=" * 80)

# Get all annotation files
anno_files = list(annots_dir.glob('*.json'))
print(f"\nTotal annotation files: {len(anno_files)}")

# Focus on files with multiple annotations (likely to have highlights)
multi_anno_files = []
for f in anno_files:
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        if isinstance(data, list) and len(data) > 3:  # Files with 4+ annotations
            multi_anno_files.append((f, data))
    except:
        pass

print(f"Files with 4+ annotations: {len(multi_anno_files)}")

if multi_anno_files:
    # Take first file with many annotations
    sample_file, sample_data = multi_anno_files[0]

    print(f"\n{'='*80}")
    print(f"SAMPLE FILE: {sample_file.name}")
    print(f"Total annotations: {len(sample_data)}")
    print(f"{'='*80}")

    # Group by type
    by_type = {}
    for anno in sample_data:
        anno_type = anno.get('type', 'unknown')
        if anno_type not in by_type:
            by_type[anno_type] = []
        by_type[anno_type].append(anno)

    for anno_type, annos in by_type.items():
        print(f"\n--- TYPE: {anno_type} (count: {len(annos)}) ---")

        # Show first annotation of this type
        first = annos[0]
        print(f"Keys: {list(first.keys())}")

        # Check for text fields
        if 'highlighted_text' in first:
            print(f"✓ HAS 'highlighted_text': {first['highlighted_text'][:80]}...")
        else:
            print(f"✗ NO 'highlighted_text'")

        if 'notes' in first:
            print(f"✓ HAS 'notes': {first['notes'][:80] if first['notes'] else '(empty)'}...")
        else:
            print(f"✗ NO 'notes'")

        # Show full first annotation structure
        print(f"\nFull structure:")
        for key, value in first.items():
            if isinstance(value, str) and len(value) > 80:
                print(f"  {key}: {value[:80]}...")
            else:
                print(f"  {key}: {value}")

print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")

# Check all annotations
total_annos = 0
with_text = 0
without_text = 0

for f in anno_files[:50]:  # Check first 50 files
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)

        if isinstance(data, list):
            for anno in data:
                total_annos += 1
                if anno.get('highlighted_text'):
                    with_text += 1
                else:
                    without_text += 1
    except:
        pass

print(f"\nSample of {total_annos} annotations:")
print(f"  With 'highlighted_text': {with_text} ({with_text/total_annos*100:.1f}%)")
print(f"  Without text: {without_text} ({without_text/total_annos*100:.1f}%)")
