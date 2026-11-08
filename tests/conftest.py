"""Puts the repo root on the path, so the tests import the engine modules from any folder."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
