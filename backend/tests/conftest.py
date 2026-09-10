"""Pytest configuration for backend tests."""

import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
