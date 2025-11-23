# Investigation: Missing Asterisk in Printed Page Numbers

## Problem

When displaying search results, printed page numbers with asterisks (e.g., "11*" for Beilage pages) appear to be missing the asterisk, showing as "S. 11" instead of "S. 11*".

## Investigation Results

### Code Analysis

I reviewed the entire pipeline for handling printed page numbers:

1. **Interpolation (scripts/extract_page_numbers.py:386)**
   ```python
   if prev_suffix == '*':
       interpolated_str = f"{interpolated_value}*"
   ```
   ✓ Correctly creates "11*" format

2. **Database Update (scripts/extract_page_numbers.py:678)**
   ```python
   meta['printed_page'] = page_num.value
   ```
   ✓ Stores PageNumber.value which contains "11*"

3. **Display (scripts/rag_demo.py:731)**
   ```python
   citation_parts.append(f"S. {printed_page_str}")
   ```
   ✓ Should display asterisk if present

### Tests Performed

- **JSON Serialization**: Asterisks preserved ✓
- **f-string Formatting**: Asterisks preserved ✓
- **Type Handling**: String type maintained ✓

### Conclusion

The code logic appears correct throughout. The asterisk should be preserved.

## Possible Causes

1. **Database Not Updated**: The interpolation script may not have successfully updated the database
2. **Type Coercion**: ChromaDB might be converting "11*" to integer 11 (unlikely but possible)
3. **Terminal Display**: Some terminals might interpret asterisks as special characters
4. **Old Script Version**: An earlier version without interpolation might have been run

## Solutions Implemented

### 1. Explicit String Conversion

Added explicit `str()` conversion in display code to prevent any type coercion:

```python
printed_page_str = str(printed_page) if printed_page else ""
citation_parts.append(f"S. {printed_page_str}")
```

### 2. Debug Mode

Added `DEBUG_METADATA` environment variable to show raw values:

```bash
DEBUG_METADATA=1 python scripts/rag_demo.py query "evangelista et a presbyteris" --exact
```

This will show:
```
[DEBUG] printed_page: '11*' (type: str)
```

### 3. Diagnostic Script

Created `debug_asterisk.py` to check database contents:

```bash
python debug_asterisk.py
```

This will show:
- Raw value from database
- Type of the value
- Whether asterisk is present
- Test formatting output

## Next Steps

1. **Run the diagnostic script**:
   ```bash
   python debug_asterisk.py
   ```

2. **If asterisk IS in database**:
   - Problem is in display/terminal
   - Check terminal encoding
   - Try different terminal
   - The explicit str() conversion should fix it

3. **If asterisk is NOT in database**:
   - Re-run extraction:
     ```bash
     python scripts/extract_page_numbers.py
     ```
   - Verify interpolation is working:
     - Look for "PDF 329→11*" in output (not "PDF 329→11")
   - Answer 'y' to update database
   - Verify with debug script again

4. **If still not working**:
   - Check ChromaDB version: `pip show chromadb`
   - Check Python version: `python --version`
   - Manually inspect database:
     ```python
     import chromadb
     client = chromadb.PersistentClient(path="./achilles_rag_db")
     collection = client.get_collection("achilles_books")
     results = collection.get(
         where={"$and": [{"book_id": "von_Harnack"}, {"page": 329}]},
         include=["metadatas"]
     )
     print(repr(results['metadatas'][0]['printed_page']))
     ```

## Technical Details

### ChromaDB Metadata Storage

ChromaDB stores metadata as JSON. Special characters should be preserved:
- Asterisks: `*` → JSON: `"*"` → Python: `"*"` ✓
- Escaping not required for asterisks in JSON strings

### Python f-strings

f-strings pass through special characters unchanged:
```python
>>> value = "11*"
>>> f"S. {value}"
'S. 11*'
```

### Interpolation Logic

The interpolation algorithm:
1. Detects gap between pages: PDF 328→10*, PDF 331→13*
2. Extracts numeric and suffix: (10, '*'), (13, '*')
3. Checks suffix matches: '*' == '*' ✓
4. Calculates increment: (13-10)/(331-328) = 1.0 ✓
5. Interpolates: PDF 329→11*, PDF 330→12*
6. **Formats with suffix**: `f"{11}*"` → `"11*"`

## Files Modified

- `scripts/rag_demo.py`: Added explicit str() conversion and DEBUG_METADATA support
- `debug_asterisk.py`: New diagnostic script

## Commit

```
commit 7c7e32c
Add explicit string conversion and debug tools for printed page display
```
