"""
ARCHILLES - Adaptive RAG for Calibre Historical & Literary Library Exploration System

This module provides hardware-adaptive indexing profiles and utilities
for the ARCHILLES RAG system.
"""

from .hardware import HardwareProfile, detect_hardware
from .profiles import IndexingProfile, get_profile

__all__ = [
    'HardwareProfile',
    'detect_hardware',
    'IndexingProfile',
    'get_profile',
]
