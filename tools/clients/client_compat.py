#!/usr/bin/env python3
"""Compatibiliteitstest van de clients met de Jelly Leon 12.x-server (P4-0, JC3). Zie compat/cli.py en ADR-0011.

Alleen voor ontwikkeling (emulator/Xvfb op de ontwikkelmachine); nooit een installatiemethode en nooit op de NAS.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compat.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
