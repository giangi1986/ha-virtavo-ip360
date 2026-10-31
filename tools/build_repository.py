#!/usr/bin/env python3
"""Build source archive with per-file hashes; never uploads or publishes."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from validate_repository import validate
ROOT=Path(__file__).resolve().parents[1]


def build(output,root=ROOT,publication=False):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.is_relative_to(root):raise ValueError('Archive output must be outside repository')
    report,ok=validate(root,publication=publication)
    if not ok:raise ValueError('Repository checks failed or publication metadata missing')
    files=[]
    for path in sorted(root.rglob('*')):
        if any(p in ('.git','__pycache__','.venv','.pytest_cache') for p in path.relative_to(root).parts):continue
        if not path.is_file() or path.name=='PACKAGE_SHA256.json':continue
        files.append((path.relative_to(root).as_posix(),path.read_bytes()))
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in files}
    files.append(('PACKAGE_SHA256.json',(json.dumps(manifest,indent=2)+'\n').encode()))
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in files:
            entry=zipfile.ZipInfo(name,date_time=(2026,10,31,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
            archive.writestr(entry,data)
    return {'files':len(manifest),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'publication_metadata_pending':report['publication_metadata_pending'],'published':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--publication',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.output,publication=a.publication),indent=2))
