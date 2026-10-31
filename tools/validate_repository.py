#!/usr/bin/env python3
"""Check local HACS structure; --publication also requires bound owner metadata."""
import argparse
import json
from pathlib import Path
from audit_repository import audit
ROOT=Path(__file__).resolve().parents[1]


def validate(root=ROOT,publication=False):
    root=Path(root);report=audit(root);issues=list(report['findings']);pending=[]
    for name in ('README.md','LICENSE','hacs.json','repository.json','custom_components/virtavo/manifest.json'):
        if not (root/name).is_file():issues.append({'path':name,'kind':'missing_required_file'})
    if issues:
        report.update(findings=issues,publication_metadata_pending=[],publication_authorized=False)
        return report,False
    directories=[p.name for p in (root/'custom_components').iterdir() if p.is_dir() and p.name!='__pycache__']
    if directories!=['virtavo']:issues.append({'kind':'one_integration_required'})
    manifest=json.loads((root/'custom_components/virtavo/manifest.json').read_text())
    for key in ('domain','name','version','documentation','issue_tracker','codeowners','config_flow'):
        if key not in manifest:issues.append({'kind':'missing_manifest_key','key':key})
    if manifest.get('domain')!='virtavo' or manifest.get('requirements')!=[]:
        issues.append({'kind':'runtime_domain_or_requirements_mismatch'})
    hacs=json.loads((root/'hacs.json').read_text())
    if not hacs.get('name') or hacs.get('content_in_root',False) or not hacs.get('render_readme'):
        issues.append({'kind':'hacs_layout_or_readme_mismatch'})
    metadata=json.loads((root/'repository.json').read_text())
    if not metadata.get('owner'):pending.append('github_owner_and_final_urls')
    else:
        manifest=json.loads((root/'custom_components/virtavo/manifest.json').read_text())
        url='https://github.com/'+metadata['owner']+'/ha-virtavo-ip360'
        if manifest.get('documentation')!=url or manifest.get('issue_tracker')!=url+'/issues' or manifest.get('codeowners')!=['@'+metadata['owner']]:
            issues.append({'kind':'repository_metadata_mismatch'})
        codeowners=root/'.github/CODEOWNERS'
        if not codeowners.is_file() or codeowners.read_text().strip()!='* @'+metadata['owner']:
            issues.append({'kind':'codeowners_mismatch'})
    if metadata.get('publication_authorized'):issues.append({'kind':'publication_not_authorized_for_this_preparation'})
    report.update(findings=issues,publication_metadata_pending=pending,publication_authorized=False)
    return report,not issues and (not publication or not pending)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--publication',action='store_true');args=p.parse_args()
    report,ok=validate(publication=args.publication);print(json.dumps(report,indent=2));raise SystemExit(0 if ok else 2)
