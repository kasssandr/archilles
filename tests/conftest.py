"""Pytest configuration for ARCHILLES tests."""

import sys
from pathlib import Path

# Add project root to sys.path so that 'src' imports work
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
