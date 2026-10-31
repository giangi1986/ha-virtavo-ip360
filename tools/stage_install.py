#!/usr/bin/env python3
"""Install a trusted repository ZIP into a new isolated config directory.

No existing configuration is overwritten; no service is started. Hashes check
archive consistency, not the identity of an untrusted archive's publisher.
"""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import stat
import tempfile
import zipfile
from audit_repository import BRAND_ICON, valid_brand_png

PREFIX='custom_components/virtavo/'


def stage_install(archive_path,parent):
    parent=Path(parent).resolve(strict=True)
    if not parent.is_dir():raise ValueError('Existing staging parent directory required')
    payload=[]
    with zipfile.ZipFile(archive_path) as archive:
        entries=archive.infolist()
        if len(entries)>2048:raise ValueError('Too many archive members')
        names=[e.filename for e in entries]
        if len(set(names))!=len(names):raise ValueError('Duplicate archive member')
        for entry in entries:
            path=PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename:
                raise ValueError('Unsafe archive path')
            if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Archive symlinks are not allowed')
        info=archive.getinfo('PACKAGE_SHA256.json')
        if info.file_size>2*1024*1024:raise ValueError('Oversized hash inventory')
        hashes=json.loads(archive.read(info))
        if not isinstance(hashes,dict):raise ValueError('Invalid hash inventory')
        total=0
        for entry in entries:
            if not entry.filename.startswith(PREFIX) or entry.is_dir():continue
            if entry.file_size>2*1024*1024 or (Path(entry.filename).suffix not in ('.py','.json') and entry.filename not in (BRAND_ICON,PREFIX+'brand/README.md')):
                raise ValueError('Unexpected or oversized runtime asset')
            total+=entry.file_size
            if total>10*1024*1024:raise ValueError('Runtime package exceeds size limit')
            data=archive.read(entry)
            if entry.filename==BRAND_ICON and not valid_brand_png(data):raise ValueError('Invalid brand icon')
            if hashes.get(entry.filename)!=hashlib.sha256(data).hexdigest():raise ValueError('Runtime archive hash mismatch')
            payload.append((entry.filename,data))
        files=dict(payload)
        manifest=json.loads(files.get(PREFIX+'manifest.json',b'{}'))
        if manifest.get('domain')!='virtavo' or manifest.get('requirements')!=[]:
            raise ValueError('Unexpected integration manifest')
        for required in ('__init__.py','camera.py','config_flow.py','engine/receiver.py','engine/des_launcher_isolato.py'):
            if PREFIX+required not in files:raise ValueError('Incomplete runtime package')
    # Validation completes before the new directory or any output is created.
    stage=Path(tempfile.mkdtemp(prefix='virtavo-install-',dir=parent))
    try:
        for relative,data in payload:
            target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return stage

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');p.add_argument('--parent',required=True);a=p.parse_args()
    print(stage_install(a.archive,a.parent))
