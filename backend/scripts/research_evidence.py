#!/usr/bin/env python3
"""Build or verify a research evidence package.

Usage:
    python scripts/research_evidence.py build --config roots.json --output out/pkg
    python scripts/research_evidence.py verify --package out/pkg

The command only reads authorised source roots and writes into a new output
directory. It never initialises the database, the model runtime or the app
lifespan.
"""

from __future__ import annotations

from app.research_evidence.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
