#!/usr/bin/env python3
"""Bind local metadata to a GitHub owner. No network, upload or publication."""
import argparse
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
NAME='ha-virtavo-ip360'


def configure(owner,root=ROOT):
    if not isinstance(owner,str) or not re.fullmatch(r'(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?',owner):
        raise ValueError('Valid GitHub username required')
    root=Path(root)
    url='https://github.com/'+owner+'/'+NAME
    path=root/'custom_components/virtavo/manifest.json'
    manifest=json.loads(path.read_text());manifest.update(documentation=url,issue_tracker=url+'/issues',codeowners=['@'+owner])
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    (root/'repository.json').write_text(json.dumps({'name':NAME,'owner':owner,'license':'MIT','publication_authorized':False},indent=2)+'\n')
    (root/'.github').mkdir(exist_ok=True)
    (root/'.github/CODEOWNERS').write_text('* @'+owner+'\n')
    (root/'docs/REPOSITORY.md').write_text('# Repository destination\n\n'+url+'\n\nMetadata configured locally. No repository created or published.\n')
    return url

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('owner');args=parser.parse_args()
    print(configure(args.owner))
