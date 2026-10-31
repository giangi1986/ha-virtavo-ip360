#!/usr/bin/env python3
import sys
import types
import runpy
from pathlib import Path

engine = Path(__file__).resolve().parent
base = engine.parent.parent.parent

packages = [
    ("custom_components", base),
    ("custom_components.virtavo", base / "virtavo"),
    ("custom_components.virtavo.engine", engine),
    ("custom_components.virtavo.engine.des", engine / "des"),
]

for name, path in packages:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    sys.modules[name] = module

runpy.run_module(
    "custom_components.virtavo.engine.des.des_stream_puro_ottimizzato",
    run_name="__main__",
    alter_sys=True,
)
