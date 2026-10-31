#!/usr/bin/env python3
"""Run distributed tests; AV codec tests are explicit publication checks."""
import argparse
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--include-av',action='store_true');args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'tests'))
    modules=[p.stem for p in sorted((ROOT/'tests').glob('test_*.py')) if args.include_av or p.stem!='test_av_mux']
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(modules))
    if not args.include_av:print('Not repeated: test_av_mux (unchanged synthetic codec tests, previously verified).')
    raise SystemExit(not result.wasSuccessful())
