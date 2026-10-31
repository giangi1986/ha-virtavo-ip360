#!/usr/bin/env python3
"""Offline source/assets/privacy review. Findings never echo matched values."""
import ast
import ipaddress
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'.pcap','.pcapng','.apk','.xapk','.dex','.so','.pyc','.mp4','.hevc','.h265','.aac','.zip','.pem','.key'}
TOKEN=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|Bearer\s+[A-Za-z0-9_.-]{24,})')
EMAIL=re.compile(r'[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')
HOST_CONTEXT=re.compile(r'(?i)(?:/sdcard/|/workspace/|/root/|/home/(?!example\b)[A-Za-z0-9_-]+)')


def audit(root=ROOT):
    root=Path(root).resolve();findings=[];runtime=[];files=[]
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root).as_posix()
        if any(x in path.relative_to(root).parts for x in ('.git','__pycache__','.venv','.pytest_cache')):continue
        if path.is_symlink():findings.append({'path':rel,'kind':'symlink'});continue
        if not path.is_file():continue
        files.append(rel)
        if path.suffix.lower() in FORBIDDEN or path.name=='.env' or path.name.startswith('.env.'):findings.append({'path':rel,'kind':'forbidden_asset'})
        try:text=path.read_text()
        except UnicodeError:findings.append({'path':rel,'kind':'non_text_asset'});continue
        # Scanner patterns are definitions, not disclosed user data.
        scan=text
        for number,line in enumerate(scan.splitlines(),1):
            if TOKEN.search(line):findings.append({'path':rel,'line':number,'kind':'potential_secret'})
            if HOST_CONTEXT.search(line) and not (rel=='tools/audit_repository.py' and line.startswith('HOST_CONTEXT=')):findings.append({'path':rel,'line':number,'kind':'private_environment_reference'})
            for match in EMAIL.finditer(line):
                domain=match.group(1).lower()
                if not (domain.endswith(('.invalid','.test','.example')) or domain in ('example.com','example.org','example.net')):
                    findings.append({'path':rel,'line':number,'kind':'non_reserved_email'})
        if path.suffix=='.py':
            try:tree=ast.parse(text,filename=rel)
            except SyntaxError:findings.append({'path':rel,'kind':'syntax_error'});continue
            if rel.startswith('custom_components/virtavo/'):
                runtime.append(rel)
                for node in ast.walk(tree):
                    if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,(str,bytes)) and node.value.value:
                        if any(isinstance(t,ast.Name) and re.search(r'(password|passwd|token|session|api_key|secret)',t.id,re.I) for t in node.targets):
                            findings.append({'path':rel,'line':node.lineno,'kind':'hardcoded_runtime_credential_candidate'})
                    names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                    for name in names:
                        top=name.split('.')[0]
                        relative=isinstance(node,ast.ImportFrom) and node.level>0
                        local_module=(path.parent/(top+'.py')).is_file() if top else False
                        if top and not relative and not local_module and top not in sys.stdlib_module_names and top not in ('homeassistant','voluptuous','aiohttp','custom_components'):
                            findings.append({'path':rel,'line':node.lineno,'kind':'unapproved_runtime_dependency'})
                        if any(x in name.lower().split('.') for x in ('unicorn','ctypes','pcap','pcap_reader','scapy')):
                            findings.append({'path':rel,'line':node.lineno,'kind':'forbidden_runtime_import'})
                    if isinstance(node,ast.ImportFrom) and node.level and node.module:
                        base=path.parent
                        for _ in range(node.level-1):base=base.parent
                        target=base.joinpath(*node.module.split('.'))
                        if not target.with_suffix('.py').is_file() and not (target/'__init__.py').is_file():
                            findings.append({'path':rel,'line':node.lineno,'kind':'missing_local_import'})
        if path.suffix=='.json':
            try:json.loads(text)
            except ValueError:findings.append({'path':rel,'kind':'invalid_json'})
    return {'files_checked':len(files),'runtime_sources_checked':len(runtime),'findings':findings,
            'scope':'static source, selected secret/private-data patterns, assets and local imports; not a guarantee against every possible secret'}

if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2));raise SystemExit(bool(result['findings']))
