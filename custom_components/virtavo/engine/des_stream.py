"""Avviatore del decifratore Virtavo in Python puro."""

import os
import sys
from pathlib import Path


def main():
    script = Path(__file__).resolve().parent / "des_launcher_isolato.py"

    if not script.is_file():
        raise FileNotFoundError("Decifratore Python puro non trovato")

    os.execv(
        sys.executable,
        [sys.executable, "-u", str(script), *sys.argv[1:]],
    )


if __name__ == "__main__":
    main()
