"""
Test the regex pattern fix for asterisk extraction.
"""

import re

# OLD (broken) pattern
old_pattern = r'^(\d+)\*'

# NEW (fixed) pattern
new_pattern = r'^(\d+\*)'

test_string = "11*"

print("Testing Regex Pattern Fix")
print("="*60)
print(f"Test string: {repr(test_string)}\n")

# Test old pattern
match_old = re.search(old_pattern, test_string)
if match_old:
    extracted_old = match_old.group(1)
    print(f"OLD pattern: {old_pattern}")
    print(f"  Extracted: {repr(extracted_old)}")
    print(f"  Contains '*': {'*' in extracted_old}")
    print()

# Test new pattern
match_new = re.search(new_pattern, test_string)
if match_new:
    extracted_new = match_new.group(1)
    print(f"NEW pattern: {new_pattern}")
    print(f"  Extracted: {repr(extracted_new)}")
    print(f"  Contains '*': {'*' in extracted_new}")
    print()

print("Result:")
if match_old:
    print(f"  OLD extracted: '{extracted_old}' ✗ (asterisk lost)")
if match_new:
    print(f"  NEW extracted: '{extracted_new}' ✓ (asterisk preserved)")
