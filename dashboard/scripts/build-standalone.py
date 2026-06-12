#!/usr/bin/env python3
"""Build a standalone ForceDash HTML with slopgate trace data pre-baked."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_standalone._builder import main

if __name__ == "__main__":
    main()
