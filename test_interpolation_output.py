"""
Test what the interpolation actually creates.
This simulates the interpolation logic to see if asterisks are preserved.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class PageNumber:
    """Printed page number with metadata."""
    value: str
    source: str
    confidence: float
    section: Optional[str] = None

# Simulate the interpolation from the actual code
prev_numeric = 10
prev_suffix = '*'
pdf_offset = 1
interpolated_value = prev_numeric + pdf_offset

# Format with suffix (this is line 346-347 from extract_page_numbers.py)
if prev_suffix == '*':
    interpolated_str = f"{interpolated_value}*"
else:
    interpolated_str = str(interpolated_value)

# Create PageNumber object (line 355-360)
page_num = PageNumber(
    value=interpolated_str,
    source='interpolated',
    confidence=0.7,
    section=None
)

print("Interpolation Test")
print("="*60)
print(f"Input:  prev_numeric={prev_numeric}, prev_suffix='{prev_suffix}'")
print(f"Output: interpolated_str = {repr(interpolated_str)}")
print(f"PageNumber.value = {repr(page_num.value)}")
print(f"Type: {type(page_num.value)}")
print(f"Contains '*': {'*' in page_num.value}")
print()

# Test what would be stored
print("What would be stored in database:")
print(f"  meta['printed_page'] = {repr(page_num.value)}")
print(f"  Expected result: '11*'")
print(f"  Actual result:   {repr(page_num.value)}")
print(f"  Match: {page_num.value == '11*'}")
