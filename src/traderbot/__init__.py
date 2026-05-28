"""TraderBot — Autonomous prediction market investment toolkit for Kalshi."""

import importlib.metadata
from pathlib import Path

_ver_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
if _ver_file.exists():
    __version__ = _ver_file.read_text().strip().lstrip("v")
else:
    try:
        __version__ = importlib.metadata.version("traderbot")
    except importlib.metadata.PackageNotFoundError:
        __version__ = "0.0.0"
